"""以實際 0011 約束及合成資料驗證換鍵交易。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import os
from pathlib import Path
import secrets
import time
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest

from storage_safety.wire import CommitWire, proxy, wait


@dataclass(frozen=True)
class Version:
    tenant: UUID
    document: UUID
    version: UUID
    generation: UUID
    upload_id: UUID

    @property
    def key(self):
        return f"{self.tenant}/{self.document}/{self.version}/{self.generation}.pdf"

    @property
    def identity(self):
        return self.tenant, self.document, self.version, self.generation


def scalar(db, statement, args=()):
    return db.execute(statement, args).fetchone()[0]


def rotate(db, version, operation):
    return scalar(db, "SELECT key_rotation.rotate(%s,%s,%s,%s,%s)", (*version.identity, operation))


def finish(db, version):
    return scalar(db, "SELECT key_rotation.finish(%s,%s,%s,%s)", version.identity)


@pytest.fixture(scope="module")
def database():
    """只允許執行器的新資料庫。管理者布建，換鍵使用真實低權限登入。"""
    admin = conninfo_to_dict(os.environ["HEAD_DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:", 1))
    assert (admin["host"], admin["dbname"]) == ("db", "registry_head")
    assert "hostaddr" not in admin and "service" not in admin
    runtime = dict(admin, user="rotation_runtime", password=secrets.token_hex(24))
    tenant, outsider, owner = uuid4(), uuid4(), uuid4()
    with psycopg.connect(**admin) as db:
        assert scalar(db, "SELECT version_num FROM alembic_version") == "0011_document_key_registry"
        db.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        db.execute(sql.SQL("ALTER ROLE rotation_runtime PASSWORD {}").format(sql.Literal(runtime["password"])))
        db.execute("INSERT INTO tenants (id,name) VALUES (%s,'rotation'),(%s,'other')", (tenant, outsider))
        db.execute("INSERT INTO users (id,email,password_hash) VALUES (%s,%s,'synthetic')",
                   (owner, f"{owner}@example.invalid"))
        db.execute("INSERT INTO memberships (tenant_id,user_id,role) VALUES (%s,%s,'staff')", (tenant, owner))
        db.execute("INSERT INTO key_rotation.tenant_scope VALUES ('rotation_runtime',%s)", (tenant,))
    return admin, runtime, tenant, outsider, owner


@pytest.fixture
def version(database):
    admin, _, tenant, _, owner = database
    row = Version(tenant, uuid4(), uuid4(), uuid4(), uuid4())
    with psycopg.connect(**admin) as db:
        db.execute("INSERT INTO documents (id,tenant_id,title,owner_id) VALUES (%s,%s,'PDF',%s)",
                   (row.document, tenant, owner))
        db.execute("""INSERT INTO document_versions
            (id,tenant_id,document_id,version,storage_key,sha256,idempotency_key,storage_status)
            VALUES (%s,%s,%s,1,%s,repeat('a',64),%s,'failed')""",
                   (row.version, tenant, row.document, row.key, row.upload_id))
        db.execute("INSERT INTO document_user_acl (tenant_id,document_id,user_id) VALUES (%s,%s,%s)",
                   (tenant, row.document, owner))
    return row


def inspect(admin, version):
    """以新連線取得已提交的版本、物件鍵、操作結果及索引工作數。"""
    with psycopg.connect(**admin) as db:
        pointer = db.execute("""SELECT v.storage_key, v.version, v.sha256, v.storage_status, v.idempotency_key,
                                        d.current_version, a.user_id
            FROM document_versions v JOIN documents d ON (v.tenant_id,v.document_id)=(d.tenant_id,d.id)
            JOIN document_user_acl a ON (a.tenant_id,a.document_id)=(d.tenant_id,d.id)
            WHERE v.id=%s""", (version.version,)).fetchone()
        keys = dict(db.execute("SELECT storage_key,state FROM document_storage_keys WHERE document_version_id=%s",
                               (version.version,)).fetchall())
        ledger = db.execute("""SELECT old_key,new_key,status FROM key_rotation.operations WHERE version_id=%s""",
                            (version.version,)).fetchall()
        job_count = scalar(db, "SELECT count(*) FROM document_index_jobs WHERE document_version_id=%s",
                           (version.version,))
        version_count = scalar(db, "SELECT count(*) FROM document_versions WHERE document_id=%s",
                               (version.document,))
    return pointer, keys, ledger, job_count, version_count


def test_atomic_switch_preserves_version_contract_and_terminal_old_key(database, version):
    admin, runtime, *_ = database
    before = inspect(admin, version)
    operation = uuid4()
    with psycopg.connect(**runtime) as db:
        db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        new = rotate(db, version, operation)
        assert inspect(admin, version) == before
    pointer, keys, operations, jobs, versions = inspect(admin, version)
    assert pointer == (new, *before[0][1:])
    assert keys == {version.key: "retired", new: "live"}
    assert operations == [(version.key, new, "waiting_fence")]
    assert (jobs, versions) == (0, 1)
    with psycopg.connect(**runtime) as db:
        assert rotate(db, version, operation) == new
        with pytest.raises(psycopg.errors.InvalidParameterValue), db.transaction():
            rotate(db, replace(version, generation=uuid4()), operation)
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            db.execute("SET ROLE rotation_owner")
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            db.execute("UPDATE public.document_versions SET storage_key='synthetic'")
    with psycopg.connect(**admin) as db:
        with pytest.raises(psycopg.errors.RaiseException), db.transaction():
            db.execute("UPDATE document_storage_keys SET state='live', retired_at=NULL WHERE storage_key=%s",
                       (version.key,))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute("UPDATE document_storage_keys SET state='retired', retired_at=now() WHERE storage_key=%s",
                       (new,))
        # 即使使用具換鍵權限的角色，原版 FK 仍禁止把指標移回 retired。
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute("SET LOCAL ROLE rotation_owner")
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
            db.execute("UPDATE document_versions SET storage_key=%s WHERE id=%s", (version.key, version.version))


@pytest.mark.parametrize("field", ["tenant", "document", "version", "generation"])
def test_wrong_owner_or_generation_cannot_rotate(database, version, field):
    admin, runtime, _, outsider, _ = database
    wrong = replace(version, **{field: outsider if field == "tenant" else uuid4()})
    error = psycopg.errors.InsufficientPrivilege if field == "tenant" else psycopg.errors.InvalidParameterValue
    with pytest.raises(error), psycopg.connect(**runtime) as db:
        rotate(db, wrong, uuid4())
    assert inspect(admin, version)[1:] == ({version.key: "live"}, [], 0, 1)


def test_rollback_undoes_replacement_tombstone_and_operation(database, version):
    admin, runtime, *_ = database
    before = inspect(admin, version)
    operation = uuid4()
    with pytest.raises(psycopg.errors.DivisionByZero), psycopg.connect(**runtime) as db:
        rotate(db, version, operation)
        db.execute("SELECT 1/0")
    assert inspect(admin, version) == before
    with psycopg.connect(**runtime) as db:
        rotate(db, version, operation)
    assert len(inspect(admin, version)[2]) == 1


@pytest.mark.parametrize("reference", ["current", "index_job"])
def test_rotation_rejects_an_existing_publication_pointer_or_job(database, version, reference):
    admin, runtime, *_ = database
    with psycopg.connect(**admin) as db:
        if reference == "current":
            db.execute("UPDATE documents SET current_version=1 WHERE id=%s", (version.document,))
        else:
            db.execute("INSERT INTO document_index_jobs (tenant_id,document_version_id) VALUES (%s,%s)",
                       (version.tenant, version.version))
    before = inspect(admin, version)
    with pytest.raises(psycopg.errors.InvalidParameterValue), psycopg.connect(**runtime) as db:
        rotate(db, version, uuid4())
    assert inspect(admin, version) == before


def wait_for_block(observer, blocker, waiter):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if scalar(observer, "SELECT %s = ANY(pg_blocking_pids(%s))", (blocker, waiter)):
            return
        time.sleep(0.02)
    pytest.fail("尚未觀察到預期的 PostgreSQL 鎖等待")


@pytest.mark.parametrize("second_call", ["same_operation", "other_operation", "finish", "rotate_after_finish"])
def test_competing_calls_wait_then_revalidate(database, version, second_call):
    admin, runtime, *_ = database
    operation = uuid4()
    with (ThreadPoolExecutor(max_workers=1) as workers, psycopg.connect(**runtime) as first,
          psycopg.connect(**runtime) as second, psycopg.connect(**admin, autocommit=True) as observer):
        first_pid, second_pid = first.info.backend_pid, second.info.backend_pid
        second.execute("SET LOCAL lock_timeout = '10s'")
        if second_call == "rotate_after_finish":
            assert finish(first, version)
        else:
            replacement = rotate(first, version, operation)
        if second_call == "finish":
            pending = workers.submit(finish, second, version)
        else:
            pending = workers.submit(rotate, second, version, operation if second_call == "same_operation" else uuid4())
        wait_for_block(observer, first_pid, second_pid)
        first.commit()
        if second_call == "same_operation":
            assert pending.result(timeout=5) == replacement
        elif second_call == "finish":
            assert pending.result(timeout=5) is False
        else:
            with pytest.raises(psycopg.errors.InvalidParameterValue):
                pending.result(timeout=5)
            second.rollback()

    keys, ledger, jobs, versions = inspect(admin, version)[1:]
    if second_call == "rotate_after_finish":
        assert (keys, ledger, jobs, versions) == ({version.key: "live"}, [], 1, 1)
    else:
        assert (keys, ledger, jobs, versions) == (
            {version.key: "retired", replacement: "live"}, [(version.key, replacement, "waiting_fence")], 0, 1
        )


def test_only_current_generation_creates_one_index_job(database, version):
    admin, runtime, *_ = database
    operation = uuid4()
    with psycopg.connect(**runtime) as db:
        first_key = rotate(db, version, operation)
        first = replace(version, generation=UUID(first_key.rsplit("/", 1)[1][:-4]))
        new = rotate(db, first, uuid4())
        latest = replace(version, generation=UUID(new.rsplit("/", 1)[1][:-4]))
        assert rotate(db, version, operation) == first_key
        assert not finish(db, version)
        assert not finish(db, first)
        assert finish(db, latest)
        assert not finish(db, latest)
        with pytest.raises(psycopg.errors.InvalidParameterValue), db.transaction():
            rotate(db, latest, uuid4())
    assert inspect(admin, version)[3:] == (1, 1)


def test_lost_commit_reply_is_reconciled_from_new_connection(database, version):
    admin, runtime, *_ = database
    operation = uuid4()
    wire = CommitWire()
    with proxy((runtime["host"], 5432), wire) as port, ThreadPoolExecutor(max_workers=1) as workers:
        with psycopg.connect(**(runtime | {"host": "127.0.0.1", "port": port, "sslmode": "disable",
                                            "gssencmode": "disable", "connect_timeout": 5})) as db:
            replacement = rotate(db, version, operation)
            commit = workers.submit(db.commit)
            try:
                wait(wire.withheld)
                assert inspect(admin, version)[2] == [(version.key, replacement, "waiting_fence")]
            finally:
                wire.disconnect.set()
            with pytest.raises(psycopg.OperationalError):
                commit.result(timeout=10)
    with psycopg.connect(**runtime) as db:
        assert rotate(db, version, operation) == replacement
    assert inspect(admin, version)[2:] == ([(version.key, replacement, "waiting_fence")], 0, 1)
