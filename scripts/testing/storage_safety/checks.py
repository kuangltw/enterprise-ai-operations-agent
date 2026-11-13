"""Executable proof against the fixed, disposable Docker service aliases."""

import argparse
import io
import json
import multiprocessing
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from minio import Minio
from minio.commonconfig import ENABLED
from minio.credentials import StaticProvider
from minio.error import S3Error
from minio.minioadmin import MinioAdmin
from minio.versioningconfig import VersioningConfig
from urllib3 import PoolManager, Timeout
from urllib3.exceptions import HTTPError

from wire import CommitWire, PutWire, proxy, send_put, wait


DB_HOST = "proof-db"
STORE = "proof-minio:9000"
SCHEMA = Path(__file__).with_name("schema.sql")
DOWNGRADE = Path(__file__).with_name("downgrade.sql")
RUN = os.environ["PROOF_RUN"]
RUNTIME_PASSWORD = secrets.token_hex(24)
TENANT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def report(case, **result):
    print(json.dumps({"case": case, **result}, default=str, sort_keys=True))


def expect_error(kind, code, action):
    try:
        action()
    except kind as exc:
        actual = exc.sqlstate if isinstance(exc, psycopg.Error) else exc.code
        assert actual == code, (actual, code)
    else:
        raise AssertionError(f"expected {code}")


def db(*, runtime=False, host=DB_HOST, port=5432):
    return psycopg.connect(
        host=host, port=port, dbname="storage_proof",
        user="proof_runtime" if runtime else "postgres",
        password=RUNTIME_PASSWORD if runtime else os.environ["POSTGRES_PASSWORD"],
        sslmode="disable",
        connect_timeout=5, options="-c statement_timeout=8000",
    )


def physical_key(owner):
    return "/".join([*(str(value) for value in owner[1:]), f"{uuid4()}.pdf"])


def seed(connection, namespace, tenant=TENANT_A, *, referenced=True):
    owner = (namespace, tenant, uuid4(), uuid4())
    key = physical_key(owner)
    connection.execute(
        "INSERT INTO storage_proof.keys (namespace,tenant,document,version,object_key,generation)"
        " VALUES (%s,%s,%s,%s,%s,1)", (*owner, key),
    )
    if referenced:
        reference(connection, owner, key)
    return owner, key


def reference(connection, owner, key, generation=1):
    connection.execute(
        "INSERT INTO storage_proof.versions (namespace,tenant,document,version,object_key,generation)"
        " VALUES (%s,%s,%s,%s,%s,%s)", (*owner, key, generation),
    )


def rotate(connection, operation, owner, generation=1):
    return connection.execute(
        "SELECT storage_proof.rotate(%s,%s,%s,%s,%s,%s)",
        (operation, *owner, generation),
    ).fetchone()[0]


def finish(connection, owner, key, generation=1):
    return connection.execute(
        "SELECT storage_proof.finish(%s,%s,%s,%s,%s,%s)", (*owner, generation, key)
    ).fetchone()[0]


def lookup(connection, operation):
    return connection.execute(
        "SELECT old_key,new_key,old_generation,new_generation,status"
        " FROM storage_proof.reconciliation WHERE operation_id=%s", (operation,),
    ).fetchone()


def current(connection, owner):
    return connection.execute(
        "SELECT object_key,generation,status FROM storage_proof.versions"
        " WHERE (namespace,tenant,document,version)=(%s,%s,%s,%s)", owner,
    ).fetchone()


def key_state(connection, namespace, key):
    return connection.execute(
        "SELECT state FROM storage_proof.keys WHERE (namespace,object_key)=(%s,%s)",
        (namespace, key),
    ).fetchone()[0]


def blocked_by(observer, waiter, blocker):
    """Check PostgreSQL actually reports blocking before releasing the first transaction."""
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if blocker.info.backend_pid in observer.execute(
            "SELECT pg_blocking_pids(%s)", (waiter.info.backend_pid,),
        ).fetchone()[0]:
            return
        time.sleep(0.02)
    raise AssertionError("no observed lock wait")


