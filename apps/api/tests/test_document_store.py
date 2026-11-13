"""文件儲存連線設定須失敗封閉且不需要網路即可驗證。"""

import pytest
from minio import Minio

from src.document_store import DocumentStoreUnavailable, get_document_store
from src.settings import Settings


def config(**overrides):
    values = {
        "database_url": "sqlite:///synthetic",
        "minio_endpoint": None,
        "minio_access_key": None,
        "minio_secret_key": None,
        "minio_bucket": None,
        "minio_secure": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_missing_scoped_credentials_rejects_document_store():
    with pytest.raises(DocumentStoreUnavailable):
        get_document_store(config(minio_endpoint="minio:9000",
                                  minio_bucket="documents"))
    with pytest.raises(DocumentStoreUnavailable):
        get_document_store(config(minio_endpoint="minio:9000",
                                  minio_access_key="synthetic-user",
                                  minio_secret_key=" ", minio_bucket="documents"))


def test_plaintext_document_store_rejects_external_endpoint():
    with pytest.raises(DocumentStoreUnavailable):
        get_document_store(config(minio_endpoint="storage.example.invalid:9000",
                                  minio_access_key="synthetic-user",
                                  minio_secret_key="synthetic-secret",
                                  minio_bucket="documents", minio_secure=False))


def test_internal_document_store_uses_explicit_bucket_and_credentials():
    store = get_document_store(config(minio_endpoint="minio:9000",
                                      minio_access_key="synthetic-user",
                                      minio_secret_key="synthetic-secret",
                                      minio_bucket="documents", minio_secure=False))
    assert isinstance(store.client, Minio)
    assert store.bucket == "documents"
