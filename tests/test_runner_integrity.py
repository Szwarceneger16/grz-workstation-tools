"""Mode locks, legacy bootstrap identities and prompt/copy races in fixtures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_runner_review_regressions as fixtures

ROOT = Path(__file__).resolve().parents[1]


class ModeLockTests(unittest.TestCase):
    def test_mode_only_changes_and_legacy_records_fail_for_both_roles(self):
        fixture = fixtures.RunnerDocumentationTests()
        for role in ("source", "consumer"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture.fixture(root, role)
                command = [f"RUNNER_SYNC_EXPECTED_ROLE={role}", "RUNNER_SYNC_WRITE=0", "./scripts/sync-runner", "check"]
                for path in ("code.txt", "docs/runner-sync.md"):
                    target = root / path
                    target.chmod(0o755)
                    result = fixture.execute(root, command)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("mode mismatch", result.stderr)
                    target.chmod(0o644)
                lock = root / "runner.lock"
                lock.write_text("\n".join(line.split(" ", 1)[1] for line in lock.read_text().splitlines()) + "\n")
                result = fixture.execute(root, command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid lock record", result.stderr)

    def test_source_lock_binds_executable_removal_without_git_metadata(self):
        fixture = fixtures.RunnerDocumentationTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture.fixture(root, "source")
            (root / "code.txt").chmod(0o755)
            self.assertEqual(fixture.execute(root, ["RUNNER_SYNC_EXPECTED_ROLE=source", "RUNNER_SYNC_WRITE=1", "./scripts/sync-runner", "lock"]).returncode, 0)
            (root / "code.txt").chmod(0o644)
            result = fixture.execute(root, ["RUNNER_SYNC_EXPECTED_ROLE=source", "RUNNER_SYNC_WRITE=0", "./scripts/sync-runner", "check"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("mode mismatch", result.stderr)


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class LegacyIdentityTests(unittest.TestCase):
    def test_known_and_local_markers_migrate_but_foreign_links_stay_untouched(self):
        for marker, accepted in (("grz-workstation-tools", True), ("grz-zsh-tools", True),
                                 ("private-consumer", True), ("legacy-fixture", True), ("foreign", False)):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo, target, old = root / "repo", root / "target", root / "old"
                (repo / "scripts").mkdir(parents=True)
                (old / "packages/fixture/install").mkdir(parents=True)
                target.mkdir()
                shutil.copy2(ROOT / "scripts/ensure-rcd-loaders", repo / "scripts/ensure-rcd-loaders")
                (repo / ".rcd-loader-legacy-repo-ids").write_text("legacy-fixture\n")
                (old / ".rcd-loader-repo-id").write_text(marker + "\n")
                for name in (".zshrc", ".profile"):
                    (target / name).symlink_to(old / "packages/fixture/install" / name)
                env = {"PATH": os.environ["PATH"], "HOME": str(target), "STOW_TARGET": str(target)}
                cmd = ["zsh", str(repo / "scripts/ensure-rcd-loaders")]
                checked = subprocess.run(cmd + ["--check"], env=env, capture_output=True, text=True)
                self.assertNotEqual(checked.returncode, 0)
                self.assertTrue((target / ".zshrc").is_symlink())
                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, accepted, result.stderr)
                for name in (".zshrc", ".profile"):
                    self.assertEqual((target / name).is_symlink(), not accepted)
                if accepted:
                    before = [(target / name).read_bytes() for name in (".zshrc", ".profile")]
                    self.assertEqual(subprocess.run(cmd, env=env, capture_output=True).returncode, 0)
                    self.assertEqual(before, [(target / name).read_bytes() for name in (".zshrc", ".profile")])


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class SecretCopyRaceTests(unittest.TestCase):
    def test_destination_created_during_prompt_aborts_without_privileged_copy(self):
        helper = fixtures.ExistingReviewFixTests()
        function = helper.function("scripts/system-copy-select", "process_package_configs")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.write_text("synthetic fixture only\n")
            script = function + '''
fixture_root="$1"
fixture_race="$2"
configs_missing=0
load_config_metadata() {
  typeset -gA config_modes config_owners config_groups
  config_modes=(etc/fixture.conf 600)
  config_owners=(etc/fixture.conf root)
  config_groups=(etc/fixture.conf root)
}
die() { print -u2 -- "$*"; exit 65; }
prompt_path() {
  touch "$fixture_root/prompted"
  print -r -- "$fixture_root/source"
}
sudo() {
  case "$*" in
    '-n test -e /etc/fixture.conf'|'-n test -L /etc/fixture.conf')
      [[ -f "$fixture_root/prompted" && "$fixture_race" == during-prompt ]] ;;
    '-n test -f /etc/fixture.conf') return 0 ;;
    '-n install '*)
      [[ "$*" == '-n install -D -T '* ]] || exit 98
      print -- 'mock-install exact destination'
      [[ "$fixture_race" != after-check ]] ;;
    *) exit 99 ;;
  esac
}
process_package_configs fixture
print -- 'allowed continuation'
'''
            for race in ("during-prompt", "after-check", "none"):
                (root / "prompted").unlink(missing_ok=True)
                result = helper.zsh(script, str(root), race)
                self.assertEqual(result.returncode == 0, race == "none", result.stderr)
                if race == "during-prompt":
                    self.assertNotIn("mock-install", result.stdout)
                if race != "none":
                    self.assertNotIn("allowed continuation", result.stdout)
