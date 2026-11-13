"""文件中繼資料與狀態查詢。

Tenant Context 先從資料庫重驗成員資格；每個文件 SQL 同時再查目前
User／Tenant／Membership 與 ACL，避免兩次查詢間撤權或改角色後沿用舊角色。
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import AuthError, get_db
from .tenant_context import TenantContext, get_tenant_context

router = APIRouter(prefix="/api/v1/documents", tags=["文件"])

# 三種讀取共用目前成員與 ACL 的 SQL 條件，避免新增端點時遺漏租戶隔離。
_ACCESS_JOINS = """
    FROM documents AS d
    JOIN memberships AS m ON m.tenant_id = d.tenant_id AND m.user_id = :user_id
    JOIN tenants AS t ON t.id = d.tenant_id AND t.status = 'active'
    JOIN users AS u ON u.id = m.user_id AND u.status = 'active'
"""
_ACCESS_FILTER = """
    WHERE d.tenant_id = :tenant_id AND d.status = 'active'
      AND (
        EXISTS (SELECT 1 FROM document_acl AS acl
                WHERE acl.tenant_id = d.tenant_id AND acl.document_id = d.id
                  AND acl.role = m.role)
        OR EXISTS (SELECT 1 FROM document_user_acl AS ua
                   WHERE ua.tenant_id = d.tenant_id AND ua.document_id = d.id
                     AND ua.user_id = :user_id)
      )
"""


class DocumentMetadata(BaseModel):
    """只含可公開給已授權成員的文件中繼資料。"""
    id: UUID
    tenant_id: UUID
    title: str
    current_version: int | None
    created_at: datetime


class DocumentList(BaseModel):
    """授權篩選後的一頁文件及下一頁游標。"""
    items: list[DocumentMetadata]
    next_cursor: UUID | None


class DocumentStatus(BaseModel):
    """ACL 可見文件的最新版本進度；空欄位代表尚無版本。"""
    document_id: UUID
    current_version: int | None
    latest_version: int | None
    storage_status: str | None
    indexing_status: str | None


@router.get("", response_model=DocumentList)
def list_documents(
    cursor: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentList:
    """列出目前租戶可讀文件；成員與 ACL 篩選先於分頁，避免游標洩漏。"""
    query = f"""
        SELECT d.id, d.tenant_id, d.title, d.current_version, d.created_at
        {_ACCESS_JOINS}
        {_ACCESS_FILTER}
    """
    parameters = {"tenant_id": str(context.tenant_id),
                  "user_id": str(context.user_id)}
    if cursor is not None:
        query += " AND d.id > :cursor"
        parameters["cursor"] = str(cursor)
    rows = db.execute(text(query + " ORDER BY d.id LIMIT 51"), parameters).mappings().all()
    items = [DocumentMetadata.model_validate(row) for row in rows[:50]]
    return DocumentList(items=items, next_cursor=items[-1].id if len(rows) > 50 else None)


@router.get("/{document_id}", response_model=DocumentMetadata)
def get_document_metadata(
    document_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentMetadata:
    """單筆文件只回 Metadata；無權限與不存在同樣回 404。"""
    row = db.execute(text(f"""
        SELECT d.id, d.tenant_id, d.title, d.current_version, d.created_at
        {_ACCESS_JOINS}
        {_ACCESS_FILTER}
        AND d.id = :document_id
    """), {"tenant_id": str(context.tenant_id), "document_id": str(document_id),
           "user_id": str(context.user_id)}).mappings().first()
    if row is None:
        raise AuthError(404, "DOCUMENT_NOT_FOUND", "文件不存在或無法存取")
    return DocumentMetadata.model_validate(row)


@router.get("/{document_id}/status", response_model=DocumentStatus)
def get_document_status(
    document_id: UUID,
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentStatus:
    """同一 SQL 快照重驗成員與 ACL 並讀取版本，避免撤權後洩漏狀態。"""
    row = db.execute(text(f"""
        SELECT d.current_version, latest.version, latest.storage_status,
               latest.indexing_status
        {_ACCESS_JOINS}
        LEFT JOIN LATERAL (
            SELECT v.version, v.storage_status, v.indexing_status
            FROM document_versions AS v
            WHERE v.tenant_id = d.tenant_id AND v.document_id = d.id
            ORDER BY v.version DESC LIMIT 1
        ) AS latest ON true
        {_ACCESS_FILTER}
        AND d.id = :document_id
    """), {"tenant_id": str(context.tenant_id), "document_id": str(document_id),
           "user_id": str(context.user_id)}).mappings().first()
    if row is None:
        raise AuthError(404, "DOCUMENT_NOT_FOUND", "文件不存在或無法存取")
    return DocumentStatus(
        document_id=document_id,
        current_version=row["current_version"],
        latest_version=row["version"],
        storage_status=row["storage_status"],
        indexing_status=row["indexing_status"],
    )
