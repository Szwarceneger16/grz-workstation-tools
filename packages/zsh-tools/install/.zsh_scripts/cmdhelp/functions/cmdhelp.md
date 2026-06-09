# cmdhelp

Frontend do lokalnego systemu helpów dla własnych funkcji i komend.

## Użycie

```bash
cmdhelp <komenda>
cmdhelp <komenda> functions
cmdhelp <komenda> bin
cmdhelp --less <komenda>
cmdhelp <komenda> --less
cmdhelp --list
cmdhelp --list functions
cmdhelp --list bin
cmdhelp audit
cmdhelp --audit
cmdhelp [-h|--help]
```

## Co robi

cmdhelp wyszukuje help dla wskazanej nazwy w katalogu helpów i wyświetla go w terminalu.

Domyślnie wynik trafia bezpośrednio na konsolę.

Opcja `--less` wymusza wyświetlenie wyniku przez pager `less`.

Przy każdym uruchomieniu `cmdhelp` pokazuje krótki status spójności systemu helpów.

## Zakres wyszukiwania

### Dostępne scope

- `functions` — szuka tylko w `cmdhelp/functions`
- `bin` — szuka tylko w `cmdhelp/bin`
- brak scope — tryb auto, czyli najpierw `functions`, potem `bin`

## Opcje

- `--less` — pokaż wynik przez `less`
- `-l`, `--list` — wypisz realne entrypointy
- `audit`, `--audit` — pokaż pełny raport niespójności
- `-h`, `--help` — pokaż krótką pomoc użycia

## Co pokazuje `--list`

`cmdhelp --list` pokazuje tylko realne entrypointy:

- funkcje publiczne, które są aktualnie załadowane do powłoki
- komendy z `~/.local/bin`, które są faktycznie aktywne na `PATH`

## Co pokazuje `audit`

### Help bez realnego entrypointu

Pokazuje wpisy istniejące w:

- `cmdhelp/functions`
- `cmdhelp/bin`

Dla których nie ma odpowiadającego:

- załadowanego entrypointu funkcji
- aktywnej komendy z `~/.local/bin` na `PATH`

### Entrypointy bez helpa

Pokazuje:

- załadowane funkcje bez pliku helpa
- aktywne komendy z `~/.local/bin` bez pliku helpa

### Nieaktywne entrypointy

Pokazuje:

- pliki funkcji z `~/.zsh_scripts/functions`, które nie zostały załadowane do bieżącej powłoki
- pliki z `~/.local/bin`, które nie są aktywne na `PATH` albo są shadowed przez inną komendę o tej samej nazwie

## Przykłady

```bash
cmdhelp jlog
cmdhelp --less jlog
cmdhelp gfr functions
cmdhelp --list
cmdhelp --list functions
cmdhelp audit
```

## Uwagi

Domyślny katalog helpów wynika z prywatnej zmiennej `__CMDHELP_ROOT`.

Jeśli help istnieje w obu formach, preferowana jest kolejność:

1. `<nazwa>.help.zsh`
2. `<nazwa>.md`
