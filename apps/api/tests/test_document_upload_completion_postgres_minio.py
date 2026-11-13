"""以隔離 PostgreSQL 與 MinIO 驗證上傳對帳及狀態轉換。"""

from io import BytesIO
import os
from uuid import uuid4

import pytest
from minio import Minio
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db import engine
from src.document_uploads import (
    StoredObjectMissing, UploadForbidden, complete_document_upload,
    reserve_document_upload,
)
from src.object_storage import prepare_pdf

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1" or os.getenv("RUN_MINIO_TESTS") != "1",
    reason="需明確啟用隔離 PostgreSQL 與 MinIO 整合測試",
)


class AmbiguousPut:
    def __init__(self, client):
        self.client = client

    def get_object(self, **kwargs):
        return self.client.get_object(**kwargs)

    def put_object(self, **kwargs):
        self.client.put_object(**kwargs)
        raise TimeoutError("合成的寫入後回應遺失")


class FailedPut:
    def __init__(self, client):
        self.client = client

    def get_object(self, **kwargs):
        return self.client.get_object(**kwargs)

    def put_object(self, **kwargs):
        raise TimeoutError("合成的寫入前失敗")


def test_upload_completion_reconciles_ambiguous_results():
    client = Minio(os.environ["MINIO_ENDPOINT"],
                   access_key=os.environ["MINIO_ACCESS_KEY"],
                   secret_key=os.environ["MINIO_SECRET_KEY"], secure=False)
    bucket = os.environ["MINIO_BUCKET"]
    client.make_bucket(bucket)
    tenant_id, user_id = uuid4(), uuid4()
    prepared = prepare_pdf(BytesIO(b"%PDF-1.4\nsynthetic transaction\n%%EOF\n"))
    keys = []
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                connection.execute(text("""
                    INSERT INTO tenants (id, name) VALUES (:id, '合成上傳租戶')
                """), {"id": str(tenant_id)})
                connection.execute(text("""
                    INSERT INTO users (id, email, password_hash)
                    VALUES (:id, :email, 'synthetic-hash')
                """), {"id": str(user_id),
                       "email": f"{uuid4().hex}@example.invalid"})
                connection.execute(text("""
                    INSERT INTO memberships (tenant_id, user_id, role)
                    VALUES (:tenant_id, :user_id, 'staff')
                """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    first_key = uuid4()
                    first = reserve_document_upload(db, tenant_id, user_id,
                                                    "合成文件", first_key, prepared)
                    keys.append(first.storage_key)
                    stored = complete_document_upload(db, client, bucket, tenant_id,
                                                      user_id, first_key, prepared)
                    assert stored.key == first.storage_key
                    assert complete_document_upload(db, client, bucket, tenant_id,
                                                    user_id, first_key, prepared) == stored

                    connection.execute(text("""
                        UPDATE memberships SET role = 'viewer'
                        WHERE tenant_id = :tenant_id AND user_id = :user_id
                    """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})
                    with pytest.raises(UploadForbidden):
                        complete_document_upload(db, client, bucket, tenant_id,
                                                 user_id, first_key, prepared)
                    connection.execute(text("""
                        UPDATE memberships SET role = 'staff'
                        WHERE tenant_id = :tenant_id AND user_id = :user_id
                    """), {"tenant_id": str(tenant_id), "user_id": str(user_id)})

                    second_key = uuid4()
                    second = reserve_document_upload(db, tenant_id, user_id,
                                                     "第二份文件", second_key, prepared)
                    keys.append(second.storage_key)
                    result = complete_document_upload(db, AmbiguousPut(client), bucket,
                                                      tenant_id, user_id, second_key,
                                                      prepared)
                    assert result.key == second.storage_key

                    third_key = uuid4()
                    third = reserve_document_upload(db, tenant_id, user_id,
                                                    "第三份文件", third_key, prepared)
                    with pytest.raises(TimeoutError):
                        complete_document_upload(db, FailedPut(client), bucket,
                                                 tenant_id, user_id, third_key,
                                                 prepared)
                    assert connection.execute(text("""
                        SELECT storage_status FROM document_versions WHERE id = :id
                    """), {"id": str(third.version_id)}).scalar_one() == "pending_upload"

                    client.remove_object(bucket, first.storage_key)
                    keys.remove(first.storage_key)
                    with pytest.raises(StoredObjectMissing):
                        complete_document_upload(db, client, bucket, tenant_id,
                                                 user_id, first_key, prepared)
            finally:
                outer.rollback()
    finally:
        for key in keys:
            client.remove_object(bucket, key)
        client.remove_bucket(bucket)
