# gwtrm

`gwtrm` — usuwa worktree powiązany z podanym branchem (branch pozostaje nietknięty).

## Użycie

```bash
gwtrm <branch>
gwtrm [-h|--help]
```

## Opcje

- `<branch>` — nazwa brancha, którego worktree ma zostać usunięty
- `-h`, `--help` — pokaż pomoc

## Co robi

- odnajduje katalog worktree powiązany z `<branch>` (`git worktree list --porcelain`)
- jeśli istnieje: `git worktree remove -- <katalog>`
- jeśli worktree ma niezacommitowane zmiany, `git worktree remove` odmówi — usuń ręcznie z `--force` w razie potrzeby

Używane przez `gwrm` (razem z `gbd`).

## Efekt końcowy

Katalog worktree znika; branch nadal istnieje lokalnie.

## Przykłady

```bash
gwtrm feature/foo
gwtrm --help
```
