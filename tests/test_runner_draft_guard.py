"""Pre-publication state races, using the trusted helper with a mocked API."""
import argparse
import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import shutil
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class DraftGuardTests(unittest.TestCase):
    def setUp(self):
        self.check = runpy.run_path(str(ROOT / "scripts/check-runner-draft"))["check"]
        self.args = argparse.Namespace(repository="test/fixture", branch="automation/runner-release-next",
                                       expected_pr="7", expected_head="a" * 40)
        self.pr = {"number": 7, "state": "open", "draft": True, "merged_at": None,
                   "base": {"ref": "main", "repo": {"full_name": "test/fixture"}},
                   "head": {"ref": self.args.branch, "sha": "a" * 40,
                            "repo": {"full_name": "test/fixture"}}}

    def execute(self, current=None, pages=None):
        current = self.pr if current is None else current
        pages = [[self.pr]] if pages is None else pages
        calls = []
        def api(argv, **kwargs):
            calls.append(argv)
            self.assertEqual(argv[:2], ["gh", "api"])
            value = pages if "--paginate" in argv else current
            return subprocess.CompletedProcess(argv, 0, json.dumps(value), "")
        with mock.patch("subprocess.run", side_effect=api):
            self.check(self.args)
        return calls

    def test_unchanged_draft_queries_exact_pr_and_all_open_branch_prs(self):
        for branch in ("automation/runner-release-next", "automation/runner-sync/runner-v1.2.3"):
            self.args.branch = self.pr["head"]["ref"] = branch
            calls = self.execute()
            self.assertIn("--paginate", calls[0])
            self.assertEqual(calls[1][-1], "repos/test/fixture/pulls/7")

    def test_ready_closed_retargeted_and_changed_head_are_rejected(self):
        for key, value in (("draft", False), ("draft", "true"), ("state", "closed"),
                           ("merged_at", "2026-01-01"), ("number", 8), ("number", True),
                           ("head", {**self.pr["head"], "sha": "b" * 40}),
                           ("head", {**self.pr["head"], "repo": {"full_name": "other/fork"}}),
                           ("base", {**self.pr["base"], "ref": "staging"})):
            with self.subTest(key=key, value=value):
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    self.execute(current={**copy.deepcopy(self.pr), key: value})

    def test_new_closed_ambiguous_and_malformed_api_responses_fail_closed(self):
        for pages in ([], {}, [None], [[self.pr, self.pr]], [[]], [[None]]):
            with self.subTest(pages=pages), self.assertRaises((ValueError, KeyError, TypeError, AttributeError)):
                self.execute(pages=pages)
        self.args.expected_pr = self.args.expected_head = ""
        self.assertEqual(len(self.execute(pages=[[]])), 1)
        with self.assertRaises(ValueError):
            self.execute()

    def test_workflow_checks_immediately_before_each_proposal_push(self):
        workflows = list((ROOT / ".github/workflows").glob("runner-*.yml"))
        found = 0
        for path in workflows:
            text = path.read_text()
            if "git push origin" not in text:
                continue
            found += 1
            prefix = text.split("git push origin", 1)[0].rstrip().splitlines()
            self.assertIn('--expected-head "$EXPECTED_HEAD"', prefix[-1])
            self.assertIn('python3 "$RUNNER_TEMP/check-runner-draft"', prefix[-2])
            self.assertLess(text.index("cp scripts/check-runner-draft"), text.index("git switch"))
        self.assertEqual(found, 1)

    def test_real_publication_step_never_pushes_after_guard_failure(self):
        workflow = ROOT / ".github/workflows/runner-sync-proposal.yml"
        step = "Commit and push the proposal without force"
        if not workflow.exists():
            workflow = ROOT / ".github/workflows/runner-release-draft.yml"
            step = "Commit and push metadata without rewriting history"
        block = workflow.read_text().split("      - name: " + step + "\n", 1)[1].split("\n      - name:", 1)[0]
        script = textwrap.dedent(block.split("        run: |\n", 1)[1]).replace("${{ inputs.release_tag }}", "runner-v1.2.3")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            shutil.copy2(ROOT / "scripts/check-runner-draft", root / "check-runner-draft")
            (root / "runner.source.lock").write_text("private_base_commit " + "a" * 40 + "\n")
            gh = root / "bin/gh"
            gh.write_text("#!" + sys.executable + "\n" + '''import json, os, sys
pr = json.loads(os.environ["FIXTURE_PR"])
if os.environ["FIXTURE_FAILURE"] == "1": sys.exit(22)
print(json.dumps([[pr]] if "--slurp" in sys.argv else pr))
''')
            gh.chmod(0o755)
            prefix = '''set -euo pipefail
git() {
  if [[ "$1" == rev-parse ]]; then printf '%s\\n' "$EXPECTED_HEAD"
  elif [[ "$1" == push ]]; then printf 'PUSH\\n' >> "$PUSH_TRACE"
  fi
}
'''
            for variant in ("draft", "ready", "closed", "head-changed", "api-failure"):
                pr = copy.deepcopy(self.pr)
                if variant == "ready": pr["draft"] = False
                if variant == "closed": pr["state"] = "closed"
                if variant == "head-changed": pr["head"]["sha"] = "b" * 40
                trace = root / "push-trace"
                trace.unlink(missing_ok=True)
                env = {"PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
                       "HOME": directory, "RUNNER_TEMP": directory, "GITHUB_REPOSITORY": "test/fixture",
                       "EXPECTED_PR": "7", "EXPECTED_HEAD": "a" * 40, "BRANCH": self.args.branch,
                       "RELEASE_BRANCH": self.args.branch, "PUSH_TRACE": str(trace),
                       "FIXTURE_PR": json.dumps(pr), "FIXTURE_FAILURE": str(int(variant == "api-failure"))}
                result = subprocess.run(["bash", "-c", prefix + script], cwd=root, env=env,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode == 0, variant == "draft", result.stderr)
                self.assertEqual(trace.exists(), variant == "draft")
