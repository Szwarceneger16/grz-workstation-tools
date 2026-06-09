# branchclear

Czyści lokalne branche Git według logiki zdefiniowanej w funkcji, których upstream jest "[gone]"

## Użycie

```bash
branchclear [-f|--force]
branchclear [-h|--help]
```

## Opcje:

-f, --force Użyj force przy usuwaniu worktree (git worktree remove --force), jeśli potrzebne.

## Co robi (high-level):

1. git fetch -p
   - aktualizuje remote-tracking branche
   - usuwa śmieci po zdalnych branchach (pruning)
2. git worktree prune
   - sprząta nieistniejące/odłączone worktree
3. Szuka lokalnych branchy z upstream: [gone]
4. Próbuje bezpiecznie usunąć: git branch -d
5. Jeśli nie da się bezpiecznie:
   - wykrywa "no-op merge" względem base (origin/HEAD, zwykle origin/main/master)
   - i tylko wtedy usuwa force

## Efekt:

Usuwa tylko te branche, które:

- mają upstream [gone]
- i są bezpieczne do usunięcia (merged/no-op) względem bazowego brancha.
