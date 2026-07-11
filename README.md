# grz-workstation-tools

Public Zsh toolkit repository.

This repository owns the public Zsh runtime. It does not own `~/.zshrc` or `~/.profile`.

## Requirements

- **GNU Stow** (`apt install stow`)
- Zsh

## Install

```sh
./run.sh install all
```

Installs all packages (from `stow/`) as symlinks into `$HOME` using GNU Stow.

## Commands

```
./run.sh install  [--verbose] [--verify] [--test] all|all-user|all-system|<package>
./run.sh uninstall [--verbose] all|all-user|all-system|<package>
./run.sh activate  all|all-user|all-system|<package>
./run.sh verify    all|all-user|all-system|<package>
./run.sh test      all|all-user|all-system|<package>
```

- `all` — all packages not in `manifests/ignore-all-install.txt`
- `all-user` — user (stow) packages only
- `all-system` — system packages only (require `sudo`)
- `<package>` — single named package

Override install target: `GRZ_STOW_TARGET=/path ./run.sh install all`

## Adding a user package

1. Create `packages/<name>/install/` with files mirroring their `$HOME` paths.
2. Create a symlink: `ln -s ../packages/<name>/install stow/<name>`
3. Run `./run.sh install <name>`

## System packages (root-owned files, sudo)

A package may carry a root-owned layer under `packages/<name>/system-install/`, described
entirely by **declarative manifests** (no per-package shell code for the privileged layer):

| Manifest | Purpose |
|---|---|
| `system-install.manifest` | files to copy to `/` — lines `rel_path mode owner group` |
| `system-config.manifest` | required root-only secret configs — lines `dest mode owner group` |
| `system-units.manifest` | systemd system units to activate — one unit name per line |

The repo only ever contains `*.example` configs and unit files — **never real secrets**.

### Installing configs/secrets

`./run.sh install <name>` copies the files, then for each entry in `system-config.manifest`
it prompts for the **path** to your real config. The script copies it with `install` and
**never reads its contents**. Three outcomes per config:

- **destination already exists** → left untouched (no overwrite);
- **empty answer** → opens `sudoedit` to create the file in place (cancelling the editor
  aborts the install). `sudoedit` runs your editor as your normal user and writes back as
  root, so the editor never runs privileged and the secret only ever lives at its final
  root-only path;
- **a path is given** → copied to the destination as declared (e.g. `root:root` `0600`).

When all configs are present (or none are required) the installer offers to activate the
package's units. If any config was skipped, activation is left for later:

```sh
./run.sh activate <name>
```

Activation first runs `scripts/check-repo`, then reloads systemd; a failed `daemon-reload`
aborts activation. Per `system-units.manifest`: `.timer` is enabled when it has `[Install]`
and then restarted; `.path`/`.socket` are enabled when they have `[Install]` and then
started, but not restarted; `.target`/`.mount` are enabled only when they have `[Install]`
and otherwise started; `.service` is start-only. Uninstall disables/stops trigger units
first, then tears down the remaining units in reverse manifest order before removing files.
Post-uninstall reload is best-effort. Verify checks installed file modes/contents, that
required configs exist and are root-only, and runs `systemd-analyze verify` on the installed
units.

## User systemd units

A user-layer package may declare `systemd --user` units via `packages/<name>/user-units.manifest`
(one unit name per line). The unit files must live under `packages/<name>/install/.config/systemd/user/`
and are installed by GNU Stow as symlinks in `~/.config/systemd/user/`.

```
./run.sh activate <name>   # enable/start units
./run.sh uninstall <name>  # disable/stop units, then remove stow links
./run.sh verify <name>     # check units exist and pass systemd-analyze --user verify
```

Activation first runs `scripts/check-repo`, then reloads the user systemd manager; a failed
`daemon-reload` aborts activation. User timers are enabled when they have `[Install]` and
then restarted. User paths/sockets are enabled when they have `[Install]` and then started,
but not restarted. User services are enabled only when they have `[Install]`, then started;
services managed by a timer, path, or socket are skipped. Deactivation disables/stops
trigger units first, then the rest in reverse manifest order. Activation and deactivation
run only when `STOW_TARGET` resolves to `$HOME`.

## Package hooks (user layer only)

The privileged layer is fully declarative — there are **no system hooks**. For custom
verification logic that can't be expressed as a manifest, a package may ship a `verify.hook.sh`
hook, which runs after stow-link verification and user unit verification.

| File in `packages/<name>/` | When it runs |
|---|---|
| `verify.hook.sh` | `./run.sh verify <name>`, after stow-link and user unit verification |

The hook must be executable, run as the normal user (**no `sudo`**), be idempotent, and exit
non-zero to signal failure. It receives: `GRZ_REPO_ROOT`, `GRZ_PACKAGE`, `STOW_TARGET`.
Any other `*.hook.sh` is rejected by `check-repo`.

## Consistency check (`check-repo`)

`scripts/check-repo` statically verifies that every system file, unit, and example config is
declared in the right manifest, that no real secret is committed, and that only the allowed
hooks exist. It runs automatically before a system install, in CI, and as a local pre-push hook:

```sh
git config core.hooksPath githooks   # enable the pre-push check once
./scripts/check-repo                  # or run it manually anytime
```

## Excluding packages from `all`

Add the package name to `manifests/ignore-all-install.txt` (one per line).

## Bootstrap

Copy the relevant snippet from `bootstrap/` into your `~/.zshrc` / `~/.profile` to load rc fragments from `~/.config/zsh/rc.d/`.

## Third-party components

Some completion scripts are generated by their upstream tools and vendored here for
convenience. They remain under their respective upstream licenses:

- `packages/zsh-tools/install/.zsh_scripts/completion/functions/_pnpm` — based on the
  output of [pnpm](https://github.com/pnpm/pnpm) (`pnpm completion zsh`) under the MIT
  license, with local modifications: Corepack-aware binary resolution, short-flag alias
  injection for common subcommands, and a static fallback command list for offline use.
- `packages/zsh-tools/install/.zsh_scripts/completion/functions/_volta` — generated by
  [Volta](https://github.com/volta-cli/volta) (`volta completions zsh`) under the
  [BSD 2-Clause license](https://github.com/volta-cli/volta/blob/main/LICENSE).

## License

Released under the [MIT License](LICENSE).
