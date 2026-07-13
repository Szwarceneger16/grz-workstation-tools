# yubico-auth upgrade

Ręcznie pobiera, weryfikuje i instaluje nowszą wersję.

## Użycie

```bash
yubico-auth upgrade [--version WERSJA] [--dry-run] [--no-switch] [--keep-staging]
yubico-auth upgrade --help
```

## Opcje

- `--version WERSJA` — pobierz konkretną wersję zamiast najnowszej
- `--dry-run` — pokaż plan bez zmian na dysku
- `--no-switch` — zainstaluj wersję, ale nie przestawiaj `current`
- `--keep-staging` — nie usuwaj staging po zakończeniu

## Bezpieczeństwo

- wymusza podpis od jednego z aktualnych kluczy wydań Yubico (weryfikacja `gpgv`)
- używa wydzielonego keyringu w `~/.local/share/yubico-authenticator/trust/gnupg`
- nie pozwala na downgrade
- nie nadpisuje istniejącej wersji
