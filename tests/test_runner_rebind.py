"""WP-5 integration and fault injection: disposable roots only, never live HOME."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("runner_rebind", str(ROOT / "scripts/rebind-user-package"))
spec = importlib.util.spec_from_loader(loader.name, loader)
engine = importlib.util.module_from_spec(spec)
loader.exec_module(engine)


class RebindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-runner-rebind-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "new checkout"
        self.old = self.base / "old checkout"
        self.target = self.base / "target"
        self.target.mkdir()
        self.files = [".local/bin/alpha", ".local/bin/beta"]
        for root in (self.repo, self.old):
            (root / "packages/demo/install").mkdir(parents=True)
            (root / "stow").mkdir()
            (root / "stow/demo").symlink_to("../packages/demo/install")
            for rel in self.files:
                p = root / "packages/demo/install" / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture\n")
                p.chmod(0o755)
        (self.repo / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/rebind-user-package", self.repo / "scripts/rebind-user-package")
        shutil.copy2(ROOT / "run.sh", self.repo / "run.sh")
        (self.repo / "runner.conf").write_text("RUNNER_ENV_PREFIX=FIXTURE\n")
        for rel in self.files:
            self.link(rel)
        # Keep test journals inside the disposable fixture.
        original = tempfile.mkdtemp
        self.patcher = mock.patch.object(engine.tempfile, "mkdtemp",
            side_effect=lambda suffix=None, prefix=None, dir=None: original(suffix, prefix, str(self.base)))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def link(self, rel, root=None):
        p = self.target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.symlink_to(os.path.relpath((root or self.old) / "stow/demo" / rel, p.parent))
        return p

    def command(self, *args, input=None):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.target), "STOW_TARGET": str(self.target),
               "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run(["zsh", str(self.repo / "run.sh"), *args], env=env,
                              input=input, text=True, capture_output=True, timeout=30)

    def cli(self, *args):
        return self.command("install", "--rebind", "--legacy-root", str(self.old), *args, "demo")

    def snapshot(self):
        return engine.plan(self.repo, self.target, "demo", [self.old])

    def apply(self, snapshot=None):
        with contextlib.redirect_stdout(io.StringIO()):
            engine.apply(self.repo, self.target, "demo", [self.old], snapshot or self.snapshot())

    def state(self):
        return {str(p.relative_to(self.target)): os.readlink(p)
                for p in self.target.rglob("*") if p.is_symlink()}

    def test_dry_run_is_read_only_and_classifies(self):
        before = self.state()
        result = self.cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rebind: .local/bin/alpha", result.stdout)
        self.assertEqual(self.state(), before)

    def test_verify_inspects_without_installation(self):
        before = self.state()
        result = self.command("verify", "--rebind", "--legacy-root", str(self.old), "demo")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.state(), before)

    def test_apply_preserves_current_links_and_is_idempotent(self):
        self.apply()
        first = {rel: engine.identity(self.target / rel) for rel in self.files}
        self.apply()
        self.assertEqual(first, {rel: engine.identity(self.target / rel) for rel in self.files})
        for rel in self.files:
            self.assertEqual((self.target / rel).resolve(), self.repo / "packages/demo/install" / rel)

    def test_cli_never_runs_hooks_system_copy_or_external_verify(self):
        marker = self.base / "unexpected"
        for rel in ("packages/demo/install.hook.sh", "packages/demo/verify.hook.sh",
                    "scripts/stow-select", "scripts/system-copy-select"):
            p = self.repo / rel
            p.write_text("#!/bin/sh\ntouch '" + str(marker) + "'\nexit 99\n")
            p.chmod(0o755)
        result = self.cli("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        # CLI journal location is disclosed; remove only its exact temporary fixture output.
        journal = Path(next(line.split(": ", 1)[1] for line in result.stdout.splitlines()
                            if line.startswith("Rollback journal: ")))
        self.assertTrue(journal.parent.name.startswith("runner-rebind-journal-"))
        self.addCleanup(shutil.rmtree, journal.parent)

    def test_rejects_bulk_and_flags_on_normal_install(self):
        for selector in ("all", "all-user", "all-system", "..", "-invalid"):
            result = self.command("install", "--rebind", "--legacy-root", str(self.old), selector)
            self.assertNotEqual(result.returncode, 0)
        for flag in ("--dry-run", "--yes", "--legacy-root", "--from-repo"):
            args = [flag, str(self.old)] if flag in {"--legacy-root", "--from-repo"} else [flag]
            self.assertNotEqual(self.command("install", *args, "demo").returncode, 0)
        self.assertNotEqual(self.cli("--test").returncode, 0)
        self.assertNotEqual(self.cli("--verify").returncode, 0)
        self.assertNotEqual(self.command("install", "--rebind", "demo").returncode, 0)

    def test_noninteractive_requires_explicit_yes(self):
        before = self.state()
        self.assertNotEqual(self.cli().returncode, 0)
        self.assertEqual(self.state(), before)

    def test_optional_helper_absence_does_not_break_unrelated_commands(self):
        (self.repo / "scripts/rebind-user-package").unlink()
        result = self.cli("--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("optional rebind helper is not installed", result.stderr)
        result = self.command("verify", "unknown-package")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("optional rebind helper", result.stderr)

    def test_stow_projection_is_checked_before_live_changes(self):
        before = self.state()
        with mock.patch.object(engine.subprocess, "run", return_value=mock.Mock(returncode=1)):
            with self.assertRaises(engine.Refusal):
                engine.stow_projection(self.repo, "demo", self.snapshot()["files"])
        self.assertEqual(self.state(), before)

    def test_new_target_collision_during_publication_is_not_overwritten(self):
        rel = ".config/new/path"
        p = self.repo / "packages/demo/install" / rel
        p.parent.mkdir(parents=True)
        p.write_text("fixture")
        destination = self.target / rel
        original = os.link
        def collide(src, dst, *args, **kwargs):
            if dst == "path":
                destination.write_text("concurrent owner data")
            return original(src, dst, *args, **kwargs)
        with mock.patch.object(engine.os, "link", side_effect=collide):
            with self.assertRaises(FileExistsError):
                self.apply()
        self.assertEqual(destination.read_text(), "concurrent owner data")

    def test_payload_mode_changes_are_reported(self):
        (self.repo / "packages/demo/install" / self.files[0]).chmod(0o644)
        result = self.cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("payload differs", result.stdout)

    def test_normal_install_still_dispatches_without_optional_helper(self):
        (self.repo / "scripts/rebind-user-package").unlink()
        marker = self.base / "normal-install"
        (self.repo / "scripts/stow-select").write_text("#!/bin/sh\ntouch '" + str(marker) + "'\n")
        (self.repo / "scripts/stow-select").chmod(0o755)
        result = self.command("install", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(marker.exists())

    def test_conflict_at_last_path_changes_nothing(self):
        p = self.target / self.files[-1]
        p.unlink()
        p.write_text("owner data")
        before = self.state()
        self.assertNotEqual(self.cli("--yes").returncode, 0)
        self.assertEqual(self.state(), before)
        self.assertEqual(p.read_text(), "owner data")

    def test_dangling_wrong_package_and_indirect_links_are_refused(self):
        p = self.target / self.files[-1]
        for destination in (self.base / "absent", self.old / "packages/other/install/.local/bin/beta",
                            self.base / "indirect"):
            if destination.name == "indirect":
                destination.symlink_to(self.old / "stow/demo" / self.files[-1])
            p.unlink()
            p.symlink_to(destination)
            self.assertNotEqual(self.cli("--dry-run").returncode, 0)

    def test_symlinked_target_parent_is_rejected(self):
        shutil.rmtree(self.target / ".local/bin")
        (self.target / ".local/bin").symlink_to(self.old / "packages/demo/install/.local/bin")
        self.assertNotEqual(self.cli("--yes").returncode, 0)

    def test_symlink_payload_and_custom_ignore_are_rejected(self):
        source = self.repo / "packages/demo/install" / self.files[-1]
        source.unlink()
        source.symlink_to(self.old / "packages/demo/install" / self.files[-1])
        self.assertNotEqual(self.cli("--dry-run").returncode, 0)
        source.unlink()
        source.write_text("fixture")
        (self.repo / "packages/demo/install/.stow-local-ignore").write_text("beta\n")
        self.assertNotEqual(self.cli("--dry-run").returncode, 0)

    def test_new_file_and_directories_created_then_verified(self):
        rel = ".config/example/deep/new"
        p = self.repo / "packages/demo/install" / rel
        p.parent.mkdir(parents=True)
        p.write_text("fixture")
        self.apply()
        self.assertEqual((self.target / rel).resolve(), p)

    def test_explicit_rename_removes_only_proven_old_link(self):
        oldrel, newrel = ".config/zsh/rc.d/old.zsh", ".config/zsh/rc.d/new.zsh"
        for root, rel in ((self.old, oldrel), (self.repo, newrel)):
            p = root / "packages/demo/install" / rel
            p.parent.mkdir(parents=True)
            p.write_text("fixture")
        self.link(oldrel)
        manifest = self.repo / "packages/demo/rebind-paths.manifest"
        before = self.state()
        self.assertNotEqual(self.cli("--dry-run").returncode, 0)
        self.assertEqual(self.state(), before)
        manifest.write_text(oldrel + " " + newrel + "\n")
        (self.repo / "packages/demo/install" / newrel).write_text("updated renamed payload")
        preview = self.cli("--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("missing: " + newrel + " (payload differs)", preview.stdout)
        self.apply()
        self.assertFalse(os.path.lexists(self.target / oldrel))
        self.assertEqual((self.target / newrel).resolve(), self.repo / "packages/demo/install" / newrel)
        self.apply()

    def test_bad_rename_records_are_rejected(self):
        manifest = self.repo / "packages/demo/rebind-paths.manifest"
        for data in ("../old .local/bin/alpha", ".local/bin/alpha .local/bin/beta",
                     ".local/bin/old .local/bin/absent",
                     ".local/bin/old .local/bin/alpha\n.local/bin/other .local/bin/alpha"):
            manifest.write_text(data)
            self.assertNotEqual(self.cli("--dry-run").returncode, 0)

    def test_snapshot_is_rechecked_after_approval(self):
        snapshot = self.snapshot()
        (self.repo / "packages/demo/install" / self.files[0]).write_text("changed")
        before = self.state()
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)

    def test_apply_failure_rolls_back_only_its_own_changes(self):
        before = self.state()
        original = os.replace
        calls = 0
        def fail_second(*a, **kw):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected failure")
            return original(*a, **kw)
        with mock.patch.object(engine.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(self.state(), before)
        self.assertFalse(list(self.target.rglob(".runner-rebind-*")))

    def test_signal_after_publication_still_records_rollback_ownership(self):
        before = self.state()
        original = os.replace
        sent = False
        def interrupt(*args, **kwargs):
            nonlocal sent
            result = original(*args, **kwargs)
            if not sent:
                sent = True
                os.kill(os.getpid(), signal.SIGTERM)
            return result
        def handler(signum, frame):
            raise engine.Refusal("injected signal")
        previous = signal.signal(signal.SIGTERM, handler)
        try:
            with mock.patch.object(engine.os, "replace", side_effect=interrupt):
                with self.assertRaises(engine.Refusal):
                    self.apply()
        finally:
            signal.signal(signal.SIGTERM, previous)
        self.assertEqual(self.state(), before)
        self.assertFalse(list(self.target.rglob(".runner-rebind-*")))

    def test_interruption_after_staging_does_not_leave_temporary_link(self):
        before = self.state()
        original = os.symlink
        def interrupt(*args, **kwargs):
            original(*args, **kwargs)
            raise engine.Refusal("injected staging interruption")
        with mock.patch.object(engine.os, "symlink", side_effect=interrupt):
            with self.assertRaises(engine.Refusal):
                self.apply()
        self.assertEqual(self.state(), before)
        self.assertFalse(list(self.target.rglob(".runner-rebind-*")))

    def test_final_verify_failure_restores_missing_and_old_paths(self):
        new = self.repo / "packages/demo/install/.config/new/file"
        new.parent.mkdir(parents=True)
        new.write_text("fixture")
        before = self.state()
        with mock.patch.object(engine, "verify_result", side_effect=engine.Refusal("injected")):
            with self.assertRaises(engine.Refusal):
                self.apply()
        self.assertEqual(self.state(), before)
        self.assertFalse((self.target / ".config").exists())

    def test_rollback_preserves_concurrent_replacement(self):
        p = self.target / self.files[0]
        def changed(*args):
            p.unlink()
            p.write_text("concurrent owner edit")
            raise engine.Refusal("injected")
        with mock.patch.object(engine, "verify_result", side_effect=changed), contextlib.redirect_stderr(io.StringIO()) as log:
            with self.assertRaises(engine.Refusal):
                self.apply()
        self.assertEqual(p.read_text(), "concurrent owner edit")
        self.assertIn("Manual rollback required", log.getvalue())

    def test_advisory_lock_refuses_overlapping_apply(self):
        import fcntl
        fd = os.open(self.target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = self.state()
            with self.assertRaises(BlockingIOError):
                self.apply()
            self.assertEqual(self.state(), before)
        finally:
            os.close(fd)

    def test_rename_failure_restores_old_name(self):
        oldrel, newrel = ".config/zsh/rc.d/a-old.zsh", ".config/zsh/rc.d/z-new.zsh"
        for root, rel in ((self.old, oldrel), (self.repo, newrel)):
            p = root / "packages/demo/install" / rel
            p.parent.mkdir(parents=True)
            p.write_text("fixture")
        self.link(oldrel)
        (self.repo / "packages/demo/rebind-paths.manifest").write_text(oldrel + " " + newrel + "\n")
        before = self.state()
        with mock.patch.object(engine, "verify_result", side_effect=engine.Refusal("injected")):
            with self.assertRaises(engine.Refusal):
                self.apply()
        self.assertEqual(self.state(), before)

    def test_stow_does_not_read_caller_configuration(self):
        (self.repo / ".stowrc").write_text("--ignore=.*\n")
        (self.target / ".stowrc").write_text("--ignore=.*\n")
        result = self.cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_journal_has_exact_original_links_and_private_permissions(self):
        snapshot = self.snapshot()
        self.apply(snapshot)
        journal = next(self.base.glob("runner-rebind-journal-*/before.json"))
        recorded = json.loads(journal.read_text())
        self.assertEqual(recorded["target"], str(self.target))
        self.assertEqual([row["old"] for row in recorded["snapshot"]["rows"]],
                         [row["old"] for row in snapshot["rows"]])
        self.assertEqual(journal.stat().st_mode & 0o777, 0o600)

    def test_multiple_explicit_roots(self):
        second = self.base / "another-old"
        shutil.copytree(self.old, second, symlinks=True)
        p = self.target / self.files[-1]
        p.unlink()
        self.link(self.files[-1], root=second)
        self.assertNotEqual(self.cli("--dry-run").returncode, 0)
        result = self.cli("--legacy-root", str(second), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_manifest_symlink_and_source_parent_symlink_are_rejected(self):
        manifest = self.repo / "packages/demo/rebind-paths.manifest"
        external = self.base / "mapping"
        external.write_text("")
        manifest.symlink_to(external)
        self.assertNotEqual(self.cli("--dry-run").returncode, 0)
        manifest.unlink()
        folder = self.repo / "packages/demo/install/.local/bin"
        shutil.rmtree(folder)
        folder.symlink_to(self.old / "packages/demo/install/.local/bin")
        self.assertNotEqual(self.cli("--dry-run").returncode, 0)

    def test_auto_discovery_finds_every_source_used_by_the_package(self):
        second = self.base / "second source"
        shutil.copytree(self.old, second, symlinks=True)
        (self.target / self.files[-1]).unlink()
        self.link(self.files[-1], second)
        self.assertEqual(engine.discover_sources(self.repo, self.target, "demo"), sorted([self.old, second]))
        result = self.command("verify", "--rebind", "demo")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("Detected source candidate: " + str(self.old), result.stdout)
        self.assertIn("Detected source candidate: " + str(second), result.stdout)
        self.assertIn("--from-repo", result.stdout)

    def test_discovery_never_enumerates_target_directories_or_reads_live_files(self):
        unrelated = self.target / ".local/bin/unrelated"
        unrelated.symlink_to(self.base / "unrelated source/stow/demo/.local/bin/unrelated")
        (self.target / "owner-file").write_text("unrelated user content")
        original_scandir = os.scandir
        original_read = Path.read_bytes
        def scan(path):
            scanned = Path(os.readlink(f"/proc/self/fd/{path}")) if isinstance(path, int) else Path(path)
            self.assertFalse(scanned.is_relative_to(self.target), "enumerated a live target directory")
            return original_scandir(path)
        def read(path):
            self.assertFalse(path.is_relative_to(self.target), "read live file contents")
            return original_read(path)
        with mock.patch.object(engine.os, "scandir", side_effect=scan), mock.patch.object(Path, "read_bytes", read):
            with contextlib.redirect_stdout(io.StringIO()):
                roots, snapshot = engine.prepare(self.repo, self.target, "demo", [])
        self.assertEqual(roots, [self.old])
        self.assertNotIn(".local/bin/unrelated", [row["path"] for row in snapshot["rows"]])

    def test_from_repo_is_a_restriction_and_legacy_root_remains_an_alias(self):
        for flag in ("--from-repo", "--legacy-root"):
            result = self.command("verify", "--rebind", flag, str(self.old), "demo")
            self.assertEqual(result.returncode, 3, result.stderr)
        other = self.base / "other"
        shutil.copytree(self.old, other, symlinks=True)
        (self.target / self.files[-1]).unlink()
        self.link(self.files[-1], other)
        result = self.command("verify", "--rebind", "--from-repo", str(self.old), "demo")
        self.assertEqual(result.returncode, 1)
        self.assertIn("conflict:", result.stdout)
        self.assertNotIn("Detected source candidate:", result.stdout)

    def test_auto_discovery_cannot_be_approved_with_bare_yes(self):
        before = self.state()
        result = self.command("install", "--rebind", "--yes", "demo")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--yes requires explicit --from-repo", result.stderr)
        self.assertEqual(self.state(), before)

    def test_current_installation_can_be_inspected_without_a_source_argument(self):
        self.apply()
        result = self.command("verify", "--rebind", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Detected source candidate:", result.stdout)

    def test_missing_installation_can_be_previewed_without_a_source_argument(self):
        for rel in self.files:
            (self.target / rel).unlink()
        result = self.command("install", "--rebind", "--dry-run", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("missing:"), 2)
        self.assertEqual(self.state(), {})

    def test_discovery_includes_declared_old_names(self):
        newrel = ".local/bin/new-alpha"
        (self.repo / "packages/demo/install" / self.files[0]).rename(self.repo / "packages/demo/install" / newrel)
        (self.repo / "packages/demo/rebind-paths.manifest").write_text(self.files[0] + " " + newrel + "\n")
        (self.target / self.files[1]).unlink()
        self.link(self.files[1], self.repo)
        before = self.state()
        result = self.command("verify", "--rebind", "demo")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("rename: " + self.files[0], result.stdout)
        self.assertIn("Detected source candidate: " + str(self.old), result.stdout)
        self.assertEqual(self.state(), before)

    def test_discovery_rejects_missing_and_symlinked_source_roots(self):
        p = self.target / self.files[0]
        alias = self.base / "alias"
        alias.symlink_to(self.old)
        for root in (self.base / "absent", alias):
            p.unlink()
            self.link(self.files[0], root)
            self.assertEqual(self.command("verify", "--rebind", "demo").returncode, 1)

    def test_foreign_link_is_not_followed_to_discover_an_indirect_source(self):
        p = self.target / self.files[0]
        p.unlink()
        indirect = self.base / "indirect"
        indirect.symlink_to(self.old / "stow/demo" / self.files[0])
        p.symlink_to(indirect)
        original = Path.resolve
        def resolve(path, *args, **kwargs):
            self.assertNotEqual(path, p, "resolved an unrecognized foreign chain")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "resolve", resolve):
            roots = engine.discover_sources(self.repo, self.target, "demo")
            snapshot = engine.plan(self.repo, self.target, "demo", roots)
        self.assertIn(self.files[0], snapshot["conflicts"])

    def test_incomplete_source_tree_is_not_silently_accepted(self):
        original = os.scandir
        blocked = self.old / "packages/demo/install/.local/bin"
        def scan(path):
            if path == str(blocked):
                raise PermissionError("fixture inaccessible subtree")
            return original(path)
        with mock.patch.object(engine.os, "scandir", side_effect=scan):
            with self.assertRaisesRegex(engine.Refusal, "complete package tree"):
                engine.plan(self.repo, self.target, "demo", [self.old])

    def test_discovered_source_cannot_execute_configuration_or_hooks(self):
        marker = self.base / "must-not-exist"
        payload = "#!/bin/sh\ntouch '" + str(marker) + "'\n"
        for rel in ("runner.conf", "packages/demo/install.hook.sh", "packages/demo/verify.hook.sh"):
            (self.old / rel).write_text(payload)
            (self.old / rel).chmod(0o755)
        result = self.command("verify", "--rebind", "demo")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertFalse(marker.exists())

    def test_discovery_does_not_trust_a_different_package_or_relative_path(self):
        p = self.target / self.files[0]
        for suffix in ("stow/other/.local/bin/alpha", "stow/demo/.local/bin/beta"):
            p.unlink()
            p.symlink_to(self.old / suffix)
            result = self.command("verify", "--rebind", "demo")
            self.assertEqual(result.returncode, 1)
            self.assertIn("conflict: " + self.files[0], result.stdout)

    def auto_main(self, reply):
        argv = ["rebind", "--target", str(self.target), "--package", "demo"]
        with mock.patch.object(engine, "__file__", str(self.repo / "scripts/rebind-user-package")), \
             mock.patch.object(sys, "argv", argv), mock.patch.object(sys.stdin, "isatty", return_value=True), \
             mock.patch("builtins.input", side_effect=reply), contextlib.redirect_stdout(io.StringIO()) as output:
            engine.main()
        return output.getvalue()

    def test_discovered_plan_requires_literal_confirmation_before_mutation(self):
        before = self.state()
        def approve(prompt):
            self.assertEqual(self.state(), before)
            self.assertIn("REBIND", prompt)
            return "REBIND"
        output = self.auto_main(approve)
        self.assertIn("Detected source candidate:", output)
        self.assertTrue(all((self.target / rel).resolve().is_relative_to(self.repo) for rel in self.files))

    def test_cancelled_discovered_plan_does_not_change_links(self):
        before = self.state()
        with self.assertRaises(engine.Refusal):
            self.auto_main(lambda prompt: "no")
        self.assertEqual(self.state(), before)

    def test_discovered_link_change_during_confirmation_aborts(self):
        p = self.target / self.files[0]
        def approve(prompt):
            p.unlink()
            p.write_text("concurrent user edit")
            return "REBIND"
        with self.assertRaises(engine.Refusal):
            self.auto_main(approve)
        self.assertEqual(p.read_text(), "concurrent user edit")
        self.assertEqual((self.target / self.files[1]).resolve(), self.old / "packages/demo/install" / self.files[1])

    def test_all_user_inspection_is_read_only_and_does_not_skip_ignored_packages(self):
        (self.repo / "manifests").mkdir()
        (self.repo / "manifests/ignore-all-install.txt").write_text("demo\n")
        before = self.state()
        result = self.command("verify", "--rebind", "all-user")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("1 packages, 1 need migration, 0 failed", result.stdout)
        self.assertEqual(self.state(), before)

    def test_all_user_inspection_continues_after_a_package_conflict(self):
        source = self.repo / "packages/second/install/.local/bin/other"
        source.parent.mkdir(parents=True)
        source.write_text("fixture")
        (self.repo / "stow/second").symlink_to("../packages/second/install")
        p = self.target / self.files[0]
        p.unlink()
        p.write_text("user owned")
        result = self.command("verify", "--rebind", "all-user")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Package: second", result.stdout)
        self.assertIn("2 packages, 1 need migration, 1 failed", result.stdout)
        self.assertEqual(p.read_text(), "user owned")


if __name__ == "__main__":
    unittest.main()
