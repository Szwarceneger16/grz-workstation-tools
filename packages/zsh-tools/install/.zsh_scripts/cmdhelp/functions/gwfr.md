# gwfr

Worktree fetch remote": fetch z remote + dodanie worktree

## Użycie

```bash
 gwfr <branch>
gwfr [-h|--help]
```

## Opcje

- `-h`, `--help` — pokaż pomoc

## Co robi

`gwfr` woła po kolei:
- `fetchremote <branch>` — pobiera branch z `origin`
- `gwadd <branch>` — dodaje worktree dla tego brancha

## Efekt końcowy

Po jednej komendzie masz pobranego brancha i worktree w ~/.worktree.

## Przykłady

```bash
gwfr feature/foo #wezmie branch z origin
gwfr --help
```
