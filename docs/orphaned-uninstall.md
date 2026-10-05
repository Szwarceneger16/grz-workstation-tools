# Orphaned uninstall (`uninstall --orphaned`)

## What it does

Removes installed Stow symlinks (and, when the target is `$HOME`, deactivates
the package's user systemd units) after the package source tree has already
been removed from this repository.

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

If the package still exists in this repository, use the normal
`./run.sh uninstall <package>` path instead. The orphaned path refuses to run
for a package that still has a source tree here.

## How it finds things

The scan is bounded to known Stow-managed subtrees. A candidate symlink must
still point into this checkout's own `stow/<package>/` tree (or the equivalent
`packages/<package>/install/` tree). The source does not need to exist: the
link may be dangling after the package was deleted.

The scan roots are `.local/bin`, `.local/lib`, `.local/my-custom-bin`,
`.local/share/applications`, `.config/systemd/user`, `.config/autostart`,
`.config/zsh/rc.d`, `.config/profile.d`, and `.zsh_scripts`. A root that is
itself a symlink is inspected too, including a dangling root left by Stow
directory folding. The scan does not follow directory symlinks.

Only symlinks matching that package marker are candidates. Real files and
directories are never removed, and the command does not scan all of `$HOME`.

For user-systemd enablement links that no longer contain a package-tree marker,
the command has a narrower fallback heuristic: a dangling link under a
`*.wants/`, `*.requires/`, or `*.upholds/` directory is considered only when
its unit name is `<package>.<type>` or `<package>-*.<type>`, where the type is
`service`, `timer`, `path`, `socket`, or `target`. A live, healthy unit is never
removed by this heuristic.

## Usage

```bash
# Preview only — lists candidates, removes nothing, asks nothing.
./run.sh uninstall --orphaned --dry-run <package>

# Interactive — asks before each symlink and user-unit cleanup.
./run.sh uninstall --orphaned <package>

# Non-interactive — removes/deactivates without prompting.
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

## Scope and limitations

- Covers user Stow symlinks and user systemd units only.
- User-unit deactivation runs only when the target resolves to `$HOME`.
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
