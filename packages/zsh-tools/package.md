# zsh-tools package

Owns public Zsh runtime files.

## Completion ownership

`core/05-fpath.zsh` exposes this package's completion directories and records
whether Zsh completion had already been initialized before those paths were
added. `core/90-completion_init.zsh` then calls `compinit` only when no
completion owner exists yet, or when the package paths were added after an
already-completed `compinit` and need one rescan.

This keeps the package standalone while avoiding an unconditional second
`compinit` when another completion manager initializes after the public fpath
is already available.

`zshreloadcomp` clears the configured/default completion dump files and
replaces the current shell with a fresh Zsh process. It deliberately does not
source `~/.zshrc` or invoke `compinit` directly in the existing process.

Run the package regression test with:

```sh
./run.sh test zsh-tools
```
