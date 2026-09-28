# Security Policy

## Purpose

`grz-workstation-tools` is a public workstation-tooling repository and the
canonical source of a shared runner used by downstream repositories.

Repository content can affect both user-owned files and privileged host state.
Some packages may install root-owned files, root-only configuration, and
systemd units. The runner can also be exported to other repositories.

The repository is therefore treated as a software supply-chain boundary.

The primary security objective is:

> No unreviewed, unverified, ambiguously identified, or attacker-controlled
> repository content may become a trusted runner release or cross into a
> privileged installation boundary without the required independent checks.

Integrity, provenance, confidentiality, least privilege, and fail-closed
behavior are security requirements.

## Supported and trusted revisions

| Surface | Security status |
| --- | --- |
| Protected `main` | Authoritative repository state |
| Verified `runner-vMAJOR.MINOR.PATCH` release | Trusted only after the complete signed-release contract below passes |
| Pull-request branch | Untrusted candidate |
| Automation branch | Untrusted candidate/data unless independently revalidated |
| Workflow artifact or output | Not a trust root |
| Lightweight or unsigned tag | Not a trusted runner release |
| Mutable branch/tag name by itself | Not proof of provenance |

Canonical SHA-256 locks establish snapshot consistency only. They do not, by
themselves, establish provenance or release authenticity.

## Reporting a vulnerability

Do not disclose suspected vulnerabilities, credentials, private keys, tokens,
machine-specific data, or exploitable details in a public issue.

Use GitHub Private Vulnerability Reporting when it is available for this
repository. If it is not available, open only a minimal public issue requesting
a private disclosure channel and do not include vulnerability details.

A useful report should identify:

- the affected file, package, workflow, or release;
- the attacker-controlled input or prerequisite;
- the violated trust boundary or invariant;
- the expected and actual behavior;
- the resulting impact;
- safe reproduction steps, when available.

Never include real credentials or sensitive host data in a report.

# Security model

## Trust roots

The repository security model relies on:

1. protected `main`;
2. branch, ruleset, and tag protections administered outside repository code;
3. administrator-managed public signature-verification material;
4. the owner's commit-signing private key;
5. a distinct runner release-signing private key;
6. independently configured trust roots in each downstream consumer.

Signing private keys must never be stored in repository files, GitHub Actions
secrets, workflow artifacts, workflow caches, or generated release metadata.

The commit-signing key and runner release-signing key must be distinct.

An administrator able to replace repository protections, trusted workflow
definitions, signing-verification variables, or other trust roots is outside
the repository-level threat model. Administrative access must therefore be
restricted independently.

## Untrusted inputs

Unless independently validated, treat all of the following as untrusted:

- pull-request contents, descriptions, and comments;
- issue contents;
- workflow inputs;
- branch and tag names;
- mutable Git refs;
- automation branches;
- paths derived from input;
- candidate manifests and lock files;
- workflow artifacts and outputs;
- downloaded archives;
- candidate release metadata;
- files supplied as local secret/config sources;
- downstream repository state.

A workflow success produced by an untrusted revision is not itself proof that
the revision is trustworthy.

# Core repository invariants

## Package structure

User-layer package content is rooted under:

`packages/<package>/install/`

Privileged package content is rooted under:

`packages/<package>/system-install/`

The privileged layer is declarative data, not arbitrary package-specific root
code. Privileged behavior is described through the supported manifests:

- `system-install.manifest`;
- `system-config.manifest`;
- `system-units.manifest`.

User systemd units are described through:

- `user-units.manifest`.

There are no package-specific privileged system hooks.

If a privileged operation cannot be represented by the supported declarative
contract, it must not be added as an arbitrary `sudo` hook.

## Repository consistency before mutation

`scripts/check-repo` is the static policy gate for package declarations.

Before a privileged system install or activation mutates the live system, the
repository/manifest consistency checks must pass.

Repository inconsistency must fail before privileged mutation begins.

The checks are expected to reject, among other things:

- undeclared or missing system files;
- malformed manifest rows;
- unsafe or non-canonical manifest paths;
- protected system paths;
- undeclared systemd units;
- real secret configs committed instead of examples;
- unsupported package hooks;
- privileged use from user-layer hooks;
- unsafe special permission bits unless explicitly allowed.

## System paths

System manifest paths must be repository-relative and canonical.

Validation must reject:

- absolute paths;
- parent-directory traversal;
- redundant or ambiguous path components;
- duplicate entries;
- unsupported ownership or mode values;
- undeclared files;
- missing files;
- symbolic-link package sources.

Paths matching `manifests/protected-system-paths.txt` must never be managed by
a package manifest.

The protected-path policy exists to prevent packages from taking ownership of
sensitive certificate, credential, or externally administered system state.

## Privileged destination safety

A system installation must not overwrite a symbolic link at the exact target
destination.

Privileged copies must install to the validated destination and must not use a
destination symlink as a substitute for that destination.

Uninstall must fail rather than remove a target that is unexpectedly symlinked,
non-regular, or has drifted where exact source/destination identity is required.

Unexpected destination state is a reason to stop, not to broaden the operation.

## Set-id and special permission bits

Setuid, setgid, and sticky permission bits on system-installed files are denied
by default.

A system-installed path using these bits requires an explicit exact-path entry
in:

`manifests/allow-setid-system-paths.txt`

Such an entry is a deliberate security exception and requires review.

Secret/configuration destinations declared in `system-config.manifest` must
never use setuid, setgid, or sticky bits.

## Root-only configuration and secrets

Real secret configuration must not be committed to this repository.

The repository may contain `*.example` configuration files. Each example must
map to an explicitly declared real destination.

A `system-config.manifest` destination must:

- be root-owned;
- have no group/world permission bits;
- have no set-id/sticky bits.

The installer may copy a user-selected config source to the declared
destination, but it must not print secret contents.

The source must be a regular non-symlink file.

Existing secret destinations must not be silently overwritten.

When `sudoedit` is used, the resulting destination must still be validated as
a regular non-symlink file before final ownership and permissions are accepted.

## Package hooks

The only package hook names permitted by the repository contract are:

- `install.hook.sh`;
- `verify.hook.sh`.

They are user-layer escape hatches only.

Hooks must:

- be regular files, not symlinks;
- reside in the package root;
- be executable;
- run as the normal user;
- not invoke `sudo`;
- be idempotent;
- return non-zero on failure.

Unknown `*.hook.sh` files are rejected.

# Confidentiality and public-repository scanning

`scripts/audit-public-safety` is the repository-local confidentiality gate.

It must report only the affected path and finding category, never discovered
secret values.

The scanner is expected to detect high-signal credential material and
machine-specific private data in tracked content, with additional checks for
secret-like content in installable package trees.

Security exceptions, if supported by the scanner, must be narrow, explicit,
reviewable, and content-bound. A changed blob must not remain authorized merely
because its path was previously allow-listed.

The confidentiality scanner is repository-local policy. It is not itself a
cryptographic trust root for runner releases.

# Runner synchronization and release provenance

## Legacy synchronization is not release provenance

A direct branch/ref synchronization mechanism such as the pre-release-train
`scripts/sync-runner pull` command is a convenience mechanism, not sufficient
proof of release authenticity.

Branch names are mutable, and a content lock generated after copying bytes does
not prove who authorized those bytes.

A downstream consumer must not treat successful branch pulling plus SHA-256
relocking as a trusted release decision.

The signed release-train contract below is the required provenance model once
that automation is enabled.

## Release-train activation gate

The signed runner release train is considered active only when all of the
following are true:

- the trusted release workflow/helper definitions are present on protected
  `main`;
- repository branch/ruleset and tag protections are configured;
- CODEOWNERS/review requirements cover the security-sensitive surface;
- administrator-managed public verification material is configured;
- required checks are configured and tested;
- `RUNNER_AUTOMATION_ENABLED` is explicitly enabled.

Until then, no automation branch or `runner-v*` tag should be treated as a
trusted release merely because the repository contains part of the
implementation.

When present, the detailed implementation is documented by:

- `docs/runner-release-process.md`;
- `docs/runner-release-ci.md`;
- `docs/runner-sync.md`.

Repository documentation explains the implementation. This policy defines the
security properties that implementation must preserve.

# GitHub Actions security invariants

## Trusted workflow definitions

Security-sensitive runner dispatchers and release verifiers must execute their
workflow/helper definitions from protected `main`.

A tag, pull request, release candidate, or automation branch must not be able to
replace the workflow definition used to decide whether that same candidate is
trusted.

For the release security boundary, `workflow_run` events are signals only.
The trusted verifier must independently re-fetch and validate authoritative Git
and GitHub state instead of trusting artifacts, commands, conclusions, or
success claims from the triggering run.