def setup_database():
    with db() as setup:
        version = setup.execute("SHOW server_version").fetchone()[0]
        setup.execute(SCHEMA.read_text(encoding="utf-8"))
        setup.execute(sql.SQL("ALTER ROLE proof_runtime LOGIN PASSWORD {}")
                      .format(sql.Literal(RUNTIME_PASSWORD)))
    return version


def downgrade_checks(version):
    downgrade = DOWNGRADE.read_text(encoding="utf-8")
    with db() as maint:
        maint.execute(downgrade)
        assert maint.execute("SELECT to_regnamespace('storage_proof')").fetchone() == (None,)
        maint.rollback()  # Leave the same fixture available for the nonempty cases.
    report("empty_prototype_downgrade", postgres=version, result="schema removed inside transaction")

    with db() as writer, db() as maintenance, db() as observer, \
            ThreadPoolExecutor(max_workers=1) as workers:
        maintenance.autocommit = True
        _, first_key = seed(writer, RUN, referenced=False)
        future = workers.submit(expect_error, psycopg.Error, "55000",
                                lambda: maintenance.execute(downgrade))
        blocked_by(observer, maintenance, writer)
        writer.commit()
        future.result(10)
        assert key_state(observer, RUN, first_key) == "live"
    report("first_key_races_downgrade", observed_lock_wait=True, nonempty="55000",
           first_identity_retained=True, autocommit=True)

    with db() as admin:
        owner, old = seed(admin, RUN)
    with db(runtime=True) as writer, db() as maintenance, db() as observer, \
            ThreadPoolExecutor(max_workers=1) as workers:
        maintenance.autocommit = True
        operation = uuid4()
        new = rotate(writer, operation, owner)
        future = workers.submit(expect_error, psycopg.Error, "55000",
                                lambda: maintenance.execute(downgrade))
        blocked_by(observer, maintenance, writer)
        writer.commit()
        future.result(10)
        assert lookup(observer, operation) == (old, new, 1, 2, "waiting_fence")
        assert key_state(observer, RUN, old) == "retired"
        assert current(observer, owner) == (new, 2, "pending")
        assert key_state(observer, RUN, new) == "live"
    with db() as maintenance:
        maintenance.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        expect_error(psycopg.Error, "22023", lambda: maintenance.execute(downgrade))
        maintenance.rollback()
    report("nonempty_prototype_downgrade", observed_lock_wait=True,
           nonempty="55000", repeatable_read="22023", identities_retained=True, autocommit=True)


