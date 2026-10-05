# Optional user-package rebind (WP-5)

`scripts/rebind-user-package` discovers and transfers selected packages' user-layer
symlinks from approved, still-existing checkouts to this checkout. An explicit
recovery mode also accepts exact dangling links after a checkout was removed.
An explicit `--force-links` mode can replace otherwise unproven symlink leaves.
It is a separate
optional Python helper; `run.sh` only routes arguments. Consumers may omit the
helper from their selection manifest. Ordinary install/verify still work without
it; requesting rebind then fails with an explicit unavailable-feature message.
The canonical manifest is a maximum export, not a mandatory dependency list.

## Scope

Only `packages/<package>/install/` and the corresponding `stow/<package>` mapping
are used. No hooks, package tests, system-copy operation, system configuration
values, systemd command, startup-file edit or network access occurs.
Mixed user/system packages are allowed, but **only their user links migrate**.
Use a stable checkout for normal installations; switching its branch later also
changes what installed links expose. Per-package worktree installations remain
an explicit choice.

## Migration and orphan cleanup

Use rebind from the destination checkout while the approved source package tree
still exists. It verifies package mappings, exact declared paths and source
inventories before transferring user links. By default, dangling links after
source loss remain conflicts. The missing-checkout recovery mode below accepts
a narrower class of dangling links. Removed packages and undeclared leftovers
are not repaired by either mode.

`uninstall --orphaned PACKAGE` is a separate cleanup command for leftovers
anchored in the checkout running it. It uses a bounded target scan and a
user-unit naming heuristic, can deactivate user units, and does not migrate
links, share rebind's lock or provide its package rollback. Do not use it as a
preparatory step for rebind or run it concurrently against the same target.
Ordinary `verify PACKAGE` checks installed files and package verification;
`verify --rebind PACKAGE` performs read-only migration inspection instead.

## Read-only discovery and approval

From the destination checkout:

```sh
./run.sh verify --rebind all-user
./run.sh verify --rebind PACKAGE
./run.sh install --rebind --dry-run PACKAGE
./run.sh install --rebind PACKAGE
./run.sh install --rebind --dry-run all-user
./run.sh install --rebind all-user
```

Discovery reads link metadata only at exact destinations declared by the selected
package's new inventory and old names in its rename manifest. It recognizes the
same package and relative path under either `stow/<package>/` or
`packages/<package>/install/`, collecting **all** matching source checkouts used
by these links. It does not list target directories, recurse through HOME or
follow arbitrary foreign symlink chains. Source package trees are inventoried;
the final preflight also checks exact destinations declared by those old trees.

Detected roots are candidates, not proof of trusted Git provenance. Each needs a
valid package/Stow mapping and safe source files. The preview shows source roots,
destination checkout, individual link states and payload differences. The last
command asks for literal `REBIND` to approve that preview; changed state after
approval blocks the affected package. An aggregate run still attempts the
remaining eligible packages; shared plan changes or explicit interruption stop
the series. No source checkout's scripts or configuration are executed.

Optionally repeat `--from-repo` to restrict the operation to explicitly selected
roots instead of discovery. `--legacy-root` remains a compatibility alias; it
does not mean the source is obsolete. Noninteractive publication requires both
explicit roots and `--yes`, after reviewing their dry-run. Bare `--yes` must not
approve roots inferred from mutable links. For example:

```sh
./run.sh install --rebind --from-repo /path/to/source-checkout --dry-run PACKAGE
./run.sh install --rebind --from-repo /path/to/source-checkout --yes PACKAGE
```

`STOW_TARGET` and the runner's existing prefix-specific target override retain
their meaning. The helper also supports direct invocation:

```sh
python3 -I scripts/rebind-user-package --target /path/to/target \
  --package PACKAGE --dry-run
```

Exit codes: 0 means a valid dry-run or completed/unchanged installation; 3 from
`verify --rebind` means an otherwise valid migration is needed; 1 means refusal
or execution failure (argument parsing errors may return 2).
Publication accepts one named package or the user-only `all-user` selector.
Combined `all`, `all-system` and `--verify`/`--test` hook execution are refused.
Normal install flags do not implicitly select rebind.
The read-only `verify --rebind all-user` enumerates package names under the
repository's `stow/`, including packages excluded from ordinary `install all`,
and performs the same exact-path inspection for each. It continues after package
failures and returns 1 if any failed, otherwise 3 if any need migration, or 0 if
all are current. It does not widen the target search. Explicit root restrictions
apply to every inspected package; roots missing that package fail validation
in normal rebind mode.

