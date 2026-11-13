"""文件狀態端點的 ACL 與版本進度契約。"""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.auth import AuthError, get_db
from src.db import engine
from src.documents import get_document_metadata, get_document_status, list_documents
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter
from src.settings import settings
from src.tenant_context import TenantContext

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用 PostgreSQL 整合測試",
)


def test_document_status_shows_latest_version_only_to_acl_member(monkeypatch):
    tenant_id, owner_id, other_id, document_id = (uuid4() for _ in range(4))
    owner_email = f"{uuid4().hex}@example.invalid"
    other_email = f"{uuid4().hex}@example.invalid"
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO tenants (id, name) VALUES (:id, '合成狀態租戶')
            """), {"id": str(tenant_id)})
            for user_id, email in ((owner_id, owner_email), (other_id, other_email)):
                connection.execute(text("""
                    INSERT INTO users (id, email, password_hash)
                    VALUES (:id, :email, :password_hash)
                """), {"id": str(user_id), "email": email,
                       "password_hash": hash_password("synthetic-password-123")})
                connection.execute(text("""
                    INSERT INTO memberships (tenant_id, user_id, role)
                    VALUES (:tenant_id, :user_id, 'staff')
                """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})
            connection.execute(text("""
                INSERT INTO documents (id, tenant_id, title, owner_id)
                VALUES (:id, :tenant_id, '合成狀態文件', :owner_id)
            """), {"id": str(document_id), "tenant_id": str(tenant_id),
                   "owner_id": str(owner_id)})
            connection.execute(text("""
                INSERT INTO document_user_acl (tenant_id, document_id, user_id)
                VALUES (:tenant_id, :document_id, :user_id)
            """), {"tenant_id": str(tenant_id), "document_id": str(document_id),
                   "user_id": str(owner_id)})

            def override_db():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    yield db

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_login_limiter] = lambda: type(
                "SyntheticLimiter", (), {"allow": lambda self, *_: True},
            )()
            monkeypatch.setattr(settings, "jwt_signing_key", "synthetic-test-only-" * 3)
            client = TestClient(app)
            owner_login = client.post("/api/v1/auth/login", json={
                "email": owner_email, "password": "synthetic-password-123",
            })
            other_login = client.post("/api/v1/auth/login", json={
                "email": other_email, "password": "synthetic-password-123",
            })
            assert owner_login.status_code == other_login.status_code == 200
            headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}",
                       "X-Tenant-ID": str(tenant_id)}
            other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}",
                             "X-Tenant-ID": str(tenant_id)}
            path = f"/api/v1/documents/{document_id}/status"
            assert client.get(path, headers=headers).json() == {
                "document_id": str(document_id), "current_version": None,
                "latest_version": None, "storage_status": None,
                "indexing_status": None,
            }
            assert client.get(path, headers=other_headers).status_code == 404
            assert client.get(path).status_code == 401

            for version, storage_status, indexing_status in (
                (1, "stored", "ready"), (2, "pending_upload", "pending"),
            ):
                connection.execute(text("""
                    INSERT INTO document_versions
                        (tenant_id, document_id, version, storage_key, sha256,
                         storage_status, indexing_status)
                    VALUES (:tenant_id, :document_id, :version, :storage_key,
                            :sha256, :storage_status, :indexing_status)
                """), {"tenant_id": str(tenant_id), "document_id": str(document_id),
                       "version": version, "storage_key": f"synthetic/{version}",
                       "sha256": "a" * 64, "storage_status": storage_status,
                       "indexing_status": indexing_status})
            connection.execute(text("""
                UPDATE documents SET current_version = 1 WHERE id = :id
            """), {"id": str(document_id)})
            assert client.get(path, headers=headers).json() == {
                "document_id": str(document_id), "current_version": 1,
                "latest_version": 2, "storage_status": "pending_upload",
                "indexing_status": "pending",
            }
            connection.execute(text("""
                DELETE FROM document_user_acl
                WHERE tenant_id = :tenant_id AND document_id = :document_id
                  AND user_id = :user_id
            """), {"tenant_id": str(tenant_id), "document_id": str(document_id),
                   "user_id": str(owner_id)})
            assert client.get(path, headers=headers).status_code == 404
            connection.execute(text("""
                INSERT INTO document_acl (tenant_id, document_id, role)
                VALUES (:tenant_id, :document_id, 'staff')
            """), {"tenant_id": str(tenant_id), "document_id": str(document_id)})
            connection.execute(text("""
                DELETE FROM memberships WHERE tenant_id = :tenant_id AND user_id = :user_id
            """), {"tenant_id": str(tenant_id), "user_id": str(owner_id)})
            stale_context = TenantContext(tenant_id, owner_id, "合成狀態租戶", "staff")
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                with pytest.raises(AuthError) as metadata_error:
                    get_document_metadata(document_id, stale_context, db)
                assert metadata_error.value.status_code == 404
                with pytest.raises(AuthError) as status_error:
                    get_document_status(document_id, stale_context, db)
                assert status_error.value.status_code == 404
                assert list_documents(None, stale_context, db).items == []
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
