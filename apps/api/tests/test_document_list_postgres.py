"""文件列表只能列出所選租戶且目前角色可讀的文件。"""

import os
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


def test_document_list_filters_acl_and_paginates(monkeypatch):
    user_id, tenant_a, tenant_b = uuid4(), uuid4(), uuid4()
    visible_ids = sorted(uuid4() for _ in range(52))
    hidden_id, deleted_id, foreign_id = uuid4(), uuid4(), uuid4()
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
            """), {"tenant_id": str(tenant_a), "user_id": str(user_id)})
            connection.execute(text("""
                INSERT INTO documents (id, tenant_id, title, owner_id)
                VALUES (:id, :tenant_id, '合成文件', :owner_id)
            """), [{"id": str(document_id), "tenant_id": str(tenant_a),
                     "owner_id": str(user_id)} for document_id in (*visible_ids, hidden_id, deleted_id)] + [
                         {"id": str(foreign_id), "tenant_id": str(tenant_b),
                          "owner_id": str(user_id)},
                     ])
            connection.execute(text("""
                INSERT INTO document_acl (tenant_id, document_id, role)
                VALUES (:tenant_id, :document_id, 'viewer')
            """), [{"tenant_id": str(tenant_a), "document_id": str(document_id)}
                   for document_id in (*visible_ids, deleted_id)] + [
                       {"tenant_id": str(tenant_b), "document_id": str(foreign_id)},
                   ])
            connection.execute(text("""
                UPDATE documents SET status = 'deleted' WHERE id = :id
            """), {"id": str(deleted_id)})

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

            first = client.get("/api/v1/documents", headers=headers)
            assert first.status_code == 200
            assert [item["id"] for item in first.json()["items"]] == [
                str(document_id) for document_id in visible_ids[:50]
            ]
            assert first.json()["next_cursor"] == str(visible_ids[49])
            second = client.get("/api/v1/documents", headers=headers,
                                params={"cursor": first.json()["next_cursor"]})
            assert second.status_code == 200
            assert [item["id"] for item in second.json()["items"]] == [
                str(document_id) for document_id in visible_ids[50:]
            ]
            assert second.json()["next_cursor"] is None
            headers["X-Tenant-ID"] = str(tenant_b)
            assert client.get("/api/v1/documents", headers=headers).status_code == 404
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
