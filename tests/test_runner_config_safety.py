"""Regression tests for shared config validation and staged public-safety scans."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_runner_review_regressions as fixtures

ROOT = Path(__file__).resolve().parents[1]


class RunnerPrefixTests(unittest.TestCase):
    def check_config(self, role, prefix, command="check", remote=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = fixtures.RunnerDocumentationTests()
            helper.fixture(root, role)
            config = f"RUNNER_SYNC_ROLE={role}\n"
            if prefix is not None:
                config += f"RUNNER_ENV_PREFIX={prefix}\n"
            if remote is not None:
                config += f"RUNNER_CANONICAL_REMOTE={remote}\n"
            (root / "runner.conf").write_text(config)
            before = [(root / name).read_bytes() for name in ("runner.lock", "runner.docs.lock")]
            result = helper.execute(root, [
                f"RUNNER_SYNC_EXPECTED_ROLE={role}", f"RUNNER_SYNC_WRITE={int(command == 'lock')}",
                "./scripts/sync-runner", command,
            ])
            self.assertEqual(before, [(root / name).read_bytes() for name in ("runner.lock", "runner.docs.lock")])
            return result

    def test_invalid_prefixes_fail_before_check_or_lock(self):
        for role in ("source", "consumer"):
            for prefix in (None, "", "TOOLS-WORK", "foo/bar", "9TOOLS", "foo.bar", "foo:bar", "foo@bar", "foo+bar", "foo%bar"):
                for command in ("check", "lock"):
                    with self.subTest(role=role, prefix=prefix, command=command):
                        result = self.check_config(role, prefix, command)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("RUNNER_ENV_PREFIX", result.stderr)

    def test_valid_identifiers_and_remote_url_remain_supported(self):
        for role in ("source", "consumer"):
            for prefix in ("FIXTURE", "_tools", "tools_2"):
                with self.subTest(role=role, prefix=prefix):
                    result = self.check_config(role, prefix, remote="https://example.invalid/owner/runner.git")
                    self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(shutil.which("zsh") and shutil.which("git"), "requires zsh and git")
class PublicSafetyPathTests(unittest.TestCase):
    def audit(self, content, unstaged=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts/audit-public-safety", root / "scripts/audit-public-safety")
            sample = root / "fixture.txt"
            sample.write_text(content)
            env = {"PATH": os.environ["PATH"], "HOME": directory,
                   "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
            subprocess.run(["git", "init", "-q", root], check=True, env=env, capture_output=True)
            subprocess.run(["git", "add", "--", "scripts/audit-public-safety", "fixture.txt"],
                           cwd=root, check=True, env=env, capture_output=True)
            if unstaged is not None:
                sample.write_text(unstaged)
            return subprocess.run(["zsh", "scripts/audit-public-safety"], cwd=root, env=env,
                                  text=True, capture_output=True, timeout=10)

    def test_runner_placeholder_is_the_only_exempt_home(self):
        allowed = "/" + "home/runner"
        self.assertEqual(self.audit(allowed + "/work " + allowed + "/cache\n").returncode, 0)
        for personal in ("/" + "home/fixture-person", "/" + "Users/fixture-person",
                         allowed + "-other", allowed + "_other", allowed + ".other", "/" + "Users/runner"):
            for content in (personal + " " + allowed, allowed + " " + personal, allowed + "\n" + personal):
                with self.subTest(personal=personal, content_order=content.startswith(allowed)):
                    result = self.audit(content + "\n")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("[home-path]: fixture.txt", result.stderr)
                    self.assertNotIn(personal, result.stdout + result.stderr)
                    self.assertNotIn(allowed, result.stdout + result.stderr)

    def test_many_matches_do_not_hide_findings_via_pipefail(self):
        allowed, personal = "/" + "home/runner", "/" + "home/fixture-person"
        result = self.audit((personal + " " + allowed + "\n") * 10000)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.count("[home-path]: fixture.txt"), 1)
        self.assertNotIn(personal, result.stderr)

    def test_scan_reads_staged_content_not_worktree(self):
        allowed, personal = "/" + "home/runner", "/" + "home/fixture-person"
        self.assertNotEqual(self.audit(allowed + " " + personal, unstaged=allowed).returncode, 0)
        self.assertEqual(self.audit(allowed, unstaged=personal).returncode, 0)
