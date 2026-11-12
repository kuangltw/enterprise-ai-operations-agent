"""以已驗證租戶成員資格與文件 ACL 讀取文件中繼資料。"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import AuthError, get_db
from .tenant_context import TenantContext, get_tenant_context

router = APIRouter(prefix="/api/v1/documents", tags=["文件"])


class DocumentMetadata(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    current_version: int | None
    created_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentMetadata]
    next_cursor: UUID | None


@router.get("", response_model=DocumentList)
def list_documents(
    cursor: UUID | None = None,
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentList:
    query = """
        SELECT d.id, d.tenant_id, d.title, d.current_version, d.created_at
        FROM documents AS d
        JOIN document_acl AS acl
          ON acl.tenant_id = d.tenant_id AND acl.document_id = d.id
        WHERE d.tenant_id = :tenant_id AND d.status = 'active' AND acl.role = :role
    """
    parameters = {"tenant_id": str(context.tenant_id), "role": context.role}
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
    row = db.execute(text("""
        SELECT d.id, d.tenant_id, d.title, d.current_version, d.created_at
        FROM documents AS d
        JOIN document_acl AS acl
          ON acl.tenant_id = d.tenant_id AND acl.document_id = d.id
        WHERE d.tenant_id = :tenant_id AND d.id = :document_id
          AND d.status = 'active' AND acl.role = :role
    """), {"tenant_id": str(context.tenant_id), "document_id": str(document_id),
           "role": context.role}).mappings().first()
    if row is None:
        raise AuthError(404, "DOCUMENT_NOT_FOUND", "文件不存在或無法存取")
    return DocumentMetadata.model_validate(row)
