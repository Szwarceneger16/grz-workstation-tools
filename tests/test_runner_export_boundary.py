"""Repository safety policy must stay outside the synchronized runner."""
from pathlib import Path
import tempfile
import unittest

import test_runner_review_regressions as fixtures

ROOT = Path(__file__).resolve().parents[1]
SCANNER = "scripts/audit-public-safety"
POLICY = "manifests/public-safety-allowlist.json"


class RunnerExportBoundaryTests(unittest.TestCase):
    def test_scanner_and_policy_are_not_exported_selected_or_locked(self):
        for name in ("scripts/runner-canonical-files.txt", "scripts/runner-canonical-docs.txt",
                     "scripts/runner-sync-files.txt", "scripts/runner-sync-docs.txt",
                     "runner.lock", "runner.docs.lock"):
            path = ROOT / name
            if not path.exists():
                continue  # Selection manifests belong only to consumers.
            entries = {line.split("  ", 1)[-1] for line in path.read_text().splitlines()
                       if line and not line.startswith("#")}
            with self.subTest(name=name):
                self.assertNotIn(SCANNER, entries)
                self.assertNotIn(POLICY, entries)
                if name.endswith("files.txt") or name == "runner.lock":
                    self.assertIn("scripts/check-repo", entries)
        self.assertTrue((ROOT / SCANNER).is_file())

    def test_local_scanner_change_does_not_change_runner_locks(self):
        helper = fixtures.RunnerDocumentationTests()
        for role in ("source", "consumer"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                helper.fixture(root, role)
                scanner = root / SCANNER
                scanner.write_text("repository-local scanner revision one\n")
                before = [(root / name).read_bytes() for name in ("runner.lock", "runner.docs.lock")]
                scanner.write_text("repository-local scanner revision two\n")
                result = helper.execute(root, [f"RUNNER_SYNC_EXPECTED_ROLE={role}",
                    "RUNNER_SYNC_WRITE=0", "./scripts/sync-runner", "check"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(before, [(root / name).read_bytes() for name in ("runner.lock", "runner.docs.lock")])


if __name__ == "__main__":
    unittest.main()
