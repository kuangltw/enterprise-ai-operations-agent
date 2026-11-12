"""資料庫操作員建立租戶，並指定既有啟用使用者為首位管理員。"""

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .db import engine
from .identity_input import normalize_email


def create_tenant(connection: Connection, name: str, admin_email: str) -> UUID:
    """呼叫端提供交易；租戶與首位管理員成員資格必須一同提交。"""
    tenant_name = name.strip()
    if not 1 <= len(tenant_name) <= 120:
        raise ValueError("租戶名稱長度不符規定")
    email = normalize_email(admin_email)
    admin = connection.execute(text("""
        SELECT id FROM users
        WHERE lower(email) = :email AND status = 'active'
        FOR UPDATE
    """), {"email": email}).mappings().first()
    if admin is None:
        raise ValueError("找不到啟用中的管理員使用者")

    tenant_id = uuid4()
    connection.execute(text("""
        INSERT INTO tenants (id, name) VALUES (:tenant_id, :name)
    """), {"tenant_id": str(tenant_id), "name": tenant_name})
    connection.execute(text("""
        INSERT INTO memberships (tenant_id, user_id, role)
        VALUES (:tenant_id, :user_id, 'admin')
    """), {"tenant_id": str(tenant_id), "user_id": str(admin["id"])})
    return tenant_id


def main() -> None:
    name = input("新租戶名稱：")
    admin_email = input("既有管理員 User Email：")
    if input("輸入 CREATE 確認建立租戶：") != "CREATE":
        print("操作已取消。")
        return
    with engine.begin() as connection:
        tenant_id = create_tenant(connection, name, admin_email)
    print(f"租戶已建立：{tenant_id}")


if __name__ == "__main__":
    main()
