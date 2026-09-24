# Runner synchronization contract

This repository publishes a neutral, versioned runner contract. It does not
know which repositories consume that contract and never dispatches to them.
Consumers poll signed releases, apply their own selection policy, and decide
whether to accept a proposed update.

## Public export boundary

The maximum public export is the union of two sorted allow-lists:

- `scripts/runner-canonical-files.txt` for executable and supporting code;
- `scripts/runner-canonical-docs.txt` for public documentation.

There is no wildcard export of `scripts/**` or `docs/**`. A consumer may select
any subset, but it must reject a selected path that is absent from the
corresponding public allow-list.

`runner.lock` and `runner.docs.lock` contain SHA-256 records for the exact code
and documentation sets. Every manifest entry must be a normalized,
repository-relative regular file. Absolute paths, `..`, duplicates, missing
files, symlinks, and overlapping code/documentation entries are rejected.

The locks prove internal source consistency only. They do not establish an
accepted release and are not a substitute for signature verification.

## Repository roles

`runner.conf` declares `RUNNER_SYNC_ROLE=source` here. CI also sets
`RUNNER_SYNC_EXPECTED_ROLE=source`; changing only the file therefore fails the
required check. CODEOWNERS and branch protection must cover both the role and
the workflow. The role remains policy metadata, not a cryptographic trust root.
Neither CODEOWNERS nor a default read-only token prevents an authorized writer
from submitting a different workflow definition. Restrict that authority before
enabling automation; see the release process deployment prerequisites.

The supported local commands are:

```text
RUNNER_SYNC_EXPECTED_ROLE=source RUNNER_SYNC_WRITE=0 ./scripts/sync-runner check
RUNNER_SYNC_EXPECTED_ROLE=source RUNNER_SYNC_WRITE=1 ./scripts/sync-runner lock
```

`check` is read-only. `lock` is source-only and requires an explicit write
guard. There is intentionally no network-enabled `pull` command: release
selection, signature verification, candidate testing, and write proposals
belong to each consumer's trusted automation.

## Consumer requirements

A conforming consumer should:

1. poll immutable `runner-vMAJOR.MINOR.PATCH` tags;
2. fetch the exact tag and expected commit from a fixed, administrator-managed
   origin, never from workflow input;
3. independently verify both the release-attestation commit and annotated tag;
4. verify release metadata, ancestry, unchanged attestation tree, public
   manifests, and public locks before copying bytes;
5. apply an explicit local code/docs selection;
6. execute candidate code only in a secretless, tokenless, network-isolated
   sandbox;
7. let a separate trusted job propose a draft pull request;
8. treat only reviewed locks on the consumer's default branch as accepted.

Verification and publication must bind the exact accepted base commit and
accepted provenance-lock digest. If main changes between those jobs, discard
the stale proposal and verify again. Recheck the baseline against current main
at PR time as well, with strict up-to-date branch protection.

Pin both the accepted tag object ID and release commit: a replaced tag pointing
to the same commit is still a replacement. Require the attestation's parent to
be the exact commit that introduced frozen metadata on main, not merely an
ancestor with the same shared files. Verify historical release signatures and
ancestry as well as the new release.

Hash the complete transfer envelope (archive, digest, proposed provenance,
verification metadata) across the verify/write job boundary. Before any local
mutation, reject symlinks/non-regular files at every target and ancestor,
including locks and stale paths, and use fresh atomic temporary files.

Canonical manifests declare the maximum export; a consumer validates only its
selected files for local existence. Unselected exports need not be present.
Keep monitor notices separate from acceptance: preserve a candidate's approval,
failure, or draft-PR state and compare tag/commit identity, not only its name.

Release-signing public keys may be published here for convenience, but a
consumer must use trust roots configured by its own administrator. It must not
silently trust verification material fetched from the same origin as the
candidate.
