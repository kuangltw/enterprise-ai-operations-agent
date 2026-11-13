-- One statement keeps the guard and drop atomic even under autocommit.
-- Only the disposable proof schema may be removed.
DO $$
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'downgrade requires a fresh READ COMMITTED transaction'
            USING ERRCODE = '22023';
    END IF;
    PERFORM pg_advisory_xact_lock(740101, 0);
    LOCK TABLE storage_proof.keys IN ACCESS EXCLUSIVE MODE;
    IF EXISTS (SELECT 1 FROM storage_proof.keys) THEN
        RAISE EXCEPTION 'registry identity exists, downgrade refused' USING ERRCODE = '55000';
    END IF;
    DROP SCHEMA storage_proof CASCADE;
END
$$;
