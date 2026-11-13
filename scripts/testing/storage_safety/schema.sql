-- Disposable proof schema. Never run against an application database.
CREATE ROLE proof_runtime NOLOGIN;
CREATE SCHEMA storage_proof;
SET search_path = storage_proof, pg_catalog;

CREATE TABLE keys (
    namespace text NOT NULL,
    object_key text NOT NULL,
    tenant uuid NOT NULL,
    document uuid NOT NULL,
    version uuid NOT NULL,
    generation integer NOT NULL CHECK (generation > 0),
    state text NOT NULL DEFAULT 'live' CHECK (state IN ('live', 'retired')),
    CHECK (object_key ~ ('^' || tenant || '/' || document || '/' || version ||
        '/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[.]pdf$')),
    PRIMARY KEY (namespace, object_key),
    UNIQUE (namespace, tenant, document, version, generation),
    UNIQUE (namespace, object_key, tenant, document, version, generation),
    UNIQUE (namespace, object_key, tenant, document, version, generation, state)
);

CREATE TABLE versions (
    namespace text NOT NULL,
    tenant uuid NOT NULL,
    document uuid NOT NULL,
    version uuid NOT NULL,
    generation integer NOT NULL,
    object_key text NOT NULL,
    key_state text GENERATED ALWAYS AS ('live'::text) STORED NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'stored')),
    PRIMARY KEY (namespace, tenant, document, version),
    FOREIGN KEY (namespace, object_key, tenant, document, version, generation, key_state)
        REFERENCES keys (namespace, object_key, tenant, document, version, generation, state)
);

CREATE TABLE reconciliation (
    operation_id uuid PRIMARY KEY,
    namespace text NOT NULL,
    tenant uuid NOT NULL,
    document uuid NOT NULL,
    version uuid NOT NULL,
    old_key text NOT NULL,
    old_generation integer NOT NULL,
    old_state text GENERATED ALWAYS AS ('retired'::text) STORED NOT NULL,
    new_key text NOT NULL,
    new_generation integer NOT NULL CHECK (new_generation = old_generation + 1),
    status text NOT NULL DEFAULT 'waiting_fence' CHECK (status = 'waiting_fence'),
    CHECK (old_key <> new_key),
    UNIQUE (namespace, old_key, old_generation),
    FOREIGN KEY (namespace, old_key, tenant, document, version, old_generation, old_state)
        REFERENCES keys (namespace, object_key, tenant, document, version, generation, state),
    FOREIGN KEY (namespace, new_key, tenant, document, version, new_generation)
        REFERENCES keys (namespace, object_key, tenant, document, version, generation)
);

CREATE FUNCTION guard_key() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RAISE EXCEPTION 'permanent registry' USING ERRCODE = '23514';
    END IF;
    IF ROW(NEW.namespace, NEW.object_key, NEW.tenant, NEW.document, NEW.version, NEW.generation)
        IS DISTINCT FROM
       ROW(OLD.namespace, OLD.object_key, OLD.tenant, OLD.document, OLD.version, OLD.generation)
       OR OLD.state <> 'live' OR NEW.state <> 'retired' THEN
        RAISE EXCEPTION 'immutable identity and terminal retirement' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER guard_key_row BEFORE UPDATE OR DELETE ON keys
    FOR EACH ROW EXECUTE FUNCTION guard_key();
CREATE TRIGGER guard_key_truncate BEFORE TRUNCATE ON keys
    FOR EACH STATEMENT EXECUTE FUNCTION guard_key();

-- Proof runtime is one trusted synthetic service role. It does not model tenant authentication.
-- Both operations use gate -> operation (if any) -> version -> key/work. No storage I/O.
CREATE FUNCTION rotate(
    op uuid, ns text, t uuid, d uuid, v uuid, expected_generation integer
) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, storage_proof, pg_temp AS $$
DECLARE
    prior reconciliation%ROWTYPE;
    current_version versions%ROWTYPE;
    replacement text;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed'
       OR op IS NULL OR expected_generation IS NULL THEN
        RAISE EXCEPTION 'invalid transaction or input' USING ERRCODE = '22023';
    END IF;
    PERFORM pg_advisory_xact_lock_shared(740101, 0);
    PERFORM pg_advisory_xact_lock(740102, hashtext(op::text));
    SELECT * INTO prior FROM reconciliation WHERE operation_id = op;
    IF FOUND THEN
        IF ROW(prior.namespace, prior.tenant, prior.document, prior.version, prior.old_generation)
            IS DISTINCT FROM ROW(ns, t, d, v, expected_generation) THEN
            RAISE EXCEPTION 'operation input mismatch' USING ERRCODE = '22023';
        END IF;
        RETURN prior.new_key;
    END IF;
    PERFORM 1 FROM versions
        WHERE (namespace, tenant, document, version) = (ns, t, d, v) FOR UPDATE;
    SELECT * INTO STRICT current_version FROM versions
        WHERE (namespace, tenant, document, version) = (ns, t, d, v);
    IF current_version.status <> 'pending' OR current_version.generation <> expected_generation THEN
        RAISE EXCEPTION 'ineligible or stale generation' USING ERRCODE = '22023';
    END IF;
    replacement := t || '/' || d || '/' || v || '/' || gen_random_uuid() || '.pdf';
    INSERT INTO keys (namespace, object_key, tenant, document, version, generation)
        VALUES (ns, replacement, t, d, v, expected_generation + 1);
    UPDATE versions SET object_key = replacement, generation = expected_generation + 1
        WHERE (namespace, tenant, document, version) = (ns, t, d, v);
    UPDATE keys SET state = 'retired'
        WHERE (namespace, object_key) = (ns, current_version.object_key);
    INSERT INTO reconciliation (
        operation_id, namespace, tenant, document, version, old_key, old_generation,
        new_key, new_generation
    ) VALUES (
        op, ns, t, d, v, current_version.object_key, expected_generation,
        replacement, expected_generation + 1
    );
    RETURN replacement;
END
$$;

CREATE FUNCTION finish(
    ns text, t uuid, d uuid, v uuid, expected_generation integer, expected_key text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, storage_proof, pg_temp AS $$
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'invalid transaction isolation' USING ERRCODE = '22023';
    END IF;
    PERFORM pg_advisory_xact_lock_shared(740101, 0);
    PERFORM 1 FROM versions
        WHERE (namespace, tenant, document, version) = (ns, t, d, v) FOR UPDATE;
    UPDATE versions SET status = 'stored'
        WHERE (namespace, tenant, document, version) = (ns, t, d, v)
          AND (generation, object_key, status) = (expected_generation, expected_key, 'pending');
    RETURN FOUND;
END
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA storage_proof FROM PUBLIC;
GRANT USAGE ON SCHEMA storage_proof TO proof_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA storage_proof TO proof_runtime;
GRANT EXECUTE ON FUNCTION rotate(uuid, text, uuid, uuid, uuid, integer),
    finish(text, uuid, uuid, uuid, integer, text) TO proof_runtime;
