# Orphaned uninstall (`uninstall --orphaned`)

## What it does

Removes matching installed Stow symlinks within the scan roots listed below
after a package is removed from this checkout. When the target resolves to
`$HOME`, it also attempts best-effort user-unit deactivation. A successful
exit does not prove that all links were removed or that the units stopped.

Normal user-layer uninstall requires the package to exist under both
`stow/<package>` and `packages/<package>/install`. Once that tree is gone,
`stow --delete` cannot reconstruct the set of links to remove. The orphaned
path exists for that recovery case.

## When to use it

Use it when a package was installed and later removed from this checkout
without first running `./run.sh uninstall <package>`. Typical leftovers are:

- dangling symlinks under `.local/bin`, `.local/lib`, `.local/share/applications`,
  `.config/autostart`, or `.zsh_scripts`;
- enabled user units whose unit files came from the removed package;
- dangling `*.wants/<unit>` links left by user-unit enablement.

The existing-package safeguard refuses cleanup when **both** `stow/<package>`
exists and `packages/<package>/install` is a directory. A dangling Stow entry
does not count as existing. With both paths present, use the normal
`./run.sh uninstall <package>` path instead.

If the source directory remains but the Stow entry is missing or dangling,
the orphaned path can still run and remove matching installed links, including
links to that remaining source. For a user-only package, normal uninstall also
rejects that incomplete mapping. Restore the valid Stow mapping before using
normal uninstall if you intend to retain the package's normal teardown path.

## How it finds things

The package-tree scan examines symlinks under the listed paths. It makes each
link's own target absolute and normalizes `.` and `..` before matching this
checkout's `stow/<package>/` or `packages/<package>/install/` prefix. It does
not resolve the full target chain, require the link to be dangling, or prove
ownership through Git provenance. The source does not need to exist.

The scan roots are `.local/bin`, `.local/lib`, `.local/my-custom-bin`,
`.local/share/applications`, `.config/systemd/user`, `.config/autostart`,
`.config/zsh/rc.d`, `.config/profile.d`, and `.zsh_scripts`. A root that is
itself a symlink is inspected too, including a dangling root left by Stow
directory folding. The package-tree walk does not descend through a symlink
at the scan root or one encountered below it.

Symlinked ancestors of a scan root are different: pathname resolution follows
them before the walk starts. For example, if `$HOME/.local` points to
`/data/local`, scanning `$HOME/.local/bin` inspects `/data/local/bin` and can
remove matching links there. The listed target-relative paths therefore do
not guarantee physical containment within the target directory. Check their
ancestor paths before cleanup.

Target-relative destinations outside the listed paths are not scanned. In
particular, `ai-agents-hooks` installs sound links under
`.local/share/agent-sounds`, and
`simplified_netrole` installs a configuration-example link under
`.local/share/simplified-netrole`. Removing either package can leave those
links behind even when its `.local/bin` links are cleaned up successfully.
Inspect those destinations separately. Even "No orphaned symlinks found"
reports only the bounded scan, not the absence of all package leftovers.

In the package-tree scan, symlinks matching that package marker are candidates.
Before unlinking a candidate, the script checks that the path is still a
symlink, but does not atomically revalidate its original target or identity.
This is not protection against concurrent path replacement. The command
does not scan all of `$HOME`.

For user-systemd enablement links that no longer contain a package-tree marker,
the command has a narrower fallback heuristic: a dangling link under a
`*.wants/`, `*.requires/`, or `*.upholds/` directory is considered only when
its unit name is `<package>.<type>` or `<package>-*.<type>`, where the type is
`service`, `timer`, `path`, `socket`, or `target`.

This dangling-link check selects a **unit name**, not a bounded set of broken
links. One dangling link can select a name also used by a healthy unit from
another checkout. For a home-directory target with `systemctl` available,
confirming cleanup can stop that unit and remove valid links. The same
unit-name processing applies to units selected by package-tree links.
The operation and its wider effects are described below.

## Usage

