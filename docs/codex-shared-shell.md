# Opt-in shared Codex App Server shell environment

The `zsh-tools` package installs two shell fragments:

- `~/.config/profile.d/90-codex-shared.sh` for login shells.
- `~/.config/zsh/rc.d/90-codex-shared.zsh` for interactive Zsh.

The existing managed loaders in `~/.profile` and `~/.zshrc` source them.
The Zsh fragment reuses the profile fragment. Neither loader is rewritten.
Both fragments are inert unless the workstation has the following readable
local opt-in file at `~/.config/environment.d/90-codex-shared.conf`:

```ini
CODEX_APP_SERVER_WS_URL=ws+unix://localhost${HOME}/.codex/app-server-control/app-server-control.sock:/rpc
CODEX_APP_SERVER_FORCE_CLI=0
```

The profile fragment reads only these two literal assignments (including an
absolute URL using the current home directory, or the `$HOME` / `${HOME}`
forms shown above). It does not source or evaluate the environment.d file.
Other assignments are ignored. The last assignment for each supported key
is used. Unrecognized values leave the inherited environment unchanged.
The local file is not owned by this package.

## Install and migrate

```sh
./run.sh install --verify zsh-tools
```

Before installation, inspect any existing unmanaged files at the two
fragment paths. If present, back them up and move them out of the loader
directories to allow Stow to create its links. Do not use `--adopt` blindly.
After installation, remove only the old hand-added `CODEX SHARED BACKEND`
block from `~/.profile` and (if present) `~/.zshenv`, after taking backups
and reviewing the diff. Retain any necessary graphical-session integration
until a fresh desktop login has been verified.

```sh
zsh -ic 'printenv CODEX_APP_SERVER_WS_URL CODEX_APP_SERVER_FORCE_CLI'
python3 -m unittest discover -s tests -p 'test_runner_zsh_tools_codex_shared.py' -v
```

## Scope and limitations

This change only propagates the opt-in environment for the ChatGPT desktop
client. It does not start or manage the App Server, modify package launchers,
enforce the CLI transport, change VS Code, alter SSH or enable network
listeners. It does not guarantee that all desktop clients will honor an
experimental environment override. Existing processes keep their previous
environment; start a fresh shell or desktop session to pick up changes.
Keep host-specific service and fail-closed launcher configuration separate
until those mechanisms are validated. No systemd activation is required
by these fragments.
