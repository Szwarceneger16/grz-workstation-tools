# Runner release process

Runner releases use an aggregate release train. Normal pull requests update
shared code or documentation and their locks; they never create a release tag.
After those pull requests merge, automation maintains one draft release pull
request on `automation/runner-release-next`.

## State model

| State | Meaning |
| --- | --- |
| `NO_CHANGES` | No shared delta exists after the latest release. |
| `DRAFT_OPEN` | One aggregate draft release PR collects shared changes. |
| `READY_FOR_REVIEW` | The owner manually marked the release PR ready. |
| `AWAITING_SIGNATURE` | Frozen metadata on main has no independently verified matching tag. |
| `TAG_VERIFIED` | Both signatures and the frozen snapshot were verified. |
| `RELEASE_FAILED` | A pushed tag failed signature or structural verification. |

Automation cannot mark a release PR ready, approve it, merge it, create an
attestation commit, or create/change a release tag.

Issues are notifications only. Their title, author, open/closed state, deletion,
or recreation never controls this state machine. Signing notifications are
adopted/closed only when owned by the Actions bot and carrying the protocol
marker. Each gate verifies actual Git objects; an invalid highest tag fails
closed instead of becoming the comparison baseline.

## Aggregate draft pull request

`.github/workflows/runner-release-draft.yml` runs after pushes to `main`. It
validates the public manifests and locks, compares the union of the latest
release manifests and current manifests, and detects additions, changes,
deletions, renames, and file-type changes.

If a shared delta exists, the workflow creates or updates one draft PR. Its
only generated tracked change is `runner.release`:

```text
version X.Y.Z
previous-tag runner-vA.B.C
code-manifest-sha256 HASH
docs-manifest-sha256 HASH
code-tree-sha256 HASH
docs-tree-sha256 HASH
```

For the first release, `previous-tag` is `none` and the default version is
`0.1.0`. Later releases default to the next patch. The owner may edit the draft
to a higher minor or major version; automation preserves a valid unused manual
version. Unexpected branch changes outside `runner.release` stop the update.
An invalid manual version is an error, never silently reset to a patch.
No new shared snapshot means no branch merge or empty metadata commit, even
when unrelated commits have advanced main. Git identity is set before merges.

Merging the release PR freezes the shared snapshot but does not create a tag.
The signing-request workflow opens one owner issue, and the required `Runner
release state` check blocks new shared changes until the expected tag is
verified. Unrelated pull requests remain eligible to merge.

## Manual signing ceremony

The owner performs this step outside GitHub Actions. Signing private keys must
not be stored in repository files, Actions secrets, artifacts, or caches.

Starting from the exact merge/squash commit that introduced `runner.release`:

1. verify `runner.release` and the merge commit SHA;
2. create an empty direct child with subject
   `chore(runner): attest release vX.Y.Z` using the normal commit-signing key;
3. run `git verify-commit` on the new commit;
4. verify that the attestation tree equals its parent tree;
5. create an annotated `runner-vX.Y.Z` tag using the dedicated runner release
   key;
6. run `git verify-tag` locally;
7. push only after a separate explicit approval.

The tag message is machine-readable data followed by the SSH signature:

```text
runner-release-v1
version X.Y.Z
release-parent MERGE_SHA
code-tree-sha256 HASH
docs-tree-sha256 HASH
```

The attestation commit does not need to be pushed to `main`; the signed tag may
be its only ref. This keeps the signed tree identical to the reviewed snapshot
without bypassing default-branch protection.

A reviewable command sequence is shown below. Replace placeholders only after
checking them against the signing-request issue. The final push is intentionally
separate and must not be run without explicit approval.

