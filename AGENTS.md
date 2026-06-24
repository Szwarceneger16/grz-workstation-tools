# AGENTS.md

## Repository purpose

This is a public Zsh toolkit repository. It provides a Zsh runtime (functions, completions, aliases, rc fragments) installed via GNU Stow.

The repository does not own `~/.zshrc` or `~/.profile`. It owns only the files placed under `packages/*/install/`.

## Core rule

Do not make live-system changes from this repository unless the user explicitly asks for that exact action.

By default, work only inside the normal repository checkout.

## Safety rules

- Do not use `sudo`.
- Do not install, remove, or reconfigure system packages.
- Do not run `apt`, `dpkg`, `flatpak`, `snap`, or other package-manager commands.
- Do not run `systemctl --user daemon-reload`, `restart`, `start`, `stop`, `enable`, `disable`, `mask`, or `unmask` unless explicitly requested.
- Do not modify files outside this repository unless explicitly requested.
- Do not edit live files under `$HOME` directly.
- Do not assume files in this repo are safe to execute.
- Prefer static analysis, diffs, and syntax checks over execution.
- If a command may affect the live shell, autostart, or files in `$HOME`, explain it rather than running it.

## Sensitive data rules

Before committing or proposing changes, check for accidental secrets without printing secret values.

Look for, and do not introduce:

- private keys, API tokens, passwords, cookies
- `.env` files, SSH keys, machine-specific credentials
- browser/profile data, auth headers, personal access tokens

Useful read-only check:

```bash
./scripts/audit-public-safety
```

Or manually:

```bash
find . -path ./.git -prune -o -type f -print0 |
  xargs -0 grep -IlE 'password|passwd|secret|token|api[_-]?key|private key|BEGIN .*PRIVATE KEY|Authorization:|Bearer ' || true
```

Report only file path and category of concern — never print matching values.

## Repository layout

```text
packages/<package>/install/         # source of truth for user (stow) files
packages/<package>/system-install/  # source of truth for system files (sudo)
stow/<package>                      # symlink -> ../packages/<package>/install
manifests/ignore-all-install.txt    # packages excluded from `all`
manifests/protected-system-paths.txt # paths a system manifest may never manage
scripts/                            # repository helper scripts
docs/                               # explanations, design notes
bootstrap/                          # ~/.zshrc / ~/.profile snippets for users
```

File path mapping:

```text
packages/<package>/install/.zsh_scripts/            -> ~/.zsh_scripts
packages/<package>/install/.local/bin/              -> ~/.local/bin
packages/<package>/install/.local/my-custom-bin/    -> ~/.local/my-custom-bin
packages/<package>/install/.config/zsh/rc.d/        -> ~/.config/zsh/rc.d
packages/<package>/install/.config/systemd/user/    -> ~/.config/systemd/user
```

When creating a new package:

```bash
mkdir -p packages/<package>/install
ln -s ../packages/<package>/install stow/<package>
```

## Package/stow install rules

These commands modify live files in `$HOME`. Do not run them unless the user explicitly requests the live action:

```bash
./run.sh install all
./run.sh install <package>
./run.sh uninstall all
./run.sh uninstall <package>
./run.sh activate all
./run.sh activate <package>
```

Package structure rules:
- `packages/<package>/install` is the source of truth.
- `stow/<package>` must point to `../packages/<package>/install`.
- `all` selects all packages under `stow/`, except names listed in `manifests/ignore-all-install.txt`.

## Package hook rules

Packages may provide optional executable hook scripts:

| Hook | Trigger |
|---|---|
| `packages/<pkg>/user-activate.sh` | `./run.sh activate <pkg>` |
| `packages/<pkg>/user-deactivate.sh` | `./run.sh uninstall <pkg>` |
| `packages/<pkg>/verify-installed.sh` | `./run.sh verify <pkg>` |
| `packages/<pkg>/system-activate.sh` | `./run.sh activate <pkg>` (system layer, sudo) |
| `packages/<pkg>/system-deactivate.sh` | `./run.sh uninstall <pkg>` (system layer) |
| `packages/<pkg>/system-verify.sh` | `./run.sh verify <pkg>` (system layer) |

Hooks receive environment variables: `GRZ_REPO_ROOT`, `GRZ_PACKAGE`, `STOW_TARGET`.
The system-activate hook also receives `GRZ_CONFIG_SOURCE` (from `./run.sh activate --config PATH`).

System hooks run under an already-active sudo session and may call `sudo`. Per-package
systemd activation, config installation, and service teardown belong in these hooks — do not
hardcode package-specific behavior into `scripts/system-copy-select`.

Do not run these hooks directly to inspect them — prefer reading them.

## Shell script rules

For all scripts under `packages/`, `scripts/`:

- Use `#!/usr/bin/env bash` for Bash scripts unless there is a reason not to.
- Use `set -euo pipefail` for new Bash scripts.
- Quote variables. Avoid unsafe globbing.
- Avoid hidden dependencies on the current working directory.
- Prefer clear error messages.
- Do not run scripts just to understand them — prefer syntax checks.

```bash
bash -n path/to/script
shellcheck path/to/script
zsh -n path/to/file
```

## Zsh rules

- Do not rewrite Zsh-specific files as Bash unless requested.
- Preserve Zsh syntax.
- Be careful with PATH manipulation, aliases, functions, completions, and shell startup behavior.
- Do not introduce heavy work or network calls on shell startup.

## systemd user unit rules

For files under `packages/<package>/install/.config/systemd/user/`:

- Do not reload or restart user services unless explicitly requested.
- Preserve unit names and dependencies unless that is the task.
- Prefer absolute installed paths in `ExecStart`.
- Separate validation from activation.

```bash
systemd-analyze --user verify path/to/unit.service
```

Activation commands must be shown to the user, not run automatically.

## Git workflow

Before editing, inspect current state:

```bash
git status --short --branch
git diff --stat
```

After editing:

```bash
git diff --stat
git diff
git diff --check
```

Do not claim a change is safe without looking at the diff.

## Documentation rules

When behavior is non-obvious, add or update documentation under `docs/`.

Document: what the file does, package name, target installed path, validation command, activation command (if any).

## Validation checklist

```bash
# Repo state
git status --short --branch
git diff --stat
git diff --check

# Shell scripts
bash -n path/to/script
zsh -n path/to/file
shellcheck path/to/script

# Secrets
./scripts/audit-public-safety

# systemd
systemd-analyze --user verify path/to/unit
```

## Response style

- Answer in Polish unless the user asks otherwise.
- Be direct and concrete.
- Prefer short command blocks over long explanations.
- Distinguish facts, assumptions, and unverified risks.
- If only static checks were run, say so.
- If a live activation step is needed, provide it as a manual command for the user to run.

## Forbidden default actions

Unless the user explicitly requests them, do not:

- modify live `$HOME` files
- run `sudo`
- reload or restart systemd services
- enable or disable services/timers
- install dependencies
- run arbitrary scripts from this repo without syntax-checking first
- run `./run.sh install`, `./run.sh uninstall`, or `./run.sh activate`
- introduce network calls into shell startup behavior
