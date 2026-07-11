# yubico-auth check

Sprawdza, czy na stronie Yubico jest nowszy linuxowy release.

## Użycie

```bash
yubico-auth check [--notify|--no-notify] [--force-notify]
yubico-auth check --upgradable
yubico-auth check --help
```

## Opcje

- `--notify` — pokaż powiadomienie, jeśli jest nowa wersja
- `--no-notify` — nie pokazuj powiadomienia
- `--force-notify` — wymuś powiadomienie dla tej samej wersji ponownie
- `--upgradable` — tryb skryptowy:
  - `0` = jest nowa wersja
  - `1` = brak nowej wersji
  - `2` = błąd
