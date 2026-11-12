"""資料庫操作員使用的全域停權指令。"""

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .db import engine
from .identity_input import normalize_email


def disable_user(connection: Connection, email: str) -> bool:
    """在呼叫端交易內停權 User 並撤銷其全部 Session。"""
    normalized_email = normalize_email(email)
    row = connection.execute(text("""
        SELECT id, status FROM users WHERE lower(email) = :email FOR UPDATE
    """), {"email": normalized_email}).mappings().first()
    if row is None:
        return False
    if row["status"] != "disabled":
        connection.execute(text("""
            UPDATE users SET status = 'disabled' WHERE id = :user_id
        """), {"user_id": str(row["id"])})
    connection.execute(text("""
        UPDATE sessions SET revoked_at = :now
        WHERE user_id = :user_id AND revoked_at IS NULL
    """), {"user_id": str(row["id"]), "now": datetime.now(timezone.utc)})
    return True


def main() -> None:
    email = input("要停權的 User Email：")
    if input("輸入 DISABLE 確認停權及撤銷所有 Session：") != "DISABLE":
        print("操作已取消。")
        return
    with engine.begin() as connection:
        found = disable_user(connection, email)
    print("使用者已停權。" if found else "找不到使用者。")


if __name__ == "__main__":
    main()
