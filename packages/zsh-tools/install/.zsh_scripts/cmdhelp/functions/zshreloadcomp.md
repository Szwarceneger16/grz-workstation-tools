# zshreloadcomp

Rebuild Zsh completion state by clearing known completion dump files and replacing
the current shell process with a fresh Zsh instance.

## Usage

```bash
zshreloadcomp
zshreloadcomp [-h|--help]
```

## What it does

The command removes regular completion dump files that can influence the next
shell startup, including:

- the active `_comp_dumpfile`, when available,
- `ZSH_COMPDUMP`, when configured,
- the default `${ZDOTDIR:-$HOME}/.zcompdump*` files,
- legacy `$HOME/.zcompdump*` files when `ZDOTDIR` differs,
- the default XDG cache dump under `${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump`.

Dump and cache paths must be absolute. If an active/configured/default path is
relative, the command returns an error before removing any files or restarting.
In particular, `compinit -d cache.dump` does not record its original directory;
use an absolute dump path when configuring completion. This also applies to
`ZSH_COMPDUMP`, `ZDOTDIR` and `XDG_CACHE_HOME`.

Directories and non-file dump sinks such as `/dev/null` or FIFOs are skipped
in every location, including compiled `.zwc` companions. Symlinks are unlinked
without removing their targets; dangling symlinks are removed too.

Every required file removal is fail-closed. If an existing dump file cannot be
removed, `zshreloadcomp` returns an error and keeps the current shell instead
of restarting into a state that could reuse the stale dump.

Before removing dumps, the command finds an executable Zsh in `PATH`. It bypasses
shell functions and aliases named `zsh`. If the interpreter is unavailable, it
returns an error and leaves both the dumps and the current session intact.

After successful cleanup it replaces the current process with that external Zsh:

- an interactive Zsh receives `-i`, including when stdin is redirected,
- a login Zsh additionally receives `-l` so login-shell startup/logout semantics
  are preserved,
- a noninteractive Zsh receives `+i` and stays noninteractive.

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
