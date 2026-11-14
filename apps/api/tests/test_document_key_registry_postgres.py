"""正式 Storage Key Registry 的 PostgreSQL 不變條件（僅限隔離資料庫）。

測試含真實提交及並行交易，會保留合成資料，必須使用一次性的隔離資料庫。
不呼叫物件儲存服務。
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from queue import Queue
from time import monotonic, sleep
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from src.db import engine
from src.document_cleanup_preview import preview_upload_cleanup

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_KEY_REGISTRY_ISOLATED_TESTS") != "1",
    reason="需要明確啟用一次性隔離 PostgreSQL 測試",
)


def _rejected(connection, sql, parameters, expected=None):
    """限接受約束或明確防護失敗，缺欄位等環境錯誤不能算通過。"""
    with pytest.raises(DBAPIError) as caught:
        with connection.begin_nested():
            connection.execute(text(sql), parameters)
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    code = getattr(caught.value.orig, "sqlstate", None) or getattr(
        caught.value.orig, "pgcode", None
    )
    assert code in (expected or {"23503", "23505", "23514", "23502", "P0001", "55000"}), code


@pytest.fixture
def versions():
    """以獨立提交建立兩租戶；不得在持久或共用資料庫執行。"""
    owner = uuid4()
    records = []
    with engine.begin() as db:
        db.execute(text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'synthetic-hash')"),
                   {"id": owner, "email": f"{uuid4().hex}@example.invalid"})
        for _ in range(2):
            tenant, document, version, generation = (uuid4() for _ in range(4))
            key = f"{tenant}/{document}/{version}/{generation}.pdf"
            db.execute(text("INSERT INTO tenants (id, name) VALUES (:id, '合成租戶')"), {"id": tenant})
            db.execute(text("INSERT INTO documents (id, tenant_id, title, owner_id) VALUES (:id, :tenant, '合成文件', :owner)"),
                       {"id": document, "tenant": tenant, "owner": owner})
            db.execute(text("""
                INSERT INTO document_versions (id, tenant_id, document_id, version, storage_key, sha256)
                VALUES (:id, :tenant, :document, 1, :key, :sha)
            """), {"id": version, "tenant": tenant, "document": document,
                   "key": key, "sha": "a" * 64})
            records.append({"tenant": tenant, "document": document, "version": version,
                            "generation": generation, "key": key})
    with engine.connect() as db:
        for item in records:
            row = db.execute(text("""
                SELECT namespace, tenant_id, document_id, document_version_id, generation, state
                FROM document_storage_keys WHERE storage_key = :key
            """), item).mappings().one()
            assert (row["tenant_id"], row["document_id"], row["document_version_id"],
                    row["generation"], row["state"]) == (
                        item["tenant"], item["document"], item["version"], item["generation"], "live")
            item["namespace"] = row["namespace"]
    return records


def _new_key(item):
    generation = uuid4()
    return {**item, "generation": generation,
            "key": f"{item['tenant']}/{item['document']}/{item['version']}/{generation}.pdf"}


_INSERT = """
    INSERT INTO document_storage_keys
      (namespace, storage_key, tenant_id, document_id, document_version_id, generation, state)
    VALUES (:namespace, :key, :tenant, :document, :version, :generation, 'live')
