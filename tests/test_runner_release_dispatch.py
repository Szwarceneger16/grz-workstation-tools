"""Exercise the trusted dispatcher's API/ref guards without network or writes."""

import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / "scripts/dispatch-runner-release-checks"
BRANCH = "automation/runner-release-next"
BASE, HEAD = "a" * 40, "b" * 40


class ReleaseCheckDispatchTests(unittest.TestCase):
    def run_dispatch(self, case="ok"):
        scope = runpy.run_path(str(DISPATCH))
        calls = []
        pr = {"number": 7, "state": "open", "head": {"sha": HEAD, "ref": BRANCH,
              "repo": {"full_name": "test/fixture"}},
              "base": {"ref": "main", "repo": {"full_name": "test/fixture"}}}
        if case == "fork":
            pr["head"]["repo"]["full_name"] = "other/fixture"
        elif case == "wrong-branch":
            pr["head"]["ref"] = "other"
        elif case == "wrong-base":
            pr["base"]["ref"] = "other"
        elif case == "malformed-sha":
            pr["head"]["sha"] = "--malicious"
        main_reads = 0

        def execute(argv, **kwargs):
            nonlocal main_reads
            calls.append(list(argv))
            self.assertEqual(kwargs["cwd"], ROOT)
            self.assertTrue(kwargs["check"])
            output = ""
            if argv[:2] == ("gh", "api"):
                endpoint = argv[2].removeprefix("repos/test/fixture/")
                if endpoint == "git/ref/heads/main":
                    main_reads += 1
                    value = "c" * 40 if case == "stale-main" or (case == "main-race" and main_reads == 2) else BASE
                    data = {"object": {"sha": value}}
                elif endpoint.startswith("pulls?"):
                    data = [] if case == "missing-pr" else [pr, pr] if case == "multiple-prs" else [pr]
                elif endpoint == "pulls/7":
                    data = copy.deepcopy(pr)
                    if case == "head-race":
                        data["head"]["sha"] = "c" * 40
                    elif case == "closed-pr":
                        data["state"] = "closed"
                    elif case == "retargeted-pr":
                        data["base"]["ref"] = "other"
                else:
                    self.fail(endpoint)
                output = json.dumps(data)
            elif argv[:2] == ("git", "rev-parse"):
                output = BASE if argv[2] == "HEAD" else "d" * 40 if case == "fetch-race" else HEAD
            elif argv[:2] == ("git", "fetch"):
                self.assertEqual(argv[-1], f"refs/heads/{BRANCH}")
            elif argv[:2] == ("git", "merge-base"):
                if case == "stale-branch":
                    raise subprocess.CalledProcessError(1, argv)
            elif argv[:2] == ("git", "diff"):
                output = "runner.release\n.github/workflows/check-repo.yml" if case == "code-change" else "" if case == "empty-diff" else "runner.release"
            elif argv[:3] == ("gh", "workflow", "run"):
                if case == "dispatch-error":
                    raise subprocess.CalledProcessError(1, argv)
            else:
                self.fail(argv)
            return subprocess.CompletedProcess(argv, 0, output, "")

        env = {"GITHUB_REPOSITORY": "test/fixture", "GITHUB_REF": "refs/heads/feature" if case == "wrong-ref" else "refs/heads/main"}
        with mock.patch.dict(os.environ, env), mock.patch("subprocess.run", side_effect=execute):
            if case == "ok":
                scope["main"]()
            else:
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    scope["main"]()
        return calls

    def test_dispatch_passes_exact_sha_and_fixed_workflow_and_branch(self):
        expected = ["gh", "workflow", "run", "check-repo.yml", "--repo", "test/fixture", "--ref", BRANCH,
                    "-f", f"expected_head_sha={HEAD}"]
        # An idempotent publication retry must still be able to request checks.
        for _ in range(2):
            calls = self.run_dispatch()
            self.assertEqual(calls[-1], expected)
            self.assertEqual(sum(call[:3] == ["gh", "workflow", "run"] for call in calls), 1)
            self.assertFalse(any(call[0] == "git" and call[1] in ("switch", "checkout", "push") for call in calls))

    def test_untrusted_stale_or_ambiguous_targets_never_dispatch(self):
        for case in ("wrong-ref", "fork", "wrong-branch", "wrong-base", "malformed-sha", "missing-pr", "multiple-prs",
                     "stale-main", "fetch-race", "stale-branch", "code-change", "empty-diff",
                     "main-race", "head-race", "closed-pr", "retargeted-pr"):
            with self.subTest(case=case):
                calls = self.run_dispatch(case)
                self.assertFalse(any(call[:3] == ["gh", "workflow", "run"] for call in calls))

    def test_dispatch_api_failure_is_not_reported_as_success(self):
        self.run_dispatch("dispatch-error")

    def test_actual_workflow_sha_guard_rejects_ref_races(self):
        text = (ROOT / ".github/workflows/check-repo.yml").read_text()
        guard = text.split("      - name: Bind explicit dispatch to the exact release head\n", 1)[1].split("      - name:", 1)[0]
        script = guard.split("        run: |\n", 1)[1]
        script = "\n".join(line.removeprefix("          ") for line in script.splitlines())
        for ref, expected, actual, code in (
            (f"refs/heads/{BRANCH}", HEAD, HEAD, 0),
            (f"refs/heads/{BRANCH}", HEAD, BASE, 1),
            ("refs/heads/main", HEAD, HEAD, 1),
            (f"refs/heads/{BRANCH}", "", HEAD, 1),
            (f"refs/heads/{BRANCH}", "$(exit 0)", HEAD, 1),
        ):
            with self.subTest(ref=ref, expected=expected, actual=actual):
                result = subprocess.run(["bash", "-c", script], env={**os.environ,
                    "GITHUB_REF": ref, "EXPECTED_HEAD_SHA": expected, "GITHUB_SHA": actual}, capture_output=True)
                self.assertEqual(result.returncode, code)
        self.assertLess(text.index("Bind explicit dispatch"), text.index("uses: actions/checkout@"))
        self.assertIn("contents: read", text)
        self.assertNotIn("secrets.", text)
        self.assertIn("persist-credentials: false", text)

    def test_dispatch_write_permission_is_separate_from_candidate_tests(self):
        text = (ROOT / ".github/workflows/runner-release-draft.yml").read_text()
        publish, dispatch = text.split("  dispatch-release-checks:\n", 1)
        self.assertNotIn("actions: write", publish)
        self.assertIn("needs: update-release-draft", dispatch)
        self.assertNotIn("steps.branch.outputs.skip", dispatch)
        self.assertIn("actions: write", dispatch)
        self.assertIn("ref: main", dispatch)
        self.assertIn("persist-credentials: false", dispatch)
        self.assertNotRegex(dispatch, r"contents: write|secrets\.")

    def test_signing_issue_uses_derived_parent(self):
        text = (ROOT / ".github/workflows/runner-release-signing-request.yml").read_text()
        self.assertIn("RELEASE_SHA: ${{ steps.state.outputs.release_parent }}", text)
        self.assertNotIn("RELEASE_SHA: ${{ github.sha }}", text)
