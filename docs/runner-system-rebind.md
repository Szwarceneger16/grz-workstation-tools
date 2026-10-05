# Proof-based system-file migration

System rebind updates copied regular files whose installed bytes and ownership
can be proven against an explicitly selected legacy package. It is distinct
from user symlink rebind and ordinary system installation. The optional
`scripts/rebind-system-package` owns this operation; `run.sh` only routes it.

## Scope and commands

Select one package and at least one existing, normalized absolute old checkout:

```sh
./run.sh verify --rebind-system --from-repo /srv/old-toolkit example-package
./run.sh install --rebind-system --from-repo /srv/old-toolkit --dry-run example-package
```

Repeat `--from-repo` to admit additional old sources. Duplicate, nested, missing,
symlinked and current-source roots are refused. No old root is auto-discovered.
`--legacy-root` remains a routing alias for `--from-repo`.

Every root argument uses a normalized absolute Linux path with one leading
slash. Double-leading-slash aliases (including `//`) and control characters are
refused before root comparison, so they cannot bypass source/target overlap or
live-root privilege checks.
Root ancestry device/inode identities also bind the approved plan. Overlap in
these directory identities is refused between offline targets and source roots,
or between source roots. Installed leaves sharing an inode with any declared
source are conflicts. These checks detect aliases present in root ancestry or
declared-file identity evidence that lexical comparison alone cannot detect;
the helper does not enumerate mount topology or perform mount operations.

The current source is `packages/PACKAGE/system-install/`, with metadata from
`packages/PACKAGE/system-install.manifest`. The old checkout must contain the
same package layout and its own manifest. Each installed file normally lives
under `/` at its exact declared relative path. Source permissions are recorded
for race detection; installed mode and owner/group come from the manifest.

The helper validates the selected current package's system-unit contract before
inspection, preview or writes, including direct privileged invocation. Supported
unit files at `system-install/etc/systemd/system/` must be declared in
`system-units.manifest`, and every declared unit must have a source file or an
applicable service/trigger template. Timer/path/socket targets must be declared,
including implicit services and every selected template instance. An `Accept=yes`
socket requires its explicitly declared service template; a bare service-template
declaration without such a socket is refused. Duplicate/invalid declarations and
ambiguous repeated or continued target directives are refused too.

This is data validation inside the reviewed Python helper: it never executes a
checker or hook from an input checkout. It implements the system-unit checks of
`check-repo`, with regression comparisons against that authoritative validator;
it does not claim to run all user-layer/hook checks. Unit files in other systemd
system load directories, nested unit layouts, drop-ins and unsupported suffixes
are outside this rebind contract and refused. Invalid unselected packages do not
block the selected package. Legacy unit declarations do not grant current
activation authority; legacy file bytes/metadata remain proof input only.

The current unit manifest's absence or exact file identity, bytes and ancestry
are part of the approved snapshot. Unit payloads are already bound through the
installation manifest. Every revalidation repeats the unit gate, so changed
declarations stop forward work and enter the existing bounded rollback if any
file has already been published. Validation never reloads or starts units.

Inspection reports:

| Classification | Meaning |
| --- | --- |
| `CURRENT` | Installed content, mode and owner/group match the current source and manifest. |
| `REBINDABLE` | All those values match at least one explicitly admitted old source and manifest. |
| `MISSING` | No installed file exists; migration does not create it. Use ordinary installation separately. |
| `FOREIGN` | Content/metadata drift, an unsafe type/path, or an unverifiable lookup. |
| `RESIDUE` | An old-only declared path; reported without reading its installed contents or modifying it. |

Inspection returns 0 when all current destinations are current, 3 for a
conflict-free plan containing legacy/missing files, and 1 on conflicts/errors.
Residue is explicitly unverified and does not change the exact-current-path
inspection result. Inspection never repairs or starts services.

