"""文件上傳的 HTTP 契約與請求邊界。"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src import documents
from src.auth import get_db, get_signing_key
from src.document_store import DocumentStoreUnavailable
from src.main import app
from src.tenant_context import TenantContext, get_tenant_context

PATH = "/api/v1/documents"


@pytest.fixture
def upload_client(monkeypatch):
    tenant_id, user_id = uuid4(), uuid4()
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: None)
    monkeypatch.setitem(app.dependency_overrides, get_tenant_context,
                        lambda: TenantContext(tenant_id, user_id, "合成租戶", "staff"))

    def unavailable():
        raise DocumentStoreUnavailable("合成測試環境無儲存設定")

    monkeypatch.setattr(documents, "get_document_store", unavailable)
    with TestClient(app) as client:
        yield client, {"Idempotency-Key": str(uuid4())}


def test_upload_openapi_declares_multipart_and_security():
    schema = app.openapi()["paths"][PATH]["post"]
    assert set(schema["requestBody"]["content"]) == {"multipart/form-data"}
    assert {p["name"] for p in schema["parameters"]} == {"X-Tenant-ID", "Idempotency-Key"}
    assert {"HTTPBearer": []} in schema["security"]
    assert {"202", "401", "403", "404", "409", "413", "415", "422", "503"} <= schema["responses"].keys()


def test_upload_requires_authentication_before_parsing(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_signing_key,
                        lambda: "synthetic-test-only-" * 3)
    with TestClient(app) as client:
        response = client.post(PATH, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 401


@pytest.mark.parametrize(("fields", "filename", "payload", "expected"), [
    ({}, "sop.pdf", b"%PDF-1.4", 422),
    ({"title": "  "}, "sop.pdf", b"%PDF-1.4", 422),
    ({"title": "SOP"}, "sop.pdf", b"not a PDF", 415),
    ({"title": "SOP"}, "sop.pdf", b"%PDF-1.4", 503),
])
def test_upload_rejects_invalid_input_or_unconfigured_store(
    upload_client, fields, filename, payload, expected,
):
    client, headers = upload_client
    response = client.post(PATH, headers=headers, data=fields,
                           files={"file": (filename, payload, "application/pdf")})
    assert response.status_code == expected
    assert set(response.json()["error"]) == {"code", "message", "details", "trace_id"}


def test_upload_rejects_oversized_stream_without_content_length(upload_client, monkeypatch):
    client, headers = upload_client
    monkeypatch.setattr(documents, "_MAX_UPLOAD_BODY", 8)
    response = client.post(PATH, headers={
        **headers, "Content-Type": "multipart/form-data; boundary=upload",
    }, content=iter([b"12345", b"67890"]))
    assert response.status_code == 413
