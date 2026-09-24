from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class RunnerSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(REPO, self.root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        self.script = self.root / "scripts/sync-runner"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_sync(self, command: str, *, role: str = "source", write: str = "0") -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(RUNNER_SYNC_EXPECTED_ROLE=role, RUNNER_SYNC_WRITE=write)
        return subprocess.run(
            [str(self.script), command],
            cwd=self.root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_source_lock_and_check_cover_code_and_docs(self) -> None:
        locked = self.run_sync("lock", write="1")
        self.assertEqual(locked.returncode, 0, locked.stderr)
        checked = self.run_sync("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("docs (2)", checked.stdout)

    def test_lock_requires_explicit_write_guard(self) -> None:
        result = self.run_sync("lock")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RUNNER_SYNC_WRITE=1", result.stderr)

    def test_ci_role_mismatch_is_rejected(self) -> None:
        result = self.run_sync("check", role="consumer")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CI expected", result.stderr)

    def test_manifest_symlink_is_rejected(self) -> None:
        target = self.root / "docs/runner-sync.md"
        target.unlink()
        target.symlink_to("runner-release-process.md")
        result = self.run_sync("lock", write="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular file", result.stderr)

    def test_content_drift_is_rejected(self) -> None:
        locked = self.run_sync("lock", write="1")
        self.assertEqual(locked.returncode, 0, locked.stderr)
        with (self.root / "docs/runner-sync.md").open("a", encoding="utf-8") as handle:
            handle.write("\ndrift\n")
        result = self.run_sync("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content hash mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
