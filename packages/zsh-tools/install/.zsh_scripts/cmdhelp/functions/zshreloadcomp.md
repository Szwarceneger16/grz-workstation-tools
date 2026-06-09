# zshreloadcomp

Przeładowanie systemu completion w bieżącej sesji Zsh.

## Użycie

```bash
zshreloadcomp
zshreloadcomp [-h|--help]
```

## Co robi

Komenda odświeża mechanizm completion, tak aby bieżąca sesja zobaczyła:

- nowe pliki completion,
- zmienione pliki completion,
- nowe mapowania komend do funkcji completion,
- zmiany w `fpath` związane z completion.

## Efekt końcowy

Po wykonaniu komendy aktualna sesja Zsh zaczyna używać najnowszych definicji completion bez potrzeby otwierania nowego terminala.

## Kiedy używać

- po dodaniu nowego pliku `_nazwa` w katalogu completion,
- po zmianie `_grzcmds`,
- po zmianie `fpath`,
- po refactorze completion.

## Przykłady

```bash
zshreloadcomp
```

## Typowy workflow

```bash
source ~/.zshrc
zshreloadcomp
```

## Uwagi

- Ta komenda przeładowuje **completion**, nie całą konfigurację shellową.
- Jeśli zmieniałeś również funkcje, helpery albo zmienne globalne, najpierw przeładuj konfigurację, np. przez `source ~/.zshrc` albo nową sesję Zsh.
