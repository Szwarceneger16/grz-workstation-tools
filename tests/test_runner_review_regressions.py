"""Shared documentation examples and existing review fixes, using disposable fixtures."""
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RunnerDocumentationTests(unittest.TestCase):
    def fixture(self, root, role):
        (root / "scripts").mkdir()
        (root / "docs").mkdir()
        shutil.copy2(ROOT / "scripts/sync-runner", root / "scripts/sync-runner")
        (root / "runner.conf").write_text(f"RUNNER_ENV_PREFIX=FIXTURE\nRUNNER_SYNC_ROLE={role}\n")
        (root / "code.txt").write_text("fixture\n")
        (root / "docs/runner-sync.md").write_text((ROOT / "docs/runner-sync.md").read_text())
        code = ["code.txt", "scripts/runner-canonical-docs.txt", "scripts/runner-canonical-files.txt"]
        docs = ["docs/runner-sync.md"]
        for paths, canonical, selected, lock in (
            (code, "runner-canonical-files.txt", "runner-sync-files.txt", "runner.lock"),
            (docs, "runner-canonical-docs.txt", "runner-sync-docs.txt", "runner.docs.lock"),
        ):
            (root / "scripts" / canonical).write_text("\n".join(paths) + "\n")
            (root / "scripts" / selected).write_text("\n".join(paths) + "\n")
        for paths, lock in ((code, "runner.lock"), (docs, "runner.docs.lock")):
            (root / lock).write_text("".join(f"{100755 if (root / path).stat().st_mode & 0o100 else 100644} {hashlib.sha256((root / path).read_bytes()).hexdigest()}  {path}\n" for path in paths))

    def commands(self, role):
        document = (ROOT / "docs/runner-sync.md").read_text()
        section = document.split(f"### {role.title()} checkout\n", 1)[1].split("\n##", 1)[0]
        blocks = re.findall(r"```sh\n(.*?)\n```", section, re.DOTALL)
        self.assertEqual(len(blocks), 1)
        commands = [shlex.split(line) for line in blocks[0].splitlines()]
        expected = ["check", "lock"] if role == "source" else ["check"]
        self.assertEqual([command[-1] for command in commands], expected)
        for command in commands:
            self.assertEqual(command, [
                f"RUNNER_SYNC_EXPECTED_ROLE={role}",
                f"RUNNER_SYNC_WRITE={int(command[-1] == 'lock')}",
                "./scripts/sync-runner", command[-1],
            ])
        return commands

    def execute(self, root, command):
        env = {"PATH": os.environ["PATH"], "HOME": str(root)}
        env.update(dict(assignment.split("=", 1) for assignment in command[:2]))
        return subprocess.run(command[2:], cwd=root, env=env, text=True, capture_output=True, timeout=10)

    def test_documented_checks_match_both_roles_and_do_not_write_locks(self):
        for role in ("source", "consumer"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root, role)
                before = [(root / lock).read_bytes() for lock in ("runner.lock", "runner.docs.lock")]
                result = self.execute(root, self.commands(role)[0])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(before, [(root / lock).read_bytes() for lock in ("runner.lock", "runner.docs.lock")])

    def test_documented_lock_refresh_is_source_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, "source")
            (root / "code.txt").write_text("updated fixture\n")
            self.assertNotEqual(self.execute(root, self.commands("source")[0]).returncode, 0)
            result = self.execute(root, self.commands("source")[1])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.execute(root, self.commands("source")[0]).returncode, 0)
            (root / "runner.conf").write_text("RUNNER_ENV_PREFIX=FIXTURE\nRUNNER_SYNC_ROLE=consumer\n")
            before = (root / "runner.lock").read_bytes()
            result = self.execute(root, ["RUNNER_SYNC_EXPECTED_ROLE=consumer", "RUNNER_SYNC_WRITE=1", "./scripts/sync-runner", "lock"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source-only", result.stderr)
            self.assertEqual(before, (root / "runner.lock").read_bytes())

    def test_empty_consumer_selections_require_empty_locks(self):
        for empty_sets in (("files",), ("docs",), ("files", "docs")):
            for payload in ("", "# intentionally select nothing\n\n"):
                with self.subTest(empty_sets=empty_sets, comments=bool(payload)), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.fixture(root, "consumer")
                    for name in empty_sets:
                        (root / f"scripts/runner-sync-{name}.txt").write_text(payload)
                    self.assertNotEqual(self.execute(root, self.commands("consumer")[0]).returncode, 0)
                    for name in empty_sets:
                        (root / ("runner.lock" if name == "files" else "runner.docs.lock")).write_text("")
                    result = self.execute(root, self.commands("consumer")[0])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    # Missing or symlink selections are not equivalent to empty files.
                    path = root / f"scripts/runner-sync-{empty_sets[0]}.txt"
                    path.unlink()
                    self.assertNotEqual(self.execute(root, self.commands("consumer")[0]).returncode, 0)
                    path.symlink_to(root / "runner.docs.lock")
                    self.assertNotEqual(self.execute(root, self.commands("consumer")[0]).returncode, 0)

    def test_empty_canonical_manifests_remain_invalid_for_both_roles(self):
        for role in ("source", "consumer"):
            for name in ("files", "docs"):
                with self.subTest(role=role, name=name), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.fixture(root, role)
                    (root / f"scripts/runner-canonical-{name}.txt").write_text("# empty\n")
                    for command in self.commands(role):
                        result = self.execute(root, command)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("manifest is empty", result.stderr)

    def test_source_example_cannot_silently_validate_a_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, "consumer")
            result = self.execute(root, self.commands("source")[0])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CI expected", result.stderr)


@unittest.skipUnless(shutil.which("zsh"), "zsh is needed for isolated function tests")
class ExistingReviewFixTests(unittest.TestCase):
    def function(self, relative, name):
        text = (ROOT / relative).read_text()
        match = re.search(rf"^{name}\(\) \{{\n.*?^\}}$", text, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match, name)
        return match.group()

    def zsh(self, script, *args):
        # Only the reviewed function definitions are loaded, never CLI entrypoints.
        return subprocess.run(["zsh", "-f", "-c", script, "fixture", *args],
                              env={"PATH": os.environ["PATH"], "HOME": "/nonexistent"},
                              text=True, capture_output=True, timeout=10)

    def test_noncanonical_manifest_spelling_is_rejected(self):
        script = self.function("scripts/check-repo", "load_4col_manifest")
        script += '\nerrors=0\nerr() { errors=$(( errors + 1 )); }\nload_4col_manifest "$1"\nprint -- "$errors"\n'
        for path in ("etc/letsencrypt/./live/foo", "etc/letsencrypt//live/foo", "./etc/example",
                     "etc/../example", "etc/example", "etc/skel/.gitignore"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                manifest = Path(directory) / "fixture.manifest"
                manifest.write_text(f"{path} 0644 root root\n")
                result = self.zsh(script, str(manifest))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "0" if path in ("etc/example", "etc/skel/.gitignore") else "1")

    def test_system_and_user_meta_classifiers_agree(self):
        paths = (".gitkeep", "etc/.gitignore", "etc/.gitattributes", "etc/.gitmodules",
                 "etc/.stow-local-ignore", "etc/.git/config", "etc/real.conf")
        outputs = []
        for relative, name in (("scripts/check-repo", "is_meta_file"), ("scripts/system-copy-select", "is_meta_file"),
                               ("run.sh", "is_install_meta_file")):
            result = self.zsh(self.function(relative, name) + f'\nfor item in "$@"; do {name} "$item"; print -- "$?"; done', *paths)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(result.stdout.splitlines())
        self.assertEqual(outputs, [["0"] * 6 + ["1"]] * 3)

    def test_unreachable_user_manager_aborts_before_deactivation_or_unlink(self):
        script = self.function("run.sh", "deactivate_user_units") + """
load_user_units_metadata() { user_units=(fixture.service); }
stow_target_is_home() { return 0; }
user_manager_reachable() { return 1; }
systemctl() { print -- 'unexpected systemctl'; exit 99; }
die() { print -u2 -- "$*"; exit 65; }
deactivate_user_units fixture
print -- 'unexpected continuation to unlink'
"""
        result = self.zsh(script)
        self.assertEqual(result.returncode, 65, result.stderr)
        self.assertIn("refusing to remove files while units may be active", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_user_template_enumeration_failure_aborts_even_with_partial_output(self):
        script = self.function("run.sh", "stop_user_template_instances") + """
systemctl() {
  if [[ "$2" == list-units ]]; then print -- 'fixture@one.service loaded active running'; return 1; fi
  print -- 'unexpected stop'; exit 99
}
die() { print -u2 -- "$*"; exit 65; }
stop_user_template_instances fixture fixture@.service
print -- 'unexpected continuation to unlink'
"""
        result = self.zsh(script)
        self.assertEqual(result.returncode, 65, result.stderr)
        self.assertIn("failed to enumerate user instances", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_deactivation_preflights_all_units_before_first_mutation(self):
        script = self.function("run.sh", "verify_user_unit_owned_for_deactivation")
        script += "\n" + self.function("run.sh", "deactivate_user_units") + """
repo_root=/fixture
target=/fixture-target
fixture_bad_unit="$1"
fixture_failure="$2"
load_user_units_metadata() { user_units=(early.timer early.path early.socket late.service late@one.service late@.service late.target late.mount); }
stow_target_is_home() { return 0; }
user_manager_reachable() { return 0; }
activation_bases_for_unit() { return 0; }
resolve_unit_file_path() {
  if [[ "$2" == late@one.service ]]; then print -- "$1/late@.service";
  else print -- "$1/$2"; fi
}
find_shadowing_user_unit_path() {
  if [[ "$1" == "$fixture_bad_unit" && "$fixture_failure" == shadow ]]; then
    print -- /fixture-shadow; return 0
  fi
  return 1
}
verify_stow_link() {
  print -- "checked $unit"
  [[ "$unit" != "$fixture_bad_unit" || "$fixture_failure" == shadow ]]
}
unit_has_install_section() { return 0; }
is_template_unit_name() { [[ "$1" == *@.* ]]; }
stop_user_template_instances() { print -- "mutation instances $2"; }
systemctl() { print -- "mutation $*"; }
die() { print -u2 -- "$*"; exit 65; }
deactivate_user_units fixture
print -- 'unlink allowed'
"""
        units = ("early.timer", "early.path", "early.socket", "late.service",
                 "late@one.service", "late@.service", "late.target", "late.mount")
        for unit in units:
            with self.subTest(unit=unit):
                result = self.zsh(script, unit, "foreign-or-missing-link")
                self.assertEqual(result.returncode, 65, result.stderr)
                self.assertNotIn("mutation", result.stdout)
                self.assertNotIn("unlink allowed", result.stdout)
        result = self.zsh(script, "late@one.service", "shadow")
        self.assertEqual(result.returncode, 65, result.stderr)
        self.assertIn("shadows template", result.stderr)
        self.assertNotIn("mutation", result.stdout)
        result = self.zsh(script, "none", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        preflight = result.stdout.split("mutation", 1)[0]
        for unit in units:
            self.assertIn("checked " + unit + "\n", preflight)
        mutations = [line for line in result.stdout.splitlines() if line.startswith("mutation")]
        self.assertEqual(mutations, [
            "mutation --user disable --now early.timer", "mutation --user disable --now early.path",
            "mutation --user disable --now early.socket", "mutation --user disable --now late.mount",
            "mutation --user disable --now late.target", "mutation instances late@.service",
            "mutation --user disable --now late@one.service", "mutation --user disable --now late.service",
        ])

    def test_user_template_enumeration_empty_success_instances_and_stop_failure(self):
        script = self.function("run.sh", "stop_user_template_instances") + """
fixture_listing="$1"
stop_rc="$2"
systemctl() {
  if [[ "$2" == list-units ]]; then print -r -- "$fixture_listing"; return 0; fi
  print -- "stopped $3"; return "$stop_rc"
}
die() { print -u2 -- "$*"; exit 65; }
stop_user_template_instances fixture fixture@.service
print -- 'unlink allowed'
"""
        for listing, stop_rc, expected in (("", "0", 0), ("fixture@one.service loaded active running\nfixture@two.service loaded active running", "0", 0),
                                           ("fixture@one.service loaded active running", "1", 65)):
            result = self.zsh(script, listing, stop_rc)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual("unlink allowed" in result.stdout, expected == 0)

    def test_later_missing_stale_or_foreign_link_does_not_stop_earlier_trigger(self):
        script = "\n".join(self.function("run.sh", name) for name in (
            "verify_stow_link", "verify_user_unit_owned_for_deactivation", "deactivate_user_units"))
        script += """
repo_root="$1"
target="$2"
load_user_units_metadata() { user_units=(early.timer late.service); }
stow_target_is_home() { return 0; }
user_manager_reachable() { return 0; }
activation_bases_for_unit() { return 0; }
resolve_unit_file_path() { print -- "$1/$2"; }
unit_has_install_section() { return 0; }
systemctl() { print -- 'unexpected mutation'; exit 99; }
die() { print -u2 -- "$*"; exit 65; }
deactivate_user_units fixture
print -- 'unexpected unlink'
"""
        for bad_link in ("missing", "dangling", "foreign", "regular-file"):
            with self.subTest(bad_link=bad_link), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                units = root / "repo/packages/fixture/install/.config/systemd/user"
                live = root / "target/.config/systemd/user"
                units.mkdir(parents=True)
                live.mkdir(parents=True)
                for name in ("early.timer", "late.service"):
                    (units / name).write_text("[Install]\nWantedBy=default.target\n")
                (live / "early.timer").symlink_to(units / "early.timer")
                if bad_link == "dangling":
                    (live / "late.service").symlink_to(root / "absent")
                elif bad_link == "foreign":
                    (root / "foreign.service").write_text("[Unit]\n")
                    (live / "late.service").symlink_to(root / "foreign.service")
                elif bad_link == "regular-file":
                    (live / "late.service").write_text("[Unit]\n")
                result = self.zsh(script, str(root / "repo"), str(root / "target"))
                self.assertEqual(result.returncode, 65, result.stderr)
                self.assertIn("live unit does not belong", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_system_template_enumeration_failure_warns_without_using_partial_output(self):
        script = self.function("scripts/system-copy-select", "stop_system_template_instances") + """
sudo() {
  if [[ "$3" == list-units ]]; then print -- 'fixture@one.service loaded active running'; return 1; fi
  print -- 'unexpected stop'; exit 99
}
stop_system_template_instances fixture@.service
"""
        result = self.zsh(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning: failed to enumerate system instances", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_user_manager_probe_handles_online_offline_and_degraded_status(self):
        script = self.function("run.sh", "user_manager_reachable") + """
systemctl() { print -r -- "$fixture_state"; return "$fixture_rc"; }
fixture_state="$1"
fixture_rc="$2"
user_manager_reachable
"""
        for state, command_rc, expected in (("running", "0", 0), ("degraded", "1", 0),
                                             ("starting", "1", 0), ("offline", "1", 1), ("", "1", 1)):
            with self.subTest(state=state):
                result = self.zsh(script, state, command_rc)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertNotIn("read-only variable", result.stderr)

    def test_activation_enables_offline_without_reload_or_start(self):
        script = self.function("run.sh", "activate_user_units") + "\n" + self.function("run.sh", "enable_user_unit") + """
repo_root=/fixture
target=/fixture-target
load_user_units_metadata() { user_units=(fixture.service); }
stow_target_is_home() { return 0; }
user_manager_reachable() { return 1; }
resolve_unit_file_path() { print -r -- "$1/$2"; }
verify_stow_link() { return 0; }
activation_bases_for_unit() { return 0; }
# This offline routing fixture models a valid service with no explicit Type.
systemd_directive_value() { return 0; }
unit_has_install_section() { return 0; }
systemctl() { print -r -- "mock-systemctl:$*:offline=${SYSTEMD_OFFLINE:-0}"; }
die() { print -u2 -- "$*"; exit 65; }
activate_user_units fixture
"""
        result = self.zsh(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mock-systemctl:--user enable fixture.service:offline=1", result.stdout)
        self.assertNotIn("mock-systemctl:--user start", result.stdout)
        self.assertNotIn("mock-systemctl:--user daemon-reload", result.stdout)

    def test_install_hook_receives_the_configured_verbose_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hook = root / "packages/fixture/install.hook.sh"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\nexit 99\n")
            hook.chmod(0o755)
            script = self.function("run.sh", "run_install_hooks") + """
repo_root="$1"
target="$1/target"
env_prefix=FIXTURE
hook_packages=(fixture)
env() { print -rl -- "$@"; }
die() { print -u2 -- "$*"; exit 65; }
run_install_hooks "$2"
"""
            for verbose in ("0", "1"):
                result = self.zsh(script, str(root), verbose)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [
                    f"FIXTURE_REPO_ROOT={root}", "FIXTURE_PACKAGE=fixture",
                    f"STOW_TARGET={root}/target", f"FIXTURE_VERBOSE={verbose}", str(hook),
                ])

    def test_existing_secret_modes_reject_setid_sticky_and_group_world_bits(self):
        mocks = """
fixture_mode="$1"
load_config_metadata() {
  typeset -gA config_modes config_owners config_groups
  config_modes=(etc/fixture.conf 600)
  config_owners=(etc/fixture.conf root)
  config_groups=(etc/fixture.conf root)
}
load_system_config_metadata() { load_config_metadata "$@"; }
ensure_system_verify_sudo() { return 0; }
die() { print -u2 -- "$*"; exit 65; }
sudo() {
  case "$*" in
    '-n test -e /etc/fixture.conf'|'-n test -f /etc/fixture.conf') return 0 ;;
    '-n test -L /etc/fixture.conf') return 1 ;;
    '-n stat -c %u -- /etc/fixture.conf') print -- 0 ;;
    '-n stat -c %a -- /etc/fixture.conf') print -- "$fixture_mode" ;;
    *) print -u2 -- 'unexpected privileged command'; exit 99 ;;
  esac
}
"""
        for relative, name in (("scripts/system-copy-select", "process_package_configs"),
                               ("scripts/system-copy-select", "require_configs_present"),
                               ("run.sh", "verify_system_config_paths")):
            for mode in ("600", "400", "4600", "2600", "1600", "640", "604"):
                with self.subTest(function=name, mode=mode):
                    result = self.zsh(self.function(relative, name) + mocks + f"\n{name} fixture\n", mode)
                    self.assertEqual(result.returncode == 0, mode in ("600", "400"), result.stderr)
                    self.assertNotIn("unexpected privileged command", result.stderr)
