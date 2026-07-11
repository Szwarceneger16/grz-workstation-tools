# gwta

`gwta` — dodaje worktree pod podaną ścieżką; nazwa brancha jest wyliczana z ostatniego segmentu ścieżki.

## Użycie

```bash
gwta <ścieżka>
gwta [-h|--help]
```

## Opcje

- `<ścieżka>` — docelowa ścieżka worktree (branch = nazwa ostatniego segmentu)
- `-h`, `--help` — pokaż pomoc

## Co robi

- jeśli lokalny branch o tej nazwie istnieje: `git worktree add <ścieżka> <branch>`
- inaczej, jeśli istnieje `origin/<branch>`: `git worktree add <ścieżka> -b <branch> origin/<branch>`
- inaczej: `git worktree add <ścieżka> -b <branch>` (nowy branch)

Używane przez `gwadd`.

## Efekt końcowy

Nowy worktree pod `<ścieżka>` z odpowiednim branchem (istniejącym lokalnie, śledzącym origin, albo świeżo utworzonym).

## Przykłady

```bash
gwta "$HOME/repos/.worktree/feature/foo"
gwta --help
```
