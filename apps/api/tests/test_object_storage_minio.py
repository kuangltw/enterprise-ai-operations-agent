"""以隔離 MinIO 驗證原始 PDF 儲存及大小限制。"""

from io import BytesIO
import os
from uuid import uuid4

import pytest
from minio import Minio
from minio.error import S3Error

from src.object_storage import (
    MAX_PDF_BYTES, InvalidObjectKey, InvalidPdf, PdfTooLarge,
    StoredPdfMismatch, reserve_pdf_key, store_pdf, verify_stored_pdf,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MINIO_TESTS") != "1", reason="需明確啟用隔離 MinIO 整合測試",
)


def test_store_pdf_uses_generated_key_and_enforces_size():
    client = Minio(
        endpoint=os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )
    bucket = os.environ["MINIO_BUCKET"]
    client.make_bucket(bucket_name=bucket)
    tenant_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    payload = b"%PDF-1.4\nsynthetic test only\n%%EOF\n"

    reserved_key = reserve_pdf_key(tenant_id, document_id, version_id)
    stored = store_pdf(client, bucket, tenant_id, document_id, version_id,
                       BytesIO(payload), reserved_key=reserved_key)
    assert stored.key == reserved_key
    assert stored.key.startswith(f"{tenant_id}/{document_id}/{version_id}/")
    assert stored.key.endswith(".pdf")
    assert stored.size == len(payload)
    assert len(stored.sha256) == 64
    assert verify_stored_pdf(client, bucket, tenant_id, document_id, version_id,
                             stored.key, stored.sha256, stored.size)
    with pytest.raises(StoredPdfMismatch):
        verify_stored_pdf(client, bucket, tenant_id, document_id, version_id,
                          stored.key, "0" * 64, stored.size)
    with pytest.raises(InvalidObjectKey):
        verify_stored_pdf(client, bucket, tenant_id, document_id, uuid4(),
                          stored.key, stored.sha256, stored.size)
    response = client.get_object(bucket_name=bucket, object_name=stored.key)
    try:
        assert response.read() == payload
    finally:
        response.close()
        response.release_conn()

    with pytest.raises(InvalidPdf):
        store_pdf(client, bucket, tenant_id, document_id, uuid4(),
                  BytesIO(b"not a PDF"))
    with pytest.raises(InvalidObjectKey):
        store_pdf(client, bucket, tenant_id, document_id, uuid4(),
                  BytesIO(payload), reserved_key=reserved_key)
    with pytest.raises(InvalidObjectKey):
        store_pdf(client, bucket, tenant_id, document_id, version_id,
                  BytesIO(payload), reserved_key=reserved_key.replace(".pdf", "/x.pdf"))
    with pytest.raises(InvalidObjectKey):
        store_pdf(client, bucket, tenant_id, document_id, version_id,
                  BytesIO(payload), reserved_key="")
    with pytest.raises(PdfTooLarge):
        store_pdf(client, bucket, tenant_id, document_id, uuid4(),
                  BytesIO(b"%PDF-" + b"x" * MAX_PDF_BYTES))

    client.remove_object(bucket_name=bucket, object_name=stored.key)
    with pytest.raises(S3Error) as error:
        client.stat_object(bucket_name=bucket, object_name=stored.key)
    assert error.value.code == "NoSuchKey"
    assert not verify_stored_pdf(client, bucket, tenant_id, document_id, version_id,
                                 stored.key, stored.sha256, stored.size)
