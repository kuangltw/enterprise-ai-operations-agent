"""由登入身分及資料庫成員資格建立可信租戶上下文。"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import AuthError, Principal, get_current_user, get_db


@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    user_id: UUID
    name: str
    role: str


def get_tenant_context(
    tenant_id: UUID = Header(alias="X-Tenant-ID"),
    principal: Principal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    row = db.execute(text("""
        SELECT t.name, m.role FROM memberships AS m
        JOIN tenants AS t ON t.id = m.tenant_id
        WHERE m.tenant_id = :tenant_id AND m.user_id = :user_id
          AND t.status = 'active'
    """), {"tenant_id": str(tenant_id),
           "user_id": str(principal.user_id)}).mappings().first()
    if row is None:
        raise AuthError(404, "TENANT_NOT_FOUND", "租戶不存在或無法存取")
    return TenantContext(tenant_id, principal.user_id, row["name"], row["role"])
