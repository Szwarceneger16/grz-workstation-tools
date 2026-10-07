"""Regression tests for the zsh-tools mise hard cutover."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "packages/zsh-tools/install/.config/profile.d/68-grz-workstation-tools-mise.sh"
RC = ROOT / "packages/zsh-tools/install/.config/zsh/rc.d/68-grz-workstation-tools-mise.zsh"
FINALIZER = ROOT / "packages/zsh-tools/install/.zsh_scripts/core/99-path-finalize.zsh"
PNPM_COMPLETION = ROOT / "packages/zsh-tools/install/.zsh_scripts/completion/functions/_pnpm"
MISE_COMPLETION = ROOT / "packages/zsh-tools/install/.zsh_scripts/completion/functions/_mise"
VERIFY_HOOK = ROOT / "packages/zsh-tools/verify.hook.sh"


def source_profile(home, path, **extra):
    env = {"HOME": str(home), "PATH": path}
    env.update(extra)
    result = subprocess.run(
        [
            "sh",
            "-c",
            '. "$1"; . "$1"; printf "%s\\n%s\\n%s\\n" "$PATH" "$PNPM_HOME" "${VOLTA_HOME-unset}"',
            "sh",
            str(PROFILE),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result


class MiseProfileTests(unittest.TestCase):
    def test_profile_preserves_caller_mise_variables(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            shims = home / ".local/share/mise/shims"
            shims.mkdir(parents=True)
            env = {
                "HOME": str(home),
                "PATH": "/usr/bin:/bin",
                "mise_shims": "caller-shims",
                "mise_data_dir": "caller-data",
            }
            result = subprocess.run(
                [
                    "sh",
                    "-c",
                    '. "$1"; printf "%s\\n%s\\n" "$mise_shims" "$mise_data_dir"',
                    "sh",
                    str(PROFILE),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["caller-shims", "caller-data"])

    def test_xdg_data_home_is_used_when_no_mise_overrides_exist(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            xdg = Path(temp) / "xdg"
            shims = xdg / "mise/shims"
            shims.mkdir(parents=True)
            result = source_profile(home, "/usr/bin:/bin", XDG_DATA_HOME=str(xdg))
            self.assertEqual(result.returncode, 0, result.stderr)
            path_value, pnpm_home, _ = result.stdout.splitlines()
            self.assertEqual(path_value.split(":")[0], str(shims))
            self.assertEqual(pnpm_home, str(home / ".local/share/pnpm"))
            self.assertEqual(path_value.split(":")[-1], str(home / ".local/share/pnpm/bin"))

    def test_mise_data_dir_is_used_before_xdg_default(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            data = Path(temp) / "mise-data"
            xdg = Path(temp) / "xdg"
            shims = data / "shims"
            shims.mkdir(parents=True)
            (xdg / "mise/shims").mkdir(parents=True)
            result = source_profile(
                home,
                "/usr/bin:/bin",
                MISE_DATA_DIR=str(data),
                XDG_DATA_HOME=str(xdg),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path_value, pnpm_home, _ = result.stdout.splitlines()
            entries = path_value.split(":")
            self.assertEqual(entries[0], str(shims))
            self.assertNotIn(str(xdg / "mise/shims"), entries)
            self.assertEqual(pnpm_home, str(home / ".local/share/pnpm"))
            self.assertEqual(entries[-1], str(home / ".local/share/pnpm/bin"))

    def test_mise_shims_dir_overrides_data_and_xdg_locations_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            dedicated = Path(temp) / "dedicated-shims"
            data = Path(temp) / "data"
            xdg = Path(temp) / "xdg"
            dedicated.mkdir(parents=True)
            (data / "shims").mkdir(parents=True)
            (xdg / "mise/shims").mkdir(parents=True)
            initial = f"/usr/bin:{dedicated}:/bin"
            result = source_profile(
                home,
                initial,
                MISE_SHIMS_DIR=str(dedicated),
                MISE_DATA_DIR=str(data),
                XDG_DATA_HOME=str(xdg),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path_value, pnpm_home, _ = result.stdout.splitlines()
            entries = path_value.split(":")
            self.assertEqual(entries.count(str(dedicated)), 1)
            self.assertNotIn(str(data / "shims"), entries)
            self.assertNotIn(str(xdg / "mise/shims"), entries)
            self.assertEqual(pnpm_home, str(home / ".local/share/pnpm"))
            self.assertEqual(entries[-1], str(home / ".local/share/pnpm/bin"))

    def test_inherited_volta_is_removed_and_pnpm_bin_is_moved_to_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            default_volta = home / ".volta/bin"
            custom_volta_home = Path(temp) / "custom-volta"
            custom_volta_bin = custom_volta_home / "bin"
            pnpm_home = Path(temp) / "pnpm"
            pnpm_bin = pnpm_home / "bin"
            shims = home / ".local/share/mise/shims"
            for directory in (default_volta, custom_volta_bin, pnpm_bin, shims):
                directory.mkdir(parents=True)

            initial = os.pathsep.join(
                (
                    str(pnpm_bin),
                    "/usr/bin",
                    str(default_volta),
                    str(pnpm_bin),
                    str(custom_volta_bin),
                    "/bin",
                )
            )
            result = source_profile(
                home,
                initial,
                VOLTA_HOME=str(custom_volta_home),
                PNPM_HOME=str(pnpm_home),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path_value, exported_pnpm_home, volta_home = result.stdout.splitlines()
            entries = path_value.split(os.pathsep)

            self.assertNotIn(str(default_volta), entries)
            self.assertNotIn(str(custom_volta_bin), entries)
            self.assertEqual(volta_home, "unset")
            self.assertEqual(exported_pnpm_home, str(pnpm_home))
            self.assertEqual(entries[-1], str(pnpm_bin))
            self.assertEqual(entries.count(str(pnpm_bin)), 1)

    def test_custom_pnpm_home_is_preserved_at_lowest_priority_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            custom_pnpm = Path(temp) / "pnpm-global"
            result = source_profile(
                home,
                "/usr/bin:/bin",
                PNPM_HOME=str(custom_pnpm),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path_value, pnpm_home, _ = result.stdout.splitlines()
            entries = path_value.split(":")
            self.assertEqual(pnpm_home, str(custom_pnpm))
            self.assertEqual(entries[-1], str(custom_pnpm / "bin"))
            self.assertEqual(entries.count(str(custom_pnpm / "bin")), 1)


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class PathFinalizerTests(unittest.TestCase):
    def test_strips_default_and_custom_inherited_volta_and_normalizes_pnpm_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            default_volta = home / ".volta/bin"
            custom_volta_home = Path(temp) / "custom-volta"
            custom_volta_bin = custom_volta_home / "bin"
            pnpm_home = Path(temp) / "pnpm"
            pnpm_bin = pnpm_home / "bin"
            for directory in (default_volta, custom_volta_bin, pnpm_bin):
                directory.mkdir(parents=True)

            env = {
                "HOME": str(home),
                "PATH": os.pathsep.join(
                    (
                        str(default_volta),
                        "/usr/bin",
                        str(pnpm_bin),
                        str(custom_volta_bin),
                        str(pnpm_bin),
                        "/bin",
                    )
                ),
                "VOLTA_HOME": str(custom_volta_home),
                "PNPM_HOME": str(pnpm_home),
            }
            result = subprocess.run(
                [
                    "zsh",
                    "-dfc",
                    'source "$1"; print -r -- "$PATH"; print -r -- "${VOLTA_HOME-unset}"; print -r -- "$PNPM_HOME"',
                    "zsh",
                    str(FINALIZER),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path_value, volta_home, exported_pnpm_home = result.stdout.splitlines()
            entries = path_value.split(os.pathsep)

            self.assertNotIn(str(default_volta), entries)
            self.assertNotIn(str(custom_volta_bin), entries)
            self.assertEqual(volta_home, "unset")
            self.assertEqual(exported_pnpm_home, str(pnpm_home))
            self.assertEqual(entries[-1], str(pnpm_bin))
            self.assertEqual(entries.count(str(pnpm_bin)), 1)


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class MiseInteractiveTests(unittest.TestCase):
    def fake_mise(self, home, version):
        binary = home / ".local/bin/mise"
        binary.parent.mkdir(parents=True)
        binary.write_text(
            "#!/bin/sh\n"
            f"version='{version}'\n"
            "[ \"${MISE_SELF_UPDATE_AVAILABLE:-}\" = false ] || exit 93\n"
            "case \"$1:$2\" in\n"
            "  help:__complete_word__) [ \"$version\" = 2026.10.3 ] || exit 98 ;;\n"
            "  activate:zsh) printf '%s\\n' 'export GRZ_FAKE_MISE_ACTIVATED=1' ;;\n"
            "  --version:*) exit 99 ;;\n"
            "  *) exit 92 ;;\n"
            "esac\n"
        )
        binary.chmod(0o755)
        return binary

    def run_rc(self, version):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            self.fake_mise(home, version)
            env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
            return subprocess.run(
                [
                    "zsh",
                    "-dfc",
                    'source "$1"; print -r -- "${GRZ_FAKE_MISE_ACTIVATED:-0}"',
                    "zsh",
                    str(RC),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_startup_scopes_self_update_disable_without_overwriting_caller_value(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            self.fake_mise(home, "2026.10.3")
            env = {
                "HOME": str(home),
                "PATH": "/usr/bin:/bin",
                "MISE_SELF_UPDATE_AVAILABLE": "caller-value",
            }
            result = subprocess.run(
                [
                    "zsh",
                    "-dfc",
                    'source "$1"; print -r -- "${GRZ_FAKE_MISE_ACTIVATED:-0}"; print -r -- "$MISE_SELF_UPDATE_AVAILABLE"',
                    "zsh",
                    str(RC),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["1", "caller-value"])

    def test_validated_binary_is_retained_for_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            selected = self.fake_mise(home, "2026.10.3")
            competing_dir = Path(temp) / "competing"
            competing_dir.mkdir()
            competing = competing_dir / "mise"
            competing.write_text("#!/bin/sh\nexit 97\n")
            competing.chmod(0o755)

            env = {
                "HOME": str(home),
                "PATH": os.pathsep.join((str(competing_dir), "/usr/bin", "/bin")),
            }
            result = subprocess.run(
                [
                    "zsh",
                    "-dfc",
                    'source "$1"; print -r -- "${__GRZ_MISE_BIN:-unset}"',
                    "zsh",
                    str(RC),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(selected))

    def test_supported_mise_is_activated(self):
        result = self.run_rc("2026.10.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1")

    def test_older_mise_is_rejected_without_fallback(self):
        result = self.run_rc("2026.4.28")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "0")
        self.assertIn("mise with __complete_word__ support is required", result.stderr)


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class MiseCompletionTests(unittest.TestCase):
    def test_completion_isolates_zsh_options_and_uses_validated_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            selected_marker = root / "selected"
            competing_marker = root / "competing"

            selected = root / "selected-mise"
            selected.write_text(
                "#!/bin/sh\n"
                'touch "$SELECTED_MARKER"\n'
                '[ "$1" = __complete_word__ ] || exit 91\n'
                "printf 'alpha\\tdescription\\talpha\\n'\n"
            )
            selected.chmod(0o755)

            competing_dir = root / "bin"
            competing_dir.mkdir()
            competing = competing_dir / "mise"
            competing.write_text(
                "#!/bin/sh\n"
                'touch "$COMPETING_MARKER"\n'
                "exit 92\n"
            )
            competing.chmod(0o755)

            env = {
                "PATH": os.pathsep.join((str(competing_dir), "/usr/bin", "/bin")),
                "SELECTED_MARKER": str(selected_marker),
                "COMPETING_MARKER": str(competing_marker),
            }
            script = (
                'compdef() { :; }; '
                'compadd() { return 0; }; '
                '_files() { return 0; }; '
                '_command_names() { return 0; }; '
                'fpath=("$1" $fpath); '
                'autoload -Uz _mise; '
                'typeset -g __GRZ_MISE_BIN="$2"; '
                'setopt KSH_ARRAYS; '
                'BUFFER="mise a"; CURSOR=${#BUFFER}; words=(mise a); CURRENT=2; '
                '_mise; status=$?; '
                '[[ -o KSH_ARRAYS ]] || exit 98; '
                'exit $status'
            )
            result = subprocess.run(
                ["zsh", "-dfc", script, "zsh", str(MISE_COMPLETION.parent), str(selected)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(selected_marker.exists())
            self.assertFalse(competing_marker.exists())


class MiseVerifyHookTests(unittest.TestCase):
    def test_verify_checks_required_completion_capability_without_version_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            target = root / "home"
            scripts = repo / "scripts"
            scripts.mkdir(parents=True)
            target.mkdir()

            ensure = scripts / "ensure-rcd-loaders"
            ensure.write_text("#!/bin/sh\nexit 0\n")
            ensure.chmod(0o755)

            mise = target / ".local/bin/mise"
            mise.parent.mkdir(parents=True)
            mise.write_text(
                "#!/bin/sh\n"
                '[ "${MISE_SELF_UPDATE_AVAILABLE:-}" = false ] || exit 93\n'
                '[ "$1" = help ] || exit 94\n'
                '[ "$2" = __complete_word__ ] || exit 95\n'
                "exit 0\n"
            )
            mise.chmod(0o755)

            env = os.environ.copy()
            env.update(
                GRZ_REPO_ROOT=str(repo),
                STOW_TARGET=str(target),
                HOME=str(target),
                MISE_SELF_UPDATE_AVAILABLE="caller-value",
            )
            result = subprocess.run(
                ["bash", str(VERIFY_HOOK)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("mise completion capability satisfies", result.stdout)


class HardCutoverTests(unittest.TestCase):
    def test_active_runtime_does_not_export_volta_or_restore_corepack_pnpm_selection(self):
        combined = "\n".join(
            path.read_text()
            for path in (PROFILE, RC, FINALIZER, PNPM_COMPLETION)
        )
        self.assertNotIn("export VOLTA_HOME", combined)
        self.assertNotIn("corepack which pnpm", combined)
        self.assertIn("unset VOLTA_HOME", combined)
        self.assertIn("unset __MISE_ORIG_PATH", RC.read_text())
        self.assertNotIn(" --version", RC.read_text())
        self.assertNotIn(" --version", VERIFY_HOOK.read_text())
        completion = MISE_COMPLETION.read_text()
        self.assertIn("_mise() {\n    emulate -L zsh", completion)
        self.assertIn("__grz_mise_dispatch() {\n    emulate -L zsh", completion)
        self.assertIn("__GRZ_MISE_BIN", completion)
        self.assertNotIn("command 'mise' __complete_word__", completion)

    def test_pnpm_home_is_preserved_as_independent_pnpm_infrastructure(self):
        profile = PROFILE.read_text()
        finalizer = FINALIZER.read_text()
        self.assertIn('export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"', profile)
        self.assertIn('$PNPM_HOME/bin', profile)
        self.assertIn('export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"', finalizer)
        self.assertIn('$PNPM_HOME/bin', finalizer)


if __name__ == "__main__":
    unittest.main()
