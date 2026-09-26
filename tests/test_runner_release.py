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

    def test_snapshot_rejects_symlink_locks_even_with_valid_record_bytes(self):
        for relative in ("runner.lock", "runner.docs.lock"):
            with self.subTest(relative=relative):
                path = self.root / relative
                payload = path.read_text()
                path.unlink()
                path.symlink_to(payload)
                self.commit("malicious symlink lock")
                result = self.helper("inspect", "--json-out", str(self.root / "inspection.json"), check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("regular file", result.stderr)
                self.assertIn(relative, result.stderr)
                path.unlink()
                path.write_text(payload)

    def test_snapshot_rejects_mode_drift_without_lock_update(self):
        (self.root / "code.txt").chmod(0o755)
        self.commit("mode drift")
        result = self.helper("inspect", "--json-out", str(self.root / "inspection.json"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode mismatch", result.stderr)

    def test_pending_metadata_is_immutable_in_bytes_mode_and_presence(self):
        base, _ = self.prepare_release()
        path = self.root / "runner.release"
        payload = path.read_text()
        for mutation in ("version", "mode", "delete", "symlink"):
            with self.subTest(mutation=mutation):
                if path.exists() or path.is_symlink():
                    path.unlink()
                if mutation == "symlink":
                    path.symlink_to(payload)
                elif mutation != "delete":
                    path.write_text(payload.replace("version 0.1.0", "version 0.2.0") if mutation == "version" else payload)
                    path.chmod(0o755 if mutation == "mode" else 0o644)
                head = self.commit("mutate frozen metadata")
                result, _ = self.release_state_result(base, head)
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, "immutable|regular file")

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
                mode = "100755" if (self.root / relative).stat().st_mode & 0o100 else "100644"
                records.append(f"{mode} {digest}  {relative}\n")
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
        self.trust_environment = {}
        for role in ("commit", "release"):
            _, fingerprint, allowed = self.generate_key(role)
            self.trust_environment[f"RUNNER_{role.upper()}_ALLOWED_SIGNER_B64"] = base64.b64encode(allowed.read_bytes()).decode()
            self.trust_environment[f"RUNNER_{role.upper()}_SIGNING_FINGERPRINT"] = fingerprint
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

    def test_bootstrap_release_state_checks_tags_without_metadata(self):
        base = self.git("rev-parse", "HEAD").stdout.strip()
        self.write("code.txt", "runner v2\n")
        self.write_locks()
        head = self.commit("shared change before first release")
        self.assertFalse((self.root / "runner.release").exists())
        output = self.root / "state.json"
        args = ("release-state", "--main-ref", base, "--base-ref", base,
                "--head-ref", head, "--json-out", str(output))
        self.helper(*args)
        state = json.loads(output.read_text())
        self.assertFalse(state["pending_release"])
        self.assertTrue(state["shared_change"])
        output.unlink()

        # Use disposable trust roots so structurally invalid tags cannot fail
        # merely because the verification environment has not been configured.
        self.trust_environment = {}
        for role in ("commit", "release"):
            _, fingerprint, allowed = self.generate_key(role)
            self.trust_environment[f"RUNNER_{role.upper()}_ALLOWED_SIGNER_B64"] = (
                base64.b64encode(allowed.read_bytes()).decode())
            self.trust_environment[f"RUNNER_{role.upper()}_SIGNING_FINGERPRINT"] = fingerprint
        for tag, annotated, error in (
            ("runner-vfoo", False, "invalid runner release tag"),
            ("runner-v1.0", False, "invalid runner release tag"),
            ("runner-v1.0.0", False, "annotated"),
            ("runner-v1.0.0", True, "signature"),
        ):
            with self.subTest(tag=tag, annotated=annotated):
                if annotated:
                    self.git("tag", "-a", tag, base, "-m", "unsigned release")
                else:
                    self.git("tag", tag, base)
                result = self.helper(*args, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)
                self.assertFalse(output.exists())
                self.git("tag", "-d", tag)

    def test_malformed_protected_tags_fail_inspection_before_trust_loading(self):
        for tag in ("runner-v1.0", "runner-vfoo", "runner-v01.2.3", "runner-v1.2.3-rc1"):
            with self.subTest(tag=tag):
                self.git("tag", tag)
                result = self.helper("inspect", "--json-out", str(self.root / "state.json"), check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid runner release tag", result.stderr)
                self.assertFalse((self.root / "state.json").exists())
                self.git("tag", "-d", tag)

    def test_malformed_tag_cannot_hide_next_to_a_verified_release(self):
        self.signed_release()
        self.git("tag", "runner-vfoo")
        result = self.helper("inspect", "--json-out", str(self.root / "state.json"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid runner release tag", result.stderr)
        result = self.helper(
            "verify-tag", "--tag", "runner-v0.1.0", "--main-ref", "main",
            "--commit-allowed-signers", str(self.root / "commit-key.allowed_signers"),
            "--commit-fingerprint", self.trust_environment["RUNNER_COMMIT_SIGNING_FINGERPRINT"],
            "--release-allowed-signers", str(self.root / "release-key.allowed_signers"),
            "--release-fingerprint", self.trust_environment["RUNNER_RELEASE_SIGNING_FINGERPRINT"],
            "--json-out", str(self.root / "verified.json"), check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid runner release tag", result.stderr)

    def release_state_result(self, base, head):
        output = self.root / "gate-state.json"
        output.unlink(missing_ok=True)
        result = self.helper("release-state", "--main-ref", base, "--base-ref", base,
                             "--head-ref", head, "--json-out", str(output), check=False)
        return result, output

    def test_existing_metadata_does_not_mask_malformed_namespace_for_any_pr(self):
        base = self.signed_release()
        self.write("README.md", "unrelated change\n")
        unrelated = self.commit("unrelated change")
        self.write("code.txt", "shared change\n")
        self.write_locks()
        shared = self.commit("shared change")
        for tag in ("runner-vfoo", "runner-v1.0", "runner-v01.2.3", "runner-v1.0.0-rc1"):
            self.git("tag", tag)
            for head in (base, unrelated, shared):
                with self.subTest(tag=tag, head=head):
                    result, output = self.release_state_result(base, head)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("invalid runner release tag", result.stderr)
                    self.assertFalse(output.exists())
            self.git("tag", "-d", tag)

    def test_other_invalid_release_and_missing_trust_are_not_pending_states(self):
        base = self.signed_release()
        self.write("README.md", "unrelated change\n")
        head = self.commit("unrelated change")
        for tag in ("runner-v0.0.1", "runner-v9.0.0"):
            with self.subTest(tag=tag):
                self.git("tag", tag)
                result, output = self.release_state_result(base, head)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("annotated", result.stderr)
                self.assertFalse(output.exists())
                self.git("tag", "-d", tag)
        self.trust_environment["RUNNER_RELEASE_ALLOWED_SIGNER_B64"] = ""
        result, output = self.release_state_result(base, head)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification keys are required", result.stderr)
        self.assertFalse(output.exists())

    def test_missing_expected_tag_cannot_mask_malformed_namespace(self):
        base, _ = self.prepare_release()
        self.git("tag", "runner-vfoo")
        result, output = self.release_state_result(base, base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid runner release tag", result.stderr)
        self.assertFalse(output.exists())

    def test_bad_pending_tag_cannot_hide_later_unverified_releases(self):
        base = self.signed_release()
        self.git("tag", "-d", "runner-v0.1.0")
        self.git("-c", "tag.gpgSign=false", "tag", "runner-v0.1.0", base)
        self.git("-c", "tag.gpgSign=false", "tag", "runner-v9.0.0", base)
        result, output = self.release_state_result(base, base)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_verified_namespace_still_allows_unrelated_and_shared_prs(self):
        base = self.signed_release()
        for path in ("README.md", "code.txt"):
            self.write(path, "new contents\n")
            self.write_locks()
            head = self.commit("candidate change")
            result, output = self.release_state_result(base, head)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(output.read_text())["pending_release"])

    def test_tags_outside_runner_namespace_do_not_trigger_release_validation(self):
        self.git("tag", "unrelated-vfoo")
        self.assertTrue(self.inspect()["needs_release"])

    def propose_noop_release(self):
        base = self.signed_release()
        release = self.root / "runner.release"
        release.write_text(release.read_text().replace("version 0.1.0", "version 0.1.1")
                           .replace("previous-tag none", "previous-tag runner-v0.1.0"))
        return base

    def test_metadata_only_release_fails_validation_state_and_pending_inspection(self):
        base = self.propose_noop_release()
        head = self.commit("attempt metadata-only release")
        for args in (
            ("validate-release", "--ref", head),
            ("release-state", "--main-ref", base, "--base-ref", base, "--head-ref", head,
             "--json-out", str(self.root / "state.json")),
            ("inspect", "--head-ref", head, "--json-out", str(self.root / "state.json")),
        ):
            with self.subTest(command=args[0]):
                result = self.helper(*args, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("canonical code or documentation delta", result.stderr)

    def test_lock_serialization_change_does_not_allow_a_noop_release(self):
        self.propose_noop_release()
        lock = self.root / "runner.lock"
        lock.write_text(lock.read_text().rstrip("\n"))
        self.commit("metadata and lock serialization only")
        result = self.helper("validate-release", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical code or documentation delta", result.stderr)

    def test_lock_serialization_alone_does_not_open_an_invalid_release_draft(self):
        self.signed_release()
        lock = self.root / "runner.lock"
        lock.write_text(lock.read_text().rstrip("\n"))
        self.commit("lock serialization only")
        self.assertFalse(self.inspect()["needs_release"])

    def test_noop_release_is_rejected_even_with_both_valid_signatures(self):
        self.propose_noop_release()
        parent = self.commit("freeze metadata-only release")
        release = dict(line.split(" ", 1) for line in (self.root / "runner.release").read_text().splitlines())
        self.git("switch", "--detach", parent)
        self.git("commit", "--allow-empty", "-S", "-m", "attest metadata-only release")
        message = "\n".join(["runner-release-v1", "version 0.1.1", f"release-parent {parent}",
                             f"code-tree-sha256 {release['code-tree-sha256']}",
                             f"docs-tree-sha256 {release['docs-tree-sha256']}"])
        self.git("-c", f"user.signingkey={Path(self.temporary.name) / 'release-key'}",
                 "tag", "-s", "runner-v0.1.1", "-m", message)
        self.git("switch", "main")
        result = self.helper("inspect", "--json-out", str(self.root / "state.json"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical code or documentation delta", result.stderr)

    def test_genuinely_changed_snapshots_remain_releasable(self):
        self.signed_release()
        for kind in ("code", "docs", "manifest", "mode", "removal"):
            with self.subTest(kind=kind):
                self.git("switch", "-c", f"candidate-{kind}", "main")
                if kind == "code":
                    self.write("code.txt", "changed code\n")
                elif kind == "docs":
                    self.write("docs/contract.md", "changed contract\n")
                elif kind == "manifest":
                    manifest = self.root / "scripts/runner-canonical-docs.txt"
                    manifest.write_text("# Export contract\n" + manifest.read_text())
                elif kind == "mode":
                    os.chmod(self.root / "code.txt", 0o755)
                else:
                    (self.root / "code.txt").unlink()
                    manifest = self.root / "scripts/runner-canonical-files.txt"
                    manifest.write_text(manifest.read_text().replace("code.txt\n", ""))
                self.write_locks()
                self.commit(f"shared {kind} delta")
                self.helper("update", "--head-ref", "HEAD", "--body-out", str(Path(self.temporary.name) / "body.md"))
                self.commit("prepare changed release")
                self.helper("validate-release", "--ref", "HEAD")
                self.git("switch", "main")

    def test_signing_parent_is_frozen_commit_not_batched_push_tip(self):
        frozen, _ = self.prepare_release()
        for number in (1, 2):
            self.write("README.md", f"unrelated commit {number}\n")
            self.commit(f"unrelated commit {number}")
        output = Path(self.temporary.name) / "github-output"
        state = Path(self.temporary.name) / "state.json"
        self.helper("inspect", "--head-ref", "HEAD", "--json-out", str(state), "--github-output", str(output))
        data = json.loads(state.read_text())
        self.assertTrue(data["pending_release"])
        self.assertEqual(data["release_parent"], frozen)
        self.assertNotEqual(data["main_sha"], frozen)
        self.assertIn(f"release_parent={frozen}\n", output.read_text())

    def test_signing_parent_is_first_parent_merge_not_draft_commit(self):
        self.git("switch", "-c", "release-draft")
        draft, _ = self.prepare_release()
        self.git("switch", "main")
        self.git("merge", "--no-ff", "--no-edit", "release-draft")
        frozen = self.git("rev-parse", "HEAD").stdout.strip()
        self.write("README.md", "later unrelated commit\n")
        self.commit("later unrelated commit")
        self.assertNotEqual(draft, frozen)
        self.assertEqual(self.inspect()["release_parent"], frozen)

    def test_valid_signed_frozen_parent_remains_valid_after_unrelated_main_commits(self):
        self.signed_release()
        self.write("README.md", "later unrelated commit\n")
        self.commit("later unrelated commit")
        data = self.inspect()
        self.assertFalse(data["pending_release"])
        self.assertFalse(data["needs_release"])
        self.assertEqual(data["previous_tag"], "runner-v0.1.0")

    def test_reintroduced_identical_metadata_has_no_unambiguous_frozen_parent(self):
        self.prepare_release()
        release = self.root / "runner.release"
        payload = release.read_text()
        release.unlink()
        self.commit("remove metadata")
        release.write_text(payload)
        self.commit("restore identical metadata")
        result = self.helper("inspect", "--json-out", str(self.root / "state.json"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("one exact frozen metadata commit", result.stderr)

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
