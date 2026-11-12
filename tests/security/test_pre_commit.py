"""以實際 git commit 驗證本機機密防護。所有測試資料均為合成資料。"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".githooks" / "pre-commit"
SCANNER = ROOT / "scripts" / "security" / "check_staged_secrets.py"


def run(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=repo, env=env, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


class PreCommitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="git-secret-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / ".githooks").mkdir()
        (self.repo / "scripts" / "security").mkdir(parents=True)
        shutil.copy2(HOOK, self.repo / ".githooks" / "pre-commit")
        shutil.copy2(SCANNER, self.repo / "scripts" / "security" / SCANNER.name)
        for args in (
            ("init", "-q"),
            ("config", "--local", "user.name", "Security Test"),
            ("config", "--local", "user.email", "security-test@example.invalid"),
            ("config", "--local", "core.hooksPath", ".githooks"),
        ):
            self.assertEqual(run(self.repo, "git", *args).returncode, 0)

    def commit(self, name: str, content: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        (self.repo / name).write_text(content, encoding="utf-8")
        self.assertEqual(run(self.repo, "git", "add", "-f", name).returncode, 0)
        return run(self.repo, "git", "commit", "-m", "測試：隔離提交", env=env)

    def count(self) -> str:
        return run(self.repo, "git", "rev-list", "--all", "--count").stdout.strip()

    def test_01_normal_commit(self) -> None:
        result = self.commit("safe.txt", "ordinary project text\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Gitleaks", result.stdout + result.stderr)
        self.assertEqual(self.count(), "1")

    def test_02_env_rejected_without_content(self) -> None:
        marker = "private-value-for-test-only"
        result = self.commit(".env", "PASSWORD=" + marker + "\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(), "0")
        self.assertNotIn(marker, result.stdout + result.stderr)

    def test_03_official_dummy_key_rejected(self) -> None:
        # Gitleaks 官方 AWS 規則的合成測試值，執行時組合避免測試程式被誤掃。
        dummy = "AKIA" + "LALEMEL33243OLIB"
        (self.repo / "sample.py").write_text("key = '" + dummy + "'\n", encoding="utf-8")
        direct = run(self.repo, "gitleaks", "dir", "--no-banner", "--redact", "--exit-code", "1", ".")
        self.assertEqual(direct.returncode, 1, "Gitleaks 未偵測官方合成測試值")
        self.assertNotIn(dummy, direct.stdout + direct.stderr)
        self.assertEqual(run(self.repo, "git", "add", "sample.py").returncode, 0)
        result = run(self.repo, "git", "commit", "-m", "測試：隔離提交")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(), "0")
        self.assertNotIn(dummy, result.stdout + result.stderr)

    def test_04_missing_gitleaks_fails_closed(self) -> None:
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join(
            part for part in env["PATH"].split(os.pathsep)
            if "gitleaks.gitleaks" not in part.lower() and "winget\\links" not in part.lower()
        )
        result = self.commit("safe.txt", "safe\n", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(), "0")
        self.assertIn("Gitleaks", result.stderr)

    def test_05_staged_secret_overrides_safe_worktree(self) -> None:
        dummy = "AKIA" + "LALEMEL33243OLIB"
        path = self.repo / "sample.py"
        path.write_text("key = '" + dummy + "'\n", encoding="utf-8")
        self.assertEqual(run(self.repo, "git", "add", "sample.py").returncode, 0)
        path.write_text("safe = True\n", encoding="utf-8")
        result = run(self.repo, "git", "commit", "-m", "測試：隔離提交")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(), "0")
        self.assertNotIn(dummy, result.stdout + result.stderr)

    def test_06_filename_does_not_leak(self) -> None:
        marker = "private-filename-marker"
        result = self.commit(".env." + marker, "safe\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count(), "0")
        self.assertNotIn(marker, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
