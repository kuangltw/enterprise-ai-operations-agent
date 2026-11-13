"""Launch and remove only this run's disposable Docker resources."""

import argparse
import os
import secrets
import subprocess
from pathlib import Path


POSTGRES = "postgres@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139"
MINIO = (
    "public.ecr.aws/y9w4h2u9/minio@"
    "sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
)
CLIENT = (
    "enterprise-ai-operations-agent-api@"
    "sha256:8a8292c6621a9b5cad51e0701a79808c9cb4444d152f4356eb53b48c45a10ed5"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--followup", action="store_true",
                        help="Run only the downgrade, backend recovery and explicit cancellation checks.")
    followup = parser.parse_args().followup
    run = "storage-proof-" + secrets.token_hex(8)
    env = dict(os.environ, POSTGRES_PASSWORD=secrets.token_hex(24),
               MINIO_ROOT_USER="proof-bootstrap", MINIO_ROOT_PASSWORD=secrets.token_hex(24))
    containers = []

    def docker(*args, **kwargs):
        return subprocess.run(["docker", "--context", "desktop-linux", *args],
                              env=env, check=True, timeout=180, **kwargs)

    def start(suffix, alias, *args):
        name = f"{run}-{suffix}"
        container = docker(
            "run", "--detach", "--pull", "never", "--name", name, "--label",
            f"storage-safety-proof={run}", "--network", network, "--network-alias", alias,
            *args, capture_output=True, text=True,
        ).stdout.strip()
        containers.append(container)

    # Use the returned network/container IDs for teardown. No named volumes, existing
    # service mounts, host ports, or routing outside this internal network.
    network = docker("network", "create", "--internal", "--label",
                     f"storage-safety-proof={run}", run, capture_output=True, text=True).stdout.strip()
    print(f"Isolated run {run}", flush=True)
    try:
        start("postgres", "proof-db", "--tmpfs", "/var/lib/postgresql/data",
              "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_DB=storage_proof",
              POSTGRES)
        start("minio", "proof-minio", "--tmpfs", "/data",
              "--env", "MINIO_ROOT_USER", "--env", "MINIO_ROOT_PASSWORD",
              MINIO, "server", "/data")
        start("client", "proof-client",
              "--mount", f"type=bind,source={Path(__file__).resolve().parent},target=/proof,readonly",
              "--env", "POSTGRES_PASSWORD", "--env", "MINIO_ROOT_USER",
              "--env", "MINIO_ROOT_PASSWORD", "--env", f"PROOF_RUN={run}",
              "--entrypoint", "python", CLIENT, "-u", "/proof/checks.py",
              *(["--followup"] if followup else []))
        client = containers[-1]
        code = int(docker("wait", client, capture_output=True, text=True).stdout.strip())
        docker("logs", client)
        if code:
            raise SystemExit(code)
    finally:
        try:
            if containers:
                docker("rm", "--force", *reversed(containers))
        finally:
            docker("network", "rm", network)


if __name__ == "__main__":
    main()