def database_checks():
    with db() as owner_conn:
        owner, old = seed(owner_conn, RUN)
        free, unreferenced = seed(owner_conn, RUN, referenced=False)
    with db() as admin, db(runtime=True) as runtime, db() as observer:
        observer.autocommit = True

        def reject(code, sql, params=()):
            with admin.transaction():
                expect_error(psycopg.Error, code, lambda: admin.execute(sql, params))
            admin.rollback()

        # Existing version cannot lose its required live target.
        reject("23503", "UPDATE storage_proof.keys SET state='retired' WHERE object_key=%s", (old,))
        for index in (1, 2, 3):
            forged = list(owner)
            forged[index] = uuid4()
            expect_error(psycopg.Error, "23503", lambda: reference(admin, forged, old))
            admin.rollback()
        expect_error(psycopg.Error, "23503", lambda: reference(admin, free, unreferenced, 2))
        admin.rollback()
        expect_error(psycopg.Error, "23502", lambda: reference(admin, free, None))
        admin.rollback()
        for statement in (
            "UPDATE storage_proof.keys SET state='retired'",
            "UPDATE storage_proof.versions SET generation=2",
            "DELETE FROM storage_proof.reconciliation",
            "TRUNCATE storage_proof.keys",
            "ALTER TABLE storage_proof.keys DISABLE TRIGGER ALL",
        ):
            expect_error(psycopg.Error, "42501", lambda: runtime.execute(statement))
            runtime.rollback()
        report("database_constraints", live_fk="23503", tenant_document_version_generation="23503",
               null="23502", runtime_write_truncate_ddl="42501")

        operation = uuid4()
        replacement = rotate(runtime, operation, owner)
        assert lookup(observer, operation) is None
        assert current(observer, owner) == (old, 1, "pending")
        assert key_state(observer, RUN, old) == "live"
        assert observer.execute("SELECT 1 FROM storage_proof.keys WHERE object_key=%s",
                                (replacement,)).fetchone() is None
        runtime.rollback()
        assert lookup(observer, operation) is None and key_state(observer, RUN, old) == "live"
        assert observer.execute("SELECT 1 FROM storage_proof.keys WHERE object_key=%s",
                                (replacement,)).fetchone() is None
        replacement = rotate(runtime, operation, owner)
        runtime.commit()
        assert lookup(observer, operation) == (old, replacement, 1, 2, "waiting_fence")
        assert current(observer, owner) == (replacement, 2, "pending")
        assert key_state(observer, RUN, old) == "retired"
        assert key_state(observer, RUN, replacement) == "live"
        assert rotate(runtime, operation, owner) == replacement
        expect_error(psycopg.Error, "22023", lambda: rotate(runtime, operation, free))
        runtime.rollback()
        assert not finish(runtime, owner, old)
        assert finish(runtime, owner, replacement, 2)
        runtime.commit()
        expect_error(psycopg.Error, "22023", lambda: rotate(runtime, uuid4(), owner, 2))
        runtime.rollback()
        reject("23514", "UPDATE storage_proof.keys SET state='live' WHERE object_key=%s", (old,))
        reject("23514", "UPDATE storage_proof.keys SET tenant=%s WHERE object_key=%s", (TENANT_B, old))
        reject("23514", "DELETE FROM storage_proof.keys WHERE object_key=%s", (old,))
        reject("23514", "TRUNCATE storage_proof.keys CASCADE")
        reject("23505", "INSERT INTO storage_proof.keys"
               " (namespace,tenant,document,version,object_key,generation) VALUES (%s,%s,%s,%s,%s,1)",
               (*owner, old))
        report("atomic_rotation", operation_id=operation, old_key=old, new_key=replacement,
               rolled_back_attempt="no changes visible", pg=lookup(observer, operation),
               reactivation_delete_truncate="23514", reuse="23505", stale_completion=False)

        with ThreadPoolExecutor(max_workers=1) as workers:
            reference(admin, free, unreferenced)
            with db() as challenger:
                future = workers.submit(expect_error, psycopg.Error, "23503",
                                        lambda: challenger.execute(
                                            "UPDATE storage_proof.keys SET state='retired' WHERE object_key=%s",
                                            (unreferenced,)))
                blocked_by(observer, challenger, admin)
                admin.commit()
                future.result(10)
                challenger.rollback()
            free, unreferenced = seed(admin, RUN, referenced=False)
            admin.commit()
            admin.execute("UPDATE storage_proof.keys SET state='retired' WHERE object_key=%s",
                          (unreferenced,))
            with db() as challenger:
                future = workers.submit(expect_error, psycopg.Error, "23503",
                                        lambda: reference(challenger, free, unreferenced))
                blocked_by(observer, challenger, admin)
                admin.commit()
                future.result(10)
                challenger.rollback()
        report("concurrent_live_fk", observed_lock_waits=2, both_rejected="23503")

    with db() as admin:
        owner, old = seed(admin, RUN)
    operation = uuid4()
    with db(runtime=True) as first, db(runtime=True) as second, db() as observer, \
            ThreadPoolExecutor(max_workers=1) as workers:
        new = rotate(first, operation, owner)
        future = workers.submit(rotate, second, operation, owner)
        blocked_by(observer, second, first)
        first.commit()
        assert future.result(10) == new
        second.commit()
        assert lookup(observer, operation) == (old, new, 1, 2, "waiting_fence")
        third = rotate(first, uuid4(), owner, 2)
        first.commit()
        assert lookup(observer, operation) == (old, new, 1, 2, "waiting_fence")
        assert current(observer, owner) == (third, 3, "pending")
        assert key_state(observer, RUN, new) == "retired"
    report("parallel_operation_replay", observed_lock_wait=True, same_replacement=new,
           history_survives_next_rotation=True)

    with db() as admin:
        owner, old = seed(admin, RUN)
        other, other_old = seed(admin, RUN)
    with db(runtime=True) as first, db(runtime=True) as second, db() as observer, \
            ThreadPoolExecutor(max_workers=1) as workers:
        assert finish(first, owner, old)
        operation = uuid4()
        future = workers.submit(expect_error, psycopg.Error, "22023",
                                lambda: rotate(second, operation, owner))
        blocked_by(observer, second, first)
        first.commit()
        future.result(10)
        second.rollback()
        assert lookup(observer, operation) is None
        assert current(observer, owner) == (old, 1, "stored")
        new = rotate(first, operation, other)
        future = workers.submit(finish, second, other, other_old)
        blocked_by(observer, second, first)
        first.commit()
        assert not future.result(10)
        second.commit()
        assert current(observer, other) == (new, 2, "pending")
    report("rotation_completion_race", observed_lock_waits=2, stored_key_kept=True,
           old_generation_completion=False)

    with db() as admin:
        owner, old = seed(admin, RUN)
    operation = uuid4()
    wire = CommitWire()
    with proxy((DB_HOST, 5432), wire) as port:
        with closing(db(runtime=True, host="127.0.0.1", port=port)) as writer, \
                ThreadPoolExecutor(max_workers=1) as workers:
            new = rotate(writer, operation, owner)
            commit = workers.submit(writer.commit)
            wait(wire.withheld)
            wire.disconnect.set()
            try:
                commit.result(10)
            except psycopg.OperationalError:
                pass
            else:
                raise AssertionError("COMMIT response unexpectedly reached client")
    with db(runtime=True) as observer:
        assert lookup(observer, operation) == (old, new, 1, 2, "waiting_fence")
        assert rotate(observer, operation, owner) == new
    report("postgres_commit_response_lost", client="OperationalError",
           upstream="CommitComplete and ReadyForQuery(I)", operation_id=operation,
           pg=[old, new, 1, 2, "waiting_fence"])


