"""倉庫範圍由複合外鍵綁定成員資格，撤銷成員時一併清除。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.db import engine
from src.passwords import hash_password

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
