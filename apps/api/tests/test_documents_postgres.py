"""文件版本及 ACL 的跨租戶資料庫約束。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.db import engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用 PostgreSQL 整合測試",
)


def test_document_versions_and_acl_stay_in_tenant():
    tenant_a, tenant_b, user_id, document_id, version_id = (uuid4() for _ in range(5))
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, 'synthetic-hash')
            """), {"id": str(user_id), "email": f"{uuid4().hex}@example.invalid"})
            for tenant_id in (tenant_a, tenant_b):
                connection.execute(text("""
                    INSERT INTO tenants (id, name) VALUES (:id, '合成文件租戶')
                """), {"id": str(tenant_id)})
            connection.execute(text("""
                INSERT INTO documents (id, tenant_id, title, owner_id)
                VALUES (:id, :tenant_id, '合成測試文件', :owner_id)
            """), {"id": str(document_id), "tenant_id": str(tenant_a),
                   "owner_id": str(user_id)})

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO document_versions
                        (id, tenant_id, document_id, version, storage_key, sha256)
                        VALUES (:id, :tenant_id, :document_id, 1, :storage_key, :sha256)
                    """), {"id": str(version_id), "tenant_id": str(tenant_b),
                           "document_id": str(document_id), "sha256": "a" * 64,
                           "storage_key": f"{tenant_b}/{document_id}/{version_id}/{uuid4()}.pdf"})
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO document_acl (tenant_id, document_id, role)
                        VALUES (:tenant_id, :document_id, 'viewer')
                    """), {"tenant_id": str(tenant_b), "document_id": str(document_id)})

            connection.execute(text("""
                INSERT INTO document_versions
                (id, tenant_id, document_id, version, storage_key, sha256)
                VALUES (:id, :tenant_id, :document_id, 1, :storage_key, :sha256)
            """), {"id": str(version_id), "tenant_id": str(tenant_a),
                   "document_id": str(document_id), "sha256": "a" * 64,
                   "storage_key": f"{tenant_a}/{document_id}/{version_id}/{uuid4()}.pdf"})
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text("""
                        UPDATE documents SET current_version = 2 WHERE id = :id
                    """), {"id": str(document_id)})
            connection.execute(text("""
                UPDATE documents SET current_version = 1 WHERE id = :id
            """), {"id": str(document_id)})
            connection.execute(text("""
                INSERT INTO document_acl (tenant_id, document_id, role)
                VALUES (:tenant_id, :document_id, 'viewer')
            """), {"tenant_id": str(tenant_a), "document_id": str(document_id)})
            assert connection.execute(text("""
                SELECT current_version FROM documents WHERE id = :id
            """), {"id": str(document_id)}).scalar_one() == 1
        finally:
            outer.rollback()
