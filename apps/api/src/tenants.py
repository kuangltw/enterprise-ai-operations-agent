"""依目前使用者的成員資格讀取可選租戶。"""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import AuthError, Principal, get_current_user, get_db
from .identity_input import normalize_email, validate_new_password
from .passwords import hash_password

router = APIRouter(prefix="/api/v1/tenants", tags=["租戶"])


class TenantItem(BaseModel):
    id: UUID
    name: str
    role: str


class TenantList(BaseModel):
    items: list[TenantItem]
    next_cursor: UUID | None


class CreateMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["manager", "staff", "viewer"]


class MemberCreated(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    role: str


class ChangeRoleRequest(BaseModel):
    role: Literal["manager", "staff", "viewer"]


def require_tenant_admin(tenant_id: UUID, principal: Principal, db: Session) -> None:
    membership = db.execute(text("""
        SELECT m.role FROM memberships AS m
        JOIN tenants AS t ON t.id = m.tenant_id
        WHERE m.tenant_id = :tenant_id AND m.user_id = :user_id
          AND t.status = 'active'
        FOR UPDATE OF m
    """), {"tenant_id": str(tenant_id),
           "user_id": str(principal.user_id)}).mappings().first()
    if membership is None:
        raise AuthError(404, "TENANT_NOT_FOUND", "租戶不存在或無法存取")
    if membership["role"] != "admin":
        raise AuthError(403, "FORBIDDEN", "沒有管理成員的權限")


def get_managed_member(tenant_id: UUID, user_id: UUID, db: Session) -> dict:
    row = db.execute(text("""
        SELECT u.email, m.role FROM memberships AS m
        JOIN users AS u ON u.id = m.user_id
        WHERE m.tenant_id = :tenant_id AND m.user_id = :user_id
        FOR UPDATE OF m
    """), {"tenant_id": str(tenant_id),
           "user_id": str(user_id)}).mappings().first()
    if row is None:
        raise AuthError(404, "MEMBER_NOT_FOUND", "成員不存在或無法存取")
    if row["role"] == "admin":
        raise AuthError(403, "FORBIDDEN", "不可修改管理員成員資格")
    return dict(row)


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


@router.post("/{tenant_id}/members", response_model=MemberCreated, status_code=201)
def create_member(
    tenant_id: UUID,
    body: CreateMemberRequest,
    principal: Principal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberCreated:
    require_tenant_admin(tenant_id, principal, db)
    try:
        email = normalize_email(body.email)
        validate_new_password(body.password)
    except ValueError as exc:
        raise AuthError(422, "INVALID_MEMBER", "成員資料不符規定") from exc

    user_id = uuid4()
    password_hash = hash_password(body.password)
    try:
        db.execute(text("""
            INSERT INTO users (id, email, password_hash)
            VALUES (:id, :email, :password_hash)
        """), {"id": str(user_id), "email": email,
               "password_hash": password_hash})
        db.execute(text("""
            INSERT INTO memberships (tenant_id, user_id, role)
            VALUES (:tenant_id, :user_id, :role)
        """), {"tenant_id": str(tenant_id), "user_id": str(user_id),
               "role": body.role})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AuthError(409, "MEMBER_CONFLICT", "成員無法建立") from exc
    return MemberCreated(id=user_id, tenant_id=tenant_id, email=email, role=body.role)


@router.patch("/{tenant_id}/members/{user_id}", response_model=MemberCreated)
def change_member_role(
    tenant_id: UUID,
    user_id: UUID,
    body: ChangeRoleRequest,
    principal: Principal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberCreated:
    require_tenant_admin(tenant_id, principal, db)
    member = get_managed_member(tenant_id, user_id, db)
    db.execute(text("""
        UPDATE memberships SET role = :role
        WHERE tenant_id = :tenant_id AND user_id = :user_id
    """), {"role": body.role, "tenant_id": str(tenant_id),
           "user_id": str(user_id)})
    db.commit()
    return MemberCreated(id=user_id, tenant_id=tenant_id,
                         email=member["email"], role=body.role)


@router.delete("/{tenant_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_membership(
    tenant_id: UUID,
    user_id: UUID,
    principal: Principal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_tenant_admin(tenant_id, principal, db)
    get_managed_member(tenant_id, user_id, db)
    db.execute(text("""
        DELETE FROM memberships WHERE tenant_id = :tenant_id AND user_id = :user_id
    """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})
    db.commit()
