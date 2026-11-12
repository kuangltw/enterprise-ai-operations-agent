"""僅供空白資料庫首次建立管理員與租戶。密碼從終端機隱藏讀取。"""

import getpass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .db import engine
from .passwords import hash_password
from .identity_input import normalize_email, validate_new_password


def create_initial_admin(connection: Connection, email: str, password: str, tenant_name: str) -> None:
    """呼叫端須提供交易；鎖定與寫入一律在同一筆交易內。"""
    normalized_email = normalize_email(email)
    name = tenant_name.strip()
    if not 1 <= len(name) <= 120:
        raise ValueError("租戶名稱長度不符規定")
    validate_new_password(password)
    password_hash = hash_password(password)

    connection.execute(text("SELECT pg_advisory_xact_lock(934814)"))
    existing = connection.execute(text("""
        SELECT EXISTS (SELECT 1 FROM users) OR EXISTS (SELECT 1 FROM tenants)
    """)).scalar_one()
    if existing:
        raise ValueError("資料庫已初始化，拒絕再次建立初始管理員")

    user_id, tenant_id = uuid4(), uuid4()
    connection.execute(text("""
        INSERT INTO users (id, email, password_hash)
        VALUES (:id, :email, :password_hash)
    """), {"id": str(user_id), "email": normalized_email,
           "password_hash": password_hash})
    connection.execute(text("""
        INSERT INTO tenants (id, name) VALUES (:id, :name)
    """), {"id": str(tenant_id), "name": name})
    connection.execute(text("""
        INSERT INTO memberships (tenant_id, user_id, role)
        VALUES (:tenant_id, :user_id, 'admin')
    """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})


def main() -> None:
    email = input("管理員 Email：")
    tenant_name = input("租戶名稱：")
    password = getpass.getpass("管理員密碼：")
    with engine.begin() as connection:
        create_initial_admin(connection, email, password, tenant_name)
    print("初始管理員與租戶已建立。")


if __name__ == "__main__":
    main()
