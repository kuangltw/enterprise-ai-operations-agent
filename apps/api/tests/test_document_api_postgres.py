"""文件中繼資料讀取同時套用租戶成員資格與 ACL。"""

import os
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.auth import get_db
from src.db import engine
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter
from src.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用 PostgreSQL 整合測試",
)


def test_document_metadata_requires_membership_and_matching_acl(monkeypatch):
    user_id, tenant_a, tenant_b, document_a, document_b = (uuid4() for _ in range(5))
    email = f"{uuid4().hex}@example.invalid"
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, :password_hash)
            """), {"id": str(user_id), "email": email,
                   "password_hash": hash_password("synthetic-password-123")})
            for tenant_id in (tenant_a, tenant_b):
                connection.execute(text("""
                    INSERT INTO tenants (id, name) VALUES (:id, '合成文件租戶')
                """), {"id": str(tenant_id)})
                connection.execute(text("""
                    INSERT INTO memberships (tenant_id, user_id, role)
                    VALUES (:tenant_id, :user_id, 'viewer')
                """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})
            for tenant_id, document_id in ((tenant_a, document_a), (tenant_b, document_b)):
                connection.execute(text("""
                    INSERT INTO documents (id, tenant_id, title, owner_id)
                    VALUES (:id, :tenant_id, '合成文件', :owner_id)
                """), {"id": str(document_id), "tenant_id": str(tenant_id),
                       "owner_id": str(user_id)})
                connection.execute(text("""
                    INSERT INTO document_acl (tenant_id, document_id, role)
                    VALUES (:tenant_id, :document_id, 'viewer')
                """), {"tenant_id": str(tenant_id), "document_id": str(document_id)})

            def override_db():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    yield db

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_login_limiter] = lambda: type(
                "SyntheticLimiter", (), {"allow": lambda self, *_: True},
            )()
            monkeypatch.setattr(settings, "jwt_signing_key", "synthetic-test-only-" * 3)
            client = TestClient(app)
            login = client.post("/api/v1/auth/login", json={
                "email": email, "password": "synthetic-password-123",
            })
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}",
                       "X-Tenant-ID": str(tenant_a)}
            path_a = f"/api/v1/documents/{document_a}"
            path_b = f"/api/v1/documents/{document_b}"

            visible = client.get(path_a, headers=headers)
            assert visible.status_code == 200
            metadata = visible.json()
            assert set(metadata) == {
                "id", "tenant_id", "title", "current_version", "created_at",
            }
            assert {key: metadata[key] for key in ("id", "tenant_id", "title", "current_version")} == {
                "id": str(document_a), "tenant_id": str(tenant_a),
                "title": "合成文件", "current_version": None,
            }
            assert datetime.fromisoformat(metadata["created_at"]).tzinfo is not None
            assert client.get(path_b, headers=headers).status_code == 404
            assert client.get(path_a).status_code == 401

            connection.execute(text("""
                UPDATE memberships SET role = 'staff'
                WHERE tenant_id = :tenant_id AND user_id = :user_id
            """), {"tenant_id": str(tenant_a), "user_id": str(user_id)})
            denied = client.get(path_a, headers=headers)
            assert denied.status_code == 404
            assert denied.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
            connection.execute(text("""
                INSERT INTO document_acl (tenant_id, document_id, role)
                VALUES (:tenant_id, :document_id, 'staff')
            """), {"tenant_id": str(tenant_a), "document_id": str(document_a)})
            assert client.get(path_a, headers=headers).status_code == 200
            connection.execute(text("""
                UPDATE documents SET status = 'deleted' WHERE id = :id
            """), {"id": str(document_a)})
            assert client.get(path_a, headers=headers).status_code == 404

            headers["X-Tenant-ID"] = str(tenant_b)
            assert client.get(path_b, headers=headers).status_code == 200
            connection.execute(text("""
                DELETE FROM memberships WHERE tenant_id = :tenant_id AND user_id = :user_id
            """), {"tenant_id": str(tenant_b), "user_id": str(user_id)})
            assert client.get(path_b, headers=headers).status_code == 404
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
