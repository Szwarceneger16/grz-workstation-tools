"""Passphrase detection uses synthetic values and disposable Git fixtures only."""
import hashlib
import json
import shutil
import unittest

import test_runner_config_safety as fixtures


@unittest.skipUnless(shutil.which("zsh") and shutil.which("git"), "requires zsh and git")
class PassphraseSafetyTests(unittest.TestCase):
    def audit(self, *args, **kwargs):
        return fixtures.PublicSafetyPathTests().audit(*args, **kwargs)

    def test_assignments_in_all_repository_layers(self):
        for path in ("scripts/tool", ".github/workflows/example.yml", "docs/example.md",
                     "config.json", ".env.example", "packages/demo/install/config",
                     "packages/demo/system-install/config.example"):
            for name in ("passphrase", "SSH_KEY_PASSPHRASE", "keyPassphrase",
                         "GPG_PASS_PHRASE", "key-pass-phrase"):
                for payload in (name + "=synthetic-fixture", '"' + name + '": "synthetic-fixture"',
                                "'" + name + "':\n  'synthetic-fixture'", name + "=${VALUE}"):
                    with self.subTest(path=path, name=name, payload=payload):
                        result = self.audit(payload, relative=path)
                        self.assertEqual(result.returncode, 1, result.stderr)
                        self.assertIn("[secret-word]: " + path, result.stderr)
                        self.assertNotIn("synthetic-fixture", result.stdout + result.stderr)

    def test_binary_symlink_and_scanner_content_are_checked(self):
        payload = "SSH_KEY_PASSPHRASE" + "=synthetic-fixture"
        for content, kwargs in ((b"\0" + payload.encode(), {}), (payload, {"symlink": True}),
                                ("clean", {"scanner_marker": payload})):
            result = self.audit(content, **kwargs)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn("synthetic-fixture", result.stdout + result.stderr)

    def test_prose_empty_values_and_comparisons_are_not_assignments(self):
        key = "passphrase"
        for payload in ("Enter a passphrase", key + "=", key + '=\"\"',
                        key + ' == "fixture"', key + "_file=example", key + "_length=12"):
            result = self.audit(payload)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_reviewed_fixture_exception_is_bound_to_exact_blob(self):
        payload = "pass" + "phrase=synthetic-fixture"
        policy = json.dumps([{"path": "fixture.txt", "category": "secret-word",
                              "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                              "reason": "Synthetic regression fixture only."}])
        self.assertEqual(self.audit(payload, policy=policy).returncode, 0)
        self.assertEqual(self.audit(payload + "-changed", policy=policy).returncode, 1)
