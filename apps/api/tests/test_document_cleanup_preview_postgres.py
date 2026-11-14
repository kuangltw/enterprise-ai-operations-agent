"""退役鍵約束與唯讀上傳清理候選預覽；不授權刪除物件。"""

from datetime import timedelta
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from src.db import engine
from src.document_cleanup_preview import preview_upload_cleanup

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用隔離 PostgreSQL 測試",
)


@pytest.fixture
def seeded():
    with engine.connect() as connection, connection.begin() as outer:
        if connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != "0010_document_retired_keys":
            pytest.skip("此舊版墓碑可寫入與降版測試僅適用於 0010")
        user, tenant_a, tenant_b = uuid4(), uuid4(), uuid4()
        connection.execute(text("""
            INSERT INTO users (id, email, password_hash)
            VALUES (:id, :email, 'synthetic-hash')
        """), {"id": user, "email": f"{uuid4().hex}@example.invalid"})
        for tenant in (tenant_a, tenant_b):
            connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, '合成租戶')"),
                               {"id": tenant})

        def make_version(tenant=tenant_a, *, status="pending_upload", days=3,
                         idempotent=True, key=None, indexing="pending", doc_status="active"):
            document, version = uuid4(), uuid4()
            storage_key = key or f"{tenant}/{document}/{version}/{uuid4()}.pdf"
            connection.execute(text("""
                INSERT INTO documents (id, tenant_id, title, owner_id, status)
                VALUES (:id, :tenant, '合成文件', :owner, :status)
            """), {"id": document, "tenant": tenant, "owner": user, "status": doc_status})
            connection.execute(text("""
                INSERT INTO document_versions
                    (id, tenant_id, document_id, version, storage_key, sha256,
                     idempotency_key, storage_status, indexing_status, created_at)
                VALUES (:id, :tenant, :document, 1, :key, :sha, :idempotency,
                        :status, :indexing, statement_timestamp() - (:days * interval '1 day'))
            """), {"id": version, "tenant": tenant, "document": document,
                   "key": storage_key, "sha": "a" * 64,
                   "idempotency": uuid4() if idempotent else None,
                   "status": status, "indexing": indexing, "days": days})
            return document, version, storage_key

        yield connection, tenant_a, tenant_b, make_version
        outer.rollback()


def test_retired_key_enforces_canonical_identity_uniqueness_and_restricts_deletion(seeded):
    connection, tenant_a, tenant_b, make = seeded
    document, version, _ = make()
    key = f"{tenant_a}/{document}/{version}/{uuid4()}.pdf"
    insert = text("""
        INSERT INTO document_upload_retired_keys
            (storage_key, tenant_id, document_id, document_version_id)
        VALUES (:key, :tenant, :document, :version)
    """)
    values = {"key": key, "tenant": tenant_a, "document": document, "version": version}
    connection.execute(insert, values)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(insert, values)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(insert, {**values, "key": "invalid/key"})
    with pytest.raises(IntegrityError), connection.begin_nested():
        other_key = f"{tenant_b}/{document}/{version}/{uuid4()}.pdf"
        connection.execute(insert, {**values, "tenant": tenant_b, "key": other_key})
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(text("DELETE FROM document_versions WHERE id = :id"), {"id": version})


def test_preview_filters_protected_and_unowned_candidates_without_writes(seeded):
    connection, tenant_a, tenant_b, make = seeded
    eligible = make(days=5)
    failed = make(status="failed", days=4)
    other = make(tenant_b, days=5)
    make(status="stored")
    make(idempotent=False)
    make(days=0)
    make(indexing="ready")
    make(doc_status="deleted")
    make(key="malformed/key")
    current = make()
    connection.execute(text("UPDATE documents SET current_version = 1 WHERE id = :id"),
                       {"id": current[0]})
    job = make()
    connection.execute(text("""
        INSERT INTO document_index_jobs (tenant_id, document_version_id)
        VALUES (:tenant, :version)
    """), {"tenant": tenant_a, "version": job[1]})
    retired = make()
    connection.execute(text("""
        INSERT INTO document_upload_retired_keys
            (storage_key, tenant_id, document_id, document_version_id)
        VALUES (:key, :tenant, :document, :version)
    """), {"key": retired[2], "tenant": tenant_a, "document": retired[0],
           "version": retired[1]})
    shared = make()
    make(tenant_b, key=shared[2])
    with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
        before = connection.execute(text("""
            SELECT (SELECT count(*) FROM document_versions),
                   (SELECT count(*) FROM document_upload_retired_keys),
                   (SELECT count(*) FROM document_index_jobs)
        """)).one()
        rows = preview_upload_cleanup(db, tenant_a, minimum_age=timedelta(days=1), limit=100)
        assert [item.version_id for item in rows] == [eligible[1], failed[1]]
        assert [item.storage_status for item in rows] == ["pending_upload", "failed"]
        assert not hasattr(rows[0], "storage_key")
        assert [item.version_id for item in preview_upload_cleanup(
            db, tenant_b, minimum_age=timedelta(days=1), limit=100)] == [other[1]]
        assert [item.version_id for item in preview_upload_cleanup(
            db, tenant_a, minimum_age=timedelta(days=1), limit=1)] == [eligible[1]]
        after = connection.execute(text("""
            SELECT (SELECT count(*) FROM document_versions),
                   (SELECT count(*) FROM document_upload_retired_keys),
                   (SELECT count(*) FROM document_index_jobs)
        """)).one()
        assert after == before


@pytest.mark.parametrize("age,limit", [(timedelta(hours=23), 1), (timedelta(days=1), 0),
                                      (timedelta(days=1), 101)])
def test_preview_rejects_unsafe_limits(seeded, age, limit):
    connection, tenant, _, _ = seeded
    with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
        with pytest.raises(ValueError):
            preview_upload_cleanup(db, tenant, minimum_age=age, limit=limit)


def _migration():
    path = (Path(__file__).resolve().parents[1] / "migrations" / "versions" /
            "0010_document_retired_keys.py")
    spec = importlib.util.spec_from_file_location("retired_keys_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_empty_retired_table_downgrades_inside_rolled_back_savepoint(seeded):
    connection, _, _, _ = seeded
    assert connection.execute(text("SELECT count(*) FROM document_upload_retired_keys")).scalar_one() == 0
    savepoint = connection.begin_nested()
    try:
        with Operations.context(MigrationContext.configure(connection)):
            _migration().downgrade()
        assert connection.execute(text("SELECT to_regclass('document_upload_retired_keys')")).scalar_one() is None
    finally:
        # PostgreSQL DDL 也屬交易；只還原這個測試，避免影響其他案例。
        savepoint.rollback()
    assert connection.execute(text("SELECT to_regclass('document_upload_retired_keys')")).scalar_one()


def test_nonempty_retired_table_refuses_downgrade_and_preserves_record(seeded):
    connection, tenant, _, make = seeded
    document, version, _ = make()
    key = f"{tenant}/{document}/{version}/{uuid4()}.pdf"
    connection.execute(text("""
        INSERT INTO document_upload_retired_keys
            (storage_key, tenant_id, document_id, document_version_id)
        VALUES (:key, :tenant, :document, :version)
    """), {"key": key, "tenant": tenant, "document": document, "version": version})
    with pytest.raises(DBAPIError, match="退役鍵紀錄非空"):
        with connection.begin_nested():
            with Operations.context(MigrationContext.configure(connection)):
                _migration().downgrade()
    assert connection.execute(text("""
        SELECT count(*) FROM document_upload_retired_keys WHERE storage_key = :key
    """), {"key": key}).scalar_one() == 1
