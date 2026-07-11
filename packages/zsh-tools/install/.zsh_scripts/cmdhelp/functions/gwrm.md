# gwrm

Usuwa worktree i kasuje branch

## Użycie

```bash
gwrm <branch|ścieżka>
gwrm [-h|--help]
```

## Opcje

- <branch|ścieżka> To co akceptują `gwtrm` i `gbd`
- `-h`, `--help` — pokaż pomoc

## Co robi

`gwrm` woła po kolei:
- `gwtrm <arg>` — usuwa worktree powiązany z branchem
- `gbd <arg>` — bezpiecznie usuwa sam branch

## Efekt końcowy

Usunięcie worktree + usunięcie brancha (bezpieczne usunięcie — `gbd` odmówi, jeśli branch nie jest zmergowany).

## Przykłady

```bash
gwrm feature/foo
gwrm --help
```
