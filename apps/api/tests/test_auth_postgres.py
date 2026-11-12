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
from src.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_login_and_revocation_against_postgres(monkeypatch):
    user_id = uuid4()
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, :hash)
            """), {"id": str(user_id), "email": "synthetic-integration@example.invalid",
                   "hash": hash_password("synthetic-password-123")})

            def override_db():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    yield db

            app.dependency_overrides[get_db] = override_db
            monkeypatch.setattr(settings, "jwt_signing_key", "synthetic-test-only-" * 3)
            client = TestClient(app)
            response = client.post("/api/v1/auth/login", json={
                "email": "synthetic-integration@example.invalid",
                "password": "synthetic-password-123",
            })
            assert response.status_code == 200
            headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
        finally:
            app.dependency_overrides.clear()
            outer.rollback()
