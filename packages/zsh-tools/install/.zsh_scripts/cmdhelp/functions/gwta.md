# gwta

`gwta` — dodaje worktree pod podaną ścieżką; nazwa brancha domyślnie jest wyliczana z ostatniego segmentu ścieżki, ale można ją podać jawnie jako drugi argument.

## Użycie

```bash
gwta <ścieżka> [branch]
gwta [-h|--help]
```

## Opcje

- `<ścieżka>` — docelowa ścieżka worktree (domyślnie branch = nazwa ostatniego segmentu)
- `[branch]` — opcjonalna jawna nazwa brancha (potrzebna np. gdy branch zawiera `/`, jak `feature/foo`)
- `-h`, `--help` — pokaż pomoc

## Co robi

- jeśli lokalny branch o tej nazwie istnieje: `git worktree add <ścieżka> <branch>`
- inaczej, jeśli istnieje `origin/<branch>`: `git worktree add <ścieżka> -b <branch> origin/<branch>`
- inaczej: `git worktree add <ścieżka> -b <branch>` (nowy branch)

Używane przez `gwadd` (przekazuje branch jawnie, żeby zachować branche ze `/`).

## Efekt końcowy

Nowy worktree pod `<ścieżka>` z odpowiednim branchem (istniejącym lokalnie, śledzącym origin, albo świeżo utworzonym).

## Przykłady

```bash
gwta "$HOME/repos/.worktree/feature/foo"
gwta --help
```
