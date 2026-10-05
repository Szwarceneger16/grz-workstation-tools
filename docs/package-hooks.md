# User-package lifecycle hooks

Hooks are executable regular files at the package root. They perform user-level
lifecycle work that declarative manifests and Stow cannot express. The system
layer stays declarative: hooks never receive implicit privilege or service
activation authority.

| Hook | Execution point |
| --- | --- |
| `install.hook.sh` | After ordinary Stow installation. |
| `uninstall.hook.sh` | After successful deactivation of selected user units, before system-file and Stow removal. |
| `verify.hook.sh` | After ordinary installed-file and user-unit verification. |

The runner passes `<PREFIX>_REPO_ROOT`, `<PREFIX>_PACKAGE`, `STOW_TARGET` and
`<PREFIX>_VERBOSE`. `PREFIX` is the repository's configured `RUNNER_ENV_PREFIX`,
not a hardcoded toolkit identity. Verbose is `0` or `1`. Paths may contain spaces.
Hooks must be idempotent, avoid privileged commands, and return nonzero on failure.
Verification hooks must remain read-only.

## Ordinary uninstall

For `uninstall PACKAGE`, `all-user` or `all`, the runner first validates every
selected user package, including hook placement, executable mode and manifests.
The existing selection and `all` exclusions apply. It then deactivates selected
user units, runs uninstall hooks in selection order, removes selected system
files, and removes Stow links. A named mixed user/system package runs its user
hook before either layer is removed.

A preflight failure prevents all deactivation, hooks and removal. A deactivation
failure prevents hooks and file removal, although earlier units may already be
stopped. A hook failure prevents later hooks and both removal stages. Units
already deactivated remain stopped; successful earlier hook actions also remain.
There is no automatic reactivation or rollback of package hook work. Inspect the
failure, fix its cause, then retry only when appropriate for the package.

Keep cleanup ownership-aware: do not remove a pre-existing or replaced user
object merely because its name or bytes match a package source. Package-specific
ownership records and recovery are the hook author's responsibility. Hook source
files remain available until the runner reaches the removal stages.

`all-system` selects no user packages and runs no user hooks. `--orphaned`
requires a missing user source tree and cleans only its bounded remnants; it
never executes package hooks. Packages without an uninstall hook retain their
ordinary uninstall behavior.

## Validation

Use static package validation and isolated regression fixtures:

```sh
./scripts/check-repo
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_runner_uninstall_hooks.py' -v
```

The fixtures use disposable package/target directories, real validation and
hook processes, and substituted service/system-copy/Stow operations. They do
not activate units or uninstall files on the live workstation. Running the
ordinary uninstall CLI outside those fixtures is a separate live action.

This document is repository-local guidance, not an additional canonical export.
