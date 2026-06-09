# pnpmls

pnpmls — grep po liście paczek z pnpm

## Użycie

```bash
  pnpmls <wzorzec> [głębokość]
  pnpmls <wzorzec> [głębokość]
  pnpmls [-h|--help]
```

## Opcje

- <wzorzec> Tekst do grep -i (np. react, eslint, typescript)
- [głębokość] Jeśli podasz: działa na bieżącym projekcie (pnpm ls --depth=<głębokość>)
  Jeśli nie podasz: działa na całym workspace (pnpm -w ls)
- `-h`, `--help` — pokaż pomoc

## Efekt końcowy

Dostajesz przefiltrowany wynik (case-insensitive) z listy zależności.

## Przykłady

```bash
  pnpmls eslint
  pnpmls react 2
  pnpmls --help
```
