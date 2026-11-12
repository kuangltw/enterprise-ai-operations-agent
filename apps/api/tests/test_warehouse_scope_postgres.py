"""倉庫範圍由複合外鍵綁定成員資格，撤銷成員時一併清除。"""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.auth import get_db
from src.db import engine
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter
from src.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_scope_requires_same_tenant_membership_and_cascades_on_revoke():
    user_id, tenant_a, tenant_b = uuid4(), uuid4(), uuid4()
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, :password_hash)
            """), {"id": str(user_id), "email": f"{uuid4().hex}@example.invalid",
                   "password_hash": hash_password("synthetic-password-123")})
            for tenant_id in (tenant_a, tenant_b):
                connection.execute(text("""
                    INSERT INTO tenants (id, name) VALUES (:id, '合成倉庫租戶')
                """), {"id": str(tenant_id)})
            connection.execute(text("""
                INSERT INTO memberships (tenant_id, user_id, role)
                VALUES (:tenant_id, :user_id, 'staff')
            """), {"tenant_id": str(tenant_a), "user_id": str(user_id)})

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO membership_warehouse_scopes
                        (tenant_id, user_id, warehouse_code)
                        VALUES (:tenant_id, :user_id, 'WH-B')
                    """), {"tenant_id": str(tenant_b), "user_id": str(user_id)})
            connection.execute(text("""
                INSERT INTO membership_warehouse_scopes
                (tenant_id, user_id, warehouse_code)
                VALUES (:tenant_id, :user_id, 'WH-A')
            """), {"tenant_id": str(tenant_a), "user_id": str(user_id)})
            connection.execute(text("""
                DELETE FROM memberships WHERE tenant_id = :tenant_id AND user_id = :user_id
            """), {"tenant_id": str(tenant_a), "user_id": str(user_id)})
            assert connection.execute(text("""
                SELECT COUNT(*) FROM membership_warehouse_scopes
                WHERE tenant_id = :tenant_id AND user_id = :user_id
            """), {"tenant_id": str(tenant_a), "user_id": str(user_id)}).scalar_one() == 0
        finally:
            outer.rollback()


def test_warehouse_scope_api_uses_selected_tenant_and_membership(monkeypatch):
    user_id, tenant_a, tenant_b = uuid4(), uuid4(), uuid4()
    email = f"{uuid4().hex}@example.invalid"
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, :password_hash)
            """), {"id": str(user_id), "email": email,
                   "password_hash": hash_password("synthetic-password-123")})
            for tenant_id, warehouse_code in ((tenant_a, "WH-A"), (tenant_b, "WH-B")):
                connection.execute(text("""
                    INSERT INTO tenants (id, name) VALUES (:id, '合成租戶')
                """), {"id": str(tenant_id)})
                connection.execute(text("""
                    INSERT INTO memberships (tenant_id, user_id, role)
                    VALUES (:tenant_id, :user_id, 'viewer')
                """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})
                connection.execute(text("""
                    INSERT INTO membership_warehouse_scopes
                    (tenant_id, user_id, warehouse_code)
                    VALUES (:tenant_id, :user_id, :warehouse_code)
                """), {"tenant_id": str(tenant_id), "user_id": str(user_id),
                       "warehouse_code": warehouse_code})

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
            path = "/api/v1/tenants/current/warehouse-scopes"
            assert client.get(path, headers=headers).json() == {
                "items": ["WH-A"], "next_cursor": None,
            }
            assert client.get(f"{path}/WH-A", headers=headers).status_code == 200
            assert client.get(f"{path}/WH-B", headers=headers).status_code == 404
            headers["X-Tenant-ID"] = str(tenant_b)
            assert client.get(path, headers=headers).json()["items"] == ["WH-B"]
            assert client.get(f"{path}/WH-A", headers=headers).status_code == 404
            headers["X-Tenant-ID"] = str(uuid4())
            assert client.get(path, headers=headers).status_code == 404
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
