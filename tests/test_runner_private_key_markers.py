"""Synthetic private-key markers only; no real cryptographic key material."""
import hashlib
import json
import shutil
import unittest

import test_runner_config_safety as fixtures


@unittest.skipUnless(shutil.which("zsh") and shutil.which("git"), "requires zsh and git")
class PrivateKeyMarkerTests(unittest.TestCase):
    def marker(self, kind):
        return "-----BEGIN " + kind + "-----\nsynthetic-not-key-material\n"

    def test_pgp_and_existing_private_key_markers_across_repository_layers(self):
        for kind in ("PGP PRIVATE KEY BLOCK", "PRIVATE KEY", "RSA PRIVATE KEY",
                     "EC PRIVATE KEY", "OPENSSH PRIVATE KEY", "ENCRYPTED PRIVATE KEY"):
            for path in ("fixture.asc", "scripts/example", "docs/example.md", ".env.example",
                         "packages/demo/install/key.example", "packages/demo/system-install/key"):
                with self.subTest(kind=kind, path=path):
                    result = fixtures.PublicSafetyPathTests().audit(self.marker(kind), relative=path)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("[credential]: " + path, result.stderr)
                    self.assertNotIn("synthetic-not-key-material", result.stdout + result.stderr)

    def test_pgp_markers_in_binary_symlink_and_scanner_content(self):
        payload = self.marker("PGP PRIVATE KEY BLOCK")
        for content, kwargs in ((b"\0" + payload.encode(), {}), (payload, {"symlink": True}),
                                ("clean", {"scanner_marker": payload})):
            result = fixtures.PublicSafetyPathTests().audit(content, **kwargs)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn("synthetic-not-key-material", result.stdout + result.stderr)

    def test_public_material_does_not_match_private_key_marker(self):
        for kind in ("PGP PUBLIC KEY BLOCK", "PGP SIGNATURE", "PUBLIC KEY", "CERTIFICATE"):
            result = fixtures.PublicSafetyPathTests().audit(self.marker(kind))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_synthetic_exception_requires_exact_blob(self):
        payload = self.marker("PGP PRIVATE KEY BLOCK")
        policy = json.dumps([{"path": "fixture.asc", "category": "credential",
                              "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                              "reason": "Synthetic marker, not a real key."}])
        for content, expected in ((payload, 0), (payload + "changed", 1)):
            result = fixtures.PublicSafetyPathTests().audit(content, relative="fixture.asc", policy=policy)
            self.assertEqual(result.returncode, expected, result.stderr)
