"""以隔離 PostgreSQL 與 MinIO 驗證上傳對帳及狀態轉換。"""

from io import BytesIO
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from minio import Minio
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db import engine
from src.auth import get_db, get_signing_key
from src import documents
from src.document_store import DocumentStore
from src.document_uploads import (
    StoredObjectMissing, UploadForbidden, complete_document_upload,
    reserve_document_upload,
)
from src.object_storage import prepare_pdf
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter

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


def test_upload_http_flow_persists_one_job_and_keeps_version_unpublished(monkeypatch):
    storage = Minio(os.environ["MINIO_ENDPOINT"],
                    access_key=os.environ["MINIO_ACCESS_KEY"],
                    secret_key=os.environ["MINIO_SECRET_KEY"], secure=False)
    bucket = f"upload-{uuid4().hex}"
    storage.make_bucket(bucket)
    tenant_id, user_id = uuid4(), uuid4()
    email = f"{uuid4().hex}@example.invalid"
    password = "synthetic-password-123"
    try:
        with engine.connect() as connection, connection.begin() as transaction:
            connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, '合成租戶')"),
                               {"id": tenant_id})
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :hash)
            """), {"id": user_id, "email": email, "hash": hash_password(password)})
            connection.execute(text("""
                INSERT INTO memberships (tenant_id, user_id, role)
                VALUES (:tenant, :user, 'staff')
            """), {"tenant": tenant_id, "user": user_id})

            def override_db():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    yield db

            class SyntheticLimiter:
                def allow(self, *_):
                    return True

            monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
            monkeypatch.setitem(app.dependency_overrides, get_signing_key,
                                lambda: "synthetic-test-only-" * 3)
            monkeypatch.setitem(app.dependency_overrides, get_login_limiter, SyntheticLimiter)
            monkeypatch.setattr(documents, "get_document_store",
                                lambda: DocumentStore(storage, bucket))
            with TestClient(app) as client:
                login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
                assert login.status_code == 200
                headers = {"Authorization": f"Bearer {login.json()['access_token']}",
                           "X-Tenant-ID": str(tenant_id), "Idempotency-Key": str(uuid4())}
                path = "/api/v1/documents"
                files = {"file": ("sop.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")}
                accepted = client.post(path, headers=headers, files=files, data={"title": "SOP"})
                assert accepted.status_code == 202, accepted.text
                retry = client.post(path, headers=headers, files=files, data={"title": "SOP"})
                assert retry.status_code == 202
                assert retry.json() == accepted.json()
                conflict = client.post(path, headers=headers, files=files, data={"title": "另一份"})
                assert conflict.status_code == 409
                document_id = accepted.json()["document_id"]
                status = client.get(f"{path}/{document_id}/status", headers=headers)
                assert status.status_code == 200
                assert status.json()["storage_status"] == "stored"
                assert status.json()["current_version"] is None
                assert connection.execute(text("""
                    SELECT status FROM document_index_jobs WHERE document_version_id = :version
                """), {"version": accepted.json()["version_id"]}).scalar_one() == "pending"
                connection.execute(text("DELETE FROM document_user_acl WHERE document_id = :id"),
                                   {"id": document_id})
                revoked = client.post(path, headers=headers, files=files, data={"title": "SOP"})
                assert revoked.status_code == 409
            transaction.rollback()
    finally:
        for item in storage.list_objects(bucket, recursive=True):
            storage.remove_object(bucket, item.object_name)
        storage.remove_bucket(bucket)


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
                    assert connection.execute(text("""
                        SELECT count(*) FROM document_index_jobs
                        WHERE tenant_id = :tenant_id AND document_version_id = :id
                    """), {"tenant_id": str(tenant_id),
                           "id": str(first.version_id)}).scalar_one() == 1

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
                    assert connection.execute(text("""
                        SELECT count(*) FROM document_index_jobs
                        WHERE tenant_id = :tenant_id AND document_version_id = :id
                    """), {"tenant_id": str(tenant_id),
                           "id": str(second.version_id)}).scalar_one() == 1

                    third_key = uuid4()
                    third = reserve_document_upload(db, tenant_id, user_id,
                                                    "第三份文件", third_key, prepared)
                    with pytest.raises(TimeoutError):
                        complete_document_upload(db, FailedPut(client), bucket,
                                                 tenant_id, user_id, third_key,
                                                 prepared)
                    assert connection.execute(text("""
                        SELECT storage_status FROM document_versions WHERE id = :id
                    """), {"id": str(third.version_id)}).scalar_one() == "failed"
                    assert connection.execute(text("""
                        SELECT count(*) FROM document_index_jobs
                        WHERE tenant_id = :tenant_id AND document_version_id = :id
                    """), {"tenant_id": str(tenant_id),
                           "id": str(third.version_id)}).scalar_one() == 0
                    keys.append(third.storage_key)
                    recovered = complete_document_upload(db, client, bucket, tenant_id,
                                                         user_id, third_key, prepared)
                    assert recovered.key == third.storage_key
                    assert connection.execute(text("""
                        SELECT storage_status FROM document_versions WHERE id = :id
                    """), {"id": str(third.version_id)}).scalar_one() == "stored"
                    assert connection.execute(text("""
                        SELECT count(*) FROM document_index_jobs
                        WHERE tenant_id = :tenant_id AND document_version_id = :id
                    """), {"tenant_id": str(tenant_id),
                           "id": str(third.version_id)}).scalar_one() == 1

                    client.remove_object(bucket, first.storage_key)
                    keys.remove(first.storage_key)
                    with pytest.raises(StoredObjectMissing):
                        complete_document_upload(db, client, bucket, tenant_id,
                                                 user_id, first_key, prepared)
                    assert connection.execute(text("""
                        SELECT storage_status FROM document_versions WHERE id = :id
                    """), {"id": str(first.version_id)}).scalar_one() == "stored"
                    assert connection.execute(text("""
                        SELECT count(*) FROM document_index_jobs
                        WHERE tenant_id = :tenant_id AND document_version_id = :id
                    """), {"tenant_id": str(tenant_id),
                           "id": str(first.version_id)}).scalar_one() == 1
            finally:
                outer.rollback()
    finally:
        for key in keys:
            client.remove_object(bucket, key)
        client.remove_bucket(bucket)


@pytest.mark.parametrize("commit_happened", [False, True], ids=["before-commit", "after-commit"])
def test_upload_commit_error_recovers_same_version_and_one_job(monkeypatch, commit_happened):
    """資料庫提交前失敗或提交後回應遺失，都須以同鍵重新對帳。"""
    client = Minio(os.environ["MINIO_ENDPOINT"],
                   access_key=os.environ["MINIO_ACCESS_KEY"],
                   secret_key=os.environ["MINIO_SECRET_KEY"], secure=False)
    bucket = f"commit-{uuid4().hex}"
    client.make_bucket(bucket)
    tenant_id, user_id, request_key = uuid4(), uuid4(), uuid4()
    prepared = prepare_pdf(BytesIO(b"%PDF-1.4\nsynthetic commit failure\n%%EOF\n"))
    key = None
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, '合成租戶')"),
                               {"id": str(tenant_id)})
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, 'synthetic-hash')
            """), {"id": str(user_id), "email": f"{uuid4().hex}@example.invalid"})
            connection.execute(text("""
                INSERT INTO memberships (tenant_id, user_id, role)
                VALUES (:tenant, :user, 'staff')
            """), {"tenant": str(tenant_id), "user": str(user_id)})
        with engine.connect() as first, engine.connect() as retry:
            assert first.execute(text("SELECT pg_backend_pid()")).scalar_one() != retry.execute(
                text("SELECT pg_backend_pid()")
            ).scalar_one()
            first.commit()
            retry.commit()
            with Session(bind=first) as db:
                reservation = reserve_document_upload(db, tenant_id, user_id, "合成文件",
                                                      request_key, prepared)
                key = reservation.storage_key
                commit = db.commit

                def interrupted_commit():
                    if commit_happened:
                        commit()
                    raise TimeoutError("合成的資料庫提交回應中斷")

                with monkeypatch.context() as fault:
                    fault.setattr(db, "commit", interrupted_commit)
                    with pytest.raises(TimeoutError):
                        complete_document_upload(db, client, bucket, tenant_id, user_id,
                                                 request_key, prepared)

            with Session(bind=retry) as db:
                before_retry = db.execute(text("""
                    SELECT storage_status FROM document_versions WHERE id = :id
                """), {"id": str(reservation.version_id)}).scalar_one()
                assert before_retry == ("stored" if commit_happened else "pending_upload")
                same = reserve_document_upload(db, tenant_id, user_id, "合成文件",
                                               request_key, prepared)
                assert (same.document_id, same.version_id) == (reservation.document_id,
                                                               reservation.version_id)
                result = complete_document_upload(db, client, bucket, tenant_id, user_id,
                                                  request_key, prepared)
                assert result.key == key
                assert db.execute(text("""
                    SELECT storage_status FROM document_versions WHERE id = :id
                """), {"id": str(reservation.version_id)}).scalar_one() == "stored"
                assert db.execute(text("""
                    SELECT count(*) FROM document_index_jobs
                    WHERE tenant_id = :tenant AND document_version_id = :version
                """), {"tenant": str(tenant_id),
                       "version": str(reservation.version_id)}).scalar_one() == 1
    finally:
        with engine.begin() as cleanup:
            params = {"tenant": str(tenant_id), "user": str(user_id)}
            cleanup.execute(text("DELETE FROM document_index_jobs WHERE tenant_id = :tenant"), params)
            cleanup.execute(text("DELETE FROM document_user_acl WHERE tenant_id = :tenant"), params)
            cleanup.execute(text("DELETE FROM document_versions WHERE tenant_id = :tenant"), params)
            cleanup.execute(text("DELETE FROM documents WHERE tenant_id = :tenant"), params)
            cleanup.execute(text("DELETE FROM memberships WHERE tenant_id = :tenant AND user_id = :user"), params)
            cleanup.execute(text("DELETE FROM tenants WHERE id = :tenant"), params)
            cleanup.execute(text("DELETE FROM users WHERE id = :user"), params)
        if key is not None:
            client.remove_object(bucket, key)
        client.remove_bucket(bucket)
