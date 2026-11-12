"""新租戶建立只接受既有啟用使用者，並原子建立管理員成員資格。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from src.create_tenant import create_tenant
from src.db import engine
from src.passwords import hash_password

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
