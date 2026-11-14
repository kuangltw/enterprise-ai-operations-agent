"""建立永久文件儲存鍵登錄；不授權物件刪除。"""

from alembic import op

revision = "0011_document_key_registry"
down_revision = "0010_document_retired_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 升級須在維護窗口取得兩表鎖；既有資料不符合條件時整筆回滾。
    # 明確讓 public 優先於暫存 schema，避免連線中的同名暫存表遮蔽正式表。
    op.execute("SET LOCAL search_path = public, pg_temp")
    op.execute("DO $$ BEGIN IF current_setting('transaction_isolation') <> 'read committed' THEN RAISE EXCEPTION '升級需要 READ COMMITTED'; END IF; END $$")
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE document_versions, document_upload_retired_keys IN ACCESS EXCLUSIVE MODE NOWAIT")
    op.execute(r"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_class WHERE oid = 'public.document_upload_retired_keys'::regclass
                     AND (relacl IS NOT NULL OR relrowsecurity OR relforcerowsecurity
                          OR pg_get_userbyid(relowner) <> current_user))
             OR EXISTS (SELECT 1 FROM pg_attribute
                        WHERE attrelid = 'public.document_upload_retired_keys'::regclass
                          AND attacl IS NOT NULL) THEN
            RAISE EXCEPTION '舊墓碑表含非預設權限或擁有者，請先規劃相容遷移';
          END IF;
          IF EXISTS (SELECT 1 FROM document_versions v WHERE v.storage_key !~
            ('^' || v.tenant_id::text || '/' || v.document_id::text || '/' || v.id::text ||
             '/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.pdf$')) THEN
            RAISE EXCEPTION '現有版本包含非正規儲存鍵，請人工檢查';
          END IF;
          IF EXISTS (SELECT storage_key FROM document_versions GROUP BY storage_key HAVING count(*) > 1) THEN
            RAISE EXCEPTION '現有版本包含重複儲存鍵，請人工檢查';
          END IF;
          IF EXISTS (SELECT 1 FROM document_versions v JOIN document_upload_retired_keys r
                     ON r.storage_key = v.storage_key) THEN
            RAISE EXCEPTION '現用鍵與退役鍵衝突，請人工檢查';
          END IF;
        END $$
    """)
    op.execute(r"""
        CREATE TABLE document_storage_keys (
          namespace text NOT NULL DEFAULT 'documents' CHECK (namespace = 'documents'),
          storage_key text NOT NULL,
          tenant_id uuid NOT NULL,
          document_id uuid NOT NULL,
          document_version_id uuid NOT NULL,
          generation uuid NOT NULL,
          state text NOT NULL CHECK (state IN ('live', 'retired')),
          retired_at timestamptz,
          PRIMARY KEY (namespace, storage_key),
          UNIQUE (namespace, tenant_id, document_id, document_version_id, generation),
          UNIQUE (namespace, storage_key, tenant_id, document_id, document_version_id, generation, state),
          FOREIGN KEY (tenant_id, document_id, document_version_id)
            REFERENCES document_versions (tenant_id, document_id, id) ON DELETE RESTRICT,
          CHECK ((state = 'live' AND retired_at IS NULL) OR
                 (state = 'retired' AND retired_at IS NOT NULL)),
          CHECK (storage_key = tenant_id::text || '/' || document_id::text || '/' ||
                 document_version_id::text || '/' || generation::text || '.pdf')
        )
    """)
    op.execute("""
        INSERT INTO document_storage_keys
            (namespace, storage_key, tenant_id, document_id, document_version_id, generation, state, retired_at)
        SELECT 'documents', storage_key, tenant_id, document_id, id,
               substring(storage_key from '([^/]+)\\.pdf$')::uuid, 'live', NULL
        FROM document_versions
        UNION ALL
        SELECT 'documents', storage_key, tenant_id, document_id, document_version_id,
               substring(storage_key from '([^/]+)\\.pdf$')::uuid, 'retired', retired_at
        FROM document_upload_retired_keys
    """)
    op.execute("""
        ALTER TABLE document_versions
          ADD COLUMN storage_namespace text GENERATED ALWAYS AS ('documents'::text) STORED,
          ADD COLUMN storage_generation uuid GENERATED ALWAYS AS
            (substring(storage_key from '([^/]+)\\.pdf$')::uuid) STORED,
          ADD COLUMN storage_key_state text GENERATED ALWAYS AS ('live'::text) STORED
    """)
    op.execute("""
        ALTER TABLE document_versions
          ALTER COLUMN storage_namespace SET NOT NULL,
          ALTER COLUMN storage_generation SET NOT NULL,
          ALTER COLUMN storage_key_state SET NOT NULL,
          ADD CONSTRAINT fk_document_versions_live_key FOREIGN KEY
            (storage_namespace, storage_key, tenant_id, document_id, id, storage_generation, storage_key_state)
          REFERENCES document_storage_keys
            (namespace, storage_key, tenant_id, document_id, document_version_id, generation, state)
          ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
    """)
    op.execute("""
        CREATE FUNCTION protect_document_storage_key() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP <> 'UPDATE' THEN
            RAISE EXCEPTION '儲存鍵登錄不可刪除';
          END IF;
          IF (NEW.namespace, NEW.storage_key, NEW.tenant_id, NEW.document_id,
              NEW.document_version_id, NEW.generation) IS DISTINCT FROM
             (OLD.namespace, OLD.storage_key, OLD.tenant_id, OLD.document_id,
              OLD.document_version_id, OLD.generation) OR OLD.state = 'retired' THEN
            RAISE EXCEPTION '儲存鍵身分或退役紀錄不可變更';
          END IF;
          IF NEW.state <> 'retired' OR NEW.retired_at IS NULL THEN
            RAISE EXCEPTION '儲存鍵只允許由 live 轉為 retired';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER protect_document_storage_key_row BEFORE UPDATE OR DELETE
          ON document_storage_keys FOR EACH ROW EXECUTE FUNCTION protect_document_storage_key();
        CREATE TRIGGER protect_document_storage_key_truncate BEFORE TRUNCATE
          ON document_storage_keys FOR EACH STATEMENT EXECUTE FUNCTION protect_document_storage_key();
    """)
    op.execute("""
        CREATE FUNCTION protect_document_version_identity() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (NEW.id, NEW.tenant_id, NEW.document_id, NEW.storage_key) IS DISTINCT FROM
             (OLD.id, OLD.tenant_id, OLD.document_id, OLD.storage_key) THEN
            RAISE EXCEPTION '版本儲存身分不可變更';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER protect_document_version_identity BEFORE UPDATE ON document_versions
          FOR EACH ROW EXECUTE FUNCTION protect_document_version_identity();
    """)
    op.execute("""
        CREATE FUNCTION register_document_version_key() RETURNS trigger LANGUAGE plpgsql
        SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
          INSERT INTO public.document_storage_keys
            (namespace, storage_key, tenant_id, document_id, document_version_id, generation, state)
          VALUES (NEW.storage_namespace, NEW.storage_key, NEW.tenant_id, NEW.document_id,
                  NEW.id, NEW.storage_generation, 'live');
          RETURN NEW;
        END $$;
        REVOKE ALL ON FUNCTION register_document_version_key() FROM PUBLIC;
        CREATE TRIGGER "00_register_document_version_key" AFTER INSERT ON document_versions
          FOR EACH ROW EXECUTE FUNCTION register_document_version_key();
    """)
    op.execute("DROP TABLE document_upload_retired_keys")
    # OFFSET 0 使舊名稱不能作為自動可更新 view，避免兩份可寫真相。
    op.execute("""
        CREATE VIEW document_upload_retired_keys AS
        SELECT storage_key, tenant_id, document_id, document_version_id, retired_at
        FROM document_storage_keys WHERE state = 'retired' OFFSET 0
    """)


def downgrade() -> None:
    # 即使目前看似空白也不刪除鍵身分；須以受控復原程序處理。
    op.execute("DO $$ BEGIN RAISE EXCEPTION '永久儲存鍵登錄禁止降版'; END $$")
