"""以一次性容器驗證鍵登錄；不呼叫 MinIO DELETE 或使用既有磁碟區。"""

import os
from pathlib import Path
import secrets
import subprocess
import time


def main():
    run = "key-registry-" + secrets.token_hex(8)
    password = secrets.token_hex(24)
    env = dict(os.environ, POSTGRES_PASSWORD=password, POSTGRES_DB="registry_head",
               MINIO_ROOT_USER="synthetic-registry", MINIO_ROOT_PASSWORD=secrets.token_hex(24))
    env.update(DATABASE_URL=f"postgresql+psycopg://postgres:{password}@db/registry_head",
               UPGRADE_DATABASE_URL=f"postgresql+psycopg://postgres:{password}@db/registry_upgrade",
               MINIO_ENDPOINT="minio:9000", MINIO_ACCESS_KEY=env["MINIO_ROOT_USER"],
               MINIO_SECRET_KEY=env["MINIO_ROOT_PASSWORD"], REDIS_URL="redis://redis:6379/0")
    containers = []
    network = None

    def docker(*args, **kwargs):
        return subprocess.run(["docker", *args], env=env, check=True, timeout=240, **kwargs)

    def start(suffix, *args):
        container = docker("run", "-d", "--pull=never", "--name", f"{run}-{suffix}",
                           "--label", f"key-registry-test={run}", "--network", network,
                           *args, capture_output=True, text=True).stdout.strip()
        containers.append(container)
        return container

    try:
        network = docker("network", "create", "--label", f"key-registry-test={run}", run,
                         capture_output=True, text=True).stdout.strip()
        db = start("db", "--network-alias", "db", "--tmpfs", "/var/lib/postgresql/data",
                   "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB", "postgres:16-alpine")
        start("minio", "--network-alias", "minio", "--tmpfs", "/data",
              "-e", "MINIO_ROOT_USER", "-e", "MINIO_ROOT_PASSWORD",
              "public.ecr.aws/y9w4h2u9/minio:RELEASE.2025-09-07T16-13-09Z", "server", "/data")
        start("redis", "--network-alias", "redis", "--tmpfs", "/data", "redis:7-alpine")
        for _ in range(60):
            ready = subprocess.run(["docker", "exec", db, "pg_isready", "-U", "postgres"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("一次性 PostgreSQL 未啟動")
        docker("exec", db, "createdb", "-U", "postgres", "registry_upgrade")
        api_dir = Path(__file__).resolve().parents[2] / "apps" / "api"
        script = """
            set -eu
            pip install -q -r requirements-dev.txt
            DATABASE_URL="$UPGRADE_DATABASE_URL" alembic upgrade 0010_document_retired_keys
            DATABASE_URL="$UPGRADE_DATABASE_URL" RUN_POSTGRES_TESTS=1 \
              python -m pytest -p no:cacheprovider -q tests/test_document_cleanup_preview_postgres.py \
              tests/test_independent_m2_concurrency_postgres.py
            DATABASE_URL="$UPGRADE_DATABASE_URL" RUN_KEY_REGISTRY_UPGRADE_TESTS=1 \
              python -m pytest -p no:cacheprovider -q tests/test_document_key_registry_upgrade_postgres.py
            alembic upgrade head
            RUN_KEY_REGISTRY_ISOLATED_TESTS=1 RUN_REGISTRY_UPLOAD_ISOLATED_TESTS=1 \
              RUN_POSTGRES_TESTS=1 RUN_REDIS_TESTS=1 python -m pytest -p no:cacheprovider -q
        """
        docker("run", "--rm", "--pull=never", "--network", network,
               "--mount", f"type=bind,source={api_dir},target=/app,readonly",
               "-e", "DATABASE_URL", "-e", "UPGRADE_DATABASE_URL", "-e", "MINIO_ENDPOINT",
               "-e", "MINIO_ACCESS_KEY", "-e", "MINIO_SECRET_KEY", "-e", "REDIS_URL",
               "-e", "RUN_MINIO_TESTS=0",
               "enterprise-ai-operations-agent-api:latest", "sh", "-c", script)
    finally:
        if containers:
            docker("rm", "-f", *reversed(containers), stdout=subprocess.DEVNULL)
        if network:
            docker("network", "rm", network, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
