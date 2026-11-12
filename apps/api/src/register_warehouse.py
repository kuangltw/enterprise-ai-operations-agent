"""資料庫操作員核對 ERP 倉庫後，將代碼登錄至指定租戶。"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .db import engine


def register_warehouse(connection: Connection, tenant_id: UUID, warehouse_code: str) -> None:
    """呼叫端提供交易；ERP 實際歸屬必須由操作員先行核對。"""
    code = warehouse_code.strip()
    if not 1 <= len(code) <= 80 or code != warehouse_code:
        raise ValueError("倉庫代碼長度或格式不符規定")
    active = connection.execute(text("""
        SELECT 1 FROM tenants WHERE id = :tenant_id AND status = 'active' FOR UPDATE
    """), {"tenant_id": str(tenant_id)}).scalar_one_or_none()
    if active is None:
        raise ValueError("找不到啟用中的租戶")
    connection.execute(text("""
        INSERT INTO tenant_warehouses (tenant_id, warehouse_code)
        VALUES (:tenant_id, :warehouse_code)
    """), {"tenant_id": str(tenant_id), "warehouse_code": code})


def main() -> None:
    try:
        tenant_id = UUID(input("已核對的租戶 ID：").strip())
    except ValueError as exc:
        raise ValueError("租戶 ID 格式不符規定") from exc
    code = input("已核對 ERP 歸屬的倉庫代碼：")
    if input("確認已在 ERP 核實代碼與租戶歸屬，輸入 REGISTER：") != "REGISTER":
        print("操作已取消。")
        return
    with engine.begin() as connection:
        register_warehouse(connection, tenant_id, code)
    print("倉庫代碼已登錄至指定租戶。")


if __name__ == "__main__":
    main()