Install requires all destinations to be current or proven rebindable. A missing
or foreign file blocks the entire package before writes, including dry-run
acceptance. Dry run prints desired digests and metadata without creating a
journal. Actual writes require interactive `SYSTEM REBIND` or explicit `--yes`.
The exact plan is recomputed under the target-directory advisory lock after
approval, before every replacement, and before final acceptance.

The helper never escalates privilege. A normal-user preview/inspection can only
read files already accessible to that user; unreadable paths fail closed.
Writing the live `/` root requires an explicitly privileged invocation of the
reviewed helper. Do not elevate `run.sh` merely to bypass that guard: its normal
paths include repository configuration and unrelated installation behavior.
After separate owner authorization, a privileged operator can invoke the
trusted helper directly with Python isolated mode and explicit arguments:

```sh
# Run only in an independently authorized privileged session.
python3 -I /srv/reviewed-toolkit/scripts/rebind-system-package \
  --repo /srv/reviewed-toolkit --package example-package \
  --from-repo /srv/old-toolkit --yes
```

The operator must trust the reviewed helper being executed. File digest
validation is not a sandbox for running an untrusted helper as root.

## Publication, backups and recovery

Each package gets a fresh owner-only directory named
`/tmp/runner-system-rebind-*/`. Its mode is 0700; `progress.json` and payload
backups are 0600 and owned by the executing account (root for live writes).
`--journal-dir PATH` selects another existing, normalized, non-symlink directory.
The whole journal ancestry must be owned by root or the executing account. For
privileged execution, this means root-owned ancestry only. Group/world-writable
components require the sticky bit as well as a trusted owner; ordinary shared
directories and foreign-owned sticky directories are refused. A root-owned
sticky `/tmp` remains supported. Do not select a directory inside another user's
home for privileged recovery, even if the final directory itself is root-owned.

Creation, backup writes and progress updates use anchored directory descriptors.
The helper retains the journal and parent descriptors, checks their identities
and the complete named ancestry before writes, and never reopens backup files
through an unverified replacement directory. A moved/replaced journal, changed
ancestry or changed permissions stops forward work. Bounded target rollback is
still attempted if the journal is no longer reachable under its reported path;
concurrent changes by the trusted operator/root can require locating the retained
original journal manually. The helper does not provide containment against a
hostile root process or the executing account itself.
JSON records the approved manifests/policies, hashes, file and parent identities,
staging names, progress, and paths needing manual recovery. Payload contents are
never printed. Backups deliberately use 0600; original installation metadata is
recorded separately rather than granting execution or set-id rights to backups.

Before any installed-path mutation, the helper synchronizes the new journal
directory and its parent. Backup files and their directory entries are flushed
before quarantine. Each stage, quarantine, publication, restore and cleanup
transition is synchronized in the destination directory before a progress or
terminal outcome can claim it completed. A synchronization failure stops forward
work; bounded rollback still runs if recording `rolling-back` itself fails.
`rolled-back` additionally requires every approved destination to match its
original identity, content and metadata. Lost quarantines and changes to untouched
files produce `recovery-required`, while preserving concurrent writers.

These guarantees depend on storage honoring `fsync`. Use `--journal-dir` on a
persistent filesystem when recovery evidence must survive reboot or power loss:
the default `/tmp` can be memory-backed or cleaned at boot. Synchronizing it
cannot make volatile storage persistent. Keep backups on reliable storage and
retain incomplete stages if a storage failure prevents a durable outcome record.

For each proven old destination, the helper creates a new sibling stage,
revalidates the source and parent chain, and moves the installed file to a unique
quarantine name with Linux `renameat2(RENAME_NOREPLACE)`. It checks the displaced
identity and content before publishing the new stage, also with no replacement
of an occupied path. There is no unsafe rename/copy fallback. **The final path
can be briefly absent between quarantine and publication.** This is a bounded
file migration, not an atomic package update; schedule it appropriately for
programs that read those files. It does not compose a runtime transaction.

