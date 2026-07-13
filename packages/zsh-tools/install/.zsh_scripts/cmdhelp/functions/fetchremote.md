# fetchremote

`fetchremote` — pobiera branch z `origin`, tworząc albo aktualizując lokalny branch o tej samej nazwie.

Uruchamia:

```bash
git fetch origin <branch>:<branch>
```

## Użycie

```bash
fetchremote <branch>
fetchremote [-h|--help]
```

## Opcje

- `<branch>` — nazwa brancha do pobrania z `origin`
- `-h`, `--help` — pokaż pomoc

## Co robi

Używane przez `gwfr` jako pierwszy krok (pobranie brancha), przed `gwadd`.

## Efekt końcowy

Masz lokalny branch o tej samej nazwie, gotowy do `gwadd`/`checkout`/`worktree`.

## Przykłady

```bash
fetchremote feature/foo
fetchremote --help
```
