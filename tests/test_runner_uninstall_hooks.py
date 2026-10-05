"""User uninstall lifecycle using disposable packages and no live mutations."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_runner_review_regressions as fixtures

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("zsh"), "requires Zsh for isolated lifecycle tests")
class UninstallHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="runner hooks ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "source toolkit"
        self.target = self.base / "user target"
        self.target.mkdir()
        for name in ("scripts", "packages", "stow", "manifests"):
            (self.repo / name).mkdir(parents=True)
        for name in ("run.sh", "scripts/check-repo", "scripts/system-copy-select"):
            shutil.copy2(ROOT / name, self.repo / name)
        checker = self.repo / "scripts/check-repo"
        shebang, body = checker.read_text().split("\n", 1)
        checker.write_text(shebang + '\nprint -r -- "preflight:$*" >> "$TRACE_FILE"\n' + body)
        self.trace = self.base / "trace"
        self.trace.write_text("")
        self.extract = fixtures.ExistingReviewFixTests().function

    def package(self, name, *, user=True, system=False, hook=True, prefix="FIXTURE", exit_code=0):
        package = self.repo / "packages" / name
        package.mkdir()
        if user:
            (package / "install").mkdir()
            (self.repo / "stow" / name).symlink_to(Path("../packages") / name / "install")
        if system:
            (package / "system-install").mkdir()
            (package / "system-install.manifest").write_text("")
        if hook:
            path = package / "uninstall.hook.sh"
            context = [f"${{{prefix}_REPO_ROOT}}", f"${{{prefix}_PACKAGE}}",
                       "$STOW_TARGET", f"${{{prefix}_VERBOSE}}"]
            path.write_text(
                '#!/bin/sh\nset -eu\n'
                f'printf "hook:%s\\n" "${{{prefix}_PACKAGE}}" >> "$TRACE_FILE"\n'
                'printf "%s\\n" ' + " ".join(f'"{value}"' for value in context) +
                ' > "$CONTEXT_FILE"\n' + f"exit {exit_code}\n"
            )
            path.chmod(0o755)
        return package

    def invoke(self, *args, prefix="FIXTURE", fail_deactivate=""):
        names = ("validate_package_name", "package_has_user_install", "package_has_system_install",
                 "validate_any_package", "load_ignored_packages", "select_user_packages",
                 "select_uninstall_hook_packages", "run_uninstall_hooks",
                 "run_check_repo_for_packages", "parse_uninstall")
        script = "emulate -L zsh\nset -euo pipefail\n" + "\n".join(
            self.extract("run.sh", name) for name in names
        ) + '''
repo_root="$1"
target="$2"
env_prefix="$3"
fail_deactivate="$4"
stow_dir="$repo_root/stow"
ignore_all_file="$repo_root/manifests/ignore-all-install.txt"
shift 4
die() { print -u2 -- "$*"; exit 65; }
usage() { print -u2 -- "fixture usage"; }
stow_target_is_home() { return 1; }
deactivate_user_units() {
  print -r -- "deactivate:$1" >> "$TRACE_FILE"
  [[ "$1" != "$fail_deactivate" ]] || die "fixture deactivation failed"
  user_units=(fixture.service)
}
run_system_action() { print -r -- "system:$*" >> "$TRACE_FILE"; }
run_stow_action() { print -r -- "stow:$*" >> "$TRACE_FILE"; }
reap_orphaned_package() { print -r -- "orphaned:$*" >> "$TRACE_FILE"; }
parse_uninstall "$@"
'''
        return subprocess.run(
            ["zsh", "-f", "-c", script, "fixture", str(self.repo), str(self.target),
             prefix, fail_deactivate, *args],
            env={"PATH": os.environ["PATH"], "HOME": str(self.base / "unused home"),
                 "TRACE_FILE": str(self.trace), "CONTEXT_FILE": str(self.base / "context")},
            text=True, capture_output=True, timeout=15,
        )

    def events(self):
        return self.trace.read_text().splitlines()

    def test_mixed_package_hook_runs_between_deactivation_and_both_removal_stages(self):
        self.package("mixed", system=True)
        result = self.invoke("mixed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["preflight:-- mixed", "deactivate:mixed", "hook:mixed",
                                         "system:uninstall mixed 0", "stow:uninstall mixed 0"])

    def test_all_units_are_deactivated_before_the_first_hook(self):
        for name in ("alpha", "beta"):
            self.package(name)
        result = self.invoke("all-user")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["preflight:-- alpha beta", "deactivate:alpha",
                                         "deactivate:beta", "hook:alpha", "hook:beta",
                                         "system:uninstall all-user 0", "stow:uninstall all-user 0"])

    def test_named_selection_does_not_run_other_package_hooks(self):
        for name in ("alpha", "beta"):
            self.package(name)
        result = self.invoke("beta")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["preflight:-- beta", "deactivate:beta", "hook:beta",
                                         "system:uninstall beta 0", "stow:uninstall beta 0"])

    def test_all_exclusions_and_all_user_selection_keep_existing_semantics(self):
        self.package("alpha")
        self.package("excluded")
        (self.repo / "manifests/ignore-all-install.txt").write_text("excluded\n")
        for selector, expected in (("all", ["hook:alpha"]),
                                   ("all-user", ["hook:alpha", "hook:excluded"])):
            with self.subTest(selector=selector):
                self.trace.write_text("")
                result = self.invoke(selector)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([item for item in self.events() if item.startswith("hook:")], expected)

    def test_all_system_and_named_system_only_package_never_run_user_hooks(self):
        self.package("user")
        self.package("system", user=False, system=True)
        for selector in ("all-system", "system"):
            with self.subTest(selector=selector):
                self.trace.write_text("")
                result = self.invoke(selector)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.events(), [f"system:uninstall {selector} 0",
                                                 f"stow:uninstall {selector} 0"])

    def test_orphaned_path_bypasses_hooks_preflight_and_ordinary_uninstall(self):
        result = self.invoke("--orphaned", "--dry-run", "missing-package")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["orphaned:missing-package 1 0"])

    def test_package_without_uninstall_hook_retains_ordinary_uninstall(self):
        self.package("plain", hook=False)
        result = self.invoke("plain")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), ["preflight:-- plain", "deactivate:plain",
                                         "system:uninstall plain 0", "stow:uninstall plain 0"])

    def test_nonexecutable_hook_is_rejected_before_deactivation(self):
        package = self.package("alpha")
        (package / "uninstall.hook.sh").chmod(0o644)
        result = self.invoke("alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hook is not executable", result.stderr)
        self.assertEqual(self.events(), ["preflight:-- alpha"])

    def test_unknown_hook_remains_rejected_before_deactivation(self):
        package = self.package("alpha")
        (package / "uninstall.hook.sh").rename(package / "unexpected.hook.sh")
        result = self.invoke("alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown hook file", result.stderr)
        self.assertEqual(self.events(), ["preflight:-- alpha"])

    def test_symlinked_and_nested_hooks_remain_invalid(self):
        package = self.package("alpha")
        hook = package / "uninstall.hook.sh"
        original = self.base / "external-hook"
        hook.rename(original)
        hook.symlink_to(original)
        result = self.invoke("alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hook must be a regular file", result.stderr)
        self.assertEqual(self.events(), ["preflight:-- alpha"])
        hook.unlink()
        (package / "install/nested").mkdir()
        shutil.copy2(original, package / "install/nested/uninstall.hook.sh")
        self.trace.write_text("")
        result = self.invoke("alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hook must live in package root", result.stderr)
        self.assertEqual(self.events(), ["preflight:-- alpha"])

    def test_all_lifecycle_hooks_reject_directories_and_fifos_before_deactivation(self):
        package = self.package("alpha", hook=False)
        for name in ("install.hook.sh", "uninstall.hook.sh", "verify.hook.sh"):
            for kind in ("directory", "fifo"):
                with self.subTest(hook=name, kind=kind):
                    path = package / name
                    if kind == "directory":
                        path.mkdir()
                    else:
                        os.mkfifo(path, 0o700)
                    self.trace.write_text("")
                    try:
                        result = self.invoke("alpha")
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("hook must be a regular file", result.stderr)
                        self.assertEqual(self.events(), ["preflight:-- alpha"])
                    finally:
                        if kind == "directory":
                            path.rmdir()
                        else:
                            path.unlink()

    def test_manifest_failure_on_later_package_blocks_all_deactivation(self):
        self.package("alpha")
        package = self.package("beta")
        (package / "user-units.manifest").write_text("missing.service\n")
        result = self.invoke("all-user")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events(), ["preflight:-- alpha beta"])

    def test_deactivation_failure_on_later_package_blocks_all_hooks_and_removal(self):
        for name in ("alpha", "beta"):
            self.package(name)
        result = self.invoke("all-user", fail_deactivate="beta")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events(), ["preflight:-- alpha beta", "deactivate:alpha", "deactivate:beta"])

    def test_hook_failure_stops_later_hooks_and_removal_without_reactivation(self):
        self.package("alpha", exit_code=7)
        self.package("beta")
        result = self.invoke("all-user")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("alpha uninstall hook failed", result.stderr)
        self.assertEqual(self.events(), ["preflight:-- alpha beta", "deactivate:alpha",
                                         "deactivate:beta", "hook:alpha"])

    def test_real_hook_receives_configured_prefix_paths_and_verbose(self):
        package = self.package("alpha")
        for prefix in ("GRZ", "FIXTURE", "CUSTOM"):
            for flags, verbose in (([], "0"), (["--verbose"], "1"), (["-v"], "1")):
                for trailing in (False, True):
                    with self.subTest(prefix=prefix, flags=flags, trailing=trailing):
                        shutil.rmtree(package)
                        (self.repo / "stow/alpha").unlink()
                        package = self.package("alpha", prefix=prefix)
                        self.trace.write_text("")
                        args = ["alpha", *flags] if trailing else [*flags, "--", "alpha"]
                        result = self.invoke(*args, prefix=prefix)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual((self.base / "context").read_text().splitlines(),
                                         [str(self.repo), "alpha", str(self.target), verbose])
                        self.assertEqual(self.events()[-2:], [f"system:uninstall alpha {verbose}",
                                                              f"stow:uninstall alpha {verbose}"])


if __name__ == "__main__":
    unittest.main()
