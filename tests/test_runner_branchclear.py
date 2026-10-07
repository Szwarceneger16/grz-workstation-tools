"""Isolated regression tests for squash-aware, fail-closed branchclear."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / (
    "packages/zsh-tools/install/.zsh_scripts/functions/branchclear.zsh"
)
REPO = "test-owner/branchclear-test"
ORIGIN = f"https://github.com/{REPO}.git"


@unittest.skipUnless(shutil.which("zsh"), "zsh is required")
class BranchclearTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="branchclear-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bare = self.root / "origin.git"
        self.seed = self.root / "seed"
        self.work = self.root / "checkout"
        fakebin = self.root / "fake-bin"
        fakebin.mkdir()
        self.env = {
            **os.environ,
            "HOME": str(self.root),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GH_PROMPT_DISABLED": "1",
            "GH_TEST_ROWS": "",
            "GH_TEST_FAIL": "0",
            "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
        }
        self.git("init", "-q", "-b", "main", str(self.seed), cwd=self.root)
        self.git("config", "user.name", "Fixture", cwd=self.seed)
        self.git("config", "user.email", "fixture@example.invalid", cwd=self.seed)
        (self.seed / "README").write_text("initial\n")
        self.git("add", "README", cwd=self.seed)
        self.git("commit", "-q", "-m", "Initial", cwd=self.seed)
        self.git("init", "-q", "--bare", str(self.bare), cwd=self.root)
        self.git("remote", "add", "origin", str(self.bare), cwd=self.seed)
        self.git("push", "-q", "origin", "main", cwd=self.seed)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.bare)
        self.git("clone", "-q", str(self.bare), str(self.work), cwd=self.root)
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("remote", "set-url", "origin", ORIGIN)
        # The declared origin is GitHub; all transport stays inside the fixture.
        self.git("config", f"url.file://{self.bare}.insteadOf", ORIGIN)
        gh = fakebin / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            '[ "$1" = api ] || exit 20\n'
            'case "$*" in\n'
            '  *"repos/test-owner/branchclear-test/pulls"*) ;;\n'
            "  *) exit 21 ;;\n"
            "esac\n"
            '[ "$GH_TEST_FAIL" = 1 ] && exit 22\n'
            'printf "%s\\n" "$GH_TEST_ROWS"\n'
        )
        gh.chmod(0o755)

    def git(self, *args, cwd=None, check=True):
        result = subprocess.run(
            ["git", *args], cwd=cwd or self.work, env=self.env,
            capture_output=True, text=True,
        )
        if check and result.returncode:
            self.fail(f"Fixture git {args} failed: {result.stderr}")
        return result

    def rev(self, ref):
        return self.git("rev-parse", ref).stdout.strip()

    def exists(self, branch):
        return self.git(
            "show-ref", "--verify", "--quiet", f"refs/heads/{branch}",
            check=False,
        ).returncode == 0

    def invoke(self, *args):
        command = f"source {shlex.quote(str(SOURCE))}; branchclear"
        if args:
            command += " " + " ".join(map(shlex.quote, args))
        p = subprocess.run(
            ["zsh", "-f", "-c", command], cwd=self.work, env=self.env,
            text=True, capture_output=True,
        )
        self.assertEqual(p.returncode, 0, p.stdout + "\n" + p.stderr)
        return p.stdout + p.stderr

    def squash(self, branch="codex/example"):
        self.git("switch", "-q", "-c", branch)
        (self.work / "feature.txt").write_text("version 1\n")
        self.git("add", "feature.txt")
        self.git("commit", "-q", "-m", "Feature one")
        old = self.rev("HEAD")
        (self.work / "feature.txt").write_text("version 2\n")
        self.git("add", "feature.txt")
        self.git("commit", "-q", "-m", "Feature two")
        head = self.rev("HEAD")
        self.git("push", "-q", "-u", "origin", branch)
        self.git("update-ref", "refs/pull/76/head", head, cwd=self.bare)
        self.git("switch", "-q", "main")
        self.git("merge", "--squash", branch)
        self.git("commit", "-q", "-m", "Squashed feature")
        merged = self.rev("HEAD")
        self.git("push", "-q", "origin", "main")
        self.git("branch", "-f", branch, old)
        self.git("push", "-q", "origin", "--delete", branch)
        self.env["GH_TEST_ROWS"] = f"76\t{head}\t{REPO}\tmain\t{branch}\t{merged}"
        return branch, old, head, merged

    def test_stale_local_tip_is_deleted_after_verified_squash(self):
        branch, old, head, _ = self.squash()
        self.assertNotEqual(old, head)
        base = self.git("merge-base", "origin/main", branch).stdout.strip()
        conflict = self.git(
            "merge-tree", "--write-tree", f"--merge-base={base}",
            "origin/main", branch, check=False,
        )
        self.assertEqual(conflict.returncode, 1)
        self.assertIn("verified merged GitHub PR #76", self.invoke())
        self.assertFalse(self.exists(branch))

    def test_pipe_is_valid_inside_deleted_branch_name(self):
        branch, *_ = self.squash("codex/pipe|name")
        self.assertIn("verified merged GitHub PR #76", self.invoke())
        self.assertFalse(self.exists(branch))

    def test_fetches_pr_head_if_local_object_was_pruned(self):
        branch, _, head, _ = self.squash("codex/head-fetched-from-pr")
        self.git("reflog", "expire", "--expire=now", "--all")
        self.git("gc", "--prune=now")
        missing = self.git("cat-file", "-e", f"{head}^{{commit}}", check=False)
        self.assertNotEqual(missing.returncode, 0, "Fixture must lack PR head")
        self.assertIn("verified merged GitHub PR #76", self.invoke())
        self.assertFalse(self.exists(branch))

    def test_local_extra_commit_is_retained(self):
        branch, *_ = self.squash()
        self.git("switch", "-q", branch)
        (self.work / "extra.txt").write_text("not reviewed\n")
        self.git("add", "extra.txt")
        self.git("commit", "-q", "-m", "Local extra")
        self.git("switch", "-q", "main")
        self.assertIn("Skipping", self.invoke())
        self.assertTrue(self.exists(branch))

    def test_foreign_head_and_invalid_merge_are_rejected(self):
        branch, _, head, merged = self.squash()
        valid = self.env["GH_TEST_ROWS"]
        self.env["GH_TEST_ROWS"] = valid.replace(REPO, "attacker/fork")
        self.invoke()
        self.assertTrue(self.exists(branch))
        self.env["GH_TEST_ROWS"] = f"76\t{head}\t{REPO}\tmain\t{branch}\t{head}"
        self.invoke()
        self.assertTrue(self.exists(branch))
        self.env["GH_TEST_ROWS"] = valid

    def test_api_failure_preserves_clean_worktree(self):
        branch, *_ = self.squash()
        linked = self.root / "linked"
        self.git("worktree", "add", "-q", str(linked), branch)
        self.env["GH_TEST_FAIL"] = "1"
        self.assertIn("merge conflicts", self.invoke())
        self.assertTrue(linked.is_dir())
        self.assertTrue(self.exists(branch))

    def test_dirty_worktree_preserved_after_positive_pr_proof(self):
        branch, *_ = self.squash()
        linked = self.root / "linked"
        self.git("worktree", "add", "-q", str(linked), branch)
        (linked / "important.txt").write_text("important\n")
        self.assertIn("linked worktree contains", self.invoke())
        self.assertTrue(self.exists(branch))
        self.assertEqual((linked / "important.txt").read_text(), "important\n")

    def test_clean_worktree_deleted_after_positive_pr_proof(self):
        branch, *_ = self.squash()
        linked = self.root / "linked"
        self.git("worktree", "add", "-q", str(linked), branch)
        self.assertIn("verified merged GitHub PR #76", self.invoke())
        self.assertFalse(self.exists(branch))
        self.assertFalse(linked.exists())

    def test_normal_merge_requires_no_api(self):
        branch = "codex/normal"
        self.git("switch", "-q", "-c", branch)
        (self.work / "normal.txt").write_text("normal\n")
        self.git("add", "normal.txt")
        self.git("commit", "-q", "-m", "Normal")
        self.git("push", "-q", "-u", "origin", branch)
        self.git("switch", "-q", "main")
        self.git("merge", "--ff-only", branch)
        self.git("push", "-q", "origin", "main")
        self.git("push", "-q", "origin", "--delete", branch)
        self.env["GH_TEST_FAIL"] = "1"
        self.assertIn("ancestor of", self.invoke())
        self.assertFalse(self.exists(branch))

    def test_force_explicitly_bypasses_merge_proof(self):
        branch, *_ = self.squash()
        self.env["GH_TEST_FAIL"] = "1"
        self.assertIn("explicit --force", self.invoke("--force"))
        self.assertFalse(self.exists(branch))


if __name__ == "__main__":
    unittest.main()
