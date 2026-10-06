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


def source_profile(home, path, **extra):
    env = {"HOME": str(home), "PATH": path}
    env.update(extra)
    result = subprocess.run(
        ["sh", "-c", '. "$1"; printf "%s\\n%s\\n" "$PATH" "$PNPM_HOME"', "sh", str(PROFILE)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result


class MiseProfileTests(unittest.TestCase):
    def test_xdg_data_home_is_used_when_no_mise_overrides_exist(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            xdg = Path(temp) / "xdg"
            shims = xdg / "mise/shims"
            shims.mkdir(parents=True)
            result = source_profile(home, "/usr/bin:/bin", XDG_DATA_HOME=str(xdg))
            self.assertEqual(result.returncode, 0, result.stderr)
            path_value, pnpm_home = result.stdout.splitlines()
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
            path_value, pnpm_home = result.stdout.splitlines()
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
            path_value, pnpm_home = result.stdout.splitlines()
            entries = path_value.split(":")
            self.assertEqual(entries.count(str(dedicated)), 1)
            self.assertNotIn(str(data / "shims"), entries)
            self.assertNotIn(str(xdg / "mise/shims"), entries)
            self.assertEqual(pnpm_home, str(home / ".local/share/pnpm"))
            self.assertEqual(entries[-1], str(home / ".local/share/pnpm/bin"))


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class MiseInteractiveTests(unittest.TestCase):
    def fake_mise(self, home, version):
        binary = home / ".local/bin/mise"
        binary.parent.mkdir(parents=True)
        binary.write_text(
            "#!/bin/sh\n"
            f"version='{version}'\n"
            "case \"$1\" in\n"
            "  --version) printf '%s linux-x64\\n' \"$version\" ;;\n"
            "  activate) [ \"$2\" = zsh ] || exit 91; printf '%s\\n' 'export GRZ_FAKE_MISE_ACTIVATED=1' ;;\n"
            "  *) exit 92 ;;\n"
            "esac\n"
        )
        binary.chmod(0o755)

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

    def test_supported_mise_is_activated(self):
        result = self.run_rc("2026.10.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1")

    def test_older_mise_is_rejected_without_fallback(self):
        result = self.run_rc("2026.4.28")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "0")
        self.assertIn("mise >= 2026.10.3 required", result.stderr)


class HardCutoverTests(unittest.TestCase):
    def test_active_runtime_does_not_restore_volta_or_corepack_pnpm_selection(self):
        combined = "\n".join(
            path.read_text()
            for path in (PROFILE, RC, FINALIZER, PNPM_COMPLETION)
        )
        for legacy in ("VOLTA_HOME", ".volta/bin", "corepack which pnpm"):
            self.assertNotIn(legacy, combined)

    def test_pnpm_home_is_preserved_as_independent_pnpm_infrastructure(self):
        profile = PROFILE.read_text()
        finalizer = FINALIZER.read_text()
        self.assertIn('export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"', profile)
        self.assertIn('$PNPM_HOME/bin', profile)
        self.assertIn('export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"', finalizer)
        self.assertIn('$PNPM_HOME/bin', finalizer)


if __name__ == "__main__":
    unittest.main()
