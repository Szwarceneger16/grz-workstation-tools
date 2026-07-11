# jlog-system

Podgląd logów **system service** z `systemd` w trybie śledzenia na żywo.

## Użycie

```bash
jlog-system <nazwa_usługi>
jlog-system <nazwa_usługi>.service
jlog-system [-h|--help]
```

## Co robi

Komenda przyjmuje nazwę usługi systemowej i uruchamia:

```bash
journalctl -u <usługa>.service -f
```

Jeśli podasz nazwę bez końcówki `.service`, zostanie ona dopisana automatycznie.

## Argumenty

- `<nazwa_usługi>` — nazwa usługi systemowej systemd, np. `nginx`, `sshd`, `docker`

## Efekt końcowy

- otwiera podgląd logów wskazanej usługi,
- przechodzi w tryb **follow**,
- nowe wpisy są dopisywane na bieżąco.

## Przykłady

```bash
jlog-system nginx
jlog-system sshd.service
jlog-system docker
```

## Uwagi

- Działa dla **usług systemowych** (`journalctl` bez `--user`), a nie dla usług użytkownika — do tych służy `jlog-user`.
- Może wymagać uprawnień do odczytu dziennika systemowego (członkostwo w grupie `systemd-journal` albo `sudo`).
- Jeśli usługa nie istnieje, `journalctl` zwróci błąd lub pusty wynik.