"""


def test_live_registration_and_cross_owner_identity_are_enforced(versions):
    a, b = versions
    with engine.connect() as db, db.begin():
        # 鍵須符合偽造的 owner，確保拒絕來自複合外鍵而非格式 CHECK。
        for mismatched in ({**a, "tenant": b["tenant"]},
                           {**a, "document": b["document"]},
                           {**a, "version": b["version"]}):
            _rejected(db, _INSERT, _new_key(mismatched), {"23503"})
        _rejected(db, _INSERT, {**_new_key(a), "generation": uuid4()}, {"23514"})
        _rejected(db, _INSERT, a, {"23505"})


def test_active_reference_cannot_retire_and_retired_key_cannot_revive_or_disappear(versions):
    a = versions[0]
    with engine.connect() as db, db.begin():
        _rejected(db, "UPDATE document_storage_keys SET state='retired', retired_at=now() WHERE namespace=:namespace AND storage_key=:key", a, {"23503"})
        retired = _new_key(a)
        db.execute(text(_INSERT), retired)
        db.execute(text("UPDATE document_storage_keys SET state='retired', retired_at=now() WHERE namespace=:namespace AND storage_key=:key"), retired)
        _rejected(db, "UPDATE document_storage_keys SET state='live', retired_at=NULL WHERE namespace=:namespace AND storage_key=:key", retired)
        _rejected(db, "DELETE FROM document_storage_keys WHERE namespace=:namespace AND storage_key=:key", retired)
        _rejected(db, "UPDATE document_versions SET storage_key=:key WHERE id=:version", retired)


def test_failed_transaction_rolls_back_version_and_registry(versions):
    a = versions[0]
    version, generation = uuid4(), uuid4()
    row = {**a, "version": version,
           "key": f"{a['tenant']}/{a['document']}/{version}/{generation}.pdf"}
    with engine.connect() as db:
        transaction = db.begin()
        db.execute(text("""
            INSERT INTO document_versions (id, tenant_id, document_id, version, storage_key, sha256)
            VALUES (:version, :tenant, :document, 2, :key, :sha)
        """), {**row, "sha": "b" * 64})
        transaction.rollback()
        assert db.execute(text("SELECT count(*) FROM document_versions WHERE id=:version"), row).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM document_storage_keys WHERE namespace=:namespace AND storage_key=:key"), row).scalar_one() == 0


def test_duplicate_registration_is_idempotent_without_changing_identity(versions):
    item = _new_key(versions[0])
    with engine.begin() as db:
        db.execute(text(_INSERT), item)
        result = db.execute(text(_INSERT + " ON CONFLICT (namespace, storage_key) DO NOTHING"), item)
        assert result.rowcount == 0
        row = db.execute(text("""
            SELECT tenant_id, document_id, document_version_id, generation, state
            FROM document_storage_keys WHERE namespace=:namespace AND storage_key=:key
        """), item).one()
        assert tuple(row) == (item["tenant"], item["document"], item["version"],
                              item["generation"], "live")


def test_preview_reads_registry_compatibility_view_without_exposing_keys(versions):
    item = versions[0]
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text("""
            UPDATE document_versions SET created_at=now()-interval '3 days', idempotency_key=:request
            WHERE id=:version
        """), {**item, "request": uuid4()})
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            rows = preview_upload_cleanup(db, item["tenant"], minimum_age=timedelta(days=1))
            assert [row.version_id for row in rows] == [item["version"]]
            assert not hasattr(rows[0], "storage_key")
        transaction.rollback()


def test_concurrent_registration_of_same_key_has_only_one_winner(versions):
    item = _new_key(versions[0])
    backend = Queue()
    with engine.connect() as first:
        transaction = first.begin()
        first_pid = first.execute(text("SELECT pg_backend_pid()")).scalar_one()
        first.execute(text(_INSERT), item)

        def competitor():
            with engine.connect() as other:
                tx = other.begin()
                try:
                    other.execute(text("SET LOCAL lock_timeout = '15s'"))
                    backend.put(other.execute(text("SELECT pg_backend_pid()")).scalar_one())
                    other.execute(text(_INSERT), item)
                    tx.commit()
                    return None
                except DBAPIError as error:
                    tx.rollback()
                    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(competitor)
            other_pid = backend.get(timeout=5)
            deadline = monotonic() + 8
            while monotonic() < deadline:
                if first.execute(text("SELECT :pid = ANY(pg_blocking_pids(:other))"),
                                 {"pid": first_pid, "other": other_pid}).scalar_one():
                    break
                assert not future.done(), "競爭交易在觀察到阻塞前已結束"
                sleep(0.05)
            else:
                pytest.fail("未觀察到第一筆交易阻塞同鍵寫入")
            transaction.commit()
            assert future.result(timeout=10) == "23505"
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM document_storage_keys WHERE namespace=:namespace AND storage_key=:key"), item).scalar_one() == 1


def test_non_owner_runtime_inserts_with_immediate_constraints_but_cannot_bypass_registry(versions):
    """隔離 DB 交易內建立低權限角色；結束時回滾角色、授權和合成版本。"""
    a = versions[0]
    role = "registry_test_" + uuid4().hex
    version, generation = uuid4(), uuid4()
    item = {**a, "version": version, "generation": generation,
            "key": f"{a['tenant']}/{a['document']}/{version}/{generation}.pdf"}
    with engine.connect() as db:
        transaction = db.begin()
        try:
            # 僅使用由程式產生的識別字，不接受測試外部提供的 SQL。
            db.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'))
            db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            db.execute(text(f'GRANT INSERT ON public.document_versions TO "{role}"'))
            db.execute(text(f'GRANT SELECT ON public.document_storage_keys TO "{role}"'))
            db.execute(text(f'SET LOCAL ROLE "{role}"'))
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            db.execute(text("""
                INSERT INTO public.document_versions
                    (id, tenant_id, document_id, version, storage_key, sha256)
                VALUES (:version, :tenant, :document, 2, :key, :sha)
            """), {**item, "sha": "c" * 64})
            assert db.execute(text("""
                SELECT state FROM public.document_storage_keys
                WHERE namespace=:namespace AND storage_key=:key
            """), item).scalar_one() == "live"
            _rejected(db, _INSERT, _new_key(a), {"42501"})
            _rejected(db, "UPDATE public.document_storage_keys SET state='retired', retired_at=now() WHERE storage_key=:key", item, {"42501"})
            _rejected(db, "DELETE FROM public.document_storage_keys WHERE storage_key=:key", item, {"42501"})
            _rejected(db, "TRUNCATE public.document_storage_keys", {}, {"42501"})
            _rejected(db, "ALTER TABLE public.document_storage_keys DISABLE TRIGGER ALL", {}, {"42501"})
            _rejected(db, "ALTER TABLE public.document_versions DISABLE TRIGGER ALL", {}, {"42501"})
        finally:
            transaction.rollback()


def test_downgrade_rejects_and_preserves_retired_key(versions):
    item = _new_key(versions[0])
    with engine.begin() as db:
        db.execute(text(_INSERT), item)
        db.execute(text("UPDATE document_storage_keys SET state='retired', retired_at=now() WHERE namespace=:namespace AND storage_key=:key"), item)
        before = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    api_dir = Path(__file__).resolve().parents[1]
    config = Config(str(api_dir / "alembic.ini"))
    config.set_main_option("script_location", str(api_dir / "migrations"))
    with pytest.raises(DBAPIError) as caught:
        command.downgrade(config, "0010_document_retired_keys")
    code = getattr(caught.value.orig, "sqlstate", None) or getattr(caught.value.orig, "pgcode", None)
    assert code == "P0001"
    with engine.connect() as db:
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == before
        assert db.execute(text("SELECT state FROM document_storage_keys WHERE namespace=:namespace AND storage_key=:key"), item).scalar_one() == "retired"
