# ai-agents-hooks

Completion sounds for CLI coding assistants (Claude Code and Codex). The package loops
a WAV through PipeWire, temporarily attenuates other playback in the software mixer,
and shows a desktop notification with a **Stop** action. See `README.md` for details.

## Installed files

- `~/.local/bin/agent-loop-sound` — sound, notification and coordinated ducking engine.
- `~/.local/bin/{claude-done-sound,codex-done-sound}` — detached agent wrappers.
- `~/.local/lib/agent-loop-sounds/ducking.py` — shared temporary mixing coordinator.
- `~/.local/share/agent-sounds/{claude.wav,codex.wav}` — packaged completion sounds.

## Installation

```sh
./run.sh install ai-agents-hooks
```

The source of truth is this package's `install/` tree; `stow/ai-agents-hooks` exposes it
to the ordinary installer. No service or autostart activation is required.

Requires `~/.local/bin` on `PATH`, PipeWire (`pw-play`), `python3`, `notify-send` and
`setsid`. `pw-dump` and `pw-cli` provide optional ducking; `pactl` optionally sets only
the completion sound's own stream volume. Saved application volume sliders are preserved.
