"""以可信 Tenant Context 查詢與檢查使用者的倉庫授權範圍。"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import AuthError
from .tenant_context import TenantContext


def list_warehouse_codes(context: TenantContext, db: Session,
                         cursor: str | None = None) -> tuple[list[str], str | None]:
    query = """
        SELECT warehouse_code FROM membership_warehouse_scopes
        WHERE tenant_id = :tenant_id AND user_id = :user_id
    """
    parameters = {"tenant_id": str(context.tenant_id), "user_id": str(context.user_id)}
    if cursor is not None:
        query += " AND warehouse_code > :cursor"
        parameters["cursor"] = cursor
    rows = db.execute(text(query + " ORDER BY warehouse_code LIMIT 51"), parameters).scalars().all()
    items = list(rows[:50])
    return items, items[-1] if len(rows) > 50 else None


def require_warehouse_code(context: TenantContext, warehouse_code: str, db: Session) -> str:
    """未授權、空白或超長代碼一律回覆相同的不可存取錯誤。"""
    if not 1 <= len(warehouse_code) <= 80 or warehouse_code != warehouse_code.strip():
        raise AuthError(404, "WAREHOUSE_NOT_FOUND", "倉庫不存在或無法存取")
    found = db.execute(text("""
        SELECT 1 FROM membership_warehouse_scopes
        WHERE tenant_id = :tenant_id AND user_id = :user_id
          AND warehouse_code = :warehouse_code
    """), {"tenant_id": str(context.tenant_id),
           "user_id": str(context.user_id),
           "warehouse_code": warehouse_code}).scalar_one_or_none()
    if found is None:
        raise AuthError(404, "WAREHOUSE_NOT_FOUND", "倉庫不存在或無法存取")
    return warehouse_code