On failure, further files are stopped and rollback attempts to restore only
transaction-owned files. A concurrent replacement is preserved. If restoration
would overwrite another writer, both the old quarantined file and available
stages/backups remain, with `recovery-required` evidence. A rolled-back file keeps
its original inode, bytes and metadata apart from rename-induced ctime changes.
Successful transactions retain their payload backups and remove only validated
old staging entries after the committed outcome is durable.

SIGINT/SIGTERM use the same rollback path. Short publication and progress-record
sections mask those signals to avoid losing the identity of an owned change.
SIGKILL, storage errors, power loss and hostile concurrent directory moves can
require manual reconciliation from the journal; no automatic replay command is
provided. Retain journals until independently checking the final installation.
There is no promise of atomic user-plus-system rollback.

## Safety boundaries and validation

`system-config.manifest` is used only as plain destination-exclusion metadata.
The helper never opens real configuration destinations named there, never copies
their secret payloads, and never runs config creation, hooks, package programs,
sudo, systemctl or shell reloads. Exclusions from current and admitted legacy
package declarations both apply before source/destination payload inspection.

Current protected-path and exact set-id policies apply to both manifests.
Policy entries preserve raw LF-separated text, with only empty lines and
column-zero `#` comments skipped, matching the authoritative Zsh readers.
Surrounding whitespace, CRLF entries and alternative Unicode line separators
cannot become exact set-id approvals; invalid entries fail closed. System
install/config declarations similarly accept only LF rows and ASCII space/tab
field separators, with no indented-comment or Unicode-separator normalization.
Protected patterns accept literal ASCII letters/digits, `/`, `.`, `_`, `-`,
single `*`, `?`, and positive bracket sets of ASCII letters/digits with ascending
ranges inside `a-z`, `A-Z` or `0-9` (for example `[a-cx-z]`). Everything outside
this explicit subset fails closed, including POSIX/collating/equivalence classes,
negated or malformed brackets, recursive `**`, numeric ranges, escapes and
extended Zsh patterns. Supported patterns are checked against Zsh in tests;
unsupported patterns stop the entire operation before payload inspection. Protected
directory ancestors also exclude descendants. Unsupported destination hard
links, extended attributes/ACLs/capabilities and files larger than 16 MiB are
refused. These require a separate migration design. Symlinks, FIFOs, directories,
ambiguous metadata and source/target lookup failures never become migration proof.
Every existing destination parent inside the chosen root must be owned by root
for live migration, or by the executing account for an offline root, with no
group/world write permission. System paths through conventional directory
symlinks are also refused; use separately reviewed normalized manifest paths.

For disposable tests or offline images, `--system-root PATH` substitutes an
existing non-symlink root. It is independent of `STOW_TARGET` and the repository
environment prefix and must be disjoint from all source checkouts. It grants
no authority to invoke production writes. The
generic test suite uses fake roots and the current test account's UID/GID; it
never invokes a privileged command or modifies live workstation paths.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p 'test_runner_system_rebind.py' -v
zsh -n run.sh
./scripts/check-repo
RUNNER_SYNC_EXPECTED_ROLE=source RUNNER_SYNC_WRITE=0 ./scripts/sync-runner check
```

Tests exercise proof/classification, metadata transitions, config exclusions,
parent/source/target/policy races, publication conflicts, rollback, signals,
contention, journals, CLI isolation and optional-helper refusal. Additional
durability tests trace synchronization order and inject storage/progress errors,
including journal-parent, publication and rollback failures. These are disposable
filesystem tests, not physical power-loss acceptance. Boundary regressions compare
set-id policy decisions with `check-repo`, reject root aliases, and exercise
untrusted ancestors, descriptor-relative creation and journal replacement/moves.
These ownership tests need the host's real filesystem metadata; a sandbox that
maps root ownership to another UID is not an equivalent test environment. Ordinary
install/verify remain usable when a consumer omits this helper; requesting
`--rebind-system` then fails clearly. Public release, consumer admission, trusted
consumer CI, and separately authorized live acceptance remain later milestones.
