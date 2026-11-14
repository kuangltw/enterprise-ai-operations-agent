-- 只在一次性 PostgreSQL 0011 測試庫載入。DDL 由測試管理者執行。
CREATE ROLE rotation_owner NOLOGIN NOSUPERUSER NOBYPASSRLS;
CREATE ROLE rotation_runtime LOGIN NOSUPERUSER NOBYPASSRLS;
CREATE SCHEMA key_rotation;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA key_rotation TO rotation_owner, rotation_runtime;

-- 用真實 DB 登入模擬可信租戶範圍。正式 API 的授權交接須另外驗證。
CREATE TABLE key_rotation.tenant_scope (
  principal name PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES public.tenants(id)
);
CREATE TABLE key_rotation.operations (
  tenant_id uuid NOT NULL,
  operation_id uuid NOT NULL,
  document_id uuid NOT NULL,
  version_id uuid NOT NULL,
  old_generation uuid NOT NULL,
  new_generation uuid NOT NULL CHECK (new_generation <> old_generation),
  namespace text GENERATED ALWAYS AS ('documents'::text) STORED,
  old_state text GENERATED ALWAYS AS ('retired'::text) STORED,
  old_key text GENERATED ALWAYS AS
    (tenant_id::text || '/' || document_id::text || '/' || version_id::text || '/' || old_generation::text || '.pdf') STORED,
  new_key text GENERATED ALWAYS AS
    (tenant_id::text || '/' || document_id::text || '/' || version_id::text || '/' || new_generation::text || '.pdf') STORED,
  status text NOT NULL DEFAULT 'waiting_fence' CHECK (status = 'waiting_fence'),
  PRIMARY KEY (tenant_id, operation_id),
  UNIQUE (namespace, old_key),
  FOREIGN KEY (namespace, old_key, tenant_id, document_id, version_id, old_generation, old_state)
    REFERENCES public.document_storage_keys
      (namespace, storage_key, tenant_id, document_id, document_version_id, generation, state),
  -- 正規鍵包含完整歸屬。歷史替代鍵允許在下一次換鍵後成為 retired。
  FOREIGN KEY (namespace, new_key) REFERENCES public.document_storage_keys (namespace, storage_key)
);

-- 保留 0011 的 trigger 與 FK。一般角色無法成為 rotation_owner。
CREATE OR REPLACE FUNCTION public.protect_document_version_identity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF (NEW.id, NEW.tenant_id, NEW.document_id) IS DISTINCT FROM (OLD.id, OLD.tenant_id, OLD.document_id)
     OR (NEW.storage_key IS DISTINCT FROM OLD.storage_key AND current_user <> 'rotation_owner') THEN
    RAISE EXCEPTION '版本儲存身分不可變更' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE FUNCTION key_rotation.check_scope(t uuid) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION '需要 READ COMMITTED' USING ERRCODE = '22023';
  END IF;
  PERFORM 1 FROM key_rotation.tenant_scope WHERE (principal, tenant_id) = (session_user, t) FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION '租戶超出測試角色範圍' USING ERRCODE = '42501';
  END IF;
END
$$;

CREATE FUNCTION key_rotation.active_generation(t uuid, d uuid, v uuid, expected uuid)
RETURNS public.document_versions LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  target public.document_versions%ROWTYPE;
BEGIN
  -- 兩個入口依序取得 document、version、registry，等待後重新讀取狀態。
  PERFORM 1 FROM public.documents WHERE (tenant_id, id) = (t, d) FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  PERFORM 1 FROM public.document_versions WHERE (tenant_id, document_id, id) = (t, d, v) FOR UPDATE;
  SELECT dv.* INTO target FROM public.document_versions dv
    JOIN public.documents doc ON (doc.tenant_id, doc.id) = (dv.tenant_id, dv.document_id)
    WHERE (dv.tenant_id, dv.document_id, dv.id, dv.storage_generation) = (t, d, v, expected)
      AND doc.status = 'active' AND doc.current_version IS NULL
      AND dv.storage_status IN ('pending_upload', 'failed') AND dv.indexing_status = 'pending';
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  PERFORM 1 FROM public.document_storage_keys
    WHERE (namespace, storage_key, tenant_id, document_id, document_version_id, generation, state)
      = ('documents', target.storage_key, t, d, v, expected, 'live') FOR UPDATE;
  IF NOT FOUND OR EXISTS (SELECT 1 FROM public.document_index_jobs
                          WHERE (tenant_id, document_version_id) = (t, v)) THEN
    RETURN NULL;
  END IF;
  RETURN target;
