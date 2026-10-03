# Zsh completion lifecycle

## Scope

Package: `zsh-tools`

This document describes how the public Zsh runtime exposes its completion
directories, initializes completion when used standalone, cooperates with an
already-present completion owner, and forces a clean completion rebuild through
`zshreloadcomp`.

## Installed paths

The relevant source files are installed through GNU Stow at:

| Repository source | Installed target |
|---|---|
| `packages/zsh-tools/install/.zsh_scripts/core/05-fpath.zsh` | `~/.zsh_scripts/core/05-fpath.zsh` |
| `packages/zsh-tools/install/.zsh_scripts/core/90-completion_init.zsh` | `~/.zsh_scripts/core/90-completion_init.zsh` |
| `packages/zsh-tools/install/.zsh_scripts/functions/zshreloadcomp.zsh` | `~/.zsh_scripts/functions/zshreloadcomp.zsh` |
| `packages/zsh-tools/install/.zsh_scripts/completion/functions/_zshreloadcomp` | `~/.zsh_scripts/completion/functions/_zshreloadcomp` |

## Initialization contract

`05-fpath.zsh` exposes the public runtime completion directories before
`90-completion_init.zsh` decides how to register them.

The behavior is:

1. If `compdef` does not exist, no standard Zsh completion owner is available
   yet. The package runs `compinit -i`, keeping `grz-workstation-tools`
   usable standalone.
2. If `compdef` already exists, the package does **not** run another full
   `compinit`. Instead it performs a bounded metadata scan of
   `${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}/completion/functions` and registers
   only the `#compdef` declarations found there.

The bounded registration mirrors `compinit`'s `#compdef` handling, including
`compdef -n`, so an existing user or completion-manager mapping is not
overwritten.

This design handles a manager that loads a stale `compinit -C` dump without
performing a full security check and traversal of every directory in `fpath`
on each startup. Current runtime `#compdef` declarations are registered
directly even when an external dump remains stale, and unrelated `fpath`
directories are not rescanned.

## zshreloadcomp

`zshreloadcomp` is intentionally stronger than an in-place `compinit`
refresh.

It removes:

- the active `_comp_dumpfile`, when known,
- `ZSH_COMPDUMP`, when configured,
- default `.zcompdump*` files under `${ZDOTDIR:-$HOME}`,
- legacy `.zcompdump*` files under `$HOME`,
- the default XDG cache dump.

Dump cleanup is fail-closed: if a selected dump exists but cannot be removed,
the command returns non-zero and does not replace the current shell.

After successful cleanup it replaces the current shell. A normal shell uses
`exec zsh`; a login shell uses `exec -l zsh`, preserving the Zsh `LOGIN`
mode and its login-only startup/logout file semantics.

Because the shell process is replaced, non-exported session-only state is not
guaranteed to survive. See `cmdhelp zshreloadcomp` for the user-facing behavior.

## Validation

The package regression test is discoverable through the normal package test
runner:

```bash
./run.sh test zsh-tools
```

It can also be run directly from a repository checkout:

```bash
GRZ_REPO_ROOT="$PWD" packages/zsh-tools/tests/completion-init.sh
```

The regression covers standalone initialization, bounded registration with an
existing completion owner, recovery from a stale external dump without a full
`fpath` rescan, dump-removal failure, and login-shell preservation.

The PR intentionally does not modify `.github/workflows/`; repository policy
requires workflow changes to be isolated in a dedicated CI/workflow PR.

## Activation

There is no separate activation command or systemd unit for this behavior.
After the package is installed, the rc.d loader applies the completion lifecycle
during the next Zsh startup. Installing the package itself is a live user-layer
change and is performed explicitly with:

```bash
./run.sh install zsh-tools
```
