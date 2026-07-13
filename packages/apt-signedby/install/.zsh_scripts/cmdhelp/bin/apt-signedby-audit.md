# apt-signedby-audit

## Nazwa
`apt-signedby-audit` — jednorazowy audyt wpisów APT pod kątem polityki `signed-by` / `Signed-By`.

## Składnia
```bash
apt-signedby-audit [--notify] [--popup] [--cooldown-secs SECONDS] [--state-dir DIR]
```

## Co robi
Skrypt analizuje aktywne źródła APT z:
- `/etc/apt/sources.list`
- `/etc/apt/sources.list.d/*.list`
- `/etc/apt/sources.list.d/*.sources`

Wykrywa między innymi:
- brak `signed-by=` w klasycznych plikach `.list`
- brak `Signed-By:` w plikach Deb822 `.sources`
- użycie niebezpiecznych obejść typu `trusted=yes` lub `allow-insecure=yes`
- `signed-by` wskazujące na coś, co nie wygląda jak ścieżka
- brak pliku keyringa wskazanego w `signed-by`
- keyring, którego `_apt` może nie odczytać, bo nie jest world-readable

Jeżeli wykryje problem:
- wypisuje raport na stderr
- kończy się kodem `2`
- opcjonalnie wysyła powiadomienie i/lub popup

Jeżeli wszystko jest poprawne:
- wypisuje komunikat `OK: ...`
- kończy się kodem `0`

## Opcje
### `--notify`
Wysyła powiadomienie desktopowe `notify-send`, gdy wykryto problem.

### `--popup`
Dodatkowo pokazuje okno `zenity --warning`, gdy wykryto problem.

### `--cooldown-secs SECONDS`
Minimalny odstęp między identycznymi alertami.

Domyślnie:
```text
120
```

Mechanizm działa na podstawie hasha treści raportu i znacznika czasu w katalogu stanu.

### `--state-dir DIR`
Katalog na stan cooldownu i ostatni hash raportu.

Domyślnie:
```text
~/.cache/apt-signedby-audit
```

## Kody wyjścia
### `0`
Brak wykrytych problemów.

### `2`
Wykryto co najmniej jeden problem związany z polityką `signed-by` / `Signed-By`.

## Przykłady
### Sam audyt do terminala
```bash
apt-signedby-audit
```

### Audyt z powiadomieniem desktopowym
```bash
apt-signedby-audit --notify
```

### Audyt z popupem i własnym cooldownem
```bash
apt-signedby-audit --notify --popup --cooldown-secs 300
```

### Audyt z własnym katalogiem stanu
```bash
apt-signedby-audit --notify --state-dir "$HOME/.cache/apt-audit"
```

## Uwagi
- Skrypt celowo ignoruje pliki pomocnicze typu `.bak`, `.old`, `.disabled`, `~`, żeby nie generować false-positive.
- Dla plików `.sources` respektuje `Enabled: no`.
- Dla polityki bezpieczeństwa traktuje `trusted=yes` i podobne obejścia jako problem.
- To jest audyt jednorazowy. Do nasłuchu zmian służy osobny `apt-signedby-watch`.
