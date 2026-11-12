"""只供隔離 E2E 資料庫使用；帳密由執行器於執行時提供。"""

import os

from sqlalchemy import text

from src.db import engine
from src.passwords import hash_password


def main() -> None:
    password_hash = hash_password(os.environ["E2E_USER_PASSWORD"])
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO users (id, email, password_hash) VALUES
            (:primary_id, :primary_email, :password_hash),
            (:other_id, :other_email, :password_hash)
        """), {
            "primary_id": os.environ["E2E_PRIMARY_USER_ID"],
            "primary_email": os.environ["E2E_USER_EMAIL"],
            "other_id": os.environ["E2E_OTHER_USER_ID"],
            "other_email": os.environ["E2E_OTHER_EMAIL"],
            "password_hash": password_hash,
        })
        connection.execute(text("""
            INSERT INTO tenants (id, name) VALUES
            (:tenant_a, '合成租戶甲'),
            (:tenant_b, '合成租戶乙'),
            (:tenant_c, '合成隔離租戶')
        """), {
            "tenant_a": os.environ["E2E_TENANT_A_ID"],
            "tenant_b": os.environ["E2E_TENANT_B_ID"],
            "tenant_c": os.environ["E2E_TENANT_C_ID"],
        })
        connection.execute(text("""
            INSERT INTO memberships (tenant_id, user_id, role) VALUES
            (:tenant_a, :primary_id, 'staff'),
            (:tenant_b, :primary_id, 'viewer'),
            (:tenant_b, :other_id, 'staff')
        """), {
            "tenant_a": os.environ["E2E_TENANT_A_ID"],
            "tenant_b": os.environ["E2E_TENANT_B_ID"],
            "primary_id": os.environ["E2E_PRIMARY_USER_ID"],
            "other_id": os.environ["E2E_OTHER_USER_ID"],
        })


if __name__ == "__main__":
    main()