## Exact revision binding

A security decision about a pull request or release must be bound to the exact
commit SHA.

Mutable branch identity alone is insufficient.

Before publication, dispatch, or success reporting, automation must revalidate
relevant mutable state, including as applicable:

- current `main` SHA;
- pull-request head SHA;
- base branch;
- head repository;
- automation branch identity;
- open/draft state;
- frozen release metadata.

If relevant state changes during validation, the operation must stop and be
retried against the new state.

## Least privilege

GitHub Actions permissions must be minimized per workflow and per job.

Read-only validation jobs must not receive write permissions merely because a
later job requires them.

Checkout credentials must not persist where unnecessary.

Candidate code must not receive signing keys, repository secrets, or privileged
write tokens.

Fork pull requests must never receive repository secrets or privileged tokens.

Third-party Actions used inside the enabled signed-release security boundary
should be pinned to immutable commit SHAs.

## Candidate code and write-capable jobs

A job holding write-capable credentials must not execute candidate-controlled
code merely to determine whether that candidate should be published.

The trusted release-check dispatcher must:

- run from protected `main`;
- validate a fresh `main`;
- identify exactly one expected same-repository aggregate release PR;
- verify the exact candidate head SHA;
- require the release branch to differ from trusted `main` only by the
  expected release metadata file;
- treat the candidate branch as data, not trusted executable code;
- recheck mutable state immediately before dispatch.

The dispatched read-only check must independently bind execution to the exact
validated head SHA.

Unexpected changes, stale refs, ambiguous API responses, or mismatched SHAs
must fail closed.

# Pull requests and governance

The security-sensitive surface includes at least:

- `SECURITY.md`;
- `.github/workflows/**`;
- `.github/CODEOWNERS`;
- `runner.conf`;
- `runner.release`, when present;
- runner code/documentation locks;
- `run.sh`;
- `bootstrap/**`;
- `githooks/**`;
- `scripts/**`;
- canonical runner manifests;
- release helpers;
- release documentation;
- public-safety policy;
- release/runner regression tests.

When CODEOWNERS is deployed, it must cover `SECURITY.md` and the other
security-sensitive release surfaces.

Repository protection should require review for these changes, invalidate stale
approvals after new commits, and require a fresh base where the security model
depends on current `main`.

Automation must not mark a runner release PR ready, approve it, merge it, or
create owner signatures.

Human review is a separate security boundary from automated validation.

# Canonical runner export boundary

The canonical runner uses an explicit maximum export.

Code/supporting files are declared by the canonical code manifest.

Public documentation is declared independently by the canonical documentation
manifest when that split is deployed.

Wildcard export of arbitrary repository content is not permitted.

A downstream consumer may select a subset of the public export, but it must not
import a path outside the corresponding canonical allow-list.

## Canonical path requirements

Canonical entries must be normalized repository-relative regular-file paths.

Validation must reject:

- absolute paths;
- `..` traversal;
- empty or ambiguous path components;
- `.git` paths;
- duplicate entries;
- missing files;
- symbolic links;
- non-regular Git tree entries;
- unsupported file modes;
- overlapping code/documentation exports.

## Runner locks

Runner locks bind the exact exported snapshot.

In the signed release-train format, lock records must bind:

- Git executable mode (`100644` or `100755`);
- SHA-256 digest;
- exact repository-relative path.

A content-preserving executable-bit change is therefore a security-relevant
runner change and requires a reviewed lock update.

Locks must match their manifests exactly.

Malformed, incomplete, mismatched, or ambiguously ordered locks must be rejected
rather than silently repaired during read-only validation.

Locks prove snapshot consistency only. They are not substitutes for signature
verification or provenance.

# Runner release security model

Runner releases use an aggregate release train.

Ordinary shared-code changes do not directly create release tags.

The intended state progression is:

`NO_CHANGES -> DRAFT_OPEN -> READY_FOR_REVIEW -> AWAITING_SIGNATURE -> TAG_VERIFIED`

A verification failure results in `RELEASE_FAILED`.

Automation must not convert a failed release into a trusted release by silently
rewriting metadata, replacing a tag, or changing the comparison baseline.

## 1. Shared changes reach protected main

Normal pull requests modify shared runner code, documentation, manifests,
locks, tests, or supporting logic.

Those changes are reviewed and merged through the protected-branch process.

No runner release tag is created as part of an ordinary merge.

## 2. Aggregate release draft

