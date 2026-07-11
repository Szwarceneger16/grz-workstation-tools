# jlog-user

Podgląd logów **user service** z `systemd` w trybie śledzenia na żywo.

## Użycie

```bash
jlog-user <nazwa_usługi>
jlog-user <nazwa_usługi>.service
jlog-user [-h|--help]
```

## Co robi

Komenda przyjmuje nazwę usługi użytkownika i uruchamia:

```bash
journalctl --user -u <usługa>.service -f
```

Jeśli podasz nazwę bez końcówki `.service`, zostanie ona dopisana automatycznie.

## Argumenty

- `<nazwa_usługi>` — nazwa usługi userowej systemd, np. `nextcloud`, `syncthing`, `my-worker`

## Efekt końcowy

- otwiera podgląd logów wskazanej usługi,
- przechodzi w tryb **follow**,
- nowe wpisy są dopisywane na bieżąco.

## Przykłady

```bash
jlog-user nextcloud
jlog-user syncthing.service
jlog-user my-worker
```

## Uwagi

- Działa dla **usług użytkownika** (`systemctl --user`), a nie dla usług systemowych — do tych służy `jlog-system`.
- Jeśli usługa nie istnieje, `journalctl` zwróci błąd lub pusty wynik.
