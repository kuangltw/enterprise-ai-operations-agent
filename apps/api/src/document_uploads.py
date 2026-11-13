"""文件上傳的資料庫預約交易；物件儲存與發布由後續步驟處理。"""

from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from .object_storage import MAX_PDF_BYTES, PreparedPdf, reserve_pdf_key
from .role_policy import allows


class UploadForbidden(PermissionError):
    """使用者沒有在目前租戶上傳文件的資格。"""


class IdempotencyConflict(ValueError):
    """同一冪等鍵已對應其他上傳請求。"""


@dataclass(frozen=True)
class ReservedUpload:
    document_id: UUID
    version_id: UUID
    storage_key: str
    storage_status: str
    was_existing: bool


def reserve_document_upload(db: Session, tenant_id: UUID, user_id: UUID,
                            title: str, idempotency_key: UUID,
                            prepared: PreparedPdf) -> ReservedUpload:
    """重新查驗成員與角色，原子建立只有建立者可讀的待上傳文件。"""
    normalized_title = title.strip()
    if not normalized_title or len(normalized_title) > 255:
        raise ValueError("文件標題不符合長度限制")
    if (prepared.size != len(prepared.data) or prepared.size > MAX_PDF_BYTES
            or not prepared.data.startswith(b"%PDF-")
            or prepared.sha256 != sha256(prepared.data).hexdigest()):
        raise ValueError("PDF 準備資料不一致")
    try:
        membership = db.execute(text("""
            SELECT m.role FROM memberships AS m
            JOIN tenants AS t ON t.id = m.tenant_id
            JOIN users AS u ON u.id = m.user_id
            WHERE m.tenant_id = :tenant_id AND m.user_id = :user_id
              AND t.status = 'active' AND u.status = 'active'
            FOR UPDATE OF m, t, u
        """), {"tenant_id": str(tenant_id), "user_id": str(user_id)}).mappings().first()
        if membership is None or not allows(membership["role"], "document.upload"):
            raise UploadForbidden("沒有上傳文件的權限")

        db.execute(text("""
            SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))
        """), {"lock_key": f"document-upload:{tenant_id}:{idempotency_key}"})
        existing = db.execute(text("""
            SELECT v.id AS version_id, v.document_id, v.storage_key,
                   v.storage_status, v.sha256, d.title, d.owner_id
            FROM document_versions AS v
            JOIN documents AS d ON d.tenant_id = v.tenant_id AND d.id = v.document_id
            WHERE v.tenant_id = :tenant_id AND v.idempotency_key = :idempotency_key
        """), {"tenant_id": str(tenant_id),
               "idempotency_key": str(idempotency_key)}).mappings().first()
        if existing is not None:
            if (existing["owner_id"] != user_id or existing["title"] != normalized_title
                    or existing["sha256"] != prepared.sha256):
                raise IdempotencyConflict("冪等鍵已用於其他文件或內容")
            result = ReservedUpload(existing["document_id"], existing["version_id"],
                                    existing["storage_key"], existing["storage_status"],
                                    True)
            db.commit()
            return result

        document_id, version_id = uuid4(), uuid4()
        storage_key = reserve_pdf_key(tenant_id, document_id, version_id)
        db.execute(text("""
            INSERT INTO documents (id, tenant_id, title, owner_id)
            VALUES (:document_id, :tenant_id, :title, :user_id)
        """), {"document_id": str(document_id), "tenant_id": str(tenant_id),
               "title": normalized_title, "user_id": str(user_id)})
        db.execute(text("""
            INSERT INTO document_versions
                (id, tenant_id, document_id, version, storage_key, sha256, idempotency_key)
            VALUES (:version_id, :tenant_id, :document_id, 1, :storage_key,
                    :sha256, :idempotency_key)
        """), {"version_id": str(version_id), "tenant_id": str(tenant_id),
               "document_id": str(document_id), "storage_key": storage_key,
               "sha256": prepared.sha256, "idempotency_key": str(idempotency_key)})
        db.execute(text("""
            INSERT INTO document_user_acl (tenant_id, document_id, user_id)
            VALUES (:tenant_id, :document_id, :user_id)
        """), {"tenant_id": str(tenant_id), "document_id": str(document_id),
               "user_id": str(user_id)})
        db.commit()
        return ReservedUpload(document_id, version_id, storage_key,
                              "pending_upload", False)
    except Exception:
        db.rollback()
        raise