```bash
git fetch origin main --tags
git switch --detach FROZEN_RELEASE_PARENT_SHA
git commit --allow-empty -S -m "chore(runner): attest release vX.Y.Z"
git verify-commit HEAD
test "$(git rev-parse HEAD^{tree})" = "$(git rev-parse HEAD^1^{tree})"

# Prepare TAG_MESSAGE_FILE with the exact runner-release-v1 fields documented
# above, then use the dedicated runner release-signing key:
git -c gpg.format=ssh -c user.signingkey=RELEASE_SIGNING_KEY \
  tag -s runner-vX.Y.Z HEAD -F TAG_MESSAGE_FILE
git verify-tag runner-vX.Y.Z

# Separate approval boundary:
git push origin refs/tags/runner-vX.Y.Z
```

`git verify-commit` must show the configured personal signing key, while
`git verify-tag` must show the distinct dedicated runner release key.

## Tag verification

`.github/workflows/runner-release-verify.yml` rejects:

- non-SemVer and lightweight tags;
- a tag signed by an unexpected release key;
- a target commit signed by an unexpected personal key;
- a tag that does not point directly to the attestation commit;
- an attestation with zero or multiple parents;
- any tree difference between the attestation and its parent;
- a parent not reachable from `main`;
- a parent other than the exact first-parent main commit introducing the frozen
  metadata (a later unrelated commit with identical metadata is not accepted);
- metadata, tag-message, version, or aggregate-hash mismatches;
- non-monotonic versions or broken release ancestry.

The workflow uses administrator-managed public verification material. Its
result is useful to maintainers, but every consumer must repeat verification
against independently managed trust roots.

The verifier is woken by completion of `check-repo` and by a 15-minute fallback
schedule/manual dispatch. It runs the default-branch definition through
`workflow_run`, never a definition supplied by a tag. The triggering run is
only a signal: no artifact, command, success claim, or code from it is trusted.
Verification may therefore happen after tag CI completes, not immediately at
push. The release-state dispatcher uses the same trusted-main design and
rechecks all open PRs after main changes, verification, CI, and periodic wakeups.
It never checks out PR contents, and publishes `Runner release state` for the
exact head SHA only after checking it against current main.

## Required repository settings

After the implementation is reviewed, configure branch/ruleset protection so
that:

- CODEOWNER approval is required for shared manifests, locks, release metadata,
  helpers, and workflows;
- new commits dismiss stale approvals;
- branches must be up to date before merging; no bypass for stale checks;
- `Repo consistency`, `Runner release state`, and release-specific checks are
  required as appropriate;
- bots cannot approve, merge, or enable auto-merge for release PRs;
- only the owner can create `runner-v*` tags; modification/deletion is blocked;
- the public commit/tag allowed-signers values and expected fingerprints are
  administrator-managed Actions variables.

These settings are part of the security boundary and are not created by the
repository workflows themselves.

Keep the administrator-managed `RUNNER_AUTOMATION_ENABLED` variable unset
until these protections have been configured and tested. This is a deployment
interlock, not protection from a writer who can replace workflow YAML.

CODEOWNERS protects merge review, not execution of candidate YAML. Default
workflow token permissions also are not a ceiling on permissions requested by
a same-repository workflow. Untrusted contributors must not have direct write
access to workflows or tags. Use restricted write membership (contributions
through forks with read-only tokens) or an independently enforced workflow/path
policy where the repository's plan supports it. Do not enable this automation
with arbitrary untrusted same-repository writers. Never grant fork PRs write
tokens or repository secrets. An administrator able to replace these controls
is outside the threat model.

Bootstrap order: first review/merge these trusted dispatchers with automation
disabled, configure protection, then enable automation and require the emitted
check names. The initial implementation PR cannot depend on a dispatcher that
does not exist on main yet; it is an explicit owner-reviewed bootstrap, not an
automatic successful security check.

The owner can approve bot-authored release PRs, but cannot approve their own
ordinary PR. Owner-authored shared changes need another authorized CODEOWNER
or a separately agreed governance model; do not silently bypass review.
Bot-created PR checks can require a manual workflow-run approval in GitHub.
This is separate from marking the PR ready or approving/merging it.

References: [workflow event trust](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[ruleset capabilities](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).
