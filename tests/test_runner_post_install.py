"""Exercise real install/verify parsing and hook propagation without live actions."""
import tempfile
from pathlib import Path
import unittest

import test_runner_review_regressions as fixtures


class PostInstallVerificationTests(unittest.TestCase):
    def invoke(self, args, *, fail_hook=False):
        helper = fixtures.ExistingReviewFixTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "packages/fixture"
            (package / "install").mkdir(parents=True)
            (root / "target").mkdir()
            for name in ("install.hook.sh", "verify.hook.sh"):
                hook = package / name
                hook.write_text("#!/bin/sh\nexit 99\n")
                hook.chmod(0o755)
            names = ("parse_install", "parse_verify", "run_verify", "verify_user_package", "run_install_hooks")
            script = "set -e\n" + "\n".join(helper.function("run.sh", name) for name in names) + """
repo_root="$1"
target="$1/target"
env_prefix=FIXTURE
verify_verbose=0
fixture_fail="$2"
shift 2
die() { print -u2 -- "$*"; exit 65; }
select_install_hook_packages() { hook_packages=(fixture); }
select_user_packages() { selected_user_packages=(fixture); }
select_system_packages() { selected_system_packages=(); }
run_check_repo_for_packages() { return 0; }
run_stow_action() { print -- "mock-stow:$*"; }
run_system_action() { print -- "mock-system:$*"; }
verify_user_live_units() { return 0; }
finish_system_verify_sudo() { return 0; }
run_test() { print -- "mock-tests:verbose=$verify_verbose"; }
env() {
  print -r -- "mock-hook:$*"
  if [[ "$fixture_fail" == 1 && "${@[-1]}" == */verify.hook.sh ]]; then return 7; fi
  return 0
}
mode="$1"
shift
case "$mode" in
  install) parse_install "$@" ;;
  verify) parse_verify "$@" ;;
esac
"""
            return helper.zsh(script, str(root), str(int(fail_hook)), *args)

    def test_verbose_reaches_post_install_and_standalone_verify_hooks(self):
        for mode in ("install", "verify"):
            for flags, verbose in (([], "0"), (["--verbose"], "1"), (["-v"], "1")):
                for trailing in (False, True):
                    args = [mode] + (["--verify"] if mode == "install" else [])
                    args += ["fixture", *flags] if trailing else [*flags, "--", "fixture"]
                    with self.subTest(args=args):
                        result = self.invoke(args)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        hooks = [line for line in result.stdout.splitlines() if line.startswith("mock-hook:")]
                        self.assertEqual(len(hooks), 2 if mode == "install" else 1)
                        for line in hooks:
                            self.assertIn(f"FIXTURE_VERBOSE={verbose}", line)
                        self.assertTrue(hooks[-1].endswith("/verify.hook.sh"))

    def test_install_without_verify_does_not_run_verify_hook(self):
        result = self.invoke(["install", "--verbose", "fixture"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("/verify.hook.sh", result.stdout)
        self.assertIn("FIXTURE_VERBOSE=1", result.stdout)

    def test_verbose_reaches_install_tests_with_and_without_verify(self):
        for flags, verbose in (([], "0"), (["--verbose"], "1"), (["-v"], "1")):
            for verify in ([], ["--verify"]):
                result = self.invoke(["install", *flags, *verify, "--test", "fixture"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"mock-tests:verbose={verbose}", result.stdout)

    def test_failed_post_install_verification_is_not_hidden_by_tests(self):
        result = self.invoke(["install", "--verbose", "--verify", "--test", "fixture"], fail_hook=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verify: FAILED", result.stderr)
        self.assertNotIn("mock-tests:", result.stdout)
