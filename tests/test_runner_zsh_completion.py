"""Run the package completion regression through the real runner in isolation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class ZshCompletionPackageTests(unittest.TestCase):
    def test_runtime_and_completion_files_parse(self):
        install = ROOT / "packages/zsh-tools/install"
        for source in install.rglob("*"):
            if source.is_file() and (source.suffix == ".zsh" or "completion" in source.parts):
                with self.subTest(source=str(source.relative_to(ROOT))):
                    result = subprocess.run(["zsh", "-n", str(source)],
                                            text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_reload_help_isolates_caller_array_options_and_preserves_failure(self):
        reload_file = ROOT / "packages/zsh-tools/install/.zsh_scripts/functions/zshreloadcomp.zsh"
        result = subprocess.run(
            ["zsh", "-dfc", 'source "$1"; cmdhelp() { print -r -- "$1"; return 23; }; '
             'setopt KSH_ARRAYS SH_WORD_SPLIT; zshreloadcomp --help; reload_rc=$?; '
             '[[ -o KSH_ARRAYS && -o SH_WORD_SPLIT ]] || exit 99; exit $reload_rc',
             "zsh", str(reload_file)], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(result.stdout.strip(), "zshreloadcomp")

    def test_runner_discovers_and_executes_completion_regressions(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            target = sandbox / "target"
            home = sandbox / "home"
            temp = sandbox / "tmp"
            for path in (target, home, temp):
                path.mkdir()

            # Model the installed user layer without stow/install hooks or any
            # change to the real HOME. The runner verifies these links first.
            install = ROOT / "packages/zsh-tools/install"
            for source in install.rglob("*"):
                if source.is_file() or source.is_symlink():
                    destination = target / source.relative_to(install)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.symlink_to(source)
            for source, destination in (("zshrc.snippet.zsh", ".zshrc"),
                                        ("profile.snippet.sh", ".profile")):
                (target / destination).write_bytes((ROOT / "bootstrap" / source).read_bytes())

            # Package verification runs before package tests. Provide the exact
            # local mise capability required by zsh-tools without bypassing
            # verification or touching the real user environment.
            fake_mise = target / ".local/bin/mise"
            fake_mise.parent.mkdir(parents=True, exist_ok=True)
            fake_mise.write_text(
                "#!/bin/sh\n"
                '[ "${MISE_SELF_UPDATE_AVAILABLE:-}" = false ] || exit 93\n'
                '[ "$1" = help ] || exit 94\n'
                '[ "$2" = __complete_word__ ] || exit 95\n'
                "exit 0\n"
            )
            fake_mise.chmod(0o755)

            env = os.environ.copy()
            env.update(HOME=str(home), STOW_TARGET=str(target),
                       GRZ_STOW_TARGET=str(target), TMPDIR=str(temp))
            result = subprocess.run(
                ["zsh", str(ROOT / "run.sh"), "test", "zsh-tools"],
                cwd=ROOT, env=env, text=True, capture_output=True,
                stdin=subprocess.DEVNULL, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Testing: zsh-tools completion-init.sh", result.stdout)
            self.assertIn("ok - zsh completion lifecycle", result.stdout)
            self.assertIn("test: OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
