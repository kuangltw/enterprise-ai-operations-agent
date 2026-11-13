"""文件上傳的預約與儲存交易。

PostgreSQL 保存權限、冪等鍵與索引工作；MinIO 保存原始 PDF。兩者沒有
共同交易，因此寫入結果不明時先讀回對帳，再提交 `stored` 與待索引工作。
版本發布及 Worker 消費由後續模組處理。
"""

from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid4

from minio import Minio
from sqlalchemy import text
from sqlalchemy.orm import Session

from .object_storage import (
    MAX_PDF_BYTES, PreparedPdf, StoredPdf, reserve_pdf_key,
    store_prepared_pdf, verify_stored_pdf,
)
from .role_policy import allows


class UploadForbidden(PermissionError):
    """使用者沒有在目前租戶上傳文件的資格。"""


class IdempotencyConflict(ValueError):
    """同一冪等鍵已對應其他上傳請求。"""


class StoredObjectMissing(FileNotFoundError):
    """已標示儲存完成的版本缺少可核對的物件。"""


@dataclass(frozen=True)
class ReservedUpload:
    """預約版本的識別與狀態；`was_existing` 表示冪等重試。"""
    document_id: UUID
    version_id: UUID
    storage_key: str
    storage_status: str
    was_existing: bool


def _validate_prepared(prepared: PreparedPdf) -> None:
    """防止呼叫端直接建構不一致的 PreparedPdf，避免錯誤摘要入庫。"""
    if (prepared.size != len(prepared.data) or prepared.size > MAX_PDF_BYTES
            or not prepared.data.startswith(b"%PDF-")
            or prepared.sha256 != sha256(prepared.data).hexdigest()):
        raise ValueError("PDF 準備資料不一致")


def _lock_upload_member(db: Session, tenant_id: UUID, user_id: UUID) -> None:
    """鎖定目前啟用的 User／Tenant／Membership，避免寫入期間權限變更。"""
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


def reserve_document_upload(db: Session, tenant_id: UUID, user_id: UUID,
                            title: str, idempotency_key: UUID,
                            prepared: PreparedPdf) -> ReservedUpload:
    """預約新文件或回傳同鍵、同建立者與內容的既有預約。

    此函式自行提交或回滾 DB Session。`prepared` 由 `prepare_pdf` 取得；
    重新核對內容後鎖定成員與租戶，再以租戶加冪等鍵序列化預約。
    新文件只授予建立者 ACL，尚無 MinIO 物件。權限不足與同鍵內容衝突
    分別拋出 UploadForbidden、IdempotencyConflict；資料庫錯誤向上傳遞。
    """
    normalized_title = title.strip()
    if not normalized_title or len(normalized_title) > 255:
        raise ValueError("文件標題不符合長度限制")
    _validate_prepared(prepared)
    try:
        _lock_upload_member(db, tenant_id, user_id)

        # 同租戶同鍵請求只能有一筆預約；唯一約束仍是最後防線。
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


def complete_document_upload(db: Session, client: Minio, bucket: str,
                             tenant_id: UUID, user_id: UUID,
                             idempotency_key: UUID,
                             prepared: PreparedPdf) -> StoredPdf:
    """對帳預約版本，必要時寫入 MinIO，再原子登錄儲存與索引工作。

    此函式自行提交或回滾 DB Session，外部 I/O 期間持有成員與版本鎖。
    寫入回應遺失時讀回核對；無法確認則保留原 DB 狀態並拋出錯誤，
    呼叫端可用相同冪等鍵重試。已標示 stored 卻缺物件時拒絕回報成功。
    不發送 Celery 工作，也不發布 current_version。
    """
    _validate_prepared(prepared)
    try:
        _lock_upload_member(db, tenant_id, user_id)
        row = db.execute(text("""
            SELECT v.id AS version_id, v.document_id, v.storage_key,
                   v.storage_status, v.sha256, d.owner_id, d.status,
                   EXISTS (
                       SELECT 1 FROM document_user_acl AS ua
                       WHERE ua.tenant_id = d.tenant_id AND ua.document_id = d.id
                         AND ua.user_id = :user_id
                       FOR SHARE
                   ) AS creator_has_acl
            FROM document_versions AS v
            JOIN documents AS d ON d.tenant_id = v.tenant_id AND d.id = v.document_id
            WHERE v.tenant_id = :tenant_id AND v.idempotency_key = :idempotency_key
            FOR UPDATE OF v, d
        """), {"tenant_id": str(tenant_id), "user_id": str(user_id),
               "idempotency_key": str(idempotency_key)}).mappings().first()
        if (row is None or row["owner_id"] != user_id or row["status"] != "active"
                or not row["creator_has_acl"] or row["sha256"] != prepared.sha256):
            raise IdempotencyConflict("上傳預約不存在或內容不符")

        key = row["storage_key"]
        ids = (tenant_id, row["document_id"], row["version_id"])
        exists = verify_stored_pdf(client, bucket, *ids, key,
                                   prepared.sha256, prepared.size)
        if row["storage_status"] == "stored" and not exists:
            raise StoredObjectMissing("已儲存的文件物件不存在")
        if not exists:
            try:
                store_prepared_pdf(client, bucket, *ids, prepared, key)
            except Exception:
                # 寫入可能已成功但回應遺失；對帳無法確認時保留待查狀態。
                if not verify_stored_pdf(client, bucket, *ids, key,
                                         prepared.sha256, prepared.size):
                    raise
            if not verify_stored_pdf(client, bucket, *ids, key,
                                     prepared.sha256, prepared.size):
                raise StoredObjectMissing("寫入後找不到文件物件")
        db.execute(text("""
            UPDATE document_versions SET storage_status = 'stored'
            WHERE tenant_id = :tenant_id AND id = :version_id
        """), {"tenant_id": str(tenant_id), "version_id": str(row["version_id"])})
        # 與儲存狀態同筆提交；重試不能建立第二份索引工作。
        db.execute(text("""
            INSERT INTO document_index_jobs (tenant_id, document_version_id)
            VALUES (:tenant_id, :version_id)
            ON CONFLICT (tenant_id, document_version_id) DO NOTHING
        """), {"tenant_id": str(tenant_id), "version_id": str(row["version_id"])})
        db.commit()
        return StoredPdf(key=key, sha256=prepared.sha256, size=prepared.size)
    except Exception:
        db.rollback()
        raise
