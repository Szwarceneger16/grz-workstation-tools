# TEMPLATE

Usuwa worktree i kasuje branch

## Użycie

```bash
gwrm <branch|ścieżka>
TEMPLATE [-h|--help]
```

## Opcje

- <branch|ścieżka> To co akceptują Twoje gwtrm i gbd (u Ciebie to wrappery)
- `-h`, `--help` — pokaż pomoc

## Co robi

U Ciebie gwrm woła: - gwtrm <arg> - gbd <arg>
więc obie komendy muszą istnieć.

## Efekt końcowy

Usunięcie worktree + usunięcie brancha (zależnie od implementacji gwtrm/gbd).

## Przykłady

```bash
gwrm feature/foo
TEMPLATE --help
```