```bash
# Preview only — lists candidates, removes nothing, asks nothing.
./run.sh uninstall --orphaned --dry-run <package>

# Interactive — confirms unit cleanup, then individual package-tree links.
./run.sh uninstall --orphaned <package>

# Non-interactive — removes links and attempts unit deactivation without prompts.
./run.sh uninstall --orphaned -y <package>
```

Flags:

- `--orphaned` (alias `--reap`) selects the orphaned-cleanup path.
- `--dry-run` (alias `-n`) lists locally discovered candidates and proposed
  unit commands; it makes no changes and does not prompt. It does not call
  `systemctl` to expand their effects or produce a complete systemd plan.
- `-y` / `--yes` skips confirmations for scripted use.

The confirmation prompt is read from `/dev/tty` when a terminal is available,
so it still works when standard input is redirected; otherwise it falls back
to standard input.

Accepting a unit-deactivation prompt authorizes the `systemctl` operation and
the direct same-name enablement-link removal described below, without further
per-link prompts. Individual prompts in the later package-tree pass apply to
those package-tree links only. `-y` skips both kinds of prompt.

## User-unit cleanup and verification

For a home-directory target with `systemctl` available, confirmed unit cleanup
has two operations:

1. `systemctl --user disable --now <unit>` acts according to systemd's unit
   configuration and name resolution. Its effects are not bounded by this
   script's scan roots or same-name link list: `disable` can remove manual
   links and aliases to the backing unit file, and disable companion units
   named in `Also=`. `--now` requests stopping after the unit-file operation
   succeeds; a disable failure does not prove that stopping was attempted.
2. The script directly removes surviving symlinks with the selected unit's
   basename under `*.wants/`, `*.requires/`, and `*.upholds/`, without another
   prompt or a brokenness/ownership check.

