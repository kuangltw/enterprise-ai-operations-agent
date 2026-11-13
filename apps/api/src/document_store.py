"""文件原始檔儲存連線邊界。

API 只接受明確提供的 Bucket 與受限憑證；缺少設定時失敗封閉。
MinIO Root 憑證不得注入 API，Bucket 的私有政策須在部署時建立。
"""

from dataclasses import dataclass

from minio import Minio
from urllib3 import PoolManager, Timeout

from .settings import Settings, settings


class DocumentStoreUnavailable(RuntimeError):
    """文件儲存設定不完整或不符合本機明文連線限制。"""


@dataclass(frozen=True)
class DocumentStore:
    """已設定的 MinIO Client 與預期由部署作業設為私有的 Bucket 名稱。"""

    client: Minio
    bucket: str


def get_document_store(config: Settings = settings) -> DocumentStore:
    """建立文件儲存 Client；缺少受限憑證或非本機明文連線時拒絕。

    此函式不建立 Bucket、不變更政策，亦不測試遠端可用性；呼叫端須將
    連線錯誤視為上傳未確認狀態並依冪等鍵對帳，不能盲目重試寫入。
    """
    endpoint = config.minio_endpoint
    access_key = config.minio_access_key
    secret_key = config.minio_secret_key
    bucket = config.minio_bucket
    if not all(value and value.strip() for value in (
        endpoint, access_key, secret_key, bucket,
    )):
        raise DocumentStoreUnavailable("文件儲存設定不完整")
    if not config.minio_secure and endpoint.split(":", 1)[0] not in {
        "minio", "localhost", "127.0.0.1",
    }:
        raise DocumentStoreUnavailable("非本機 MinIO 連線必須使用 TLS")
    try:
        client = Minio(endpoint, access_key=access_key,
                       secret_key=secret_key, secure=config.minio_secure,
                       # 上傳交易持有資料庫鎖；寫入結果由應用層對帳。
                       http_client=PoolManager(timeout=Timeout(connect=2, read=5),
                                               retries=False))
    except ValueError as exc:
        raise DocumentStoreUnavailable("文件儲存端點格式不正確") from exc
    return DocumentStore(client, bucket)
