"""以受控物件鍵儲存有限大小的原始 PDF；解析與掃描另行處理。"""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO
from uuid import UUID, uuid4

from minio import Minio

MAX_PDF_BYTES = 10 * 1024 * 1024
_READ_BYTES = 64 * 1024


class InvalidPdf(ValueError):
    """輸入不是具 PDF 檔頭的原始文件。"""


class PdfTooLarge(ValueError):
    """原始文件超過目前允許的大小。"""


class InvalidObjectKey(ValueError):
    """預留的物件鍵與文件版本不符。"""


@dataclass(frozen=True)
class StoredPdf:
    key: str
    sha256: str
    size: int


def reserve_pdf_key(tenant_id: UUID, document_id: UUID, version_id: UUID) -> str:
    """在資料庫交易前產生不含使用者檔名的版本物件鍵。"""
    return f"{tenant_id}/{document_id}/{version_id}/{uuid4()}.pdf"


def store_pdf(
    client: Minio,
    bucket: str,
    tenant_id: UUID,
    document_id: UUID,
    version_id: UUID,
    stream: BinaryIO,
    *,
    reserved_key: str | None = None,
) -> StoredPdf:
    """讀取最多 10 MiB，使用預留或新產生的物件鍵寫入既有私有 Bucket。"""
    key = (reserve_pdf_key(tenant_id, document_id, version_id)
           if reserved_key is None else reserved_key)
    prefix = f"{tenant_id}/{document_id}/{version_id}/"
    if (not key.startswith(prefix) or len(key) != len(prefix) + 40
            or not key.endswith(".pdf")):
        raise InvalidObjectKey("物件鍵與文件版本不符")
    try:
        if str(UUID(key[len(prefix):-4])) != key[len(prefix):-4]:
            raise ValueError("非標準 UUID")
    except ValueError as exc:
        raise InvalidObjectKey("物件鍵格式不正確") from exc
    data = bytearray()
    while chunk := stream.read(min(_READ_BYTES, MAX_PDF_BYTES + 1 - len(data))):
        data.extend(chunk)
        if len(data) > MAX_PDF_BYTES:
            raise PdfTooLarge("PDF 超過大小限制")
    if not data.startswith(b"%PDF-"):
        raise InvalidPdf("檔案格式不符 PDF")

    client.put_object(
        bucket_name=bucket,
        object_name=key,
        data=BytesIO(data),
        length=len(data),
        content_type="application/pdf",
    )
    return StoredPdf(key=key, sha256=sha256(data).hexdigest(), size=len(data))
