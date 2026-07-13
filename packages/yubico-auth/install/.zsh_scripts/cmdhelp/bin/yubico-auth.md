# yubico-auth

Jedyny publiczny entrypoint do lokalnie zarządzanej instalacji **Yubico Authenticator**.

## Użycie

```bash
yubico-auth <subkomenda> [opcje]
yubico-auth --help
yubico-auth help [subkomenda]
```

## Subkomendy

- `run` — uruchamia aktualnie aktywny bundle GUI
- `status` — pokazuje stan instalacji i timera
- `check` — sprawdza, czy jest nowa wersja
- `upgrade` — pobiera i instaluje nowszą wersję
- `switch` — przełącza aktywną wersję na już zainstalowaną
- `list` — wypisuje zainstalowane wersje
- `signers` — pokazuje/weryfikuje zaufanych sygnatariuszy wydań Yubico
- `help` — pokazuje help ogólny albo help subkomendy

## Najczęstsze użycie

```bash
yubico-auth init
yubico-auth status
yubico-auth check --notify
yubico-auth upgrade --dry-run
yubico-auth upgrade
yubico-auth switch 7.3.0
yubico-auth run
```

## Szczegóły

Pełny help dla konkretnej subkomendy:

```bash
yubico-auth <subkomenda> --help
```

Przykłady:

```bash
yubico-auth status --help
yubico-auth check --help
yubico-auth upgrade --help
yubico-auth switch --help
```

## Ważne ścieżki

- root instalacji: `~/.local/share/yubico-authenticator`
- aktywna wersja: `~/.local/share/yubico-authenticator/current`
- katalog wersji: `~/.local/share/yubico-authenticator/versions`
- keyring do weryfikacji: `~/.local/share/yubico-authenticator/trust/gnupg`
- keyring gpgv: `~/.local/share/yubico-authenticator/trust/yubico-release-signers.gpg`
- stan i locki: `~/.local/state/yubico-authenticator`
- cache i staging: `~/.cache/yubico-authenticator`

## Weryfikacja podpisów

Wydania są weryfikowane przez `gpgv` względem wydzielonego keyringu zawierającego
**aktualne klucze podpisujące wydania Yubico**
(<https://developers.yubico.com/Software_Projects/Software_Signing.html>).
Podpis od dowolnego z tych kluczy jest akceptowany; `gpgv` działa też na starszym
GnuPG (Mint 21 / GnuPG 2.2). Gdy Yubico zmieni listę, `yubico-auth check` zgłosi
rozjazd i wskaże: `yubico-auth signers --guide`.

## Uwagi

To jest hard cutover do jednego publicznego entrypointu, jednego completion i jednego publicznego helpa w `cmdhelp`.
