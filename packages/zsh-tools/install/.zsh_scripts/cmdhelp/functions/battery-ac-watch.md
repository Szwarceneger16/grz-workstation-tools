# battery-ac-watch

Monitoruje w czasie rzeczywistym, czy bateria oddaje energię podczas pracy laptopa na zasilaczu.

## Składnia

```zsh
battery-ac-watch [opcje]
```

## Opcje

- `-h`, `--help`  
  Pokazuje help polecenia.

- `-i`, `--interval <sekundy>`  
  Ustawia interwał odświeżania. Domyślnie: `2`.

- `-b`, `--battery <BATX>`  
  Wymusza konkretną baterię z `/sys/class/power_supply`, np. `BAT0`.

- `--once`  
  Pokazuje pojedynczy odczyt i kończy działanie.

## Co pokazuje

- `AC_ONLINE` — `1` oznacza, że zasilacz jest podłączony, `0` że nie.
- `STATUS` — stan baterii, np. `Charging`, `Discharging`, `Not charging`, `Full`.
- `CURRENT_NOW` lub `POWER_NOW` — bieżący pobór lub oddawanie energii według sysfs.
- `CHARGE_NOW` lub `ENERGY_NOW` — aktualny poziom ładunku lub energii.
- `CHARGE_FULL` lub `ENERGY_FULL` — pełna pojemność raportowana przez baterię.
- `CAPACITY` — procent naładowania baterii.

## Interpretacja

- `AC_ONLINE: 1` + `STATUS: Discharging`  
  Bateria oddaje energię mimo pracy na zasilaczu.

- `AC_ONLINE: 1` + `STATUS: Not charging` albo `Full`  
  Laptop działa na zasilaczu, bateria nie jest aktualnie ładowana.

- `AC_ONLINE: 1` + `STATUS: Charging`  
  Laptop działa na zasilaczu, a bateria jest doładowywana.

## Przykłady

```zsh
battery-ac-watch
battery-ac-watch --once
battery-ac-watch -i 1
battery-ac-watch -b BAT0
```

## Uwagi

Polecenie czyta dane z `/sys/class/power_supply`.

Przy BIOS-owych progach typu FlexiCharger system może nie pokazywać wszystkiego idealnie 1:1, ale `AC_ONLINE`, `STATUS` i zmiany w `CURRENT_NOW` / `CHARGE_NOW` nadal są bardzo użyteczne diagnostycznie.