The dry-run prints the selected unit command and the second operation's
same-name paths. It does not expand the first operation's aliases, manual
links, `Also=` companions or runtime effects. Before approving it, inspect
the backing file and drop-ins of each selected unit, their `[Install]`
settings (following `Also=` companion relationships), and links to those
backing files throughout the user unit lookup paths, not just the three
enablement-directory patterns. Read-only tools such
as `systemctl --user cat <unit>` and `systemd-analyze --user unit-paths` help
with this manual review. Missing unit files or an unavailable manager leave
that scope unknown; the script's preview is not a complete approval plan.
See the upstream [systemctl command reference](https://github.com/systemd/systemd/blob/main/man/systemctl.xml)
for `disable` and `--now` semantics.

If `disable --now` fails, the script prints a warning and continues with
direct enablement-link and package-link removal. If `systemctl` is unavailable,
it skips unit processing but can still remove package links. Declining a
unit's cleanup prompt skips both unit operations, but does not cancel the
later package-tree link-removal pass.

Consequently a unit can remain running after its unit-file link is removed,
and the command can still exit successfully. This orphaned path currently
does not enforce the fatal deactivation-failure rule documented in `AGENTS.md`
for ordinary uninstall. Treat warnings, skipped deactivation and the final
removal count as cleanup information, not proof that the runtime stopped.

### Manual follow-up for a home-directory target

Record the intended units, aliases, companion units and template instances
before removing their source links. The orphaned path does not enumerate and
stop all running template instances. For a detected `foo@.service` template,
querying that literal name cannot verify `foo@bar.service`. Use a quoted
pattern with `list-units` to inspect loaded instances, and `list-unit-files`
to inspect available template/instance files and enablement information:

```sh
systemctl --user list-units --all --full --no-pager --no-legend --plain -- 'foo@*.service'
systemctl --user list-unit-files --all --full --no-pager --no-legend -- 'foo@*.service'
```

Repeat with the corresponding template stem and type, including the canonical
name when a template has aliases. Runtime glob matching uses primary unit
names; an alias-only pattern can omit loaded instances. Record exact instance
names for individual checks. A successful empty runtime listing says there
are no currently loaded matches; it does not prove future instances cannot
be started. A failed listing leaves instance state unknown. Template
definitions themselves are not runnable and are not listed by `list-units`.

After unit-file links are removed, a separate, successful user-manager reload
is required before treating its configuration as refreshed. `disable` may
reload earlier, but the script removes further links afterward and performs
no final reload. The following is a **manual live-session operation**, not
part of the throwaway-target example:

```sh
systemctl --user daemon-reload
```

Reloading does not stop running units. If the manager is unreachable or reload
fails, leave the runtime/configuration state unverified. Once reload succeeds,
inspect every intended concrete unit, including recorded instances and the
companions identified before cleanup, using its exact name:

```sh
systemctl --user show <unit> --property=LoadState --property=FragmentPath \
  --property=ActiveState --property=SubState --property=TriggeredBy
```

Repeat the template runtime listing after reload and any manual stopping.
Inspect enablement links and unit lookup paths separately; another definition
of the same name may still be available. Stopping or disabling a service does
not prevent timers, sockets, paths, dependencies or global user enablement
from activating it again. Review those activation sources and pending jobs
before interpreting inactivity as the intended teardown result.

Any failed query leaves that part of verification unknown. If an intended
unit or instance remains running, stop its exact name explicitly and repeat
the checks. These checks describe a current observation, not a permanent
guarantee against reactivation. The script performs none of this follow-up.

## Scope and limitations

- Covers matching user Stow symlinks within the listed roots and the described
  dangling user-unit name heuristic; it is not a complete inventory. Systemd
  unit operations have the wider scope described above.
- User-unit deactivation is attempted only when the target resolves to `$HOME`
  and `systemctl` is available; the best-effort limitations above apply.
- Files copied to `/` by a system-install manifest are not handled: they are
  not symlinks and cannot be discovered by this scan.
- Scan/readlink errors can omit candidates without making the command fail.
  The package scan is line-oriented and does not reliably inventory names
  containing newlines. A zero exit status is not proof of a complete scan.
- The final removed/skipped counts cover the package-tree link pass only;
  they do not count systemctl's changes or direct enablement-link removal.
- There is no lock binding a preview to later cleanup and no transaction-wide
  rollback. Concurrent path or unit changes can invalidate the discovery,
  and earlier removals are not undone after a later failure.
- This is not a general `--force` or `--override` operation. It will not
  replace an existing link that points into a different checkout. For a
  migration between checkouts while both package trees remain available, run
  the separate [user-package rebind workflow](runner-rebind.md) from the
  destination checkout, starting with its read-only preview and source approval.
  Rebind accepts a named package or `all-user`, preserves successful package
  migrations, and attempts later eligible packages after a package error.
  Its package rollback and target lock do not apply to orphaned cleanup.
  If the entire source checkout was removed, rebind's explicit
  `--recover-dangling --from-repo /path/to/lost-checkout` mode can recover only
  exact declared leaves; it cannot discover arbitrary orphan leftovers.
  Rebind also offers explicit `--force-links` for unproven current destination
  symlinks. That override is separate from cleanup and does not overwrite plain
  files or remove arbitrary orphan paths.
  Do not clean up source links before migration or run both operations concurrently.

## Validation with a throwaway target

The command honors `STOW_TARGET` and the repository-specific target variable,
so it can be exercised without touching the live home directory:

```bash
REPO_ROOT="$(pwd)"  # run from the repository root
TMP="$(mktemp -d)"
mkdir -p "$TMP/.local/bin"
ln -s "$REPO_ROOT/stow/demo/.local/bin/demo-tool" "$TMP/.local/bin/demo-tool"
GRZ_STOW_TARGET="$TMP" ./run.sh uninstall --orphaned --dry-run demo
GRZ_STOW_TARGET="$TMP" ./run.sh uninstall --orphaned -y demo
rm -rf "$TMP"
```

Because the throwaway directory is not `$HOME`, user-systemd deactivation is
skipped. The example is therefore limited to the symlink scan and cleanup.