def backend_recovery_check():
    with db() as admin:
        owner, old = seed(admin, RUN)
    operation = uuid4()
    with closing(db(runtime=True)) as writer, db() as observer:
        rotate(writer, operation, owner)
        assert observer.execute("SELECT pg_terminate_backend(%s, 5000)",
                                (writer.info.backend_pid,)).fetchone() == (True,)
        try:
            writer.commit()
        except psycopg.OperationalError:
            pass
        else:
            raise AssertionError("terminated backend acknowledged commit")
    with db(runtime=True) as observer:
        assert lookup(observer, operation) is None
        assert current(observer, owner) == (old, 1, "pending")
        assert key_state(observer, RUN, old) == "live"
        new = rotate(observer, operation, owner)
    with db(runtime=True) as observer:
        assert lookup(observer, operation) == (old, new, 1, 2, "waiting_fence")
        assert current(observer, owner) == (new, 2, "pending")
        assert key_state(observer, RUN, old) == "retired"
        assert key_state(observer, RUN, new) == "live"
    report("postgres_backend_lost_before_commit", client="OperationalError", operation_id=operation,
           rollback_observed=True, retry_pg=[old, new, 1, 2, "waiting_fence"])


def minio_client(access=None, credential=None):
    return Minio(STORE, access_key=access, secret_key=credential, region="us-east-1", secure=False,
                 http_client=PoolManager(timeout=Timeout(connect=2, read=5), retries=False))


