"""跨平台執行隔離的 M1 Playwright E2E；測試容器使用 tmpfs，結束後關閉。"""

from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.e2e.yml"
WEB = ROOT / "apps" / "web"


def free_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def main() -> int:
    docker = shutil.which("docker")
    npm = shutil.which("npm")
    if not docker or not npm:
        print("需要 Docker Compose 與 npm 才能執行 E2E。", file=sys.stderr)
        return 1

    project = f"m1e2e{secrets.token_hex(4)}"
    common = [docker, "compose", "-p", project, "-f", str(COMPOSE)]
    run_id = uuid4().hex
    env = os.environ.copy()
    env.update({
        "E2E_DB_PASSWORD": secrets.token_hex(24),
        "E2E_JWT_KEY": secrets.token_hex(48),
        "E2E_WEB_PORT": str(free_port()),
        "E2E_PRIMARY_USER_ID": str(uuid4()),
        "E2E_OTHER_USER_ID": str(uuid4()),
        "E2E_USER_EMAIL": f"m1-primary-{run_id}@example.invalid",
        "E2E_OTHER_EMAIL": f"m1-other-{run_id}@example.invalid",
        "E2E_USER_PASSWORD": secrets.token_urlsafe(32),
        "E2E_TENANT_A_ID": str(uuid4()),
        "E2E_TENANT_B_ID": str(uuid4()),
        "E2E_TENANT_C_ID": str(uuid4()),
    })
    seed_vars = [
        "E2E_PRIMARY_USER_ID", "E2E_OTHER_USER_ID", "E2E_USER_EMAIL",
        "E2E_OTHER_EMAIL", "E2E_USER_PASSWORD", "E2E_TENANT_A_ID",
        "E2E_TENANT_B_ID", "E2E_TENANT_C_ID",
    ]
    stage = "啟動隔離服務"
    try:
        subprocess.run(common + ["up", "-d", "--build", "--wait"], cwd=ROOT,
                       env=env, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        stage = "建立合成帳號與租戶"
        seed = common + ["run", "--rm", "--no-deps", "-T"]
        for name in seed_vars:
            seed.extend(["-e", name])
        seed.extend(["api", "python", "tests/e2e_seed.py"])
        seeded = subprocess.run(seed, cwd=ROOT, env=env, check=False,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                text=True)
        if seeded.returncode:
            kinds = re.findall(r"(?m)^([\w.]+(?:Error|Exception)):.*$", seeded.stderr)
            print("合成資料建立錯誤類型：" + (kinds[-1] if kinds else "未知"),
                  file=sys.stderr)
            return 1
        stage = "執行瀏覽器案例"
        test_env = os.environ.copy()
        test_env.update({name: env[name] for name in seed_vars})
        test_env["E2E_BASE_URL"] = f"http://127.0.0.1:{env['E2E_WEB_PORT']}"
        test_env.pop("NO_COLOR", None)
        result = subprocess.run([npm, "run", "test:e2e"], cwd=WEB,
                                env=test_env, check=False)
        if result.returncode:
            logs = subprocess.run(common + ["logs", "--no-color", "api"], cwd=ROOT,
                                  env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, check=False)
            kinds = sorted(set(re.findall(
                r"\b(?:sqlalchemy|psycopg|redis)\.[\w.]+(?:Error|Exception)\b|\b(?:ValueError|TypeError|KeyError|AttributeError)\b",
                logs.stdout,
            )))
            print("API 錯誤類型：" + (", ".join(kinds) if kinds else "未擷取到例外類型"),
                  file=sys.stderr)
        return result.returncode
    except subprocess.CalledProcessError as exc:
        print(f"E2E {stage}失敗（exit {exc.returncode}）；未輸出測試憑證。",
              file=sys.stderr)
        return 1
    finally:
        subprocess.run(common + ["down", "--timeout", "10"], cwd=ROOT, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)


if __name__ == "__main__":
    sys.exit(main())
