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
| `packages/zsh-tools/install/.zsh_scripts/core/04-completion-paths.zsh` | `~/.zsh_scripts/core/04-completion-paths.zsh` |
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

`04-completion-paths.zsh` defines the shared managed-path list and identity
comparison used by `05-fpath.zsh` and `90-completion_init.zsh`. The three selected
completion directories are:

1. `completion/helpers`
2. `completion/functions`
3. `completion/bin`

Logical absolute paths (`:a`) retain the selected installation spelling;
physical paths (`:A`) identify symlink targets. Identity comparisons cover both
a directory and its digest, symlink aliases to either, and an alias directory's
separate implicit digest. Current/default runtime and legacy completion paths
use the same comparison.

The pre-loader removes all these paths from incoming `fpath` and revokes
initialization helpers already pinned to them. It exposes no managed completion
code before the external owner's initialization. The post-loader audits the
selected directories before adding secure paths to `fpath`. With no owner
ordering, it uses the three-directory order above; an owner's explicit managed
directory order is retained using the selected audited paths. Alias spellings
and explicit digests are not restored. Custom runtimes cannot fall back to
stale default-runtime paths.

`cmdhelp` and its completion use the same runtime root for help topics and
managed function names. Explicit `__CMDHELP_ROOT`/`__CMDHELP_FUNCTIONS_ROOT`
overrides retain precedence, including when completion runs without the help
core module. The binary root remains `~/.local/my-custom-bin`.
The `battery-ac-watch` help fallback also honors `ZSH_TOOLS_ROOT`; its existing
explicit `ZSH_SCRIPTS_ROOT` override retains precedence.

## Initialization contract

The actual rc.d order is pre-loader → external completion owner (if present)
→ post-loader. The pre-loader defers managed-path exposure until the post-loader
has audited it. This prevents both plain directories and digests from supplying
`compinit`, `compaudit`, `compdump` or `compinstall` before checking permissions.
Owner implementations outside either runtime remain available. File-symlink
helper sources are identified by their physical target too.

The post-loader repeats identity filtering for paths inserted after the
pre-loader, loads the four initialization helpers through the remaining trusted `fpath`,
and audits
the managed roots. Both logical installation paths and physical targets are
checked, including their respective parents and digest companions.

1. If `compdef` does not exist, the package runs `compinit -i` on the trusted
   search path to establish standard completion state. Managed paths remain
   hidden throughout initialization, then secure paths are added and their
   metadata is registered by the bounded scan.
2. If `compdef` already exists, the package does **not** run another full
   `compinit`. It adds only audited managed paths and performs the same bounded
   metadata scan. Unrelated directories are not rescanned.

All of compaudit's result forms matter: an insecure root, either parent, or a
directory digest quarantines that root. Insecure files and compiled companions
are associated through their logical and physical identities before scanning
or reconciling loaded state. If the auditor is missing or fails, every managed
root is quarantined. Missing initialization helpers still reach cleanup of
unsafe loaded/cached state before returning an initialization error; a failed
lookup must not abort command processing before quarantine. An unresolved
missing helper receives a harmless definition, so later fpath exposure cannot
redirect its lookup into managed code.

Filtering new registrations alone is insufficient when an owner's dump already
contains mappings. Normal, pattern, post-pattern, service and autoload metadata
referencing insecure functions are cleared. Loaded functions and autoload stubs
are replaced with harmless functions returning non-zero, also preventing
retained widget/helper references from executing them. The inventory includes
aliases defined by insecure source files and loaded functions from quarantined
roots whose source files were deleted. Functions loaded through explicit
directory digests have `root.zwc/function` source paths; these are associated
with the same managed root for quarantine and runtime refresh. File-level
identity also covers aliases loaded directly from symlink targets, including
compiled companions whose target basename differs from the source file. Loaded
functions from non-selected default/legacy roots and unaudited alias-only
digests are revoked even when the selected runtime itself is secure.

Within the secure subset, files are processed in managed-`fpath` order and each
basename is accepted only once, matching `compinit`'s `_i_test` shadowing
behavior. An insecure copy does not claim the basename, so a later secure copy
can still be registered. Each selected function is pinned to its audited file
with an absolute-path autoload, including helpers. An owner's explicit
implementation sourced outside the current/default runtime is preserved, as
are real definitions without a source path (including parameter-assigned or
empty function bodies). Undefined autoload functions are identified using Zsh's
autoload attribute, so an unresolved stub with an empty source still receives
the audited path. Explicit owner-pinned autoloads outside either runtime retain
their source path. This prevents lookup from selecting an earlier insecure file
or a previously pinned default-runtime copy.
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

