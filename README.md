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
./run.sh activate  [--config PATH] all|all-user|all-system|<package>
./run.sh verify    all|all-user|all-system|<package>
./run.sh test      all|all-user|all-system|<package>
```

- `all` — all packages not in `manifests/ignore-all-install.txt`
- `all-user` — user (stow) packages only
- `all-system` — system packages only (require `sudo`)
- `<package>` — single named package

Override install target: `GRZ_STOW_TARGET=/path ./run.sh install all`

## Adding a package

1. Create `packages/<name>/install/` with files mirroring their `$HOME` paths.
2. Create a symlink: `ln -s ../packages/<name>/install stow/<name>`
3. Run `./run.sh install <name>`

## Package hooks

Each package may provide optional hook scripts (must be executable):

| File | When called |
|---|---|
| `packages/<name>/user-activate.sh` | `./run.sh activate <name>` |
| `packages/<name>/user-deactivate.sh` | `./run.sh uninstall <name>` |
| `packages/<name>/verify-installed.sh` | `./run.sh verify <name>` |
| `packages/<name>/system-activate.sh` | `./run.sh activate <name>` (system layer, runs under an active sudo session) |
| `packages/<name>/system-deactivate.sh` | `./run.sh uninstall <name>` (system layer) |
| `packages/<name>/system-verify.sh` | `./run.sh verify <name>` (system layer) |

Hooks receive: `GRZ_REPO_ROOT`, `GRZ_PACKAGE`, `STOW_TARGET`.
The system-activate hook also receives `GRZ_CONFIG_SOURCE` (the value of `./run.sh activate --config PATH`, empty if not given).

## Excluding packages from `all`

Add the package name to `manifests/ignore-all-install.txt` (one per line).

## Bootstrap

Copy the relevant snippet from `bootstrap/` into your `~/.zshrc` / `~/.profile` to load rc fragments from `~/.config/zsh/rc.d/`.