After relevant changes reach `main`, trusted automation may maintain one draft
release PR on:

`automation/runner-release-next`

Its generated tracked release change is restricted to:

`runner.release`

Frozen metadata binds:

```text
version X.Y.Z
previous-tag runner-vA.B.C
code-manifest-sha256 HASH
docs-manifest-sha256 HASH
code-tree-sha256 HASH
docs-tree-sha256 HASH
```

For the initial release, `previous-tag` may be `none`.

Unexpected tracked changes on the aggregate release branch outside
`runner.release` are a security failure.

A release requires a real canonical code or documentation delta. A version-only
change, unrelated repository change, or lock-serialization-only change is not a
valid release delta.

Ready-for-review release PRs must not be automatically mutated.

## 3. Trusted dispatch of release checks

Publication of an aggregate draft PR does not authorize it.

A separate trusted-main dispatcher validates the exact release PR and dispatches
read-only checks for its exact SHA.

The dispatcher must not execute code from the candidate branch.

The candidate receives no signing key and no authority to approve or publish
itself.

## 4. Human freeze boundary

A human owner or authorized reviewer decides when the aggregate release PR is
ready and whether it may merge.

Automation must not:

- mark it ready;
- approve it;
- merge it;
- create a release signature;
- create a release tag.

Merging the aggregate release PR freezes the snapshot on `main`; it does not
publish a runner release.

While the frozen release awaits the expected verified tag, the frozen release
metadata must remain immutable and shared runner changes must remain gated.

## 5. Signing request

After frozen metadata reaches `main`, trusted automation identifies the unique
first-parent commit that introduced the exact `runner.release` payload.

It must not assume that the final commit in a batched push is the frozen parent.

Ambiguous identification of the frozen parent must fail closed.

A signing-request GitHub issue is a notification only. Issue title, author,
open/closed state, deletion, recreation, or comments do not establish release
state or trust.

Git objects are authoritative.

## 6. Manual signing ceremony

Signing is performed outside GitHub Actions.

Starting from the exact frozen release parent, the owner creates an empty,
signed direct-child commit with subject:

`chore(runner): attest release vX.Y.Z`

The attestation commit must have exactly one parent and an identical Git tree to
that parent.

The attestation commit is signed with the configured personal commit-signing
key.

The release is then represented by a separately signed annotated tag:

`runner-vX.Y.Z`

using the distinct dedicated runner release-signing key.

The unsigned portion of the tag message binds:

```text
runner-release-v1
version X.Y.Z
release-parent FROZEN_PARENT_SHA
code-tree-sha256 HASH
docs-tree-sha256 HASH
```

The final tag push is a separate explicit approval boundary.

GitHub Actions must never possess either signing private key.

# Release verification

The release verifier must run trusted code from protected `main` and fail if
any required property cannot be proven.

At minimum, it must reject a release when:

- a `runner-v*` namespace entry is malformed;
- the release tag is lightweight instead of annotated;
- the tag signature uses an unexpected release key;
- the attestation commit signature uses an unexpected personal key;
- commit and release signatures use the same expected key;
- the tag does not point directly to the attestation commit;
- the attestation has zero or multiple parents;
- the attestation tree differs from its parent's tree;
- the release parent is not reachable from protected `main`;
- the release parent is not the exact unique first-parent commit that introduced
  the frozen metadata;
- tag version and frozen metadata disagree;
- `previous-tag` or release ancestry is invalid;
- versions do not increase monotonically;
- no actual canonical code/documentation delta exists;
- canonical manifests, locks, modes, or hashes disagree;
- tag-message hashes differ from the frozen release snapshot;
- administrator-managed verification material is missing or invalid.

Malformed tags in the protected `runner-v*` namespace must not be silently
ignored.

An invalid highest tag must never become a trusted comparison baseline.

# Release-state gate

The trusted release-state dispatcher must reevaluate current release state from
protected `main`.

A triggering workflow completion is only a wake-up signal.

The dispatcher must not execute pull-request contents.

A published release-state check must be bound to the exact PR head SHA.

Immediately before reporting success, trusted automation must recheck current
`main` and the current pull-request head. If either changed, the result is
stale and must not be treated as successful.

# Protected release namespace

The `runner-v*` namespace is security-sensitive.

Repository rules should ensure that:

- only the owner or explicitly authorized release authority can create release
  tags;
- existing release tags cannot normally be modified or deleted;
- automation cannot rewrite a failed tag;
- malformed protected-namespace tags surface as verification failures.

