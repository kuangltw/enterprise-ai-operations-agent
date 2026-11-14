"""在獨立 Docker 網路驗證 0011 或換鍵原型。"""

import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time


POSTGRES = "postgres@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139"
MINIO = ("public.ecr.aws/y9w4h2u9/minio@"
         "sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e")
PYTHON = "python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
REGISTRY_CHECKS = """
export DATABASE_URL="$UPGRADE_DATABASE_URL" RUN_POSTGRES_TESTS=1
alembic upgrade 0010_document_retired_keys
python -m pytest -p no:cacheprovider -q tests/test_document_cleanup_preview_postgres.py \
  tests/test_independent_m2_concurrency_postgres.py
RUN_KEY_REGISTRY_UPGRADE_TESTS=1 python -m pytest -p no:cacheprovider -q \
  tests/test_document_key_registry_upgrade_postgres.py
export DATABASE_URL="$HEAD_DATABASE_URL"
alembic upgrade 0011_document_key_registry
RUN_KEY_REGISTRY_ISOLATED_TESTS=1 RUN_REGISTRY_UPLOAD_ISOLATED_TESTS=1 \
  python -m pytest -p no:cacheprovider -q tests/test_document_key_registry_postgres.py \
  tests/test_document_registry_upload_no_delete.py tests/test_document_api_postgres.py \
  tests/test_document_list_postgres.py
"""
ROTATION_CHECKS = """
export DATABASE_URL="$HEAD_DATABASE_URL"
alembic upgrade 0011_document_key_registry
python -m pytest -p no:cacheprovider -q /testing/key_rotation/test_rotation.py
"""


def main():
    """產生每次執行專用的憑證與資源，結束後只依本次資源 ID 清理。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pull", action="store_true", help="先取得固定 digest 的映像")
    parser.add_argument("--rotation", action="store_true", help="只執行隔離的換鍵原型")
    options = parser.parse_args()

    run = "key-registry-" + secrets.token_hex(8)
    password = secrets.token_hex(24)
    testing = Path(__file__).resolve().parent
    api = testing.parents[1] / "apps" / "api"
    env = dict(os.environ, POSTGRES_PASSWORD=password,
               HEAD_DATABASE_URL=f"postgresql+psycopg://postgres:{password}@db/registry_head",
               UPGRADE_DATABASE_URL=f"postgresql+psycopg://postgres:{password}@db/registry_upgrade",
               MINIO_ROOT_USER="registry-bootstrap", MINIO_ROOT_PASSWORD=secrets.token_hex(24))
    # 固定本機 Docker context。排除環境變數把一次性資源導向遠端 daemon。
    env.pop("DOCKER_HOST", None)
    context = "desktop-linux" if os.name == "nt" else "default"
    cli = ["docker", "--context", context]

    def docker(*args, **kwargs):
        return subprocess.run([*cli, *args], env=env, check=True, timeout=360, **kwargs)

    def resource(*args):
        return docker(*args, capture_output=True, text=True).stdout.strip()

    containers = []
    network = None
    built = False
    try:
        endpoint = resource("context", "inspect", context, "--format", '{{.Endpoints.docker.Host}}')
        if endpoint not in {"unix:///var/run/docker.sock", "npipe:////./pipe/dockerDesktopLinuxEngine"}:
            raise RuntimeError("專項測試必須使用本機 Docker daemon")
        if options.pull:
            for image in (POSTGRES, PYTHON) if options.rotation else (POSTGRES, PYTHON, MINIO):
                docker("pull", image)
        # 建置階段只掛入專項套件清單。服務與測試在另一個無對外路由的網路執行。
        with TemporaryDirectory(prefix=run) as build_context:
            shutil.copyfile(testing / "key-registry-requirements.txt",
                            Path(build_context) / "key-registry-requirements.txt")
            docker("build", "--tag", run, "--file", "-", build_context, input=f"""
FROM {PYTHON}
COPY key-registry-requirements.txt /tmp/key-registry-requirements.txt
RUN python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: \
    --no-deps -r /tmp/key-registry-requirements.txt && python -m pip check
""", text=True)
        built = True
        network = resource("network", "create", "--internal", run)

        def start(alias, *args):
            container = resource("run", "-d", "--pull=never", "--name", f"{run}-{alias}",
                                 "--network", network, "--network-alias", alias, *args)
            containers.append(container)
            return container

        db = start("db", "--tmpfs", "/var/lib/postgresql/data",
                   "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB=registry_head", POSTGRES)
        test_env = ["-e", "HEAD_DATABASE_URL", "-e", "PYTHONDONTWRITEBYTECODE=1",
                    "-e", "PYTHONPATH=/app:/testing"]
        if not options.rotation:
            start("minio", "--tmpfs", "/data", "-e", "MINIO_ROOT_USER", "-e", "MINIO_ROOT_PASSWORD",
                  MINIO, "server", "/data")
            test_env.extend(("-e", "UPGRADE_DATABASE_URL", "-e", "MINIO_ENDPOINT=minio:9000",
                             "-e", "MINIO_ROOT_USER", "-e", "MINIO_ROOT_PASSWORD"))
        for _ in range(60):
            ready = subprocess.run([*cli, "exec", db, "pg_isready", "-h", "127.0.0.1",
                                    "-U", "postgres", "-d", "registry_head"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("一次性 PostgreSQL 未啟動")
        if not options.rotation:
            docker("exec", db, "createdb", "-U", "postgres", "registry_upgrade")
        # Settings 預設讀取 /app/.env。僅掛測試需要的程式與設定檔。
        mounts = []
        for name in ("alembic.ini", "pytest.ini", "migrations", "src", "tests"):
            mounts.extend(("--mount", f"type=bind,source={api / name},target=/app/{name},readonly"))
        if options.rotation:
            for name in ("key_rotation", "storage_safety"):
                mounts.extend(("--mount", f"type=bind,source={testing / name},target=/testing/{name},readonly"))
        client = resource("create", "--pull=never", "--name", f"{run}-test", "--network", network,
                          "--user", "65534:65534", "--workdir", "/app", *mounts,
                          *test_env, run, "sh", "-ec", ROTATION_CHECKS if options.rotation else REGISTRY_CHECKS)
        containers.append(client)
        docker("start", "--attach", client)
    finally:
        try:
            if containers:
                docker("rm", "-f", *reversed(containers), stdout=subprocess.DEVNULL)
        finally:
            try:
                if network:
                    docker("network", "rm", network, stdout=subprocess.DEVNULL)
            finally:
                if built:
                    docker("image", "rm", run, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
