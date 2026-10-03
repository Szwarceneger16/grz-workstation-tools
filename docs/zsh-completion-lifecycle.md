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

`05-fpath.zsh` exposes the public completion directories before
`90-completion_init.zsh` decides whether any initialization work is required.

`90-completion_init.zsh` uses the public `zshreloadcomp` completion mapping as
a sentinel:

```text
_comps[zshreloadcomp] == _zshreloadcomp
```

The behavior is:

1. If `compdef` does not exist, no completion owner has initialized standard
   Zsh completion yet. The package runs `compinit -i` so that
   `grz-workstation-tools` remains usable standalone.
2. If `compdef` exists and the sentinel mapping is present, the package does
   not run another `compinit`.
3. If `compdef` exists but the sentinel mapping is missing, the loaded
   completion state did not include this package. The package runs
   `compinit -D -i`.

The `-D` path deliberately performs a full in-memory scan without reading or
writing a completion dump. This repairs the current session while leaving the
other completion owner's dump lifecycle alone. It also handles the case where a
later owner used `compinit -C` with a dump created before the zsh-tools
completion directory existed.

## zshreloadcomp

`zshreloadcomp` is intentionally stronger than an in-place `compinit`
refresh.

It removes:

- the active `_comp_dumpfile`, when known,
- `ZSH_COMPDUMP`, when configured,
- default `.zcompdump*` files under `${ZDOTDIR:-$HOME}`,
- legacy `.zcompdump*` files under `$HOME`,
- the default XDG cache dump.

It then replaces the current shell with `exec zsh`. This reruns normal shell
startup in a clean process and avoids sourcing the complete shell configuration
again inside an already-initialized Zsh process.

Because the shell process is replaced, non-exported session-only state is not
guaranteed to survive. See `cmdhelp zshreloadcomp` for the user-facing behavior.

## Validation

The package regression test is:

```bash
./run.sh test zsh-tools
```

The isolated test can also be run directly from the repository checkout:

```bash
GRZ_REPO_ROOT="$PWD" packages/zsh-tools/tests/completion-init.sh
```

The repository CI runs the isolated regression test after installing Zsh.

## Activation

There is no separate activation command or systemd unit for this behavior.
After the package is installed, the rc.d loader applies the completion lifecycle
during the next Zsh startup. Installing the package itself is a live user-layer
change and is performed explicitly with:

```bash
./run.sh install zsh-tools
```
