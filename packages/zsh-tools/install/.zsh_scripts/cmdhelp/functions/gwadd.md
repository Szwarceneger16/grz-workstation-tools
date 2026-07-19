# gwadd

Dodaje worktree do $HOME/repos/.worktree/<branch> oraz linkuje .env.lint.local (jeśli istnieje).
Opcjonalnie: `-t` bazuje nowy branch na branchu z origin, `-b` wymusza utworzenie nowego
lokalnego brancha.

## Użycie

```bash
gwadd [-b] [-t <base-branch>] [<branch>]
gwadd [-h|--help]
```

## Opcje

- `<branch>` — nazwa brancha / katalogu worktree (opcjonalna, jeśli podano `-t`)
- `-t <base-branch>` — branch źródłowy z origin (musi być poprawną nazwą brancha, walidowaną
  przez `git check-ref-format --branch`): robi `git fetch origin <base-branch>`, a następnie:
  jeśli `<branch>` nie podano — tworzy lokalny tracking branch o tej samej nazwie co
  `<base-branch>`; jeśli `<branch>` podano (i różni się od `<base-branch>`) albo podano też
  `-b` — tworzy nowy, **nietrackujący** lokalny branch `<branch>` z `origin/<base-branch>`
  (`git branch --no-track`) — tylko punkt startowy, bez ustawiania upstreamu na base
- `-b` — wymusza utworzenie **nowego** lokalnego brancha (błąd, jeśli już istnieje) zamiast
  polegania na auto-detekcji `gwta`; bez `-t` branch powstaje z bieżącego HEAD
- `-h`, `--help` — pokaż pomoc

## Co robi

- docelowy katalog: ~/repos/.worktree/<branch>
- bez flag: dodaje worktree przez `gwta` (checkout istniejącego lokalnego/origin brancha albo
  nowy branch z HEAD)
- z `-t`/`-b`: najpierw (w razie potrzeby) tworzy branch (`git branch`), potem worktree przez
  `gwta`
- jeśli w PWD istnieje .env.lint.local i nie ma go w target,
  tworzy symlink do .env.lint.local w worktree

## Efekt końcowy

Masz osobny katalog roboczy w ~/.worktree dla danego brancha.

## Przykłady

```bash
gwadd feature/foo                    # jak dotychczas
gwadd -t develop                     # nowy lokalny branch "develop" z origin/develop
gwadd -t develop feature/foo         # nowy branch "feature/foo" bazujący na origin/develop
gwadd -b feature/foo                 # wymuś nowy branch "feature/foo" z bieżącego HEAD
```
