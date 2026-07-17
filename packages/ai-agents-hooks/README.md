# ai-agents-hooks

Audio "task done" notifications for CLI coding agents. When an agent finishes, a short sound
loops for a fixed duration while other audio is ducked, and a desktop notification with a
**Stop** action lets you silence it immediately.

## Scripts

| Script | Role |
|---|---|
| `agent-loop-sound` | Engine. `agent-loop-sound <name> <sound.wav> [duration_s]`. Builds a cached looped WAV of `duration` seconds (default 15), plays it with `pw-play`, ducks other PipeWire/Pulse streams via `pactl`, and shows a `notify-send` critical notification with a Stop action. |
| `claude-done-sound` | Thin wrapper → `agent-loop-sound "Claude" ~/.local/share/agent-sounds/claude.wav 15`, launched detached via `setsid`/`nohup`. |
| `codex-done-sound` | Thin wrapper → `agent-loop-sound "Codex" ~/.local/share/agent-sounds/codex.wav 15`. |

## Install

```sh
./run.sh install ai-agents-hooks
```

Installed paths:

```text
~/.local/bin/{agent-loop-sound,claude-done-sound,codex-done-sound}
~/.local/share/agent-sounds/{claude.wav,codex.wav}
```

`~/.local/bin` must be on `PATH`.

## Dependencies

- **PipeWire** (`pw-play`) — required for playback.
- `pactl` — optional; enables ducking of other streams. Without it, playback still works.
- `notify-send` — desktop notification with the Stop action.
- `python3` — WAV loop generation and stream bookkeeping.
- `setsid` (fallback `nohup`) — detach the player from the calling agent.

## Wiring as an agent hook

`claude-done-sound` / `codex-done-sound` are meant to be called by the agent when it finishes
a turn — e.g. from a Claude Code `Stop` hook or a Codex completion hook. That hook
configuration lives in the agent's own settings (outside this repository); this package only
installs the executables and sounds they rely on.

## Environment overrides

`agent-loop-sound` honors:

- `AGENT_SOUND_DURATION_SECONDS` — loop length (overrides the 3rd argument).
- `AGENT_DUCK_PERCENT` — volume other streams are ducked to (default `80`).
- `AGENT_SOUND_VOLUME_PERCENT` — forced volume of the agent sound (default `100`).

## Notes

- The `.wav` files ship with the package so playback works out of the box. Replace them with
  your own audio at the same paths if you prefer different sounds.
- Comments in the scripts are in Polish.
