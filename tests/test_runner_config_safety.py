"""Regression tests for shared config validation and staged public-safety scans."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest

import test_runner_review_regressions as fixtures

ROOT = Path(__file__).resolve().parents[1]


class RunnerPrefixTests(unittest.TestCase):
    def check_config(self, role, prefix, command="check", remote=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = fixtures.RunnerDocumentationTests()
            helper.fixture(root, role)
            config = f"RUNNER_SYNC_ROLE={role}\n"
            if prefix is not None:
                config += f"RUNNER_ENV_PREFIX={prefix}\n"
            if remote is not None:
                config += f"RUNNER_CANONICAL_REMOTE={remote}\n"
            (root / "runner.conf").write_text(config)
            before = [(root / name).read_bytes() for name in ("runner.lock", "runner.docs.lock")]
            result = helper.execute(root, [
                f"RUNNER_SYNC_EXPECTED_ROLE={role}", f"RUNNER_SYNC_WRITE={int(command == 'lock')}",
                "./scripts/sync-runner", command,
            ])
            self.assertEqual(before, [(root / name).read_bytes() for name in ("runner.lock", "runner.docs.lock")])
            return result

    def test_invalid_prefixes_fail_before_check_or_lock(self):
        for role in ("source", "consumer"):
            for prefix in (None, "", "TOOLS-WORK", "foo/bar", "9TOOLS", "foo.bar", "foo:bar", "foo@bar", "foo+bar", "foo%bar"):
                for command in ("check", "lock"):
                    with self.subTest(role=role, prefix=prefix, command=command):
                        result = self.check_config(role, prefix, command)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("RUNNER_ENV_PREFIX", result.stderr)

    def test_valid_identifiers_and_remote_url_remain_supported(self):
        for role in ("source", "consumer"):
            for prefix in ("FIXTURE", "_tools", "tools_2"):
                with self.subTest(role=role, prefix=prefix):
                    result = self.check_config(role, prefix, remote="https://example.invalid/owner/runner.git")
                    self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(shutil.which("zsh") and shutil.which("git"), "requires zsh and git")
class PublicSafetyPathTests(unittest.TestCase):
    def audit(self, content, unstaged=None, *, relative="fixture.txt", remove_package=False,
              symlink=False, scanner_marker=None, fail_reads=False, policy=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts/audit-public-safety", root / "scripts/audit-public-safety")
            if scanner_marker is not None:
                with (root / "scripts/audit-public-safety").open("a") as stream:
                    stream.write("\n# " + scanner_marker + "\n")
            sample = root / relative
            sample.parent.mkdir(parents=True, exist_ok=True)
            if symlink:
                sample.symlink_to(content)
            else:
                sample.write_bytes(content if isinstance(content, bytes) else content.encode())
            env = {"PATH": os.environ["PATH"], "HOME": directory,
                   "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
            subprocess.run(["git", "init", "-q", root], check=True, env=env, capture_output=True)
            subprocess.run(["git", "add", "--", "scripts/audit-public-safety", relative],
                           cwd=root, check=True, env=env, capture_output=True)
            if policy is not None:
                policy_path = root / "manifests/public-safety-allowlist.json"
                policy_path.parent.mkdir()
                policy_path.write_text(policy)
                subprocess.run(["git", "add", "--", "manifests/public-safety-allowlist.json"],
                               cwd=root, check=True, env=env, capture_output=True)
            if unstaged is not None:
                sample.write_text(unstaged)
            if remove_package:
                shutil.rmtree(root / "packages")  # Disposable fixture, not repository content.
            if fail_reads:
                binary = root / "bin"
                binary.mkdir()
                wrapper = binary / "git"
                wrapper.write_text("#!/bin/sh\nfor arg do\n"
                                   "  test \"$arg\" != cat-file || exit 128\ndone\n"
                                   "exec " + shlex.quote(shutil.which("git")) + " \"$@\"\n")
                wrapper.chmod(0o755)
                env["PATH"] = str(binary) + os.pathsep + env["PATH"]
            return subprocess.run(["zsh", "scripts/audit-public-safety"], cwd=root, env=env,
                                  text=True, capture_output=True, timeout=10)

    def test_both_install_layers_are_scanned_from_the_index(self):
        for layer in ("install", "system-install"):
            for removed in (False, True):
                with self.subTest(layer=layer, removed=removed):
                    path = f"packages/new/{layer}/etc/service/config"
                    result = self.audit("password=synthetic-value\n", relative=path, remove_package=removed)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("[secret-word]: " + path, result.stderr)
                    self.assertNotIn("synthetic-value", result.stdout + result.stderr)

    def test_templates_do_not_exempt_generic_assignments(self):
        for layer in ("install", "system-install"):
            path = f"packages/new/{layer}/config.example"
            self.assertEqual(self.audit("pass" + "word=placeholder\n", relative=path).returncode, 1)
            token = "gh" + "p_" + "A" * 36
            result = self.audit(token, relative=path)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(token, result.stdout + result.stderr)

    def test_binary_runtime_blobs_do_not_bypass_either_layer(self):
        for layer in ("install", "system-install"):
            result = self.audit(b"\0password=synthetic-value\n", relative=f"packages/new/{layer}/config")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("synthetic-value", result.stderr)

    def test_scanner_itself_and_symlink_text_are_not_exempt(self):
        marker = "gh" + "p_" + "B" * 36
        for args in ({"scanner_marker": marker}, {"symlink": True}):
            result = self.audit(marker if args.get("symlink") else "clean", **args)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(marker, result.stdout + result.stderr)

    def test_object_read_error_is_fatal_not_a_clean_scan(self):
        result = self.audit("clean", fail_reads=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("audit-public-safety: ok", result.stdout)

    def test_opaque_authentication_headers_are_detected_repository_wide(self):
        header, scheme, value = "Author" + "ization", "Bea" + "rer", "opaque-fixture-value"
        payloads = (
            header + ": " + scheme + " " + value,
            "proxy-" + header.lower() + ":\tBasic " + value,
            header.upper() + " = " + value,
            '{"' + header + '": "Basic ' + value + '"}',
            "'" + header + "':\n  '" + scheme.lower() + "\t" + value + "'",
            "HTTP_PROXY_AUTHORIZATION='" + value + "'",
            scheme.swapcase() + "\t" + value,
        )
        for path in ("fixture.txt", "docs/example.md", "config.example",
                     "packages/new/install/config", "packages/new/system-install/config"):
            for index, payload in enumerate(payloads):
                with self.subTest(path=path, variant=index):
                    result = self.audit(payload, relative=path)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("[credential]: " + path, result.stderr)
                    self.assertNotIn(value, result.stdout + result.stderr)

    def test_authentication_headers_in_binary_symlink_and_scanner_blobs(self):
        payload = "Author" + "ization: Basic opaque-fixture-value"
        for content, kwargs in ((b"\0" + payload.encode(), {}), (payload, {"symlink": True}),
                                ("clean", {"scanner_marker": payload})):
            result = self.audit(content, **kwargs)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("opaque-fixture-value", result.stdout + result.stderr)

    def test_empty_authentication_indicators_in_search_documentation_are_not_values(self):
        header, scheme = "Author" + "ization", "Bea" + "rer"
        for payload in (header + ":", header + ': ""', header + ":|" + scheme + " '"):
            result = self.audit(payload)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_filenames_cannot_inject_log_commands(self):
        name = "fixture\n::warning::injected"
        result = self.audit("gh" + "p_" + "C" * 36, relative=name)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("\n::warning::", result.stderr + result.stdout)

    def test_generic_token_assignments_are_detected_in_both_install_layers(self):
        for layer in ("install", "system-install"):
            for key in ("token", "TOKEN", "api_token", "apiToken", "auth-token", "session_token"):
                for form in (key + "=opaque-fixture", '"' + key + '": "opaque-fixture"',
                             "'" + key + "' :\n  'opaque-fixture'"):
                    with self.subTest(layer=layer, key=key):
                        result = self.audit(form, relative=f"packages/demo/{layer}/config")
                        self.assertEqual(result.returncode, 1)
                        self.assertIn("[secret-word]", result.stderr)
                        self.assertNotIn("opaque-fixture", result.stdout + result.stderr)

    def test_token_assignment_detection_handles_binary_and_symlink_blobs(self):
        for layer in ("install", "system-install"):
            path = f"packages/demo/{layer}/config"
            for content, kwargs in ((b"\0token=opaque-fixture", {}),
                                    ("api_token=opaque-fixture", {"symlink": True})):
                result = self.audit(content, relative=path, **kwargs)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("opaque-fixture", result.stdout + result.stderr)

    def test_token_comparisons_and_noncredential_names_are_not_assignments(self):
        for content in ('[[ "$token" == fixture ]]', 'if token == "fixture": pass',
                        'token_count=1\ntokenizer=fixture\n'):
            result = self.audit(content, relative="packages/demo/install/script")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_generic_assignments_are_detected_repository_wide(self):
        for path in ("scripts/deploy", ".github/workflows/deploy.yml", "docs/example.md",
                     "config.json", "config.example", "nested/.env.example"):
            for name in ("PASSWORD", "dbPassword", "DB_PASSWD", "clientSecret", "api-key",
                         "session_token", "TOKEN"):
                for assignment in (name + "=opaque-fixture", '"' + name + '": "opaque-fixture"',
                                   "'" + name + "':\n  'opaque-fixture'", name + "=${VALUE}"):
                    with self.subTest(path=path, name=name, assignment=assignment):
                        result = self.audit(assignment, relative=path)
                        self.assertEqual(result.returncode, 1, result.stderr)
                        self.assertIn("[secret-word]: " + path, result.stderr)
                        self.assertNotIn("opaque-fixture", result.stdout + result.stderr)

    def test_cookies_are_detected_repository_wide(self):
        for path in ("scripts/deploy", ".github/workflows/deploy.yml", "docs/example.md",
                     "config.example", ".env.example", "packages/new/install/config"):
            for name in ("Cookie", "cookie", "Set-Cookie", "HTTP_COOKIE"):
                for assignment in (name + ": session=opaque-fixture", name + "=opaque-fixture",
                                   '"' + name + '": "opaque-fixture"',
                                   "'" + name + "':\n  'opaque-fixture'", name + "=${VALUE}"):
                    with self.subTest(path=path, name=name):
                        result = self.audit(assignment, relative=path)
                        self.assertEqual(result.returncode, 1, result.stderr)
                        self.assertIn("[credential]: " + path, result.stderr)
                        self.assertNotIn("opaque-fixture", result.stdout + result.stderr)

    def test_non_api_key_assignments_are_detected_repository_wide(self):
        names = ("SSH_PRIVATE_KEY", "encryption_key", "privateKey", "SSH_KEY",
                 "signing-key", "decryptionKey", "master_key", "AES_KEY",
                 "RSA_KEY", "ECDSA_KEY", "ED25519_KEY", "symmetric_key",
                 "asymmetric_key", "accessKey", "client_key", "auth_key",
                 "session_key", "secretKey", "PRIVATE_KEY_B64", "encryptionKeyHex",
                 "signing_key_pem")
        for path in ("scripts/deploy", ".github/workflows/deploy.yml", "docs/example.md",
                     "config.example", ".env.example", "packages/demo/install/config"):
            for name in names:
                for content in (name + "=opaque-fixture", '"' + name + '": "opaque-fixture"',
                                "'" + name + "':\n  'opaque-fixture'", name + "=${VALUE}"):
                    with self.subTest(path=path, name=name):
                        result = self.audit(content, relative=path)
                        self.assertEqual(result.returncode, 1, result.stderr)
                        self.assertIn("[secret-word]: " + path, result.stderr)
                        self.assertNotIn("opaque-fixture", result.stdout + result.stderr)

    def test_repository_wide_indicators_cover_binary_symlinks_and_scanner_itself(self):
        for payload in ("PASS" + "WORD=opaque-fixture", "Coo" + "kie: session=opaque-fixture",
                        "SSH_PRIVATE_" + "KEY=opaque-fixture"):
            for content, kwargs in ((b"\0" + payload.encode(), {}), (payload, {"symlink": True}),
                                    ("clean", {"scanner_marker": payload})):
                result = self.audit(content, **kwargs)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("opaque-fixture", result.stdout + result.stderr)

    def test_empty_indicators_prose_and_comparisons_are_not_stored_values(self):
        for name in ("PASSWORD", "secret", "api_key", "token", "Cookie", "Set-Cookie",
                     "SSH_PRIVATE_KEY", "encryptionKey"):
            for payload in (name, name + "=", name + ': ""', name + " == other",
                            name + "_count=1", name + ":|", name + "=''"):
                with self.subTest(name=name, payload=payload):
                    result = self.audit(payload)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_reviewed_policy_is_bound_to_path_category_and_complete_blob(self):
        for name, category in (("PASSWORD", "secret-word"), ("Cookie", "credential"),
                               ("SSH_PRIVATE_KEY", "secret-word")):
            payload = name + "=${FIXTURE_INPUT}"
            entry = {"path": "fixture.txt", "category": category,
                     "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                     "reason": "Reviewed synthetic variable reference"}
            policy = json.dumps([entry])
            self.assertEqual(self.audit(payload, policy=policy).returncode, 0)
            self.assertEqual(self.audit(payload + "extra", policy=policy).returncode, 1)
            self.assertEqual(self.audit(payload, relative="other.txt", policy=policy).returncode, 1)
            other = dict(entry, category="home-path")
            self.assertEqual(self.audit(payload, policy=json.dumps([other])).returncode, 1)
            marker = "gh" + "p_" + "X" * 36
            content = payload + "\n" + marker
            allowed = dict(entry, sha256=hashlib.sha256(content.encode()).hexdigest(), category="secret-word")
            self.assertEqual(self.audit(content, policy=json.dumps([allowed])).returncode, 1)

    def test_malformed_or_duplicate_policy_fails_closed(self):
        entry = {"path": "fixture.txt", "category": "secret-word",
                 "sha256": "a" * 64, "reason": "Synthetic fixture"}
        invalid = ("not-json", "{}", "[null]", json.dumps([entry, entry]),
                   json.dumps([dict(entry, path="../fixture")]),
                   json.dumps([dict(entry, category="all")]),
                   json.dumps([dict(entry, sha256="not-a-digest")]),
                   json.dumps([dict(entry, reason="")]))
        for policy in invalid:
            with self.subTest(policy=policy):
                result = self.audit("clean", policy=policy)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("not-json", result.stdout + result.stderr)

    def test_dotenv_paths_are_rejected_independently_of_content(self):
        paths = (".env", "nested/.env", "packages/demo/install/.env", ".env.local",
                 ".env.production.local", ".env.bak", ".ENV", ".env.example.bak",
                 ".env.production.example", ".env/config", ".env.example/config")
        for path in paths:
            with self.subTest(path=path):
                result = self.audit("SESSION_ID=opaque-fixture\n", relative=path)
                self.assertEqual(result.returncode, 1)
                self.assertIn("[dotenv-path]", result.stderr)
                self.assertNotIn("opaque-fixture", result.stdout + result.stderr)
        self.assertEqual(self.audit("", relative=".env").returncode, 1)
        self.assertEqual(self.audit("unread-target", relative="nested/.env", symlink=True).returncode, 1)

    def test_dotenv_template_name_does_not_exempt_credential_content(self):
        for path in (".env.example", "nested/.env.example"):
            self.assertEqual(self.audit("SESSION_ID=\n", relative=path).returncode, 0)
            marker = "gh" + "p_" + "A" * 36
            for content in (marker, "Author" + "ization: Basic opaque-fixture"):
                result = self.audit(content, relative=path)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(marker, result.stdout + result.stderr)
        self.assertEqual(self.audit("clean", relative=".environment").returncode, 0)

    def test_runner_placeholder_is_the_only_exempt_home(self):
        allowed = "/" + "home/runner"
        self.assertEqual(self.audit(allowed + "/work " + allowed + "/cache\n").returncode, 0)
        for personal in ("/" + "home/fixture-person", "/" + "Users/fixture-person",
                         allowed + "-other", allowed + "_other", allowed + ".other", "/" + "Users/runner"):
            for content in (personal + " " + allowed, allowed + " " + personal, allowed + "\n" + personal):
                with self.subTest(personal=personal, content_order=content.startswith(allowed)):
                    result = self.audit(content + "\n")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("[home-path]: fixture.txt", result.stderr)
                    self.assertNotIn(personal, result.stdout + result.stderr)
                    self.assertNotIn(allowed, result.stdout + result.stderr)

    def test_many_matches_do_not_hide_findings_via_pipefail(self):
        allowed, personal = "/" + "home/runner", "/" + "home/fixture-person"
        result = self.audit((personal + " " + allowed + "\n") * 10000)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.count("[home-path]: fixture.txt"), 1)
        self.assertNotIn(personal, result.stderr)

    def test_scan_reads_staged_content_not_worktree(self):
        allowed, personal = "/" + "home/runner", "/" + "home/fixture-person"
        self.assertNotEqual(self.audit(allowed + " " + personal, unstaged=allowed).returncode, 0)
        self.assertEqual(self.audit(allowed, unstaged=personal).returncode, 0)
