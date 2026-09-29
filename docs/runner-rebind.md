# Optional user-package rebind (WP-5)

`scripts/rebind-user-package` discovers and transfers one package's user-layer
symlinks from approved, still-existing checkouts to this checkout. It is a separate
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

## Read-only discovery and approval

From the destination checkout:

```sh
./run.sh verify --rebind all-user
./run.sh verify --rebind PACKAGE
./run.sh install --rebind --dry-run PACKAGE
./run.sh install --rebind PACKAGE
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
approval aborts. No source checkout's scripts or configuration are executed.

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
Publication allows only one named package. Bulk installation and `--verify`/`--test`
hook execution are refused. Normal install flags do not implicitly select rebind.
The read-only `verify --rebind all-user` enumerates package names under the
repository's `stow/`, including packages excluded from ordinary `install all`,
and performs the same exact-path inspection for each. It continues after package
failures and returns 1 if any failed, otherwise 3 if any need migration, or 0 if
all are current. It does not widen the target search. Explicit root restrictions
apply to every inspected package; roots missing that package fail validation.

The inventory classifies current links, missing destinations, proven legacy
links, mapped renames, unmapped legacy residue and unknown conflicts. A regular
file, dangling/indirect/foreign link, linked parent directory, special source,
source symlink, invalid package mapping or custom Stow ignore policy blocks the
operation before mutation. Source content/mode differences are disclosed; a
rebind can therefore also deploy a reviewed payload change, not merely move a
path. The old checkout must remain available for proof.

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
   legacy leaves. No hook or service activation follows.

On handled failure (including SIGINT/SIGTERM), rollback removes/restores only
links whose identity and text still belong to this transaction; concurrent
changes require manual review. Only empty directories created by this operation
are eligible for removal. Keep the printed journal if manual recovery is needed;
it contains paths and metadata, not copied configuration contents.

This is not an atomic multi-file filesystem transaction. Other applications can
observe intermediate states. The advisory lock coordinates this helper, not
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
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_runner_rebind.py' -v
zsh -n run.sh
./scripts/check-repo
RUNNER_SYNC_EXPECTED_ROLE=source RUNNER_SYNC_WRITE=0 ./scripts/sync-runner check
```

Tests use temporary repositories/targets and real GNU Stow projection, plus
fault injection for conflicts, rollback, concurrency and optional-helper routing.
They neither install workstation packages nor activate services.
