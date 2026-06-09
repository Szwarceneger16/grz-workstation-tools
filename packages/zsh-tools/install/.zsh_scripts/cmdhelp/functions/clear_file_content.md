# clear_file_content

czyści plik (truncate do 0) i otwiera w nano

## Użycie

```bash
clear_file_content <ścieżka/do/pliku>
clear_file_content [-h|--help]
```

## Opcje

- `-h`, `--help` — pokaż pomoc

## Efekt końcowy

Plik ma długość 0 bajtów, potem lądujesz w nano z tym plikiem otwartym.

## Przykłady

```bash
clear_file_content <a/b/c.txt>
```
