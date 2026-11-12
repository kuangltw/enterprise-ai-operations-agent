"""以受控物件鍵儲存有限大小的原始 PDF；解析與掃描另行處理。"""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO
from uuid import UUID, uuid4

from minio import Minio
from minio.error import S3Error

MAX_PDF_BYTES = 10 * 1024 * 1024
_READ_BYTES = 64 * 1024


class InvalidPdf(ValueError):
    """輸入不是具 PDF 檔頭的原始文件。"""


class PdfTooLarge(ValueError):
    """原始文件超過目前允許的大小。"""


class InvalidObjectKey(ValueError):
    """預留的物件鍵與文件版本不符。"""


class StoredPdfMismatch(ValueError):
    """既有物件與預期的 PDF 摘要或大小不同。"""


@dataclass(frozen=True)
class StoredPdf:
    key: str
    sha256: str
    size: int


@dataclass(frozen=True)
class PreparedPdf:
    data: bytes
    sha256: str
    size: int


def reserve_pdf_key(tenant_id: UUID, document_id: UUID, version_id: UUID) -> str:
    """在資料庫交易前產生不含使用者檔名的版本物件鍵。"""
    return f"{tenant_id}/{document_id}/{version_id}/{uuid4()}.pdf"


def _validate_key(key: str, tenant_id: UUID, document_id: UUID,
                  version_id: UUID) -> None:
    prefix = f"{tenant_id}/{document_id}/{version_id}/"
    if (not key.startswith(prefix) or len(key) != len(prefix) + 40
            or not key.endswith(".pdf")):
        raise InvalidObjectKey("物件鍵與文件版本不符")
    try:
        if str(UUID(key[len(prefix):-4])) != key[len(prefix):-4]:
            raise ValueError("非標準 UUID")
    except ValueError as exc:
        raise InvalidObjectKey("物件鍵格式不正確") from exc


def verify_stored_pdf(client: Minio, bucket: str, tenant_id: UUID,
                      document_id: UUID, version_id: UUID, key: str,
                      expected_sha256: str, expected_size: int) -> bool:
    """寫入結果不明時讀回物件核對；不存在回 False，內容不符則拒絕。"""
    _validate_key(key, tenant_id, document_id, version_id)
    if expected_size < 0 or expected_size > MAX_PDF_BYTES:
        raise ValueError("預期大小超出 PDF 限制")
    try:
        response = client.get_object(bucket_name=bucket, object_name=key)
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            return False
        raise
    try:
        data = response.read(expected_size + 1)
        if len(data) != expected_size or sha256(data).hexdigest() != expected_sha256:
            raise StoredPdfMismatch("物件內容與預期不符")
        return True
    finally:
        response.close()
        response.release_conn()


def prepare_pdf(stream: BinaryIO) -> PreparedPdf:
    """在資料庫交易前限制大小、檢查檔頭並計算原始檔摘要。"""
    data = bytearray()
    while chunk := stream.read(min(_READ_BYTES, MAX_PDF_BYTES + 1 - len(data))):
        data.extend(chunk)
        if len(data) > MAX_PDF_BYTES:
            raise PdfTooLarge("PDF 超過大小限制")
    if not data.startswith(b"%PDF-"):
        raise InvalidPdf("檔案格式不符 PDF")
    payload = bytes(data)
    return PreparedPdf(data=payload, sha256=sha256(payload).hexdigest(),
                       size=len(payload))


def store_prepared_pdf(client: Minio, bucket: str, tenant_id: UUID,
                       document_id: UUID, version_id: UUID,
                       prepared: PreparedPdf, reserved_key: str) -> StoredPdf:
    """將已驗證的 PDF 寫入私有 Bucket，保留原先產生的鍵。"""
    _validate_key(reserved_key, tenant_id, document_id, version_id)
    if len(prepared.data) > MAX_PDF_BYTES:
        raise PdfTooLarge("PDF 超過大小限制")
    if not prepared.data.startswith(b"%PDF-"):
        raise InvalidPdf("檔案格式不符 PDF")
    if (prepared.size != len(prepared.data)
            or prepared.sha256 != sha256(prepared.data).hexdigest()):
        raise ValueError("PDF 摘要或大小不一致")
    client.put_object(
        bucket_name=bucket,
        object_name=reserved_key,
        data=BytesIO(prepared.data),
        length=prepared.size,
        content_type="application/pdf",
    )
    return StoredPdf(key=reserved_key, sha256=prepared.sha256, size=prepared.size)


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
    _validate_key(key, tenant_id, document_id, version_id)
    return store_prepared_pdf(client, bucket, tenant_id, document_id, version_id,
                              prepare_pdf(stream), key)