## Explicit recovery after losing a checkout

If the entire old checkout has been removed, normal rebind lacks the source
inventory needed to prove ownership or compare old payload bytes and modes.
Use `--recover-dangling` only after reviewing the exact selected missing roots:

```sh
./run.sh verify --rebind --recover-dangling --from-repo /path/to/lost-checkout PACKAGE
./run.sh install --rebind --recover-dangling --from-repo /path/to/lost-checkout --dry-run PACKAGE
./run.sh install --rebind --recover-dangling --from-repo /path/to/lost-checkout --yes PACKAGE
```

Replace `PACKAGE` with `all-user` for a package-by-package batch. The same
exclusions, target lock, complete preflight, approval, final verification,
rollback and explicit outcome reporting apply. `verify` remains read-only and
returns 3 for recoverable links. The generated preview command retains the
recovery flag. Automatic source discovery is disabled in this mode; explicit
`--from-repo` values are mandatory even for inspection or dry-run.

Every selected root must be absent, with no symlinked ancestors. An existing
checkout with a missing package is refused; use normal rebind when its source
is available. The root cannot be the destination checkout or lie inside the
installation target. Repeated `--from-repo` values may select several missing
roots, but valid and missing source roots cannot be mixed in one recovery run.

Recovery accepts only current declared destination leaves whose direct link
text is the canonical absolute or relative spelling of exactly
`ROOT/stow/PACKAGE/RELATIVE_PATH` or
`ROOT/packages/PACKAGE/install/RELATIVE_PATH`. It does not follow foreign link
chains. Regular files, linked parents, indirect links, noncanonical link text,
other packages/paths and unrelated dangling links remain conflicts. Missing
destinations may be created and current links remain unchanged, as in normal
rebind. Rename-manifest leftovers are refused; recovery does not remove old
names or enumerate undeclared destinations.

The preview explicitly discloses that old payload and ownership cannot be
verified. A matching link text is evidence of the selected layout, not proof
of historical ownership; approval authorizes deploying the current package
payload in place of those exact dangling leaves. The journal records the
recovery mode, selected missing roots/ancestor identities and original link
texts. Reappearing roots or changed ancestors invalidate the approved plan;
changes detected during the transaction cause rollback of that package.
Rollback restores the original link text even if it remains dangling. Final
success requires every current declared link to resolve to this checkout.

This mode neither performs orphan cleanup nor enables a general force overwrite.
Combining it with `--force-links` explicitly broadens eligible symlink leaves,
as described below; the recovery flag alone retains its exact-link restrictions.
It never copies system files, reads system secrets, runs hooks or activates
services. Source reconstruction from Git, crash recovery and arbitrary writers
remain outside the transaction guarantee.

## Explicit replacement of unproven leaf links

Use `--force-links` when a current declared package path contains a symlink that
normal rebind cannot prove belongs to an approved source layout. This is a
deliberate override of leaf-link ownership, for a named package or `all-user`:

```sh
./run.sh verify --rebind --force-links --from-repo /path/to/source-checkout PACKAGE
./run.sh install --rebind --force-links --from-repo /path/to/source-checkout --dry-run PACKAGE
./run.sh install --rebind --force-links --from-repo /path/to/source-checkout --yes PACKAGE
```

Explicit `--from-repo` values are mandatory, including for inspection and
dry-run. They bind the normal source inventories and residue checks; they do
not prove that a forced link belongs to those roots. Source checkouts must
remain valid in this mode. If they were removed, also select
`--recover-dangling` and use missing roots under that mode's rules.

The preview labels each override `force-link` and prints its old and proposed
link text with JSON escaping. It also discloses that the unproven target's
payload is not read or compared. A forced leaf may point to a healthy foreign
file, a directory, an indirect link chain or a missing target; only the leaf
symlink at the current declared destination is replaced. The target object
and its data remain untouched. Without `--yes`, interactive approval requires
the distinct literal `FORCE REBIND`. Inspection returns 3 when valid changes
are needed and includes the force flag in its suggested preview command.

Regular files, directories, special objects and linked parents remain hard
conflicts. Control characters in forced link text are refused. Force does not
bypass package mappings, source safety, Stow projection, selection metadata,
overlapping plans, source/link revalidation or target locking. It does not
scan undeclared paths or authorize removal of otherwise conflicting old rename
paths or unmapped legacy residue. Proven renames retain normal rebind behavior.
Current links remain unchanged. `--force` is not an alias and normal install,
verify and uninstall do not acquire force behavior.

