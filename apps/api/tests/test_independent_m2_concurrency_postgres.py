"""獨立驗證預覽快照與退役表降版鎖；僅用隔離 PostgreSQL。"""

from datetime import timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from src.db import engine
from src.document_cleanup_preview import preview_upload_cleanup

pytestmark = pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需隔離 PostgreSQL")


@pytest.fixture
def committed_version():
    tenant, user, document, version = (uuid4() for _ in range(4))
    key = f"{tenant}/{document}/{version}/{uuid4()}.pdf"
    params = {"tenant": tenant, "user": user, "document": document, "version": version,
              "key": key, "email": f"{uuid4().hex}@example.invalid", "request": uuid4()}
    with engine.begin() as c:
        c.execute(text("INSERT INTO tenants (id,name) VALUES (:tenant,'合成租戶')"), params)
        c.execute(text("INSERT INTO users (id,email,password_hash) VALUES (:user,:email,'synthetic')"), params)
        c.execute(text("INSERT INTO documents (id,tenant_id,title,owner_id) VALUES (:document,:tenant,'合成文件',:user)"), params)
        c.execute(text("""INSERT INTO document_versions
            (id,tenant_id,document_id,version,storage_key,sha256,idempotency_key,created_at)
            VALUES (:version,:tenant,:document,1,:key,:sha,:request,now()-interval '3 days')"""), {**params, "sha": "a" * 64})
    try:
        yield params
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM document_upload_retired_keys WHERE tenant_id=:tenant"), params)
            c.execute(text("DELETE FROM document_versions WHERE tenant_id=:tenant"), params)
            c.execute(text("DELETE FROM documents WHERE tenant_id=:tenant"), params)
            c.execute(text("DELETE FROM tenants WHERE id=:tenant"), params)
            c.execute(text("DELETE FROM users WHERE id=:user"), params)


def test_preview_sees_committed_pending_during_locked_update_then_excludes_stored(committed_version):
    p = committed_version
    with engine.connect() as writer, engine.connect() as reader:
        tx = writer.begin()
        writer.execute(text("UPDATE document_versions SET storage_status='stored' WHERE id=:version"), p)
        with Session(bind=reader) as db:
            db.execute(text("SET LOCAL statement_timeout='2s'"))
            rows = preview_upload_cleanup(db, p["tenant"], minimum_age=timedelta(days=1))
            assert p["version"] in [row.version_id for row in rows]
            db.commit()
            tx.commit()
            assert p["version"] not in [row.version_id for row in preview_upload_cleanup(
                db, p["tenant"], minimum_age=timedelta(days=1))]


def test_downgrade_exclusive_lock_waits_for_uncommitted_retired_insert(committed_version):
    p = committed_version
    retired_key = f"{p['tenant']}/{p['document']}/{p['version']}/{uuid4()}.pdf"
    with engine.connect() as writer, engine.connect() as downgrader:
        tx = writer.begin()
        writer.execute(text("""INSERT INTO document_upload_retired_keys
            (storage_key,tenant_id,document_id,document_version_id)
            VALUES (:key,:tenant,:document,:version)"""), {**p, "key": retired_key})
        with pytest.raises(DBAPIError) as exc:
            with downgrader.begin():
                downgrader.execute(text("SET LOCAL lock_timeout='300ms'"))
                downgrader.execute(text("LOCK TABLE document_upload_retired_keys IN ACCESS EXCLUSIVE MODE"))
        assert exc.value.orig.sqlstate == "55P03"
        tx.commit()
        with downgrader.begin():
            assert downgrader.execute(text("SELECT count(*) FROM document_upload_retired_keys WHERE storage_key=:key"), {"key": retired_key}).scalar_one() == 1
