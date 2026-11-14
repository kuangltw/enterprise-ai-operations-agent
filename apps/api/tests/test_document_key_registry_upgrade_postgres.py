"""以交易回滾測試 0010 既有資料升級；僅供一次性 PostgreSQL 使用。"""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.db import engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_KEY_REGISTRY_UPGRADE_TESTS") != "1",
    reason="需要套用至 0010 的一次性 PostgreSQL",
)


def _upgrade(connection):
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0011_document_key_registry.py"
    spec = importlib.util.spec_from_file_location("key_registry_upgrade", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()


def _seed(connection, *, invalid=False):
    tenant, owner, document, version, generation = (uuid4() for _ in range(5))
    key = f"{tenant}/{document}/{version}/{generation}.pdf"
    connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, '合成租戶')"), {"id": tenant})
    connection.execute(text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'synthetic')"),
                       {"id": owner, "email": f"{owner}@example.invalid"})
    connection.execute(text("INSERT INTO documents (id, tenant_id, title, owner_id) VALUES (:id, :tenant, '文件', :owner)"),
                       {"id": document, "tenant": tenant, "owner": owner})
    connection.execute(text("""
        INSERT INTO document_versions (id, tenant_id, document_id, version, storage_key, sha256)
        VALUES (:id, :tenant, :document, 1, :key, :sha)
    """), {"id": version, "tenant": tenant, "document": document,
           "key": "malformed" if invalid else key, "sha": "a" * 64})
    return {"tenant": tenant, "document": document, "version": version, "key": key,
            "generation": generation}


def _retire(connection, owner, key):
    connection.execute(text("""
        INSERT INTO document_upload_retired_keys
            (storage_key, tenant_id, document_id, document_version_id, retired_at)
        VALUES (:key, :tenant, :document, :version, '2020-01-01 00:00:00+00')
    """), {**owner, "key": key})


def test_upgrade_preserves_existing_keys_and_read_only_legacy_view():
    with engine.connect() as db, db.begin() as transaction:
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0010_document_retired_keys"
        owner = _seed(db)
        old_generation = uuid4()
        old_key = f"{owner['tenant']}/{owner['document']}/{owner['version']}/{old_generation}.pdf"
        _retire(db, owner, old_key)
        _upgrade(db)
        rows = db.execute(text("""
            SELECT storage_key, generation, state, retired_at FROM document_storage_keys
            WHERE document_version_id=:version ORDER BY state
        """), owner).mappings().all()
        assert [(r["storage_key"], r["generation"], r["state"]) for r in rows] == [
            (owner["key"], owner["generation"], "live"), (old_key, old_generation, "retired")]
        assert str(rows[1]["retired_at"]) == "2020-01-01 00:00:00+00:00"
        assert db.execute(text("SELECT storage_key FROM document_upload_retired_keys")).scalar_one() == old_key
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(text("DELETE FROM document_upload_retired_keys"))
        transaction.rollback()


@pytest.mark.parametrize("conflict", ["malformed", "duplicate", "retired_live"])
def test_incompatible_legacy_data_aborts_without_mutation(conflict):
    with engine.connect() as db, db.begin() as transaction:
        owner = _seed(db, invalid=conflict == "malformed")
        if conflict == "duplicate":
            other = _seed(db)
            db.execute(text("UPDATE document_versions SET storage_key=:key WHERE id=:version"),
                       {"key": owner["key"], "version": other["version"]})
        if conflict == "retired_live":
            _retire(db, owner, owner["key"])
        with pytest.raises(DBAPIError), db.begin_nested():
            _upgrade(db)
        assert db.execute(text("SELECT to_regclass('public.document_storage_keys')")).scalar_one() is None
        assert db.execute(text("SELECT storage_key FROM document_versions WHERE id=:version"), owner).scalar_one() == (
            "malformed" if conflict == "malformed" else owner["key"])
        if conflict == "retired_live":
            assert db.execute(text("SELECT storage_key FROM document_upload_retired_keys")).scalar_one() == owner["key"]
        transaction.rollback()


@pytest.mark.parametrize("grant", ["SELECT", "SELECT (storage_key)"])
def test_upgrade_fails_closed_on_nondefault_grants_and_lock_contention(grant):
    with engine.connect() as db, db.begin() as transaction:
        db.execute(text(f"GRANT {grant} ON document_upload_retired_keys TO PUBLIC"))
        with pytest.raises(DBAPIError), db.begin_nested():
            _upgrade(db)
        assert db.execute(text("SELECT to_regclass('public.document_storage_keys')")).scalar_one() is None
        transaction.rollback()
    with engine.connect() as blocker, blocker.begin():
        blocker.execute(text("LOCK TABLE document_versions IN ACCESS EXCLUSIVE MODE"))
        with engine.connect() as db, db.begin() as transaction:
            with pytest.raises(DBAPIError) as caught, db.begin_nested():
                _upgrade(db)
            assert caught.value.orig.sqlstate == "55P03"
            assert db.execute(text("SELECT to_regclass('public.document_storage_keys')")).scalar_one() is None
            transaction.rollback()


def test_upgrade_rejects_repeatable_read_before_any_mutation():
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as db, db.begin() as transaction:
        with pytest.raises(DBAPIError) as caught, db.begin_nested():
            _upgrade(db)
        assert caught.value.orig.sqlstate == "P0001"
        assert db.execute(text("SELECT to_regclass('public.document_storage_keys')")).scalar_one() is None
        transaction.rollback()


def test_upgrade_rejects_legacy_row_security():
    with engine.connect() as db, db.begin() as transaction:
        db.execute(text("ALTER TABLE document_upload_retired_keys ENABLE ROW LEVEL SECURITY"))
        with pytest.raises(DBAPIError), db.begin_nested():
            _upgrade(db)
        assert db.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='document_upload_retired_keys'::regclass")).scalar_one()
        assert db.execute(text("SELECT to_regclass('public.document_storage_keys')")).scalar_one() is None
        transaction.rollback()


def test_z_alembic_upgrade_with_committed_existing_data():
    with engine.begin() as db:
        owner = _seed(db)
        old_key = f"{owner['tenant']}/{owner['document']}/{owner['version']}/{uuid4()}.pdf"
        _retire(db, owner, old_key)
    api_dir = Path(__file__).resolve().parents[1]
    config = Config(str(api_dir / "alembic.ini"))
    config.set_main_option("script_location", str(api_dir / "migrations"))
    command.upgrade(config, "0011_document_key_registry")
    with engine.connect() as db:
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0011_document_key_registry"
        assert db.execute(text("SELECT state FROM document_storage_keys WHERE storage_key=:key"), owner).scalar_one() == "live"
        assert db.execute(text("SELECT state FROM document_storage_keys WHERE storage_key=:key"), {"key": old_key}).scalar_one() == "retired"
