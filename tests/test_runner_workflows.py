"""Static workflow contracts and mocked trusted-state dispatch regression tests."""
import fnmatch
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "scripts/report-runner-release-state"


class RunnerWorkflowTests(unittest.TestCase):
    def test_every_exported_path_has_owner_coverage(self):
        rules = [line.split() for line in (ROOT / ".github/CODEOWNERS").read_text().splitlines()
                 if line and not line.startswith("#")]
        for manifest in ("scripts/runner-canonical-files.txt", "scripts/runner-canonical-docs.txt"):
            for entry in (ROOT / manifest).read_text().splitlines():
                if not entry or entry.startswith("#"):
                    continue
                matches = [owners for pattern, *owners in rules if fnmatch.fnmatchcase("/" + entry, pattern)]
                self.assertTrue(matches, entry)
                self.assertIn("@Szwarceneger16", matches[-1], entry)

    def test_actions_are_pinned_and_no_privileged_pr_trigger_exists(self):
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            text = path.read_text()
            self.assertNotRegex(text, r"(?m)^  pull_request_target:")
            for action in re.findall(r"uses: ([^\s]+)", text):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$", path.name)
            self.assertNotIn("gh pr merge", text)
            self.assertNotIn("gh pr ready", text)
            self.assertNotIn("gh pr review", text)
            self.assertNotRegex(text, r"git push[^\n]*--force")

    def test_state_dispatcher_is_main_defined_and_disabled_until_configured(self):
        text = (ROOT / ".github/workflows/runner-release-state.yml").read_text()
        self.assertIn("workflow_run:", text)
        self.assertIn("vars.RUNNER_AUTOMATION_ENABLED == 'true'", text)
        self.assertNotRegex(text, r"(?m)^  pull_request:")
        report = REPORT.read_text()
        self.assertNotIn('"checkout"', report)
        self.assertNotIn('"switch"', report)

    def test_tag_verifier_uses_default_branch_definition(self):
        text = (ROOT / ".github/workflows/runner-release-verify.yml").read_text()
        self.assertIn("workflow_run:", text)
        self.assertNotRegex(text, r"(?m)^  push:")
        self.assertNotIn("github.ref_name", text)
        self.assertNotIn("download-artifact", text)

    def test_draft_sets_identity_before_merge_and_never_uses_issue_state(self):
        text = (ROOT / ".github/workflows/runner-release-draft.yml").read_text()
        self.assertLess(text.index("git config user.name"), text.index("git merge --no-edit"))
        self.assertNotIn("gh issue", text)
        self.assertIn("draft=true", text)
        self.assertIn("jq -e -s", text)
        self.assertIn("RUNNER_RELEASE_REPO_ROOT", text)

    def run_dispatch(self, *, stale=False, fetch_race=False, main_race=False):
        base, head = "a" * 40, "b" * 40
        calls, updates = [], []
        with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/fixture"}):
            scope = runpy.run_path(str(REPORT))
        def execute(argv, **kwargs):
            calls.append(argv)
            if argv[0] == "gh":
                endpoint = argv[2].removeprefix("repos/test/fixture/")
                payload = json.loads(kwargs["input"]) if kwargs.get("input") else None
                if endpoint.startswith("pulls?"):
                    data = [{"number": 7, "head": {"sha": head}}] if endpoint.endswith("&page=1") else []
                elif endpoint == "check-runs":
                    data = {"id": 99}
                elif endpoint == "check-runs/99":
                    updates.append(payload)
                    self.assertEqual(argv[argv.index("--method") + 1], "PATCH")
                    data = payload
                elif endpoint == "git/ref/heads/main":
                    data = {"object": {"sha": "c" * 40 if main_race else base}}
                elif endpoint == "pulls/7":
                    data = {"head": {"sha": head}}
                else:
                    self.fail(endpoint)
                return subprocess.CompletedProcess(argv, 0, json.dumps(data), "")
            if argv[0] == "git":
                if argv[1] == "rev-parse":
                    value = head if argv[2] == "FETCH_HEAD" else base
                    if fetch_race and argv[2] == "FETCH_HEAD": value = "d" * 40
                    return subprocess.CompletedProcess(argv, 0, value + "\n", "")
                if argv[1] == "merge-base":
                    return subprocess.CompletedProcess(argv, int(stale), "", "")
                return subprocess.CompletedProcess(argv, 0, "", "")
            self.assertEqual(argv[0], "python3")
            self.assertEqual(Path(argv[1]).parent, ROOT / "scripts")
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        with mock.patch("subprocess.run", side_effect=execute):
            scope["main"]()
        self.assertEqual(len(updates), 1)
        return updates[0], calls

    def test_dispatch_publishes_success_for_exact_head_and_base(self):
        update, _ = self.run_dispatch()
        self.assertEqual(update["conclusion"], "success")

    def test_dispatch_rejects_stale_head_and_midcheck_races(self):
        for options in ({"stale": True}, {"fetch_race": True}, {"main_race": True}):
            with self.subTest(options=options):
                update, _ = self.run_dispatch(**options)
                self.assertEqual(update["conclusion"], "failure")