def put(client, bucket, key, body):
    return client.put_object(bucket, key, io.BytesIO(body), len(body)).version_id


def get(client, bucket, key, version_id=None):
    result = client.get_object(bucket, key, version_id=version_id)
    try:
        return result.read(), result.headers.get("x-amz-version-id")
    finally:
        result.close()
        result.release_conn()


def history(client, bucket, key):
    # minio-py 7.2.20 exposes IsLatest as the XML string "true" or "false".
    return [(obj.version_id, obj.is_delete_marker, obj.is_latest == "true")
            for obj in client.list_objects(bucket, prefix=key, include_version=True)
            if obj.object_name == key]


def bootstrap():
    root = os.environ["MINIO_ROOT_USER"]
    credential = os.environ["MINIO_ROOT_PASSWORD"]
    administrator = minio_client(root, credential)
    admin = MinioAdmin(endpoint=STORE, credentials=StaticProvider(root, credential), secure=False)
    plain, versioned = RUN + "-plain", RUN + "-versioned"
    administrator.make_bucket(plain)
    administrator.make_bucket(versioned)
    administrator.set_bucket_versioning(versioned, VersioningConfig(ENABLED))
    accounts = []
    for alias, tenant in (("a", TENANT_A), ("b", TENANT_B), ("shared", "*")):
        access = "proof-user-" + alias
        secret = secrets.token_hex(24)
        admin.user_add(access, secret)
        statements = [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion",
                                          "s3:PutObject", "s3:DeleteObject",
                                          "s3:DeleteObjectVersion"],
             "Resource": [f"arn:aws:s3:::{bucket}/{tenant}/*" if tenant != "*"
                          else f"arn:aws:s3:::{bucket}/*" for bucket in (plain, versioned)]},
            {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:ListBucketVersions"],
             "Resource": [f"arn:aws:s3:::{bucket}" for bucket in (plain, versioned)],
             "Condition": {"StringLike": {"s3:prefix": [f"{tenant}/*" if tenant != "*" else "*"]}}},
        ]
        policy = "proof-policy-" + alias
        admin.policy_add(policy, policy={"Version": "2012-10-17", "Statement": statements})
        admin.policy_set(policy, user=access)
        accounts.append((access, secret))
    return accounts, plain, versioned


