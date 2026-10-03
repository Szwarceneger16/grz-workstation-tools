# zshreloadcomp

Rebuild Zsh completion state by clearing known completion dump files and replacing
the current shell process with a fresh Zsh instance.

## Usage

```bash
zshreloadcomp
zshreloadcomp [-h|--help]
```

## What it does

The command removes completion dump files that can influence the next shell
startup, including:

- the active `_comp_dumpfile`, when available,
- `ZSH_COMPDUMP`, when configured,
- the default `${ZDOTDIR:-$HOME}/.zcompdump*` files,
- the default XDG cache dump under `${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump`.

Every required removal is fail-closed. If an existing dump cannot be removed,
`zshreloadcomp` returns an error and keeps the current shell instead of
restarting into a state that could reuse the stale dump.

After successful cleanup it replaces the current process with a new Zsh:

- a normal interactive Zsh uses `exec zsh`,
- a login Zsh uses `exec -l zsh` so login-shell startup/logout semantics are
  preserved.

The terminal stays open, but normal shell startup runs again.

## Effect on shell state

This is a **full shell replacement**, not an in-place completion-only reload.

The current directory and exported environment are preserved by `exec`, but
ad-hoc shell-local state that is not recreated by startup files can be lost,
including non-exported variables, temporary functions, aliases, and other
session-only changes.

When invoked from a login shell, the replacement remains a login shell and
therefore continues to use the login-only Zsh startup/shutdown files.

## When to use it

Use `zshreloadcomp` after:

- adding or removing completion files,
- changing `#compdef` mappings,
- changing completion-related `fpath`,
- updating a completion manager and needing to force a clean startup.

## Typical workflow

```bash
zshreloadcomp
```

There is no need to run `source ~/.zshrc` first; the replacement Zsh process
loads the configured startup files itself.
