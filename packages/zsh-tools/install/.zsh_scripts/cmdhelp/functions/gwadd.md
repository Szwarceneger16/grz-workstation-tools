# gwadd

Dodaje worktree do $HOME/repos/.worktree/<branch> oraz linkuje .env.lint.local (jeśli istnieje)

## Użycie

```bash
gwadd <branch>
gwadd [-h|--help]
```

## Opcje

- <branch> Nazwa brancha (zwykle lokalny branch)
- `-h`, `--help` — pokaż pomoc

## Co robi

- docelowy katalog: ~/repos/.worktree/<branch>
- dodaje worktree (przez gwta)
- jeśli w PWD istnieje .env.lint.local i nie ma go w target,
  tworzy symlink do .env.lint.local w worktree

## Efekt końcowy

Masz osobny katalog roboczy w ~/.worktree dla danego brancha.

## Przykłady

```bash
gwadd feature/foo
```
