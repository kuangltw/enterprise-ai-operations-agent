"""文件上傳、中繼資料與狀態查詢。

Tenant Context 先從資料庫重驗成員資格；每個文件 SQL 同時再查目前
User／Tenant／Membership 與 ACL，避免兩次查詢間撤權或改角色後沿用舊角色。
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from minio.error import MinioException
from pydantic import BaseModel
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import parse_options_header
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from urllib3.exceptions import HTTPError

from .auth import AuthError, get_db
from .document_store import DocumentStoreUnavailable, get_document_store
from .document_uploads import (
    IdempotencyConflict, UploadForbidden,
    complete_document_upload, reserve_document_upload,
)
from .object_storage import (
    MAX_PDF_BYTES, InvalidPdf, PdfTooLarge, StoredPdfMismatch, prepare_pdf,
)
from .role_policy import allows
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


class DocumentUploadAccepted(BaseModel):
    """已確認原始檔儲存且已持久登錄處理工作時回傳的識別。"""

    document_id: UUID
    version_id: UUID


_MAX_UPLOAD_BODY = MAX_PDF_BYTES + 64 * 1024


async def _bounded_upload_body(request: Request):
    """完整計量再交給解析器，涵蓋沒有 Content-Length 的請求。"""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_UPLOAD_BODY:
            raise AuthError(413, "PDF_TOO_LARGE", "上傳請求超過大小限制")
        body.extend(chunk)
    yield bytes(body)


def _store_upload(db: Session, context: TenantContext, idempotency_key: UUID,
                  title: str, file: UploadFile) -> DocumentUploadAccepted:
    """驗證檔頭後委派既有交易；失敗時保留可用同鍵對帳的預約。"""
    try:
        prepared = prepare_pdf(file.file)
        store = get_document_store()
        reserved = reserve_document_upload(
            db, context.tenant_id, context.user_id, title, idempotency_key, prepared,
        )
        complete_document_upload(
            db, store.client, store.bucket, context.tenant_id, context.user_id,
            idempotency_key, prepared,
        )
    except PdfTooLarge as exc:
        raise AuthError(413, "PDF_TOO_LARGE", "PDF 超過大小限制") from exc
    except InvalidPdf as exc:
        raise AuthError(415, "INVALID_PDF", "檔案格式不符 PDF") from exc
    except UploadForbidden as exc:
        raise AuthError(403, "DOCUMENT_UPLOAD_FORBIDDEN", "沒有上傳文件的權限") from exc
    except IdempotencyConflict as exc:
        raise AuthError(409, "IDEMPOTENCY_CONFLICT", "無法以此冪等鍵完成上傳") from exc
    except (DocumentStoreUnavailable, MinioException, HTTPError, OSError,
            DBAPIError, StoredPdfMismatch) as exc:
        raise AuthError(503, "DOCUMENT_UPLOAD_UNAVAILABLE", "目前無法確認文件已儲存") from exc
    return DocumentUploadAccepted(document_id=reserved.document_id, version_id=reserved.version_id)


@router.post(
    "", status_code=202, response_model=DocumentUploadAccepted,
    responses={
        401: {"description": "尚未登入或工作階段失效"},
        403: {"description": "角色無上傳權限"},
        404: {"description": "租戶不存在或無法存取"},
        409: {"description": "無法以此冪等鍵完成上傳"},
        413: {"description": "PDF 或 multipart 請求超過大小限制"},
        415: {"description": "媒體類型或 PDF 檔頭不符"},
        422: {"description": "請求資料不符規定"},
        503: {"description": "目前無法確認文件已儲存"},
    },
    openapi_extra={"requestBody": {"required": True, "content": {
        "multipart/form-data": {"schema": {
            "type": "object", "required": ["title", "file"],
            "properties": {"title": {"type": "string", "maxLength": 255},
                           "file": {"type": "string", "format": "binary"}},
        }, "encoding": {"file": {"contentType": "application/pdf"}}},
    }}},
)
async def upload_document(
    request: Request,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DocumentUploadAccepted:
    """授權後收下新文件；202 表示已儲存並待處理，原文仍未發布。"""
    if not allows(context.role, "document.upload"):
        raise AuthError(403, "DOCUMENT_UPLOAD_FORBIDDEN", "沒有上傳文件的權限")
    if parse_options_header(request.headers.get("content-type", ""))[0] != b"multipart/form-data":
        raise AuthError(415, "UNSUPPORTED_MEDIA_TYPE", "上傳須使用 multipart/form-data")
    try:
        form = await MultiPartParser(
            request.headers, _bounded_upload_body(request),
            max_files=1, max_fields=1, max_part_size=4096,
        ).parse()
    except (MultiPartException, FormParserError) as exc:
        raise AuthError(422, "VALIDATION_ERROR", "multipart 請求資料不符規定") from exc

    try:
        title, file = form.get("title"), form.get("file")
        if not isinstance(title, str) or not isinstance(file, UploadFile):
            raise AuthError(422, "VALIDATION_ERROR", "須提供文件標題及 PDF 檔案")
        title = title.strip()
        if not title or len(title) > 255 or "\x00" in title:
            raise AuthError(422, "VALIDATION_ERROR", "文件標題不符規定")
        if file.content_type != "application/pdf":
            raise AuthError(415, "INVALID_PDF", "檔案媒體類型須為 application/pdf")
        return await run_in_threadpool(_store_upload, db, context, idempotency_key, title, file)
    finally:
        await form.close()


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
