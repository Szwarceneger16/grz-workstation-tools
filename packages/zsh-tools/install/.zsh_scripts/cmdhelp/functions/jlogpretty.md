# jlogpretty

Podgląd logów **user service** z `systemd` w czytelniejszej, uproszczonej formie.

## Użycie

```bash
jlogpretty <nazwa_usługi>
jlogpretty <nazwa_usługi>.service
jlogpretty [-h|--help]
```

## Co robi

Komenda przyjmuje nazwę usługi użytkownika i uruchamia:

```bash
journalctl --user -u <usługa>.service -n 50 -f -o cat
```

Jeśli podasz nazwę bez końcówki `.service`, zostanie ona dopisana automatycznie.

## Argumenty

- `<nazwa_usługi>` — nazwa usługi userowej systemd

## Efekt końcowy

- pokazuje ostatnie **50** wpisów logu,
- przechodzi w tryb śledzenia na żywo,
- używa formatu `-o cat`, więc output jest mniej „systemd-owy” i bardziej surowy/czytelny.

## Przykłady

```bash
jlogpretty nextcloud
jlogpretty syncthing.service
jlogpretty my-worker
```

## Kiedy używać

- gdy chcesz szybko czytać log bez nadmiaru metadanych,
- gdy interesuje Cię głównie treść komunikatów aplikacji.

## Uwagi

- Działa dla **usług użytkownika** (`systemctl --user`).
- Jeśli potrzebujesz pełniejszego kontekstu logu, użyj `jlog`.