The existing transaction records the force mode and each original link text
in its owner-only journal. Handled failures restore only transaction-owned
changes and verify the entire original package layout. Concurrent edits are
preserved and reported as manual recovery. In `all-user`, a failed package
does not undo successful packages or prevent later eligible packages from
running; errors and rollback outcomes remain explicit. Lock contention or a
persistent batch-journal failure still stops the series.

After actual forced replacements, a final follow-up list groups detached
target references by their old directory and deduplicates each target within
that directory. Entries identify the package, installed link path and current
package/link result. Fully restored links and unattempted changes are omitted.
Package `result.json` saves that package's terminal observation. Batch
`progress.json` and the final console report recheck the references after all
packages finish, including after partial failure and final-state uncertainty.

The follow-up uses metadata-only `stat` to check whether each old target still
exists. That OS lookup can follow target symlinks; it does not read contents,
enumerate directories, resolve a path for ownership proof or remove anything.
Only targets confirmed missing (`ENOENT`/`ENOTDIR`) are omitted. Permission
errors, link loops and unsafe installed parents produce an `unknown` entry
requiring manual inspection. The displayed path is the direct old reference,
not a resolved payload location. Noncanonical link text is preserved rather
than collapsing interior `..` through an unknown symlink. Existence is a
point-in-time observation and may change after the report. This is a checklist
for the owner, not a claim that the old target is unused or safe to delete.

Foreign-target lookups run with SIGINT and SIGTERM unmasked, outside the
mutation/rollback recording sections. Before a lookup, the package outcome
and conservative `unknown` target references are saved in the journal (and
the batch completion callback records success). Interrupting a follow-up does
not undo a committed package or retry that lookup; it stops the remaining
batch and leaves the durable record available. Rollback results are likewise
saved before any optional follow-up, so another signal cannot interrupt the
rollback itself. After interruption the report may retain `unknown` entries
whose existence was not checked.

This mode may intentionally replace a healthy link owned by another installer.
Approval authorizes that exact link replacement and deployment of the current
package payload; it cannot establish old payload equivalence or compatibility
with the other installer. General file overwrite, system-file migration,
service activation, secret handling and automatic crash recovery are separate
work. Do not run competing installers against the same target.

Without override flags, the inventory classifies current links, missing destinations, proven legacy
links, mapped renames, unmapped legacy residue and unknown conflicts. A regular
file, dangling/indirect/foreign link, linked parent directory, special source,
source symlink or custom Stow ignore policy blocks the affected package before
its mutation. Invalid aggregate selection metadata or Stow mappings refuse the
entire batch before any package writes. Source content/mode differences are
disclosed; a rebind can therefore also deploy a reviewed payload change, not
merely move a path. The old checkout must remain available for proof.

## Aggregate user rebind

`install --rebind all-user` selects package names in sorted order from `stow/`,
honoring `manifests/ignore-all-install.txt`. It prints both selected and excluded
packages. Each Stow link must have the declared package/install mapping; eligible
packages must have safe, nonempty inventories. Read-only `verify --rebind all-user`
continues to inspect excluded packages too. A named package can be migrated
separately after reviewing its plan. An empty aggregate selection is refused.

```sh
./run.sh install --rebind --from-repo /path/to/source-checkout --dry-run all-user
./run.sh install --rebind --from-repo /path/to/source-checkout --yes all-user
```

The helper preflights every selected package before any installed write. A
package-specific preflight failure blocks only that package; the eligible
packages can still migrate after approval. The entire batch is refused if
eligible packages' destinations overlap, including rename destinations, legacy
paths and ancestor/child collisions. Explicit source-root restrictions apply
to every package: each root must contain a valid source package for a package to
be eligible. Discovery may find
different roots for different packages; those roots require one interactive
`REBIND` approval of the complete printed plan. Bare `--yes` remains invalid
for discovered roots. No source checkout's hooks or programs run.

One nonblocking target-directory lock covers the entire batch. Under that lock,
the helper revalidates the complete approved selection, exclusion-policy identity,
source inventories, destination links and parent-directory identities before the
first write. It repeats selection and package checks before each transaction,
and parent/link checks at publication. Directories created by an earlier
completed package are tracked as batch-owned additions. Arbitrary new or replaced
parents do not become approved simply because another package finished.