Consumers should pin both the annotated tag object identity and target commit
identity.

Replacing a tag object while retaining the same target commit is still a
release identity change.

# Downstream consumer trust

The canonical source publishes a neutral signed release contract. It does not
decide which consumer repository accepts a release.

A conforming consumer must independently:

1. use a fixed administrator-configured canonical origin;
2. discover immutable `runner-vMAJOR.MINOR.PATCH` releases;
3. verify the annotated tag and release-attestation commit with independently
   managed trust roots;
4. verify release ancestry and frozen metadata;
5. verify canonical manifests, modes, locks, and hashes;
6. apply an explicit local code/documentation selection;
7. reject paths outside the local selection and canonical public allow-list;
8. test executable candidate code without secrets or privileged repository
   credentials;
9. use a separate trusted job to propose local changes;
10. accept the new runner only after normal local review and merge.

A consumer must not automatically trust a public signing key merely because it
was downloaded from the same source as the candidate release.

The source repository does not need consumer credentials and must not require
privileged downstream callbacks.

# Required repository configuration for the signed release train

Release workflow files alone do not establish the security boundary.

Before signed runner release automation is enabled, repository administration
must configure and test at least:

- protection for `main`;
- appropriate CODEOWNER review for security-sensitive files;
- stale-approval dismissal after new commits;
- fresh/up-to-date branch requirements where applicable;
- required repository consistency and release-state checks;
- release-specific checks where applicable;
- restrictions preventing bots from approving or merging release PRs;
- protection of the `runner-v*` namespace;
- restriction of release-tag creation to the authorized release authority;
- protection against ordinary modification/deletion of release tags;
- restricted direct write access to security-sensitive workflow definitions;
- no secrets or privileged write tokens for fork PRs.

Administrator-managed Actions variables provide public verification material
and expected fingerprints. They are verification material, not signing private
keys.

`RUNNER_AUTOMATION_ENABLED` is a deployment interlock. It must remain disabled
until the required repository protection, trust material, and workflow behavior
have been configured and tested.

# Bootstrap requirement

Trusted dispatcher workflows must exist on protected `main` before repository
rules depend on their emitted checks.

The initial deployment of the release train is therefore an explicit bootstrap
operation.

The implementation PR that first introduces those trusted dispatchers cannot
prove its own trustworthiness using a dispatcher that does not yet exist on
trusted `main`.

After bootstrap:

1. merge the trusted implementation through explicit review;
2. configure repository and tag protections;
3. configure public verification material;
4. keep automation disabled while protections are tested;
5. enable release automation;
6. perform a complete real release lifecycle;
7. confirm required checks attach to the exact expected SHAs.

Passing implementation-PR CI is not proof that the full deployed release
lifecycle has been operationally validated.

# Fail-closed policy

Security-critical uncertainty must stop the operation.

Do not silently weaken verification to recover from:

- missing verification keys;
- invalid fingerprints;
- malformed release metadata;
- malformed protected tags;
- lightweight release tags;
- signature failures;
- stale `main`;
- changed pull-request heads;
- ambiguous GitHub API responses;
- unexpected release-branch files;
- unexpected manifest entries;
- unsafe paths;
- symlinks where regular files are required;
- lock mismatches;
- provenance mismatches;
- ancestry failures;
- release-state inconsistencies.

Missing evidence is not evidence of trust.

A failed security check must be fixed or explicitly rolled back through the
normal reviewed development process. It must not be bypassed merely to complete
a release.

# Security-sensitive changes

Changes require dedicated security review when they affect:

- `SECURITY.md`;
- `.github/workflows/**`;
- GitHub token permissions or workflow triggers;
- workflow trust boundaries;
- CODEOWNERS or repository protection assumptions;
- `runner.conf` role or canonical origin metadata;
- canonical export manifests;
- runner locks;
- `runner.release`;
- release signing or verification logic;
- Git ref/tag and release ancestry handling;
- path normalization or symlink handling;
- `scripts/check-repo`;
- `scripts/sync-runner`;
- release helper/dispatcher/state scripts;
- `scripts/system-copy-select`;
- protected-system-path policy;
- set-id allow-list policy;
- secret/config installation;
- confidentiality scanning or its exception policy;
- any operation crossing from repository-controlled data into privileged host
  state.

Security controls must be changed intentionally and reviewed as security
changes, not weakened as incidental implementation details.
