# Orphaned uninstall (`uninstall --orphaned`)

## What it does

Removes matching installed Stow symlinks within the scan roots listed below
after a package is removed from this checkout. When the target resolves to
`$HOME`, it also attempts best-effort user-unit deactivation. A successful
exit does not prove that all links were removed or that the units stopped.

The normal uninstall path requires the package to exist under both
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

The orphaned path refuses only when **both** `stow/<package>` exists and
`packages/<package>/install` is a directory. A dangling Stow entry does not
count as existing. With both paths present, use the normal
`./run.sh uninstall <package>` path instead.

If the source directory remains but the Stow entry is missing or dangling,
the orphaned path can still run and remove matching installed links, including
links to that remaining source. For a user-only package, normal uninstall also
rejects that incomplete mapping. Restore the valid Stow mapping before using
normal uninstall if you intend to retain the package's normal teardown path.

## How it finds things

The package-tree scan is bounded to known Stow-managed subtrees. A candidate
symlink must still point into this checkout's own `stow/<package>/` tree (or the equivalent
`packages/<package>/install/` tree). The source does not need to exist: the
link may be dangling after the package was deleted.

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
particular, `ai-agents-hooks` installs sound links under `.local/share/agent-sounds`, and
`simplified_netrole` installs a configuration-example link under
`.local/share/simplified-netrole`. Removing either package can leave those
links behind even when its `.local/bin` links are cleaned up successfully.
Inspect those destinations separately. Even "No orphaned symlinks found"
reports only the bounded scan, not the absence of all package leftovers.

In the package-tree scan, only symlinks matching that package marker are
candidates. Real files and directories are never removed, and the command
does not scan all of `$HOME`.

For user-systemd enablement links that no longer contain a package-tree marker,
the command has a narrower fallback heuristic: a dangling link under a
`*.wants/`, `*.requires/`, or `*.upholds/` directory is considered only when
its unit name is `<package>.<type>` or `<package>-*.<type>`, where the type is
`service`, `timer`, `path`, `socket`, or `target`.

This dangling-link check selects a **unit name**, not a bounded set of broken
links. For a home-directory target with `systemctl` available, confirming that
unit's cleanup attempts to disable and stop the unit, then removes every
surviving symlink with that basename under `*.wants/`, `*.requires/`, and
`*.upholds/`. Those later links are not checked for brokenness or ownership.
One dangling link can therefore select a name also used by a healthy unit
from another checkout, causing that unit to be stopped and its valid
enablement links to be removed. Review all enablement links for each selected
name and the unit it currently identifies before confirming cleanup.

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
- `--dry-run` (alias `-n`) lists candidates only; it makes no changes and
  does not prompt.
- `-y` / `--yes` skips confirmations for scripted use.

The confirmation prompt is read from `/dev/tty` when a terminal is available,
so it still works when standard input is redirected; otherwise it falls back
to standard input.

Accepting a unit-deactivation prompt also authorizes direct removal of its
surviving enablement symlinks without separate per-link prompts. Individual
prompts in the later package-tree pass apply to those package-tree links only.

## User-unit cleanup and verification

For a home-directory target, the command attempts
`systemctl --user disable --now <unit>` for each detected unit whose cleanup
is confirmed. That confirmation also covers direct removal of all surviving
same-name enablement symlinks in the three directory types above, including
valid links, without further prompts. If the call fails, it prints a warning
and continues removing those enablement links and package symlinks. If
`systemctl` is unavailable, it skips deactivation but can still remove package
symlinks. Declining a unit's
deactivation prompt also does not cancel the later symlink-removal pass.

Consequently a unit can remain running after its unit-file link is removed,
and the command can still exit successfully. This orphaned path currently
does not enforce the fatal deactivation-failure rule documented in `AGENTS.md`
for ordinary uninstall. Treat warnings, skipped deactivation and the final
removal count as cleanup information, not proof that the runtime stopped.

Before cleanup, record the unit names from the preview and inspect every
same-name enablement link and its destination for the collision risk above.
For each detected unit, query the reachable user manager afterward, using
the exact reported name:

```sh
systemctl --user show <unit> --property=ActiveState --property=SubState
```

Confirm that the unit is inactive and inspect its enablement links separately.
An unreachable manager or failed query leaves the runtime state unverified.
If a unit remains running, stop it explicitly once the manager is reachable
and repeat the check. The command does not perform this verification or retry
automatically.

## Scope and limitations

- Covers matching user Stow symlinks within the listed roots and the described
  dangling user-unit enablement heuristic; it is not a complete inventory.
- User-unit deactivation is attempted only when the target resolves to `$HOME`
  and `systemctl` is available; the best-effort limitations above apply.
- Files copied to `/` by a system-install manifest are not handled: they are
  not symlinks and cannot be discovered by this scan.
- This is not a general `--force` or `--override` operation. It will not
  replace an existing link that points into a different checkout. For a
  migration between checkouts, use the separate
  [user-package rebind workflow](runner-rebind.md), starting with its read-only
  preview and explicit source approval.

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
