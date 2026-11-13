"""實際 PostgreSQL 身分驗證整合測試；所有合成資料由外層交易回滾。"""

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
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_login_and_revocation_against_postgres(monkeypatch):
    user_id = uuid4()
    other_user_id, own_tenant_id, other_tenant_id = uuid4(), uuid4(), uuid4()
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, :hash)
            """), {"id": str(user_id), "email": "synthetic-integration@example.invalid",
                   "hash": hash_password("synthetic-password-123")})
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, 'synthetic-hash')
            """), {"id": str(other_user_id), "email": "other@example.invalid"})
            connection.execute(text("""
                INSERT INTO tenants (id, name) VALUES
                (:own_id, '合成租戶甲'), (:other_id, '合成租戶乙')
            """), {"own_id": str(own_tenant_id), "other_id": str(other_tenant_id)})
            connection.execute(text("""
                INSERT INTO memberships (tenant_id, user_id, role) VALUES
                (:own_id, :user_id, 'staff'), (:other_id, :other_user_id, 'admin')
            """), {"own_id": str(own_tenant_id), "user_id": str(user_id),
                   "other_id": str(other_tenant_id), "other_user_id": str(other_user_id)})

            def override_db():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    yield db

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_login_limiter] = lambda: type(
                "SyntheticLimiter", (), {"allow": lambda self, *_: True},
            )()
            monkeypatch.setattr(settings, "jwt_signing_key", "synthetic-test-only-" * 3)
            client = TestClient(app)
            response = client.post("/api/v1/auth/login", json={
                "email": "synthetic-integration@example.invalid",
                "password": "synthetic-password-123",
            })
            assert response.status_code == 200
            headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
            tenants = client.get("/api/v1/tenants", headers=headers)
            assert tenants.status_code == 200
            assert tenants.json()["items"] == [{
                "id": str(own_tenant_id), "name": "合成租戶甲", "role": "staff",
            }]
            assert client.get(f"/api/v1/tenants/{own_tenant_id}", headers=headers).status_code == 200
            current = client.get("/api/v1/tenants/current", headers={
                **headers, "X-Tenant-ID": str(own_tenant_id),
            })
            assert current.status_code == 200
            assert current.json()["role"] == "staff"
            assert "document.upload" in current.json()["permissions"]
            assert client.get("/api/v1/tenants/current", headers={
                **headers, "X-Tenant-ID": str(other_tenant_id),
            }).status_code == 404
            after = client.get(f"/api/v1/tenants?cursor={own_tenant_id}", headers=headers)
            assert after.status_code == 200
            assert after.json()["items"] == []
            hidden = client.get(f"/api/v1/tenants/{other_tenant_id}", headers=headers)
            assert hidden.status_code == 404
            assert hidden.json()["error"]["code"] == "TENANT_NOT_FOUND"
            with TestClient(app, base_url="https://testserver") as browser:
                assert browser.post("/api/v1/auth/session", headers={"X-Session-Request": "1"}, json={
                    "email": "synthetic-integration@example.invalid",
                    "password": "synthetic-password-123",
                }).status_code == 204
                assert browser.get("/api/v1/tenants/current", headers={
                    "X-Tenant-ID": str(other_tenant_id),
                }).status_code == 404
                connection.execute(text("UPDATE memberships SET role='viewer' WHERE user_id=:id"),
                                   {"id": str(user_id)})
                refreshed = browser.get("/api/v1/tenants/current", headers={"X-Tenant-ID": str(own_tenant_id)})
                assert refreshed.status_code == 200
                assert refreshed.json()["role"] == "viewer"
                assert "document.upload" not in refreshed.json()["permissions"]
            member_body = {"email": "new@example.invalid", "password": "synthetic-password-123", "role": "staff"}
            assert client.post(f"/api/v1/tenants/{own_tenant_id}/members", headers=headers,
                               json=member_body).status_code == 403
            assert client.post(f"/api/v1/tenants/{other_tenant_id}/members", headers=headers,
                               json=member_body).status_code == 404
            assert client.patch(f"/api/v1/tenants/{own_tenant_id}/members/{other_user_id}",
                                headers=headers, json={"role": "manager"}).status_code == 403
            connection.execute(text("UPDATE tenants SET status='suspended' WHERE id=:id"),
                               {"id": str(own_tenant_id)})
            assert client.get("/api/v1/tenants", headers=headers).json()["items"] == []
            assert client.get("/api/v1/tenants/current", headers={
                **headers, "X-Tenant-ID": str(own_tenant_id),
            }).status_code == 404
            # 模擬 PostgreSQL 時鐘領先 API，仍須能撤銷工作階段。
            connection.execute(text("""
                UPDATE sessions SET created_at = CURRENT_TIMESTAMP + INTERVAL '30 seconds'
                WHERE user_id = :id
            """), {"id": str(user_id)})
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 401
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
        finally:
            app.dependency_overrides.clear()
            outer.rollback()


