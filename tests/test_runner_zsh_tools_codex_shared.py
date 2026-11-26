"""Regression tests for opt-in shared Codex shell environment propagation."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "packages/zsh-tools/install/.config/profile.d/90-codex-shared.sh"
RC = ROOT / "packages/zsh-tools/install/.config/zsh/rc.d/90-codex-shared.zsh"
SOCKET_SUFFIX = "/.codex/app-server-control/app-server-control.sock:/rpc"


class CodexSharedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        profile = self.home / ".config/profile.d/90-codex-shared.sh"
        profile.parent.mkdir(parents=True)
        profile.symlink_to(PROFILE)
        self.conf = self.home / ".config/environment.d/90-codex-shared.conf"
        self.conf.parent.mkdir()
        self.url = f"ws+unix://localhost{self.home}{SOCKET_SUFFIX}"

    def run_fragment(self, shell="sh", fragment=PROFILE):
        result = subprocess.run(
            [shell, "-c", '. "$1"; . "$1"; env', "shell", str(fragment)],
            env={"HOME": str(self.home), "PATH": "/usr/bin:/bin", "KEEP_ME": "yes"},
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        self.assertEqual(result.stderr, "")
        return dict(line.split("=", 1) for line in result.stdout.splitlines())

    def test_missing_opt_in_does_not_change_environment(self):
        env = self.run_fragment()
        self.assertNotIn("CODEX_APP_SERVER_WS_URL", env)
        self.assertNotIn("CODEX_APP_SERVER_FORCE_CLI", env)
        self.assertEqual(env["KEEP_ME"], "yes")

    def test_literal_and_home_relative_urls(self):
        for url in (self.url, "ws+unix://localhost${HOME}" + SOCKET_SUFFIX,
                    "ws+unix://localhost$HOME" + SOCKET_SUFFIX):
            with self.subTest(url=url):
                self.conf.write_text(f"CODEX_APP_SERVER_WS_URL={url}\nCODEX_APP_SERVER_FORCE_CLI=0")
                env = self.run_fragment()
                self.assertEqual(env["CODEX_APP_SERVER_WS_URL"], self.url)
                self.assertEqual(env["CODEX_APP_SERVER_FORCE_CLI"], "0")
                self.assertEqual(env["KEEP_ME"], "yes")

    def test_invalid_or_conflicting_settings_are_not_applied(self):
        for url, force in (("ws://localhost:1234", "0"), (self.url, "1")):
            with self.subTest(url=url, force=force):
                self.conf.write_text(f"CODEX_APP_SERVER_WS_URL={url}\nCODEX_APP_SERVER_FORCE_CLI={force}\n")
                env = self.run_fragment()
                self.assertNotIn("CODEX_APP_SERVER_WS_URL", env)
                self.assertNotIn("CODEX_APP_SERVER_FORCE_CLI", env)

    def test_config_is_not_executed(self):
        marker = self.home / "unexpected"
        self.conf.write_text(
            f"CODEX_APP_SERVER_WS_URL={self.url}\nCODEX_APP_SERVER_FORCE_CLI=0\n"
            f"touch {marker}\n"
        )
        self.assertEqual(self.run_fragment()["CODEX_APP_SERVER_WS_URL"], self.url)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is not installed")
    def test_interactive_zsh_reuses_profile(self):
        self.conf.write_text(f"CODEX_APP_SERVER_WS_URL={self.url}\nCODEX_APP_SERVER_FORCE_CLI=0\n")
        env = self.run_fragment("zsh", RC)
        self.assertEqual(env["CODEX_APP_SERVER_WS_URL"], self.url)
        self.assertEqual(env["CODEX_APP_SERVER_FORCE_CLI"], "0")
