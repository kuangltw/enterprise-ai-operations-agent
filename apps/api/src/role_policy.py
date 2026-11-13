"""M1 角色政策；ACL、倉庫範圍及職責分離須另行檢查。"""

from typing import Literal

from fastapi import Depends

from .auth import AuthError
from .tenant_context import TenantContext, get_tenant_context

Permission = Literal[
    "tenant.read", "member.manage", "knowledge.ask", "document.upload", "inventory.read",
    "purchase.draft.create", "purchase.approve",
]

_ALLOWED: dict[str, frozenset[str]] = {
    "admin": frozenset({"tenant.read", "member.manage", "knowledge.ask", "document.upload", "inventory.read",
                        "purchase.draft.create", "purchase.approve"}),
    "manager": frozenset({"tenant.read", "knowledge.ask", "document.upload", "inventory.read",
                          "purchase.draft.create", "purchase.approve"}),
    "staff": frozenset({"tenant.read", "knowledge.ask", "document.upload", "inventory.read",
                        "purchase.draft.create"}),
    "viewer": frozenset({"tenant.read", "knowledge.ask", "inventory.read"}),
}


def allows(role: str, permission: Permission) -> bool:
    """未知角色與權限均拒絕；呼叫端仍須檢查其他資料範圍。"""
    return permission in _ALLOWED.get(role, frozenset())


def require_permission(permission: Permission):
    """供需要 `X-Tenant-ID` 的端點使用，回傳已驗證的 Tenant Context。"""
    def dependency(context: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not allows(context.role, permission):
            raise AuthError(403, "FORBIDDEN", "沒有執行此操作的權限")
        return context

    return dependency
