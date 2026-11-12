"""檢查 Git 暫存區的機密檔案及內容（需安裝 Gitleaks）。

執行方式：python scripts/security/check_staged_secrets.py
設計為 Fail Closed（安全工具缺失即拒絕提交），不會輸出機密內容。
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)


def sensitive_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    filename = parts[-1]
    if filename == ".env.example":
        return False
    if filename == ".env" or filename.startswith(".env."):
        return True
    if filename in {"id_rsa", "id_ed25519", "credentials.json", "service-account.json", "secrets.json", "appsettings.production.json"}:
        return True
    if any(fnmatch.fnmatch(filename, f"*.{ext}") for ext in ("pem", "p12", "pfx", "key", "kdbx", "jks")):
        return True
    if filename.endswith(".log") or filename.endswith(".dump"):
        return True
    if "__pycache__" in parts:
        return True
    return False


def main() -> int:
    try:
        paths = [
            p.decode("utf-8", errors="surrogateescape")
            for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
            if p
        ]
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("安全檢查失敗：無法讀取 Git 暫存區。", file=sys.stderr)
        return 1

    if not paths:
        print("安全檢查：沒有新增或修改的暫存檔案。")
        return 0

    blocked = [p for p in paths if sensitive_path(p)]
    if blocked:
        print("安全檢查拒絕提交：暫存區包含高風險檔案路徑。", file=sys.stderr)
        print("請將檔案移出暫存區並處理機密輪替。", file=sys.stderr)
        return 1

    binary = shutil.which("gitleaks")
    if not binary:
        print("安全檢查拒絕提交：找不到 Gitleaks，請先安裝後再提交。", file=sys.stderr)
        return 1

    try:
        with tempfile.TemporaryDirectory(prefix="agent-staged-scan-") as tmp:
            root = Path(tmp)
            for path in paths:
                # 暫存區中的路徑不可超出臨時根目錄。
                relative = Path(path)
                if relative.is_absolute() or ".." in relative.parts:
                    print("安全檢查拒絕提交：存在不安全的檔案路徑。", file=sys.stderr)
                    return 1
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                # 只掃描 Git Index 內容，不掃描工作目錄可能未暫存的版本。
                staged = git("show", f":{path}")
                target.write_bytes(staged)
            result = subprocess.run(
                [binary, "dir", "--no-banner", "--redact", "--exit-code", "1", str(root)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                print(f"Gitleaks：已掃描 {len(paths)} 個暫存檔案，未發現機密。")
                return 0
            # 不回傳掃描輸出，避免未預期工具版本洩漏機密。
            print("安全檢查拒絕提交：Gitleaks 發現疑似機密，或掃描未成功。", file=sys.stderr)
            print("請在本機檢查並修正，必要時輪替密鑰。", file=sys.stderr)
            return 1
    except (OSError, subprocess.CalledProcessError):
        print("安全檢查拒絕提交：無法建立或掃描 Git 暫存快照。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