def minio_checks(accounts, plain, versioned):
    a, b, shared = (minio_client(*credentials) for credentials in accounts)
    for bucket in (plain, versioned):
        owner_a = (bucket, TENANT_A, uuid4(), uuid4())
        owner_b = (bucket, TENANT_B, uuid4(), uuid4())
        own, foreign = physical_key(owner_a), physical_key(owner_b)
        version_b = put(b, bucket, foreign, b"tenant-b")
        assert put(a, bucket, own, b"tenant-a") == get(a, bucket, own)[1]
        assert get(a, bucket, own)[0] == b"tenant-a"
        original = get(b, bucket, foreign)
        versions = history(b, bucket, foreign) if version_b else []
        assert original == (b"tenant-b", version_b)
        for action in (
            lambda: get(a, bucket, foreign),
            lambda: put(a, bucket, foreign, b"denied"),
            lambda: a.remove_object(bucket, foreign),
            lambda: get(minio_client(), bucket, foreign),
        ):
            expect_error(S3Error, "AccessDenied", action)
        forged = physical_key((bucket, TENANT_B, *owner_a[2:]))
        expect_error(S3Error, "AccessDenied", lambda: put(a, bucket, forged, b"denied"))
        if version_b:
            for action in (
                lambda: get(a, bucket, foreign, version_b),
                lambda: a.remove_object(bucket, foreign, version_id=version_b),
                lambda: history(a, bucket, foreign),
            ):
                expect_error(S3Error, "AccessDenied", action)
            assert history(b, bucket, foreign) == versions
        assert get(b, bucket, foreign) == original
        assert get(shared, bucket, own) == get(a, bucket, own)
        assert get(shared, bucket, foreign) == original
        a.remove_object(bucket, own)
        expect_error(S3Error, "NoSuchKey", lambda: get(a, bucket, own))
        report("tenant_prefix_policy", bucket=bucket, key=foreign, forged_key=forged,
               version_id=version_b, own_delete="accepted", foreign_and_anonymous="AccessDenied",
               b_history=versions, shared_reads_both=True)

    for bucket in (plain, versioned):
        with db() as admin:
            owner, old = seed(admin, bucket)
        original = put(a, bucket, old, b"original")
        wire = PutWire("tail")
        operation = uuid4()
        with proxy(("proof-minio", 9000), wire) as port, ThreadPoolExecutor(max_workers=1) as workers:
            client = workers.submit(send_put, port, a.presigned_put_object(bucket, old), b"late", 1.0)
            wait(wire.reached)
            with db(runtime=True) as runtime:
                new = rotate(runtime, operation, owner)
            new_id = put(a, bucket, new, b"new-generation")
            try:
                client.result(10)
            except TimeoutError:
                pass
            else:
                raise AssertionError("expected client read timeout")
            wait(wire.client_disconnected)
            a.remove_object(bucket, old)  # Isolated counterexample, deliberately lacks a fence.
            expect_error(S3Error, "NoSuchKey", lambda: get(a, bucket, old))
            marker_history = history(a, bucket, old) if original else []
            if original:
                assert sum(mark and latest for _, mark, latest in marker_history) == 1
                assert (original, False, False) in marker_history
                assert get(a, bucket, old, original)[0] == b"original"
            wire.release.set()
        assert wire.result[0] == 200
        late_body, late_id = get(a, bucket, old)
        assert (late_body, late_id) == (b"late", wire.result[1])
        assert get(a, bucket, new) == (b"new-generation", new_id)
        with db(runtime=True) as observer:
            pg = lookup(observer, operation)
            assert pg == (old, new, 1, 2, "waiting_fence")
            assert current(observer, owner) == (new, 2, "pending")
            assert key_state(observer, bucket, old) == "retired"
            assert not finish(observer, owner, old)
        after = history(a, bucket, old) if original else []
        if original:
            assert original != late_id and (late_id, False, True) in after
            a.remove_object(bucket, old, version_id=original)
            expect_error(S3Error, "NoSuchVersion", lambda: get(a, bucket, old, original))
            assert get(a, bucket, old) == (b"late", late_id)
        a.remove_object(bucket, old)
        expect_error(S3Error, "NoSuchKey", lambda: get(a, bucket, old))
        retry_id = put(a, bucket, old, b"late")
        assert get(a, bucket, old) == (b"late", retry_id)
        if original:
            assert retry_id not in {original, late_id}
            assert get(a, bucket, old, late_id) == (b"late", late_id)
        report("late_put_after_delete", client="TimeoutError; downstream TCP closed",
               bucket=bucket, upstream=wire.result, operation_id=operation, postgres=pg,
               old_key=old, original_version=original, after_delete=marker_history,
               after_late=after, retry_version=retry_id, new_key=new, new_version=new_id)

    owner = (versioned, TENANT_A, uuid4(), uuid4())
    key = physical_key(owner)
    wire = PutWire("response")
    with proxy(("proof-minio", 9000), wire) as port, ThreadPoolExecutor(max_workers=1) as workers:
        client = workers.submit(send_put, port, a.presigned_put_object(versioned, key), b"accepted", 2)
        wait(wire.reached)
        assert wire.result[0] == 200
        try:
            client.result(10)
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected client read timeout")
        wire.release.set()
    observer = minio_client(*accounts[0])
    assert get(observer, versioned, key) == (b"accepted", wire.result[1])
    report("put_response_timeout_after_acceptance", key=key, bucket=versioned, postgres=None,
           client="TimeoutError; downstream TCP closed", upstream=wire.result,
           after_reconnect=history(observer, versioned, key))

    # Kill a separate client process after real upstream acceptance; observer reconnects.
    key = physical_key(owner)
    wire = PutWire("response")
    with proxy(("proof-minio", 9000), wire) as port:
        process = multiprocessing.get_context("fork").Process(
            target=send_put, args=(port, a.presigned_put_object(versioned, key), b"accepted", 8)
        )
        process.start()
        try:
            wait(wire.reached)
            assert wire.result[0] == 200
        finally:
            process.kill()
            process.join(5)
            wire.release.set()
        assert process.exitcode == -9
    observer = minio_client(*accounts[0])
    assert get(observer, versioned, key) == (b"accepted", wire.result[1])
    report("put_response_lost_on_process_kill", key=key, bucket=versioned, postgres=None,
           client="SIGKILL; downstream TCP closed", upstream=wire.result,
           after_reconnect=history(observer, versioned, key))

    key = physical_key(owner)
    wire = PutWire("upstream_eof")
    with proxy(("proof-minio", 9000), wire) as port, ThreadPoolExecutor(max_workers=1) as workers:
        client = workers.submit(send_put, port, a.presigned_put_object(versioned, key), b"incomplete", 1)
        wait(wire.reached)
        wire.release.set()
        try:
            client.result(10)
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected client read timeout")
    assert wire.result[0] >= 400
    expect_error(S3Error, "NoSuchKey", lambda: get(observer, versioned, key))
    assert history(observer, versioned, key) == []
    report("upstream_tcp_eof_mid_body", key=key, bucket=versioned, postgres=None,
           client="TimeoutError", upstream=wire.result, after_reconnect=[])


