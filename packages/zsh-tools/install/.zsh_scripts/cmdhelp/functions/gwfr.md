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

### Wymagania:

U Ciebie gwfr woła: - fetchremote <branch> - gwadd <branch>
więc fetchremote musi istnieć.

## Efekt końcowy

Po jednej komendzie masz pobranego brancha i worktree w ~/.worktree.

## Przykłady

```bash
gwfr feature/foo #wezmie branch z origin
gwfr --help
```
