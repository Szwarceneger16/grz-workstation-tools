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
| `packages/zsh-tools/install/.zsh_scripts/core/11-cmdhelp.zsh` | `~/.zsh_scripts/core/11-cmdhelp.zsh` |
| `packages/zsh-tools/install/.zsh_scripts/completion/functions/_cmdhelp` | `~/.zsh_scripts/completion/functions/_cmdhelp` |
| `packages/zsh-tools/install/.zsh_scripts/functions/battery-ac-watch.zsh` | `~/.zsh_scripts/functions/battery-ac-watch.zsh` |
| `packages/zsh-tools/install/.zsh_scripts/functions/zshreloadcomp.zsh` | `~/.zsh_scripts/functions/zshreloadcomp.zsh` |
| `packages/zsh-tools/install/.zsh_scripts/completion/functions/_zshreloadcomp` | `~/.zsh_scripts/completion/functions/_zshreloadcomp` |

## Runtime root and fpath

The runtime root is:

```text
${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}
```

`05-fpath.zsh` and `90-completion_init.zsh` use that same root. The three
managed completion directories are normalized to absolute paths and prepended
to `fpath` in this order:

1. `completion/helpers`
2. `completion/functions`
3. `completion/bin`

If `ZSH_TOOLS_ROOT` points outside the default `$HOME/.zsh_scripts`,
`05-fpath.zsh` also removes pre-existing default zsh-tools completion paths
from `fpath`. This prevents a registered function from a custom runtime from
being autoloaded from a stale or mismatched default-runtime copy.

`cmdhelp` and its completion use the same runtime root for help topics and
managed function names. Explicit `__CMDHELP_ROOT`/`__CMDHELP_FUNCTIONS_ROOT`
overrides retain precedence, including when completion runs without the help
core module. The binary root remains `~/.local/my-custom-bin`.
The `battery-ac-watch` help fallback also honors `ZSH_TOOLS_ROOT`; its existing
explicit `ZSH_SCRIPTS_ROOT` override retains precedence.

## Initialization contract

`05-fpath.zsh` exposes the public runtime completion directories before
`90-completion_init.zsh` decides how to register them.

The behavior is:

1. If `compdef` does not exist, no standard Zsh completion owner is available
   yet. The package resolves initialization helpers outside the managed roots,
   audits those roots, and runs `compinit -i`, keeping `grz-workstation-tools`
   usable standalone. Cached managed mappings are reconciled afterwards too.
2. If `compdef` already exists, the package does **not** run another full
   `compinit`. Instead it performs a bounded metadata scan of the same three
   runtime directories exposed by `05-fpath.zsh`.

Before registration, the managed roots are passed to `compaudit`. The audit's
autoload search excludes those roots. All of compaudit's result forms matter:
an insecure root, its parent directory, or its directory digest (`root.zwc`)
removes that managed root from live `fpath`. Insecure files and their `.zwc`
companions are skipped. If the audit cannot run, all managed roots are
quarantined instead of restoring their unchecked paths.

Filtering new registrations alone is insufficient when an owner's dump already
contains mappings. Normal, pattern, post-pattern, service and autoload metadata
referencing insecure functions are cleared. Loaded functions and autoload stubs
are replaced with harmless functions returning non-zero, also preventing
retained widget/helper references from executing them. The inventory includes
aliases defined by insecure source files and loaded functions from quarantined
roots whose source files were deleted.

Within the secure subset, files are processed in managed-`fpath` order and each
basename is accepted only once, matching `compinit`'s `_i_test` shadowing
behavior. An insecure copy does not claim the basename, so a later secure copy
can still be registered. Each selected function is pinned to its audited file
with an absolute-path autoload, including helpers. An owner's explicit
implementation sourced outside the current/default runtime is preserved.
This prevents lookup from
selecting an earlier insecure file or a previously pinned default-runtime copy.
Only `#compdef` declarations add command mappings. The current managed-root
order in `fpath` determines which secure duplicate wins.