All configured dump/cache paths must be absolute. A relative `_comp_dumpfile`
from `compinit -d cache.dump` carries no record of the original working directory.
If any active/configured/default path is relative, reload returns non-zero
before deleting any candidate or replacing the shell. The same rule covers
`ZSH_COMPDUMP`, `ZDOTDIR`, `XDG_CACHE_HOME` and HOME-derived paths, so changing
directories cannot redirect cleanup to unrelated files.

Regular dump files and symlinks are removed before restart. One policy covers
explicit paths, their compiled companions, and both legacy globs. Each candidate
is checked independently, including orphaned compiled files. Directories and
non-file sinks such as `/dev/null` or FIFOs are skipped. Dangling symlinks and
symlinks to directories are unlinked without removing their targets.

Dump cleanup is fail-closed: if a selected removable dump file cannot be
removed, the command returns non-zero and does not replace the current shell.

Before cleanup it resolves an executable Zsh from `PATH` using builtin external
command lookup. Functions and aliases named `zsh` cannot intercept replacement,
including a function named after the resolved executable path. A missing or
non-executable interpreter returns an error without deleting dumps or exiting.

After successful cleanup builtin `exec` starts the resolved external Zsh with
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

The regression executes the actual pre/post rc.d loaders with secure and
insecure managed roots in all three directories, default/custom runtimes,
Stow-like symlinks, writable physical/logical parents, helpers already pinned
before the pre-loader and aliases reintroduced afterwards. It also checks
logical/physical file and companion findings, real missing helper providers,
and relative active/configured/ZDOTDIR/XDG paths after changing directories.

The regression covers standalone initialization, bounded registration across
the runtime completion directories, custom `ZSH_TOOLS_ROOT` fpath/autoload
consistency, stale external dumps without a full `fpath` rescan, security
filtering of fresh and cached state (including actual upstream compaudit and
`compinit -C`), insecure parents/digests/compiled files, explicit digests in all
three managed roots with default/custom runtimes and both initialization owners,
deleted functions loaded from digests, basename shadowing and secure duplicate autoload, preservation of normal/pattern/
service overrides and owner implementations with/without source paths, explicit
owner-pinned autoloads, non-file sinks and symlinks in every cleanup path,
dump-removal failure, and all four LOGIN/INTERACTIVE combinations.
`zshreloadcomp` also uses local Zsh emulation so caller array options cannot
change its help dispatch or cleanup behavior; failed help retains its status.

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
| Insecure completion state | Fresh registration, cached dispatch, loaded functions, widgets/helpers, parent and digest results, explicit digest fpath entries, deleted digest-loaded functions, real missing helper providers, failed audits |
| Startup trust boundary | Actual pre/owner/post order, deferred managed fpath exposure, revocation of already pinned initialization helpers |
| Path identity | Logical/physical directories and parents, aliases to directories/digests, alias-only digests, symlinked files/companions and loaded source aliases |
| Autoload shadowing | Insecure earlier files, secure duplicates, reordered managed roots, pinned default-runtime functions, directory/digest source-path equivalence |
| Custom runtime roots | fpath, completion registration, help core defaults, help completion/command fallbacks and explicit help-root overrides |
| Owner overrides | Normal mappings, pattern/post-pattern mappings, command/service aliases, file-backed and source-less implementations, empty definitions versus unresolved autoload stubs, explicit outside-runtime autoload pins |
| Dump cleanup | Active/configured/default paths, HOME/ZDOTDIR globs, independent `.zwc` companions, directories/FIFOs, dangling/directory symlinks, absolute-path preflight for all configuration sources after cd |
| Shell invocation | Login/non-login and interactive/noninteractive, including redirected stdin; external lookup/replacement bypasses functions and aliases; missing/non-executable interpreters retain dumps and the session |
| Tool completion dispatch | PATH-only pnpm lookup despite aliases/functions; first and subsequent autoload candidates with caller KSH_ARRAYS; missing/non-executable providers; empty mise responses retain status 1 and allow later completers |
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