Each package retains its own conservative transaction and rollback journal.
The batch also records plans, package journal paths, progress and execution stage
in an owner-only `/tmp/runner-rebind-batch-*/progress.json`, updated by atomic
replacement. The journal contains metadata and content digests, never copied
payloads. Final verification checks every selected package and unchanged source
inventories, including packages completed earlier in the batch.

Package and batch journal creation synchronizes both the new directory and its
parent before link changes. Each JSON update flushes and synchronizes the file
before atomic replacement, then synchronizes its directory. Installed-link and
created-directory changes, including rollback, synchronize the affected parent
before reporting an outcome. Storage errors stop normal progress; failed rollback
synchronization is reported as manual recovery. This does not provide automatic
crash replay or package-wide atomicity. The `/tmp` journals may be volatile or
removed at boot, so their synchronization cannot guarantee reboot persistence.

User target/source root arguments also refuse double-leading-slash Linux aliases
such as `//tmp/checkout` and `//`, before traversal or root comparisons.
Every planned leaf, including rename sources and legacy residue, must be
outside the whole current and admitted old checkouts. A target may contain a
checkout, but no declared leaf may equal, contain or lie within that checkout.
Existing destination-parent device/inode identities must not alias a checkout
root. The same preflight applies to normal rebind, forced links, recovery,
batch planning and revalidation before writes; recovery still requires its
selected legacy roots to be absent.

User rebind validates the complete target ancestry before planning. Directories
above the target must be owned by root or the executing account; writable
ancestors require a sticky bit, so a trusted sticky `/tmp` remains supported.
Foreign-owned ancestors are refused even when private or sticky. The target
and existing destination parents inside it must be owned by the executing
account with no group/world write bits. This applies to normal, forced,
recovery and batch plans and their revalidation before writes. It protects the
named target tree from relocation by another account while a descendant
file descriptor remains open. Missing destination parents are still created
only by the approved user transaction, with mode 0755 further restricted by
the caller's umask; a permissive umask cannot make them group/world-writable.

Every batch prints a final result for each selected or excluded package, including
when preflight fails, approval is cancelled or the target lock is busy. The result
distinguishes actual link changes from a package that was already current:

| Result | Meaning | Retained link changes |
| --- | --- | --- |
| `rebound` | All package links verified against the new checkout | Number of published leaf changes, including removed old names |
| `unchanged` | Already current; verification succeeded without link changes | `0` |
| `rolled-back` | Transaction failed; the entire original package link layout was verified after rollback | `0` |
| `manual-recovery` | Original layout could not be fully restored or verified; listed paths need inspection | `unknown` |
| `final-state-unverified` | A completed package failed the batch's final state recheck | `unknown` |
| `unattempted` | Execution stopped before this package's transaction | `0` |
| `not-started` | Approval, preflight or a transaction check prevented link changes | `0` |
| `blocked` | This package failed batch preflight | `0` |
| `excluded` | Omitted by the aggregate exclusion policy | `0` |
| `preview-only` | Dry-run preflight only | `0` |

For example, a failure in the second package may produce:

```text
Final package results:
Package result: first: rebound; retained link changes: 3
Package result: second: rolled-back; retained link changes: 0
Package result: third: rebound; retained link changes: 1
Package result: optional: excluded; retained link changes: 0
Batch status: failed; stage: complete
```

On a package failure, only that package rolls back its own changes. The helper
records its error and rollback result, then attempts the next eligible package.
Earlier and later successful packages remain migrated, even if one package's
rollback needs manual recovery. Each later package must still pass its approved
source, link and parent checks; no unexpected path becomes approved through
continuation. Before printing the final results, the helper rechecks completed
packages under the same target lock.
The historical **completed**, **failed** and **unattempted** lists remain in the
output and journal, but each package's `outcome` records its verified final state.
An `unknown` count must never be interpreted as zero changes or a successful
rollback. The batch returns a nonzero exit status if any package failed, even
after successful rollback and successful migration of the remaining packages.
`stage: complete` means the full series was processed; `state: failed` records
its partial failure. Each failed package's printed error and journal `error`
field explain why it did not migrate. A failed final recheck marks that package
`final-state-unverified` and checks the remaining completed packages. Retain both
batch and package journals, investigate the reported state, and run a new full
dry-run before resuming. Journals are evidence, not an executable replay or
automatic-resume facility. If selection metadata itself is invalid, there is no
trusted package list to report; the helper refuses before any installed write.
Shared failures stop further transactions: selection/exclusion-policy changes,
overlapping plans, inability to obtain the target lock, a persistent batch
journal write failure, or explicit SIGINT/SIGTERM interruption. A signal rolls
back the current uncommitted package and leaves successful packages intact;
remaining packages are reported as `unattempted`. It does not silently resume
work after the user requested interruption.

