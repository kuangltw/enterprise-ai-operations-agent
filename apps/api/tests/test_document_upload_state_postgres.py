"""上傳狀態與冪等識別須由 PostgreSQL 約束。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.db import engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用 PostgreSQL 整合測試",
)


def test_upload_state_and_idempotency_are_tenant_scoped():
    user_id, tenant_a, tenant_b, doc_a, doc_b, key = (uuid4() for _ in range(6))
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, 'synthetic-hash')
            """), {"id": str(user_id), "email": f"{uuid4().hex}@example.invalid"})
            for tenant_id, document_id in ((tenant_a, doc_a), (tenant_b, doc_b)):
                connection.execute(text("""
                    INSERT INTO tenants (id, name) VALUES (:id, '合成文件租戶')
                """), {"id": str(tenant_id)})
                connection.execute(text("""
                    INSERT INTO documents (id, tenant_id, title, owner_id)
                    VALUES (:id, :tenant_id, '合成文件', :owner_id)
                """), {"id": str(document_id), "tenant_id": str(tenant_id),
                       "owner_id": str(user_id)})

            def insert_version(tenant_id, document_id, version, idempotency_key=None):
                return connection.execute(text("""
                    INSERT INTO document_versions
                    (id, tenant_id, document_id, version, storage_key, sha256, idempotency_key)
                    VALUES (:id, :tenant_id, :document_id, :version, 'synthetic/key',
                            :sha256, :idempotency_key)
                    RETURNING storage_status
                """), {"id": str(uuid4()), "tenant_id": str(tenant_id),
                       "document_id": str(document_id), "version": version,
                       "sha256": "a" * 64,
                       "idempotency_key": str(idempotency_key) if idempotency_key else None}).scalar_one()

            assert insert_version(tenant_a, doc_a, 1, key) == "pending_upload"
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    insert_version(tenant_a, doc_a, 2, key)
            assert insert_version(tenant_b, doc_b, 1, key) == "pending_upload"
            assert insert_version(tenant_a, doc_a, 2) == "pending_upload"
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text("""
                        UPDATE document_versions SET storage_status = 'unknown'
                        WHERE tenant_id = :tenant_id AND document_id = :document_id
                    """), {"tenant_id": str(tenant_a), "document_id": str(doc_a)})
            connection.execute(text("""
                UPDATE document_versions SET storage_status = 'stored'
                WHERE tenant_id = :tenant_id AND document_id = :document_id
                  AND version = 1
            """), {"tenant_id": str(tenant_a), "document_id": str(doc_a)})
            assert connection.execute(text("""
                SELECT storage_status FROM document_versions
                WHERE tenant_id = :tenant_id AND document_id = :document_id
                  AND version = 1
            """), {"tenant_id": str(tenant_a), "document_id": str(doc_a)}).scalar_one() == "stored"
        finally:
            outer.rollback()
