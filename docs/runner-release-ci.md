# Release CI and frozen snapshot validation

This is repository-local workflow documentation, not part of the canonical
documentation export. These helpers are not installable packages and do not
change the local workstation.

## Checks for the aggregate release PR

`runner-release-draft.yml` publishes with `GITHUB_TOKEN`. Do not rely on its
push/PR events to start the required checks without another approval. A separate
`dispatch-release-checks` job explicitly dispatches `check-repo.yml`, using only
`contents: read`, `pull-requests: read`, and `actions: write`.

The dispatcher runs from `main`. It requires exactly one open same-repository
release PR targeting `main`, a fresh main checkout, main ancestry, and a branch
whose entire tree diff from main is only `runner.release`. It rechecks both refs
before dispatch and never checks out or executes the release candidate. Unexpected
changes, stale refs, or API errors fail closed. The job also runs after successful
idempotent publication retries, even if no new metadata commit was needed.

The dispatch uses the fixed `automation/runner-release-next` branch and passes
its exact validated SHA as `expected_head_sha`. Before checkout, the read-only
`Repo consistency` job requires that ref and `github.sha` to match. Consequently
the check belongs to the release head, not to a main-branch run or a newer branch
tip. It receives no secrets, write permissions, or persisted checkout credentials.
The existing trusted `Runner release state` workflow independently validates the
metadata and current main after check completion. No PR is approved, made ready,
merged, or tagged by the dispatch.

The workflow must first exist on the default branch. After deployment, verify on
an actual bot-created release PR that both required checks appear on its exact
head SHA. An unrelated main advancement can make the release branch stale; update
it to current main and retry. If it is already ready for review, the bot still
refuses to mutate it: return it to draft or update it manually first.

## Metadata and tag namespace

A new release after the first one must change a canonical manifest or code/docs
tree hash relative to its verified `previous-tag`. Increasing only the version,
changing unrelated files, or changing lock serialization is not a release delta.
This check applies to candidate metadata, pending releases, and signed releases.
The initial release with `previous-tag none` remains supported.

Every fetched `runner-v*` tag must match the strict `runner-vMAJOR.MINOR.PATCH`
format. Invalid names are errors, not ignored tags. No trusted baseline or success
report is produced while the namespace contains a malformed tag. Tags outside
that namespace are unaffected. Resolving an invalid protected tag requires an
explicit owner decision; these workflows do not delete or rewrite tags.

## Signing requests for batched pushes

The signing parent is the unique first-parent commit on main that introduced the
exact `runner.release` payload. It is not necessarily the push tip: later
unrelated commits in the same push are allowed. The signing request and tag
verifier use the same resolver. Both the frozen snapshot and current shared
snapshot are validated. Reintroducing identical metadata more than once is
ambiguous and fails closed. The issue's parent, compare URL, and associated PR
lookup use the resolved frozen SHA.

## Local verification

```sh
GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GITHUB_ACTIONS=true \
  python3 -m unittest discover -s tests -p 'test_runner_*.py' -v
./scripts/check-repo
RUNNER_SYNC_EXPECTED_ROLE=source RUNNER_SYNC_WRITE=0 ./scripts/sync-runner check
./scripts/audit-public-safety
```

Tests use temporary repositories and disposable signing keys. Dispatch tests mock
GitHub and execute the real SHA guard locally; they do not dispatch live runs.
No local installation or activation is needed. Rollback is a reviewed revert of
the workflow/helper changes; never bypass failed release validation or signature
requirements to unblock a release.
