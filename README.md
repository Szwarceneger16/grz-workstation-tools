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
| `system-units.manifest` | systemd units to activate — one unit name per line |

The repo only ever contains `*.example` configs and unit files — **never real secrets**.

### Installing configs/secrets

`./run.sh install <name>` copies the files, then for each entry in `system-config.manifest`
it prompts for the **path** to your real config. The script copies it with `install` and
**never reads its contents**. Three outcomes per config:

- **destination already exists** → left untouched (no overwrite);
- **empty answer** → skipped; create it yourself, most securely in place with `sudoedit`:
  ```sh
  sudoedit /etc/<pkg>/secret.env
  sudo chown root:root /etc/<pkg>/secret.env && sudo chmod 0600 /etc/<pkg>/secret.env
  ```
  `sudoedit` runs your editor as your normal user and writes back as root, so the editor
  never runs privileged and the secret only ever lives at its final root-only path;
- **a path is given** → copied to the destination as declared (e.g. `root:root` `0600`).

When all configs are present (or none are required) the installer offers to activate the
package's units. If any config was skipped, activation is left for later:

```sh
./run.sh activate <name>
```

Activation reloads systemd and, per `system-units.manifest`: `.timer` → `enable --now`,
`.service` → `start`. Uninstall reverses this (`disable`/`stop`) before removing files.
Verify checks installed file modes/contents, that required configs exist and are root-only,
and runs `systemd-analyze verify` on the installed units.

## Package hooks (user layer only)

The privileged layer is fully declarative (manifests above) — there are **no system hooks**.
For user-session steps that can't be expressed as data, a package may ship a small, closed set
of hooks, recognised **by filename** (no manifest). Each must be executable, run as your normal
user (**no `sudo`**), be idempotent, and exit non-zero to abort the operation.

| File in `packages/<name>/` | When it runs |
|---|---|
| `user-activate.hook.sh` | `./run.sh activate <name>`, after system units (only when `STOW_TARGET=HOME`) |
| `user-deactivate.hook.sh` | `./run.sh uninstall <name>`, before files are removed (only when `STOW_TARGET=HOME`) |
| `verify.hook.sh` | `./run.sh verify <name>`, after stow-link verification |

Hooks receive: `GRZ_REPO_ROOT`, `GRZ_PACKAGE`, `STOW_TARGET`. Any other `*.hook.sh` is rejected
by `check-repo`.

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
