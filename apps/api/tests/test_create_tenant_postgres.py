"""新租戶建立只接受既有啟用使用者，並原子建立管理員成員資格。"""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.auth import get_db
from src.create_tenant import create_tenant
from src.db import engine
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter
from src.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_create_tenant_requires_active_existing_admin_and_is_atomic():
    active_id, disabled_id = uuid4(), uuid4()
    active_email = f"{uuid4().hex}@example.invalid"
    disabled_email = f"{uuid4().hex}@example.invalid"
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            for user_id, email, user_status in (
                (active_id, active_email, "active"),
                (disabled_id, disabled_email, "disabled"),
            ):
                connection.execute(text("""
                    INSERT INTO users (id, email, password_hash, status)
                    VALUES (:id, :email, :password_hash, :status)
                """), {"id": str(user_id), "email": email,
                       "password_hash": hash_password("synthetic-password-123"),
                       "status": user_status})

            with pytest.raises(ValueError):
                create_tenant(connection, "禁止", disabled_email)
            with pytest.raises(ValueError):
                create_tenant(connection, "禁止", "missing@example.invalid")
            with pytest.raises(ValueError):
                create_tenant(connection, " " * 3, active_email)

            tenant_id = create_tenant(connection, " 合成新租戶 ", active_email.upper())
            row = connection.execute(text("""
                SELECT t.name, m.user_id, m.role
                FROM tenants AS t JOIN memberships AS m ON m.tenant_id = t.id
                WHERE t.id = :tenant_id
            """), {"tenant_id": str(tenant_id)}).mappings().one()
            assert row["name"] == "合成新租戶"
            assert row["user_id"] == active_id
            assert row["role"] == "admin"
        finally:
            outer.rollback()


def test_new_tenant_is_visible_only_to_its_admin(monkeypatch):
    admin_id, outsider_id = uuid4(), uuid4()
    admin_email = f"{uuid4().hex}@example.invalid"
    outsider_email = f"{uuid4().hex}@example.invalid"
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            for user_id, email in ((admin_id, admin_email), (outsider_id, outsider_email)):
                connection.execute(text("""
                    INSERT INTO users (id, email, password_hash)
                    VALUES (:id, :email, :password_hash)
                """), {"id": str(user_id), "email": email,
                       "password_hash": hash_password("synthetic-password-123")})
            tenant_id = create_tenant(connection, "合成受控租戶", admin_email)

            def override_db():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    yield db

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_login_limiter] = lambda: type(
                "SyntheticLimiter", (), {"allow": lambda self, *_: True},
            )()
            monkeypatch.setattr(settings, "jwt_signing_key", "synthetic-test-only-" * 3)
            client = TestClient(app)

            def headers_for(email):
                login = client.post("/api/v1/auth/login", json={
                    "email": email, "password": "synthetic-password-123",
                })
                assert login.status_code == 200
                return {"Authorization": f"Bearer {login.json()['access_token']}"}

            admin_headers = headers_for(admin_email)
            outsider_headers = headers_for(outsider_email)
            assert client.get(f"/api/v1/tenants/{tenant_id}", headers=admin_headers).json() == {
                "id": str(tenant_id), "name": "合成受控租戶", "role": "admin",
            }
            assert client.get(f"/api/v1/tenants/{tenant_id}", headers=outsider_headers).status_code == 404
            assert client.get("/api/v1/tenants", headers=outsider_headers).json()["items"] == []
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
