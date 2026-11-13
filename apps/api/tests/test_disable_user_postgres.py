"""全域停權後，既有 JWT 與密碼登入均失效。"""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.auth import get_db
from src.db import engine
from src.disable_user import disable_user
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter
from src.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_disable_user_revokes_existing_sessions(monkeypatch):
    user_id, suffix = uuid4(), uuid4().hex
    email = f"{suffix}@example.invalid"
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, :password_hash)
            """), {"id": str(user_id), "email": email,
                   "password_hash": hash_password("synthetic-password-123")})

            def override_db():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    yield db

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_login_limiter] = lambda: type(
                "SyntheticLimiter", (), {"allow": lambda self, *_: True},
            )()
            monkeypatch.setattr(settings, "jwt_signing_key", "synthetic-test-only-" * 3)
            client = TestClient(app)
            body = {"email": email, "password": "synthetic-password-123"}
            login = client.post("/api/v1/auth/login", json=body)
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

            connection.execute(text("""
                UPDATE sessions SET created_at = CURRENT_TIMESTAMP + INTERVAL '30 seconds'
                WHERE user_id = :id
            """), {"id": str(user_id)})
            assert disable_user(connection, email.upper())
            assert disable_user(connection, email)
            assert not disable_user(connection, "missing@example.invalid")
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
            assert client.post("/api/v1/auth/login", json=body).status_code == 401
            assert connection.execute(text("""
                SELECT COUNT(*) FROM sessions WHERE user_id = :id AND revoked_at IS NULL
            """), {"id": str(user_id)}).scalar_one() == 0
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
