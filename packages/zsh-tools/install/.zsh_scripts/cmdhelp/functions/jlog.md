# jlog

Podgląd logów **user service** z `systemd` w trybie śledzenia na żywo.

## Użycie

```bash
jlog <nazwa_usługi>
jlog <nazwa_usługi>.service
jlog [-h|--help]
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
jlog nextcloud
jlog syncthing.service
jlog my-worker
```

## Uwagi

- Działa dla **usług użytkownika** (`systemctl --user`), a nie dla usług systemowych.
- Jeśli usługa nie istnieje, `journalctl` zwróci błąd lub pusty wynik.