A batch is not atomic across packages. Other applications may observe its
intermediate state; SIGKILL, power loss and lost temporary journals still require
manual recovery. Ordinary install tools and external writers do not participate
in the advisory lock. Mixed packages migrate user links only; the batch never
copies system files, reads system secrets, runs hooks or activates services.
Dangling links after loss of a source checkout remain conflicts unless an
explicit mode above accepts them. Aggregate rebind does not implicitly enable
force, general file overwrite or orphan cleanup.

## Renamed files

An optional `packages/<package>/rebind-paths.manifest` contains:

```text
# old relative name, new relative name
.config/example/old.conf .config/example/new.conf
```

Both columns are data, not shell. Each target must exist in the new package;
old names must be absent there. Duplicate sources/targets, unsafe paths and
ambiguous mappings are refused. An old link is removed only when it points
directly to the same old package/path in an approved root. Unknown files at an
old name remain conflicts even if a rename was declared.
The shipped Zsh package maps its two historical rc-fragment names explicitly,
preventing a successful migration from leaving both loader generations present.
These mappings are package policy, not part of the shared runner export.

## Transaction and rollback

1. Inventory the full package, relevant old paths, current live links and parents.
2. Ask GNU Stow to build the expected no-folding layout in an isolated temporary
   target, with an isolated HOME/cwd and sanitized environment. Verify every
   generated link. Even dry-run uses this temporary projection, not live Stow.
3. After confirmation, take a nonblocking advisory lock on the target directory
   and recompute the inventory. Reject changes since approval.
4. Save an owner-only journal under `/tmp/runner-rebind-journal-*/before.json`.
5. Apply validated leaf changes, with no-clobber creation for missing paths and
   atomic replacement for existing proven links. Recheck each before publication.
6. Verify unchanged source inventories, every final link and removal of renamed
   legacy leaves. Record the verified outcome in an owner-only `result.json`
   beside `before.json`. No hook or service activation follows.

The package is the transaction boundary: success requires verification of all
its declared paths. On handled failure (including SIGINT/SIGTERM), rollback
removes/restores only links whose identity and text still belong to this
transaction. It then verifies the original state of every declared path,
including unchanged links, originally missing paths and renamed legacy leaves.
Restored links preserve their original text and mode; replacement creates new
inodes and timestamps. Only empty directories created by this operation are
eligible for removal. Further handled signals are deferred until rollback and
outcome recording finish. Both a single-package operation and a batch print the
verified result; `result.json` stores it when journal writes remain available.
Concurrent edits and I/O errors can prevent full rollback: `manual-recovery`
explicitly reports that exception and the affected relative paths. Keep the
printed journal; it contains paths and metadata, not copied configuration
contents. Journal write failures are also reported and require retaining the
console result alongside the journal.

The all-or-rollback result for handled failures is not an instantaneous multi-file
filesystem switch. Other applications can observe intermediate states within a
package as well as between packages. The advisory lock coordinates this helper, not
arbitrary filesystem writers. Do not concurrently edit sources, clean worktrees
or install the same target with other tools. SIGKILL, power loss and hostile
same-user mutation require manual recovery from the journal; automatic crash
recovery and rollback replay are not implemented. Temporary journals may be
removed by host cleanup. No automatic revert of payload edits is performed.

## Boundaries and validation

This is WP-5 plus the bounded package inspection portion of WP-7, not WP-6
system-file migration or a general orphan-link scanner. Discovery cannot find
an old root represented only at paths absent from the new inventory and rename
manifest: supply it explicitly with `--from-repo` to inspect its package paths.
Completely removed packages, unrelated orphan links outside these inventories,
folded/linked target directories and running-unit verification are not supported.
Ordinary `verify all` keeps its previous behavior. System-managed files are
copies, not Stow links, and are outside this helper's inspection and mutation.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_runner_rebind*.py' -v
zsh -n run.sh
./scripts/check-repo
RUNNER_SYNC_EXPECTED_ROLE=source RUNNER_SYNC_WRITE=0 ./scripts/sync-runner check
```

Tests use temporary repositories/targets and real GNU Stow projection, plus
fault injection for conflicts, rollback, concurrency and optional-helper routing.
They neither install workstation packages nor activate services.