def test_admin_creates_member_only_in_own_tenant(monkeypatch):
    admin_id, tenant_id, foreign_tenant_id = uuid4(), uuid4(), uuid4()
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, 'synthetic-admin@example.invalid', :hash)
            """), {"id": str(admin_id), "hash": hash_password("synthetic-password-123")})
            connection.execute(text("""
                INSERT INTO tenants (id, name) VALUES
                (:tenant_id, '合成管理租戶'), (:foreign_id, '其他租戶')
            """), {"tenant_id": str(tenant_id), "foreign_id": str(foreign_tenant_id)})
            connection.execute(text("""
                INSERT INTO memberships (tenant_id, user_id, role)
                VALUES (:tenant_id, :admin_id, 'admin')
            """), {"tenant_id": str(tenant_id), "admin_id": str(admin_id)})

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
                "email": "synthetic-admin@example.invalid", "password": "synthetic-password-123",
            })
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            body = {"email": " NEW@example.invalid ", "password": "synthetic-password-123", "role": "viewer"}
            created = client.post(f"/api/v1/tenants/{tenant_id}/members", headers=headers, json=body)
            assert created.status_code == 201
            assert created.json()["email"] == "new@example.invalid"
            assert "password" not in created.json()
            assert client.post(f"/api/v1/tenants/{tenant_id}/members", headers=headers,
                               json=body).status_code == 409
            assert client.post(f"/api/v1/tenants/{foreign_tenant_id}/members", headers=headers,
                               json=body).status_code == 404
            forbidden_role = dict(body, role="admin")
            assert client.post(f"/api/v1/tenants/{tenant_id}/members", headers=headers,
                               json=forbidden_role).status_code == 422
            member = connection.execute(text("""
                SELECT m.role FROM memberships AS m JOIN users AS u ON u.id = m.user_id
                WHERE u.email = 'new@example.invalid' AND m.tenant_id = :tenant_id
            """), {"tenant_id": str(tenant_id)}).mappings().one()
            assert member["role"] == "viewer"
            new_user_id = created.json()["id"]
            new_login = client.post("/api/v1/auth/login", json={
                "email": "new@example.invalid", "password": "synthetic-password-123",
            })
            assert new_login.status_code == 200
            new_headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}
            assert len(client.get("/api/v1/tenants", headers=new_headers).json()["items"]) == 1

            connection.execute(text("""
                INSERT INTO tenant_warehouses (tenant_id, warehouse_code)
                VALUES (:tenant_id, 'WH-TEST')
            """), {"tenant_id": str(tenant_id)})
            scope_path = f"/api/v1/tenants/{tenant_id}/members/{new_user_id}/warehouse-scopes/WH-TEST"
            assert client.put(scope_path, headers=new_headers).status_code == 403
            assert client.put(scope_path.replace(str(tenant_id), str(foreign_tenant_id)),
                              headers=headers).status_code == 404
            assert client.put(scope_path, headers=headers).status_code == 200
            assert client.put(scope_path, headers=headers).status_code == 200
            new_headers["X-Tenant-ID"] = str(tenant_id)
            scopes = client.get("/api/v1/tenants/current/warehouse-scopes", headers=new_headers)
            assert scopes.json()["items"] == ["WH-TEST"]
            assert client.delete(scope_path, headers=headers).status_code == 204
            assert client.get("/api/v1/tenants/current/warehouse-scopes",
                              headers=new_headers).json()["items"] == []
            assert client.put(scope_path, headers=headers).status_code == 200

            updated = client.patch(f"/api/v1/tenants/{tenant_id}/members/{new_user_id}",
                                   headers=headers, json={"role": "staff"})
            assert updated.status_code == 200
            assert updated.json()["role"] == "staff"
            assert client.patch(f"/api/v1/tenants/{foreign_tenant_id}/members/{new_user_id}",
                                headers=headers, json={"role": "viewer"}).status_code == 404
            assert client.delete(f"/api/v1/tenants/{tenant_id}/members/{admin_id}",
                                 headers=headers).status_code == 403
            assert client.delete(f"/api/v1/tenants/{tenant_id}/members/{new_user_id}",
                                 headers=headers).status_code == 204
            assert client.get("/api/v1/tenants", headers=new_headers).json()["items"] == []
            assert connection.execute(text("""
                SELECT COUNT(*) FROM membership_warehouse_scopes
                WHERE tenant_id = :tenant_id AND user_id = :user_id
            """), {"tenant_id": str(tenant_id), "user_id": new_user_id}).scalar_one() == 0
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
