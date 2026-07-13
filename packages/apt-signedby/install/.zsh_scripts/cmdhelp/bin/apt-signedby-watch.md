# apt-signedby-watch

## Nazwa
`apt-signedby-watch` — watcher zmian w konfiguracji APT z automatycznym audytem i powiadomieniami.

## Składnia
```bash
apt-signedby-watch
```

## Co robi
Skrypt uruchamia długotrwały watcher oparty o `inotify` dla:
- `/etc/apt/sources.list`
- `/etc/apt/sources.list.d`

Przy starcie wykonuje audyt początkowy, a potem reaguje na zmiany plików:
- `sources.list`
- `*.list`
- `*.sources`

Po wykryciu zmiany:
- debouncuje zdarzenia przez około 1 sekundę
- ponownie audytuje aktywne repozytoria APT
- wysyła powiadomienie `notify-send`
- loguje stan do stdout, więc dobrze nadaje się do uruchamiania jako usługa użytkownika lub przez journal

## Co sprawdza
### 1. Politykę `signed-by` / `Signed-By`
Wykrywa:
- brak `signed-by=` w `.list`
- brak `Signed-By:` w `.sources`
- `trusted=yes` / `Trusted: yes`
- błędy odczytu plików źródeł

### 2. Minimalny zestaw oficjalnych repozytoriów
Skrypt ma zaszytą kontrolę minimalnego zestawu repo dla Linux Mint 22.3 i Ubuntu Noble:
- Mint `zena` z hosta `packages.linuxmint.com`
- komponenty Mint: `main`, `upstream`, `import`, `backport`
- Ubuntu: `noble`, `noble-updates`, `noble-backports`, `noble-security`
- komponenty Ubuntu: `main`, `restricted`, `universe`, `multiverse`
- wpisy Ubuntu są liczone jako oficjalne tylko wtedy, gdy `Signed-By` wygląda na `ubuntu-archive-keyring.gpg`

## Zachowanie
### Przy starcie
Wykonuje pełny audyt z triggerem:
```text
startup/login
```

### Przy zmianach plików
Zbiera zdarzenia i po krótkim debounce robi jeden wspólny audyt, zamiast spamować powiadomieniami dla każdej operacji zapisu.

### Wynik powiadomienia
Powiadomienie ma status:
- `APT audit: OK` — gdy nie ma naruszeń
- `APT audit: PROBLEM` — gdy są naruszenia polityki albo brakuje minimalnego zestawu oficjalnych repo

## Wymagania
- środowisko Linux z `inotify`
- `notify-send` do powiadomień desktopowych
- sensownie działa jako proces długotrwały, np. z `systemd --user`

## Przykłady
### Ręczne uruchomienie w terminalu
```bash
apt-signedby-watch
```

### Uruchomienie w tle przez `systemd --user`
Najwygodniejszy model dla tego skryptu to osobna usługa użytkownika, żeby watcher startował automatycznie po logowaniu.

## Uwagi
- Skrypt nie przyjmuje opcji CLI.
- To nie jest jednorazowy audyt. Proces ma działać stale.
- Jeżeli w systemie nie ma `notify-send`, skrypt nadal loguje zdarzenia do stdout.
- Jeżeli watcher nie może założyć watchy na `/etc/apt`, zgłasza problem i kończy się błędem.
- Zasady kontroli oficjalnych repo są zahardkodowane pod Mint 22.3 / Ubuntu Noble. Po zmianie wersji dystrybucji logika może wymagać aktualizacji.
