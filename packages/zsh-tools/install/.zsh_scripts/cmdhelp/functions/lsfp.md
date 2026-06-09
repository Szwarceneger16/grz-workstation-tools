# lsfp

Wariant `ls`, który ma ułatwiać listowanie argumentów z zachowaniem opcji, ale z naciskiem na wygodniejsze uporządkowanie operandów.

## Użycie

```bash
lsfp [opcje ls] [ścieżki...]
lsfp [-h|--help]
```

## Co robi

Komenda rozdziela przekazane argumenty na:

- opcje `ls`,
- operandy / ścieżki.

Następnie uruchamia logikę wrappera tak, aby wygodniej obsłużyć pliki i katalogi przy jednym wywołaniu, zachowując przekazane opcje `ls`.

## Argumenty

- `[opcje ls]` — standardowe opcje `ls`, np. `-l`, `-a`, `-h`, `-t`
- `[ścieżki...]` — pliki i/lub katalogi do wyświetlenia

## Efekt końcowy

- wrapper przetwarza przekazane argumenty,
- zachowuje opcje `ls`,
- pomaga wygodniej listować mieszany zestaw plików i katalogów.

## Przykłady

```bash
lsfp
lsfp -lah
lsfp -lah .
lsfp -l plik.txt katalog/
lsfp -- katalog-z-dziwna-nazwa
```

## Uwagi

- `lsfp` jest wrapperem wokół `ls`, więc większość opcji działa tak, jak w zwykłym `ls`.
- Jeśli po `--help` widzisz help od `ls`, to znaczy, że blok obsługi helpa wrappera nie zatrzymał wykonania wystarczająco wcześnie.
