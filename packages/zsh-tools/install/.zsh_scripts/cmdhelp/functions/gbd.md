# gbd

`gbd` — bezpiecznie usuwa lokalny branch (odmówi, jeśli nie jest w pełni zmergowany).

## Użycie

```bash
gbd <branch>
gbd [-h|--help]
```

## Opcje

- `<branch>` — nazwa brancha do usunięcia
- `-h`, `--help` — pokaż pomoc

## Co robi

```bash
git branch -d -- <branch>
```

Używane przez `gwrm` (po `gwtrm`).

## Efekt końcowy

Branch usunięty lokalnie, o ile Git uznał go za bezpieczny do usunięcia. W przeciwnym razie polecenie kończy się błędem i nic nie usuwa.

## Przykłady

```bash
gbd feature/foo
gbd --help
```
