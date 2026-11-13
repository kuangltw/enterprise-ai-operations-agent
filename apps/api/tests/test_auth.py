"""登入、工作階段撤銷及停權的 API 測試。"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.auth import get_db
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter
from src.settings import settings


@pytest.fixture
def auth_client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, password_hash TEXT, status TEXT)"))
        conn.execute(text("CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT, expires_at TEXT, revoked_at TEXT)"))
        conn.execute(text("INSERT INTO users VALUES (:id, :email, :hash, 'active')"), {
            "id": str(uuid4()), "email": "test@example.invalid",
            "hash": hash_password("synthetic-password-123"),
        })

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_login_limiter] = lambda: type(
        "SyntheticLimiter", (), {"allow": lambda self, *_: True},
    )()
    monkeypatch.setattr(settings, "jwt_signing_key", "synthetic-test-only-" * 3)
    try:
        yield TestClient(app), engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_login_me_and_logout_revokes_session(auth_client):
    client, _ = auth_client
    response = client.post("/api/v1/auth/login", json={
        "email": " TEST@example.invalid ", "password": "synthetic-password-123",
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_invalid_password_and_disabled_user_are_rejected(auth_client):
    client, engine = auth_client
    login = {"email": "test@example.invalid", "password": "wrong-password"}
    response = client.post("/api/v1/auth/login", json=login)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET status='disabled'"))
    login["password"] = "synthetic-password-123"
    assert client.post("/api/v1/auth/login", json=login).status_code == 401


def test_missing_signing_key_fails_closed(auth_client, monkeypatch):
    client, _ = auth_client
    monkeypatch.setattr(settings, "jwt_signing_key", None)
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.invalid", "password": "synthetic-password-123",
    })
    assert response.status_code == 503


def test_missing_token_is_rejected(auth_client):
    client, _ = auth_client
    assert client.get("/api/v1/auth/me").status_code == 401
    for value in ("Basic synthetic", "Bearer ", "Bearer synthetic invalid"):
        assert client.get("/api/v1/auth/me", headers={"Authorization": value}).status_code == 401


def test_validation_error_uses_public_error_contract(auth_client):
    client, _ = auth_client
    response = client.post("/api/v1/auth/login", json={"email": "", "password": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"] == {}
    assert "input" not in response.text


def test_openapi_contains_auth_contract():
    schema = app.openapi()
    paths = schema["paths"]
    assert "post" in paths["/api/v1/auth/login"]
    assert "get" in paths["/api/v1/auth/me"]
    assert "post" in paths["/api/v1/auth/logout"]
    assert "get" in paths["/api/v1/documents/{document_id}"]
    assert "get" in paths["/api/v1/documents/{document_id}/status"]
    assert "get" in paths["/api/v1/documents"]
    document_list = paths["/api/v1/documents"]["get"]
    assert {"HTTPBearer": []} in document_list["security"]
    assert any(parameter["name"] == "X-Tenant-ID" and parameter["required"]
               for parameter in document_list["parameters"])
    document_get = paths["/api/v1/documents/{document_id}"]["get"]
    assert {"HTTPBearer": []} in document_get["security"]
    assert any(parameter["name"] == "X-Tenant-ID" and parameter["required"]
               for parameter in document_get["parameters"])
    assert document_get["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DocumentMetadata",
    }
    document_status = paths["/api/v1/documents/{document_id}/status"]["get"]
    assert {"HTTPBearer": []} in document_status["security"]
    assert any(parameter["name"] == "X-Tenant-ID" and parameter["required"]
               for parameter in document_status["parameters"])
    assert document_status["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DocumentStatus",
    }
    assert "get" in paths["/api/v1/tenants"]
    assert "get" in paths["/api/v1/tenants/current"]
    assert "get" in paths["/api/v1/tenants/current/warehouse-scopes"]
    assert "get" in paths["/api/v1/tenants/current/warehouse-scopes/{warehouse_code}"]
    assert "get" in paths["/api/v1/tenants/{tenant_id}"]
    assert "post" in paths["/api/v1/tenants/{tenant_id}/members"]
    assert "patch" in paths["/api/v1/tenants/{tenant_id}/members/{user_id}"]
    assert "delete" in paths["/api/v1/tenants/{tenant_id}/members/{user_id}"]
    scope_path = "/api/v1/tenants/{tenant_id}/members/{user_id}/warehouse-scopes/{warehouse_code}"
    assert "put" in paths[scope_path]
    assert "delete" in paths[scope_path]
    schemes = schema["components"]["securitySchemes"]
    assert schemes["HTTPBearer"] == {"type": "http", "scheme": "bearer"}
    assert "security" not in paths["/api/v1/auth/login"]["post"]
    for path, method in (
        ("/api/v1/auth/me", "get"),
        ("/api/v1/auth/logout", "post"),
        ("/api/v1/tenants", "get"),
        ("/api/v1/tenants/current", "get"),
        (scope_path, "put"),
    ):
        assert {"HTTPBearer": []} in paths[path][method]["security"]


def test_login_limit_and_redis_outage_fail_closed(auth_client):
    client, _ = auth_client
    body = {"email": "test@example.invalid", "password": "synthetic-password-123"}

    class BlockedLimiter:
        def allow(self, *_):
            return False

    app.dependency_overrides[get_login_limiter] = lambda: BlockedLimiter()
    response = client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "LOGIN_RATE_LIMITED"

    class BrokenLimiter:
        def allow(self, *_):
            from redis.exceptions import ConnectionError
            raise ConnectionError("synthetic outage")

    app.dependency_overrides[get_login_limiter] = lambda: BrokenLimiter()
    assert client.post("/api/v1/auth/login", json=body).status_code == 503