The bounded registration uses `compdef -n` and restores pre-existing safe
owner mappings after registration. The explicit restoration also protects
pattern and `command=service` mappings, which `compdef -n` alone does not fully
preserve. Security filtering takes precedence over preserving an override.

This design handles a manager that loads a stale `compinit -C` dump without
performing a full security check and traversal of every directory in `fpath`
on each startup. Current runtime `#compdef` declarations are registered
directly even when an external dump remains stale, while unrelated `fpath`
directories are not rescanned.

## zshreloadcomp

`zshreloadcomp` is intentionally stronger than an in-place `compinit` refresh.

It considers:

- the active `_comp_dumpfile`, when known,
- `ZSH_COMPDUMP`, when configured,
- default `.zcompdump*` files under `${ZDOTDIR:-$HOME}`,
- legacy `.zcompdump*` files under `$HOME`,
- the default XDG cache dump.

Regular dump files and symlinks are removed before restart. One policy covers
explicit paths, their compiled companions, and both legacy globs. Each candidate
is checked independently, including orphaned compiled files. Directories and
non-file sinks such as `/dev/null` or FIFOs are skipped. Dangling symlinks and
symlinks to directories are unlinked without removing their targets.

Dump cleanup is fail-closed: if a selected removable dump file cannot be
removed, the command returns non-zero and does not replace the current shell.

After successful cleanup it replaces the current shell with `exec zsh` and
explicit invocation flags. `-l` preserves login mode, `-i` preserves interactive
mode even with redirected stdin, and `+i` keeps noninteractive shells
noninteractive even with a terminal on stdin. Login and interactive modes are
independent and can be combined.

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

The regression covers standalone initialization, bounded registration across
the runtime completion directories, custom `ZSH_TOOLS_ROOT` fpath/autoload
consistency, stale external dumps without a full `fpath` rescan, security
filtering of fresh and cached state (including actual upstream compaudit and
`compinit -C`), insecure parents/digests/compiled files, deleted loaded functions,
basename shadowing and secure duplicate autoload, preservation of normal/pattern/
service overrides, non-file sinks and symlinks in every cleanup path,
dump-removal failure, and all four LOGIN/INTERACTIVE combinations.

`tests/test_runner_zsh_completion.py` exercises `./run.sh test zsh-tools` against
a temporary installation fixture. It proves the shell regression is discovered
and executed, and connects it to the existing repository CI unittest discovery
without changing any workflow or requiring installation on the real workstation.
It also syntax-checks every runtime and completion file, covering both the
initialization module's glob error and the stray case terminator in `_pnpmls`.

```bash
python3 -m unittest discover -s tests -p 'test_runner_zsh_completion.py' -v
```

## Review audit coverage

The follow-up audit checked every completion initialization, fpath setup,
dump-removal and shell-replacement occurrence in this repository, including the
pre/post rc.d loaders. These related cases were fixed together:

| Problem family | Related variants covered |
|---|---|
| Insecure completion state | Fresh registration, cached dispatch, loaded functions, widgets/helpers, parent and digest results, failed audits |
| Autoload shadowing | Insecure earlier files, secure duplicates, reordered managed roots, pinned default-runtime functions |
| Custom runtime roots | fpath, completion registration, help core defaults, help completion/command fallbacks and explicit help-root overrides |
| Owner overrides | Normal mappings, pattern/post-pattern mappings, command/service aliases |
| Dump cleanup | Active/configured/default paths, HOME/ZDOTDIR globs, independent `.zwc` companions, directories/FIFOs, dangling/directory symlinks |
| Shell invocation | Login/non-login and interactive/noninteractive, including redirected stdin |
| Executable regression coverage | Glob and `_pnpmls` syntax errors, all runtime/completion syntax, a test-local variable shadowing Zsh's special `functions` parameter, actual package-runner discovery in CI |

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
