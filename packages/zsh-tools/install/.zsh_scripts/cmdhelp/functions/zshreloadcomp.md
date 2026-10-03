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

It then runs:

```bash
exec zsh
```

The terminal stays open, but the current Zsh process is replaced and normal
shell startup runs again.

## Effect on shell state

This is a **full shell replacement**, not an in-place completion-only reload.

The current directory and exported environment are preserved by `exec`, but
ad-hoc shell-local state that is not recreated by startup files can be lost,
including non-exported variables, temporary functions, aliases, and other
session-only changes.

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
