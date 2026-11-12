"""依目前使用者的成員資格讀取可選租戶。"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import AuthError, Principal, get_current_user, get_db

router = APIRouter(prefix="/api/v1/tenants", tags=["租戶"])


class TenantItem(BaseModel):
    id: UUID
    name: str
    role: str


class TenantList(BaseModel):
    items: list[TenantItem]
    next_cursor: UUID | None


@router.get("", response_model=TenantList)
def list_tenants(
    cursor: UUID | None = None,
    principal: Principal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantList:
    query = """
        SELECT t.id, t.name, m.role FROM memberships AS m
        JOIN tenants AS t ON t.id = m.tenant_id
        WHERE m.user_id = :user_id AND t.status = 'active'
    """
    parameters = {"user_id": str(principal.user_id)}
    if cursor is not None:
        query += " AND t.id > :cursor"
        parameters["cursor"] = str(cursor)
    rows = db.execute(text(query + " ORDER BY t.id LIMIT 51"), parameters).mappings().all()
    items = [TenantItem(id=row["id"], name=row["name"], role=row["role"])
             for row in rows[:50]]
    return TenantList(items=items, next_cursor=items[-1].id if len(rows) > 50 else None)


@router.get("/{tenant_id}", response_model=TenantItem)
def get_tenant(
    tenant_id: UUID,
    principal: Principal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantItem:
    row = db.execute(text("""
        SELECT t.id, t.name, m.role FROM memberships AS m
        JOIN tenants AS t ON t.id = m.tenant_id
        WHERE m.user_id = :user_id AND t.id = :tenant_id
          AND t.status = 'active'
    """), {"user_id": str(principal.user_id),
           "tenant_id": str(tenant_id)}).mappings().first()
    if row is None:
        raise AuthError(404, "TENANT_NOT_FOUND", "租戶不存在或無法存取")
    return TenantItem(id=row["id"], name=row["name"], role=row["role"])
