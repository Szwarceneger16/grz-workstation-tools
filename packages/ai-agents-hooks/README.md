# ai-agents-hooks

Audio "task done" notifications for CLI coding agents. When an agent finishes, a short sound
loops for a fixed duration while other audio is ducked, and a desktop notification with a
**Stop** action lets you silence it immediately.

## Scripts

| Script | Role |
|---|---|
| `agent-loop-sound` | Engine. `agent-loop-sound <name> <sound.wav> [duration_s]`. Builds a cached looped WAV of `duration` seconds (default 15), plays it with `pw-play`, coordinates temporary software ducking through PipeWire, and shows a `notify-send` critical notification with a Stop action. |
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
~/.local/lib/agent-loop-sounds/ducking.py
```

`~/.local/bin` must be on `PATH`.

## Dependencies

- **PipeWire** (`pw-play`) — required for playback.
- `pw-dump` and `pw-cli` — optional; enable temporary PipeWire software ducking.
- `pactl` — optional; sets only the completion sound's own stream volume.
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
- `AGENT_DUCK_PERCENT` — relative ducking level (default `80`, clamped to `1..100`).
- `AGENT_SOUND_VOLUME_PERCENT` — forced volume of the agent sound (default `100`).

## Coordinated ducking

All completion sounds share a private `coordination.lock` and `coordination.json` in
`$XDG_RUNTIME_DIR/agent-loop-sounds`. Each invocation registers its parent/player process
identities. Overlapping signals use the strongest requested ducking level once; ending
one signal keeps attenuation active until the last signal ends. No filename matching is
used to identify signal streams: they carry the `agent-loop-sound` application name and
`Notification` media role. Their own volume is set by a unique invocation tag or exact
player PID; native streams may omit the PID from the Pulse-compatible view. Signal streams
disable saved-property restoration to avoid inheriting or changing notification-role volume.

Ducking changes only PipeWire `softVolumes` and `softMute`. The application slider and
saved `channelVolumes` stay untouched. A recreated Firefox stream therefore starts from
its real saved level, including when no Firefox stream exists at the end of a signal.
The helper picks up new streams, slider changes and mute changes every 200 ms. It restores
the latest channel values rather than an old snapshot. The effective ducking corresponds
to the former Pulse percentage; the temporary linear mixing factor is `(percent/100)^3`.

The helper checks the PipeWire server generation and object serial before mutations,
and preserves a competing software mixer's observed changes. Intent is saved before a
write. SIGTERM, Stop, normal completion and a dead parent/player release the invocation;
a later invocation can recover journaled temporary mixing after a helper crash. A complete
SIGKILL of all related processes cannot run immediate cleanup; the next invocation recovers
that state. A restarted server invalidates the old node identities. Command failures keep
pending recovery in the journal. Without the PipeWire tools, playback and notifications
continue without ducking; there is no fallback that changes application sliders.

The source is `packages/ai-agents-hooks/install/.local/bin/agent-loop-sound`; its helper is
installed from `packages/ai-agents-hooks/install/.local/lib/agent-loop-sounds/ducking.py`.
Existing Stow symlinks use updated source immediately. Ordinary installation still uses
`./run.sh install ai-agents-hooks`; no new service or autostart is required. To roll back,
restore both source files to the previous revision after currently playing signals finish.

## Validation

The regression suite uses fake audio and notification tools; it never connects to live audio:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_agent_loop_sound.py' -v
bash -n packages/ai-agents-hooks/install/.local/bin/agent-loop-sound
shellcheck packages/ai-agents-hooks/install/.local/bin/agent-loop-sound
./scripts/check-repo
```

A live acceptance check uses overlapping completion signals while switching songs and
changing the application slider. The slider must retain the user's setting throughout;
audio is temporarily attenuated once and returns when the last signal stops.

## Notes

- The `.wav` files ship with the package so playback works out of the box. Replace them with
  your own audio at the same paths if you prefer different sounds.
- Comments in the scripts are in Polish.
