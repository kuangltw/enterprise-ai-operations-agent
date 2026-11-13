"""供可信任操作員盤點未完成上傳；此預覽不授權刪除任何物件。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class UploadCleanupCandidate:
    """某次查詢快照中的候選識別，不包含物件鍵或文件內容。"""

    document_id: UUID
    version_id: UUID
    storage_status: str
    created_at: datetime


def preview_upload_cleanup(db: Session, tenant_id: UUID, *,
                           minimum_age: timedelta, limit: int = 100
                           ) -> list[UploadCleanupCandidate]:
    """唯讀預覽指定租戶的舊預約，供已受信任的內部操作員使用。

    至少年齡為 24 小時，筆數限制為 1 至 100。查詢不執行授權，呼叫者
    必須先確保操作員及租戶範圍可信。建立時間不是最後上傳時間，結果
    可能包含正在進行的工作，也不證明物件存在或可被刪除。未鎖定資料列；
    未來任何清理都必須在版本鎖下重新驗證並先永久退役舊鍵。
    """
    if not isinstance(tenant_id, UUID):
        raise ValueError("須指定有效租戶識別")
    if not isinstance(minimum_age, timedelta) or minimum_age < timedelta(hours=24):
        raise ValueError("預覽年齡須至少為 24 小時")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("預覽筆數須介於 1 至 100")

    # 單一快照過濾租戶、版本與狀態；跨租戶撞鍵只排除，不洩漏其他租戶。
    rows = db.execute(text("""
        SELECT v.document_id, v.id AS version_id, v.storage_status, v.created_at
        FROM document_versions AS v
        JOIN documents AS d ON d.tenant_id = v.tenant_id AND d.id = v.document_id
        WHERE v.tenant_id = :tenant_id AND d.status = 'active'
          AND v.idempotency_key IS NOT NULL
          AND v.storage_status IN ('pending_upload', 'failed')
          AND v.indexing_status = 'pending'
          AND d.current_version IS DISTINCT FROM v.version
          AND v.created_at <= statement_timestamp() - :minimum_age
          AND v.storage_key ~ ('^' || CAST(v.tenant_id AS text) || '/' ||
              CAST(v.document_id AS text) || '/' || CAST(v.id AS text) ||
              '/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.pdf$')
          AND NOT EXISTS (
              SELECT 1 FROM document_index_jobs AS j
              WHERE j.tenant_id = v.tenant_id AND j.document_version_id = v.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM document_upload_retired_keys AS r
              WHERE r.storage_key = v.storage_key
          )
          AND NOT EXISTS (
              SELECT 1 FROM document_versions AS other
              WHERE other.storage_key = v.storage_key AND other.id <> v.id
          )
        ORDER BY v.created_at, v.id
        LIMIT :limit
    """), {"tenant_id": tenant_id, "minimum_age": minimum_age, "limit": limit})
    return [UploadCleanupCandidate(**row) for row in rows.mappings()]
