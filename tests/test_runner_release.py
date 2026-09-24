from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE_HELPER = Path(__file__).resolve().parents[1] / "scripts/propose-runner-release"


class RunnerReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "docs").mkdir()
        shutil.copy2(SOURCE_HELPER, self.root / "scripts/propose-runner-release")
        os.chmod(self.root / "scripts/propose-runner-release", 0o755)
        self.write("scripts/runner-canonical-files.txt", "code.txt\nscripts/runner-canonical-docs.txt\nscripts/runner-canonical-files.txt\n")
        self.write("scripts/runner-canonical-docs.txt", "docs/contract.md\n")
        self.write("code.txt", "runner v1\n")
        self.write("docs/contract.md", "contract v1\n")
        self.write_locks()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Runner Test")
        self.git("config", "user.email", "runner-test@example.invalid")
        self.commit("initial runner")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str) -> None:
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    def manifest(self, relative: str) -> list[str]:
        return [line for line in (self.root / relative).read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]

    def write_locks(self) -> None:
        for manifest, lock in (
            ("scripts/runner-canonical-files.txt", "runner.lock"),
            ("scripts/runner-canonical-docs.txt", "runner.docs.lock"),
        ):
            records = []
            for relative in self.manifest(manifest):
                digest = hashlib.sha256((self.root / relative).read_bytes()).hexdigest()
                records.append(f"{digest}  {relative}\n")
            self.write(lock, "".join(records))

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=check, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def commit(self, subject: str, *, sign: bool = False) -> str:
        self.git("add", ".")
        args = ["commit", "-m", subject]
        if sign:
            args.insert(1, "-S")
        self.git(*args)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def helper(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.root / "scripts/propose-runner-release"), *args],
            cwd=self.root,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **getattr(self, "trust_environment", {})},
        )

    def inspect(self) -> dict[str, object]:
        output = self.root / "inspection.json"
        self.helper("inspect", "--head-ref", "HEAD", "--json-out", str(output))
        return json.loads(output.read_text(encoding="utf-8"))

    def prepare_release(self, version: str = "0.1.0") -> tuple[str, dict[str, str]]:
        body = self.root / "body.md"
        self.helper("update", "--head-ref", "HEAD", "--body-out", str(body))
        release = self.root / "runner.release"
        if version != "0.1.0":
            lines = release.read_text(encoding="utf-8").splitlines()
            lines[0] = f"version {version}"
            release.write_text("\n".join(lines) + "\n", encoding="utf-8")
        parent = self.commit("chore(runner): freeze release")
        values = dict(line.split(" ", 1) for line in release.read_text(encoding="utf-8").splitlines())
        return parent, values

    def generate_key(self, name: str) -> tuple[Path, str, Path]:
        private = Path(self.temporary.name) / name
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(private)],
            check=True,
        )
        public_line = private.with_suffix(".pub").read_text(encoding="utf-8").strip()
        allowed = self.root / f"{name}.allowed_signers"
        allowed.write_text(f"{name}@example.invalid namespaces=\"git\" {public_line}\n", encoding="utf-8")
        fingerprint = subprocess.run(
            ["ssh-keygen", "-lf", str(private.with_suffix(".pub")), "-E", "sha256"],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout.split()[1]
        return private, fingerprint, allowed

    def test_first_shared_snapshot_proposes_one_initial_release(self) -> None:
        data = self.inspect()
        self.assertTrue(data["needs_release"])
        self.assertEqual(data["suggested_version"], "0.1.0")
        body = self.root / "body.md"
        self.helper("update", "--head-ref", "HEAD", "--body-out", str(body))
        self.assertTrue((self.root / "runner.release").is_file())
        self.assertIn("Proposed tag: `runner-v0.1.0`", body.read_text(encoding="utf-8"))

    def test_manual_minor_version_is_preserved(self) -> None:
        body = self.root / "body.md"
        self.helper("update", "--head-ref", "HEAD", "--body-out", str(body))
        release = self.root / "runner.release"
        release.write_text(release.read_text(encoding="utf-8").replace("version 0.1.0", "version 1.0.0"), encoding="utf-8")
        self.helper("update", "--head-ref", "HEAD", "--body-out", str(body))
        self.assertTrue(release.read_text(encoding="utf-8").startswith("version 1.0.0\n"))

    def test_pending_release_blocks_shared_change_but_not_unrelated_change(self) -> None:
        parent, _ = self.prepare_release()
        # An unverified tag never unlocks shared changes, regardless of issues.
        self.git("tag", "runner-v0.1.0", parent)
        self.write("README.md", "unrelated\n")
        unrelated = self.commit("docs: unrelated")
        output = self.root / "state.json"
        ok = self.helper(
            "release-state", "--main-ref", parent, "--base-ref", parent,
            "--head-ref", unrelated, "--json-out", str(output),
            check=False,
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.write("code.txt", "runner v2\n")
        self.write_locks()
        shared = self.commit("feat: shared")
        blocked = self.helper(
            "release-state", "--main-ref", parent, "--base-ref", unrelated,
            "--head-ref", shared, "--json-out", str(output),
            check=False,
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("awaiting signature", blocked.stderr)

    def test_two_independent_ssh_signatures_verify(self) -> None:
        parent, release = self.prepare_release()
        commit_key, commit_fingerprint, commit_allowed = self.generate_key("commit-key")
        release_key, release_fingerprint, release_allowed = self.generate_key("release-key")
        self.git("config", "gpg.format", "ssh")
        self.git("config", "user.signingkey", str(commit_key))
        self.git("switch", "--detach", parent)
        self.git("commit", "--allow-empty", "-S", "-m", "chore(runner): attest release v0.1.0")
        target = self.git("rev-parse", "HEAD").stdout.strip()
        message = "\n".join(
            (
                "runner-release-v1",
                "version 0.1.0",
                f"release-parent {parent}",
                f"code-tree-sha256 {release['code-tree-sha256']}",
                f"docs-tree-sha256 {release['docs-tree-sha256']}",
            )
        )
        self.git(
            "-c", "gpg.format=ssh", "-c", f"user.signingkey={release_key}",
            "tag", "-s", "runner-v0.1.0", target, "-m", message,
        )
        output = self.root / "verified.json"
        result = self.helper(
            "verify-tag", "--tag", "runner-v0.1.0", "--expected-commit", target,
            "--main-ref", "main", "--commit-allowed-signers", str(commit_allowed),
            "--commit-fingerprint", commit_fingerprint,
            "--release-allowed-signers", str(release_allowed),
            "--release-fingerprint", release_fingerprint,
            "--json-out", str(output), check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["release_parent"], parent)

    def test_lightweight_tag_is_rejected(self) -> None:
        parent, _ = self.prepare_release()
        self.git("tag", "runner-v0.1.0", parent)
        result = self.helper(
            "verify-tag", "--tag", "runner-v0.1.0", "--main-ref", "main",
            "--commit-allowed-signers", "missing", "--commit-fingerprint", "SHA256:invalid1",
            "--release-allowed-signers", "missing", "--release-fingerprint", "SHA256:invalid2",
            "--json-out", str(self.root / "out.json"), check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("annotated", result.stderr)

    def signed_release(self, *, wrong_parent=False):
        frozen, release = self.prepare_release()
        parent = frozen
        if wrong_parent:
            self.write("unrelated.txt", "unrelated main advancement")
            parent = self.commit("unrelated commit after freeze")
        commit_key, commit_fp, commit_allowed = self.generate_key("commit-key")
        release_key, release_fp, release_allowed = self.generate_key("release-key")
        self.trust_environment = {
            "RUNNER_COMMIT_ALLOWED_SIGNER_B64": base64.b64encode(commit_allowed.read_bytes()).decode(),
            "RUNNER_COMMIT_SIGNING_FINGERPRINT": commit_fp,
            "RUNNER_RELEASE_ALLOWED_SIGNER_B64": base64.b64encode(release_allowed.read_bytes()).decode(),
            "RUNNER_RELEASE_SIGNING_FINGERPRINT": release_fp,
        }
        self.git("config", "gpg.format", "ssh")
        self.git("config", "user.signingkey", str(commit_key))
        self.git("switch", "--detach", parent)
        self.git("commit", "--allow-empty", "-S", "-m", "attest release")
        message = "\n".join(["runner-release-v1", "version 0.1.0", f"release-parent {parent}",
                            f"code-tree-sha256 {release['code-tree-sha256']}",
                            f"docs-tree-sha256 {release['docs-tree-sha256']}"])
        self.git("-c", f"user.signingkey={release_key}", "tag", "-s", "runner-v0.1.0", "-m", message)
        self.git("switch", "main")
        return frozen

    def test_unsigned_highest_tag_cannot_become_release_baseline(self):
        self.git("tag", "runner-v9.0.0")
        result = self.helper("inspect", "--json-out", str(self.root / "state.json"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "state.json").exists())

    def test_trusted_state_check_recomputes_candidate_locks(self):
        base = self.git("rev-parse", "HEAD").stdout.strip()
        self.write("code.txt", "drift without lock update")
        head = self.commit("missing lock update")
        result = self.helper("release-state", "--main-ref", base, "--base-ref", base,
                             "--head-ref", head, "--json-out", str(self.root / "state.json"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content hash mismatch", result.stderr)

    def test_later_unrelated_parent_is_rejected_despite_both_valid_signatures(self):
        self.signed_release(wrong_parent=True)
        result = self.helper("inspect", "--json-out", str(self.root / "state.json"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact frozen", result.stderr)

    def test_verified_tag_unlocks_without_an_issue_and_proposes_next_patch(self):
        self.signed_release()
        self.assertFalse(self.inspect()["needs_release"])
        self.write("code.txt", "runner v2\n")
        self.write_locks()
        self.commit("feat: shared change (#12)")
        data = self.inspect()
        self.assertFalse(data["pending_release"])
        self.assertTrue(data["needs_release"])
        self.assertEqual(data["previous_tag"], "runner-v0.1.0")
        self.assertEqual(data["suggested_version"], "0.1.1")
        self.assertEqual(data["merged_prs"], [12])

    def test_unrelated_pr_is_not_in_shared_pr_list(self):
        self.write("README.md", "unrelated\n")
        self.commit("docs: unrelated (#123)")
        self.write("code.txt", "runner v2\n")
        self.write_locks()
        self.commit("feat: shared (#456)")
        self.assertEqual(self.inspect()["merged_prs"], [456])

    def test_invalid_manual_version_fails_instead_of_resetting_to_default(self):
        body = Path(self.temporary.name) / "body.md"
        self.helper("update", "--head-ref", "main", "--body-out", str(body))
        release = self.root / "runner.release"
        release.write_text(release.read_text().replace("version 0.1.0", "version 0.0.0"))
        result = self.helper("update", "--head-ref", "main", "--body-out", str(body), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manual release version", result.stderr)
        self.assertTrue(release.read_text().startswith("version 0.0.0"))

    def test_symlink_release_metadata_cannot_write_outside_worktree(self):
        outside = Path(self.temporary.name) / "outside"
        outside.write_text("untouched")
        (self.root / "runner.release").symlink_to(outside)
        result = self.helper("update", "--head-ref", "main", "--body-out", str(self.root / "body.md"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_text(), "untouched")

    def test_three_shared_merges_aggregate_without_tags_or_empty_metadata_commits(self):
        self.git("switch", "-c", "automation/runner-release-next")
        body = Path(self.temporary.name) / "body.md"
        self.helper("update", "--head-ref", "main", "--body-out", str(body))
        self.commit("prepare first draft")
        for number in (2, 3):
            self.git("switch", "main")
            self.write("code.txt", f"runner v{number}\n")
            self.write_locks()
            self.commit(f"shared change (#{number})")
            self.git("switch", "automation/runner-release-next")
            self.git("merge", "--no-edit", "main")
            self.helper("update", "--head-ref", "main", "--body-out", str(body))
            self.commit(f"refresh draft {number}")
        before = self.git("rev-parse", "HEAD").stdout
        self.helper("update", "--head-ref", "main", "--body-out", str(body))
        self.assertEqual(self.git("diff", "--name-only").stdout, "")
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, before)
        self.assertEqual(self.git("tag", "--list").stdout, "")
        self.assertEqual(self.git("diff", "--name-only", "main...HEAD").stdout, "runner.release\n")


if __name__ == "__main__":
    unittest.main()