def cancellation_check(credentials, bucket):
    writer = minio_client(*credentials)
    observer = minio_client(*credentials)
    key = physical_key((bucket, TENANT_A, uuid4(), uuid4()))
    wire = PutWire("tail")
    with proxy(("proof-minio", 9000), wire) as port:
        process = multiprocessing.get_context("fork").Process(
            target=send_put, args=(port, writer.presigned_put_object(bucket, key), b"cancelled", 8)
        )
        process.start()
        try:
            wait(wire.reached)
            process.kill()
            process.join(5)
            assert process.exitcode == -9
            wait(wire.client_disconnected)
            expect_error(S3Error, "NoSuchKey", lambda: get(observer, bucket, key))
            assert history(observer, bucket, key) == []
        finally:
            if process.is_alive():
                process.kill()
                process.join(5)
            wire.release.set()
    assert wire.result[0] == 200
    assert get(observer, bucket, key) == (b"cancelled", wire.result[1])
    report("put_client_cancelled_before_acceptance", key=key, bucket=bucket, postgres=None,
           client="SIGKILL; downstream TCP closed", before_release="NoSuchKey; no versions",
           upstream=wire.result, after_reconnect=history(observer, bucket, key))


def wait_for_services():
    health = PoolManager(timeout=Timeout(connect=2, read=2), retries=False)
    for name, ready in (
        ("PostgreSQL", lambda: db().close()),
        ("MinIO", lambda: health.request(
            "GET", f"http://{STORE}/minio/health/ready").status == 200),
    ):
        deadline = time.monotonic() + 25
        while True:
            try:
                if ready() is not False:
                    break
            except (OSError, HTTPError, psycopg.OperationalError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{name} did not start")
            time.sleep(0.25)


if __name__ == "__main__":
    if not RUN.startswith("storage-proof-") or len(RUN) != len("storage-proof-") + 16:
        raise SystemExit("use the disposable Docker launcher")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--followup", action="store_true")
    followup = parser.parse_args().followup
    wait_for_services()
    downgrade_checks(setup_database())
    backend_recovery_check()
    if not followup:
        database_checks()
    accounts, plain, versioned = bootstrap()
    cancellation_check(accounts[0], versioned)
    if not followup:
        minio_checks(accounts, plain, versioned)
