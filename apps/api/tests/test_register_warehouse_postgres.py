"""操作員登錄倉庫時須指定啟用租戶，代碼不可被其他租戶佔用。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.db import engine
from src.register_warehouse import register_warehouse

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_register_warehouse_requires_active_tenant_and_unique_code():
    active_id, suspended_id = uuid4(), uuid4()
    code = f"WH-{uuid4().hex}"
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO tenants (id, name) VALUES (:id, '合成啟用租戶')
            """), {"id": str(active_id)})
            connection.execute(text("""
                INSERT INTO tenants (id, name, status)
                VALUES (:id, '合成停用租戶', 'suspended')
            """), {"id": str(suspended_id)})
            with pytest.raises(ValueError):
                register_warehouse(connection, suspended_id, code)
            with pytest.raises(ValueError):
                register_warehouse(connection, uuid4(), code)
            with pytest.raises(ValueError):
                register_warehouse(connection, active_id, " WH-SPACE ")

            register_warehouse(connection, active_id, code)
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO tenant_warehouses (tenant_id, warehouse_code)
                        VALUES (:tenant_id, :code)
                    """), {"tenant_id": str(suspended_id), "code": code})
            assert connection.execute(text("""
                SELECT tenant_id FROM tenant_warehouses WHERE warehouse_code = :code
            """), {"code": code}).scalar_one() == active_id
        finally:
            outer.rollback()
