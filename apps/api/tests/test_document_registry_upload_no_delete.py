"""在一次性 PostgreSQL／MinIO 驗證上傳及 ACL，不執行物件刪除。"""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from minio import Minio
from sqlalchemy import text
from sqlalchemy.orm import Session

from src import documents
from src.auth import get_db, get_signing_key
from src.db import engine
from src.document_store import DocumentStore
from src.main import app
from src.passwords import hash_password
from src.rate_limit import get_login_limiter

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REGISTRY_UPLOAD_ISOLATED_TESTS") != "1",
    reason="需要明確啟用一次性 PostgreSQL／MinIO；測試物件不刪除",
)


def test_pdf_upload_retry_and_acl_revocation_with_registry(monkeypatch):
    storage = Minio(os.environ["MINIO_ENDPOINT"], access_key=os.environ["MINIO_ACCESS_KEY"],
                    secret_key=os.environ["MINIO_SECRET_KEY"], secure=False)
    bucket = f"registry-{uuid4().hex}"
    storage.make_bucket(bucket)
    tenant, user = uuid4(), uuid4()
    email, password = f"{uuid4().hex}@example.invalid", "synthetic-password-123"
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, '合成租戶')"), {"id": tenant})
        connection.execute(text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :hash)"),
                           {"id": user, "email": email, "hash": hash_password(password)})
        connection.execute(text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:tenant, :user, 'staff')"),
                           {"tenant": tenant, "user": user})

        def override_db():
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db

        class SyntheticLimiter:
            def allow(self, *_):
                return True

        monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
        monkeypatch.setitem(app.dependency_overrides, get_signing_key, lambda: "synthetic-test-only-" * 3)
        monkeypatch.setitem(app.dependency_overrides, get_login_limiter, SyntheticLimiter)
        monkeypatch.setattr(documents, "get_document_store", lambda: DocumentStore(storage, bucket))
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}",
                       "X-Tenant-ID": str(tenant), "Idempotency-Key": str(uuid4())}
            files = {"file": ("sop.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")}
            accepted = client.post("/api/v1/documents", headers=headers, files=files, data={"title": "SOP"})
            assert accepted.status_code == 202, accepted.text
            retry = client.post("/api/v1/documents", headers=headers, files=files, data={"title": "SOP"})
            assert retry.status_code == 202 and retry.json() == accepted.json()
            version, document = accepted.json()["version_id"], accepted.json()["document_id"]
            assert connection.execute(text("""
                SELECT count(*) FROM document_storage_keys k
                JOIN document_versions v ON v.id=k.document_version_id AND v.storage_key=k.storage_key
                WHERE v.id=:version AND k.state='live' AND v.storage_status='stored'
            """), {"version": version}).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM document_index_jobs WHERE document_version_id=:version"),
                                      {"version": version}).scalar_one() == 1
            connection.execute(text("DELETE FROM document_user_acl WHERE document_id=:id"), {"id": document})
            revoked = client.post("/api/v1/documents", headers=headers, files=files, data={"title": "SOP"})
            assert revoked.status_code == 409
        transaction.rollback()
