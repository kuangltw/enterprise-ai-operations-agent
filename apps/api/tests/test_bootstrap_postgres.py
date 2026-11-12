"""在 PostgreSQL 交易內驗證初始建帳與防重複。"""

import os

import pytest
from sqlalchemy import text

from src.bootstrap_identity import create_initial_admin
from src.db import engine
from src.passwords import verify_password

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_initial_admin_is_atomic_and_cannot_be_repeated():
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            existing = connection.execute(text("""
                SELECT EXISTS (SELECT 1 FROM users) OR EXISTS (SELECT 1 FROM tenants)
            """)).scalar_one()
            if existing:
                pytest.skip("現有資料庫已初始化，不執行空白資料庫案例")

            create_initial_admin(
                connection, " ADMIN@example.invalid ",
                "synthetic-password-123", "合成租戶",
            )
            row = connection.execute(text("""
                SELECT u.email, u.password_hash, m.role, t.name
                FROM users AS u JOIN memberships AS m ON m.user_id = u.id
                JOIN tenants AS t ON t.id = m.tenant_id
            """)).mappings().one()
            assert row["email"] == "admin@example.invalid"
            assert row["role"] == "admin"
            assert row["name"] == "合成租戶"
            assert verify_password("synthetic-password-123", row["password_hash"])
            with pytest.raises(ValueError):
                create_initial_admin(connection, "second@example.invalid", "synthetic-password-123", "第二租戶")
        finally:
            outer.rollback()
