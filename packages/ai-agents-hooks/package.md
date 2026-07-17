# ai-agents-hooks

Dźwiękowe powiadomienia "agent skończył zadanie" dla asystentów CLI (Claude Code, Codex).
Odtwarzają zapętlony dźwięk przez PipeWire, przyciszają (ducking) pozostałe strumienie audio
na czas grania i pokazują powiadomienie `notify-send` z akcją **Stop**. Pełny opis: `README.md`.

## Zawartość

- `agent-loop-sound` — silnik: buduje zapętlony WAV o zadanej długości, gra go przez `pw-play`,
  duckuje inne strumienie przez `pactl`, wyświetla `notify-send` z akcją Stop.
- `claude-done-sound` — wrapper: `agent-loop-sound "Claude" ~/.local/share/agent-sounds/claude.wav 15`.
- `codex-done-sound` — wrapper: `agent-loop-sound "Codex" ~/.local/share/agent-sounds/codex.wav 15`.

## Ścieżki po instalacji (stow)

```text
~/.local/bin/agent-loop-sound
~/.local/bin/claude-done-sound
~/.local/bin/codex-done-sound
~/.local/share/agent-sounds/claude.wav
~/.local/share/agent-sounds/codex.wav
```

## Instalacja

```sh
./run.sh install ai-agents-hooks
```

Wymaga `~/.local/bin` na `PATH`. Runtime: PipeWire (`pw-play`), `pactl` (opcjonalny ducking),
`notify-send`, `python3`, `setsid`.