END
$$;

CREATE FUNCTION key_rotation.rotate(t uuid, d uuid, v uuid, expected uuid, op uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  prior key_rotation.operations%ROWTYPE;
  target public.document_versions%ROWTYPE;
  replacement uuid := gen_random_uuid();
  replacement_key text := t || '/' || d || '/' || v || '/' || replacement || '.pdf';
BEGIN
  PERFORM key_rotation.check_scope(t);
  IF op IS NULL THEN
    RAISE EXCEPTION '缺少操作識別' USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('rotation-proof:' || t || ':' || op, 0));
  SELECT * INTO prior FROM key_rotation.operations WHERE (tenant_id, operation_id) = (t, op);
  IF FOUND THEN
    IF (prior.document_id, prior.version_id, prior.old_generation) IS DISTINCT FROM (d, v, expected) THEN
      RAISE EXCEPTION '操作身分不符' USING ERRCODE = '22023';
    END IF;
    RETURN prior.new_key;
  END IF;
  target := key_rotation.active_generation(t, d, v, expected);
  IF target.id IS NULL THEN
    RAISE EXCEPTION '目前版本或世代不符換鍵條件' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.document_storage_keys
    (storage_key, tenant_id, document_id, document_version_id, generation, state)
    VALUES (replacement_key, t, d, v, replacement, 'live');
  UPDATE public.document_versions SET storage_key = replacement_key
    WHERE (tenant_id, document_id, id, storage_key, storage_generation)
      = (t, d, v, target.storage_key, expected);
  -- RESTRICT 在此語句立即檢查，版本已指向同交易新建的 live key。
  UPDATE public.document_storage_keys SET state = 'retired', retired_at = clock_timestamp()
    WHERE (namespace, storage_key) = ('documents', target.storage_key);
  INSERT INTO key_rotation.operations (tenant_id, operation_id, document_id, version_id, old_generation, new_generation)
    VALUES (t, op, d, v, expected, replacement);
  RETURN replacement_key;
END
$$;

-- 原型只建模已驗證內容之後的 DB 完成交易，沒有 PUT、發布或 worker。
CREATE FUNCTION key_rotation.finish(t uuid, d uuid, v uuid, expected uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  PERFORM key_rotation.check_scope(t);
  IF (key_rotation.active_generation(t, d, v, expected)).id IS NULL THEN
    RETURN false;
  END IF;
  UPDATE public.document_versions SET storage_status = 'stored'
    WHERE (tenant_id, document_id, id, storage_generation) = (t, d, v, expected);
  INSERT INTO public.document_index_jobs (tenant_id, document_version_id) VALUES (t, v);
  RETURN true;
END
$$;

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA key_rotation FROM PUBLIC;
ALTER FUNCTION key_rotation.rotate(uuid, uuid, uuid, uuid, uuid) OWNER TO rotation_owner;
ALTER FUNCTION key_rotation.finish(uuid, uuid, uuid, uuid) OWNER TO rotation_owner;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA key_rotation TO rotation_owner;
GRANT EXECUTE ON FUNCTION key_rotation.rotate(uuid, uuid, uuid, uuid, uuid),
  key_rotation.finish(uuid, uuid, uuid, uuid) TO rotation_runtime;
GRANT SELECT ON key_rotation.tenant_scope, key_rotation.operations TO rotation_owner;
GRANT UPDATE (principal) ON key_rotation.tenant_scope TO rotation_owner;
GRANT INSERT (tenant_id, operation_id, document_id, version_id, old_generation, new_generation)
  ON key_rotation.operations TO rotation_owner;
GRANT SELECT ON public.documents, public.document_versions, public.document_storage_keys,
  public.document_index_jobs TO rotation_owner;
-- SELECT FOR UPDATE 要求至少一個欄位的 UPDATE 權限。
GRANT UPDATE (status) ON public.documents TO rotation_owner;
GRANT UPDATE (storage_key, storage_status) ON public.document_versions TO rotation_owner;
GRANT INSERT (storage_key, tenant_id, document_id, document_version_id, generation, state),
  UPDATE (state, retired_at) ON public.document_storage_keys TO rotation_owner;
GRANT INSERT (tenant_id, document_version_id) ON public.document_index_jobs TO rotation_owner;
