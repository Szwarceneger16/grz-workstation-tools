"""Repository-local public policy reads the same index as scanned content."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("zsh") and shutil.which("git"), "requires zsh and git")
class IndexedSafetyPolicyTests(unittest.TestCase):
    def test_policy_worktree_changes_cannot_authorize_indexed_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "manifests").mkdir()
            shutil.copy2(ROOT / "scripts/audit-public-safety", root / "scripts/audit-public-safety")
            env = {"PATH": os.environ["PATH"], "HOME": directory,
                   "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

            def git(*args):
                return subprocess.run(["git", *args], cwd=root, env=env, check=True,
                                      capture_output=True, text=True).stdout.strip()

            def audit():
                return subprocess.run(["zsh", "scripts/audit-public-safety"], cwd=root,
                                      env=env, capture_output=True, text=True, timeout=10)

            git("init", "-q")
            payload = "PASS" + "WORD=${FIXTURE_INPUT}"
            (root / "fixture.txt").write_text(payload)
            git("add", "fixture.txt", "scripts/audit-public-safety")
            policy = root / "manifests/public-safety-allowlist.json"
            reviewed = json.dumps([{"path": "fixture.txt", "category": "secret-word",
                                    "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                                    "reason": "Reviewed synthetic reference"}])
            policy.write_text(reviewed)
            self.assertEqual(audit().returncode, 1)  # Untracked policy is not authority.
            git("add", "manifests/public-safety-allowlist.json")
            self.assertEqual(audit().returncode, 0)
            policy.write_text("[]")
            self.assertEqual(audit().returncode, 0)  # Still uses indexed reviewed bytes.
            git("add", "manifests/public-safety-allowlist.json")
            policy.write_text(reviewed)
            self.assertEqual(audit().returncode, 1)  # Worktree cannot add authority.
            policy.unlink()  # Disposable fixture only.
            policy.symlink_to("../fixture.txt")
            git("add", "manifests/public-safety-allowlist.json")
            self.assertEqual(audit().returncode, 2)
            policy.unlink()
            policy.mkdir()
            nested = policy / "nested.json"
            nested.write_text(reviewed)
            git("add", "--all")
            self.assertEqual(audit().returncode, 2)
            nested.unlink()
            policy.rmdir()
            policy.write_text(reviewed)
            git("add", "manifests/public-safety-allowlist.json")
            oid = git("rev-parse", ":manifests/public-safety-allowlist.json")
            git("update-index", "--force-remove", "manifests/public-safety-allowlist.json")
            record = f"100644 {oid} 1\tmanifests/public-safety-allowlist.json\n"
            subprocess.run(["git", "update-index", "--index-info"], cwd=root, env=env,
                           input=record, text=True, check=True, capture_output=True)
            self.assertEqual(audit().returncode, 2)
