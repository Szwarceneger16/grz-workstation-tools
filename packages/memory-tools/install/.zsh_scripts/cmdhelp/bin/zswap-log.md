# zswap-log

Loguje statystyki `zswap` z `debugfs` do pliku, a w interaktywnym terminalu pokazuje także bieżące / minimalne / maksymalne wartości.

## Użycie

```bash
zswap-log [INTERWAŁ]
zswap-log [opcje]
```

## Opcje

- `-h`, `--help` — pokazuje help.
- `-i`, `--interval SEC` — interwał próbkowania; domyślnie `5`.
- `-d`, `--log-dir DIR` — jawnie ustawia katalog logów.
- `--no-auto-sudo` — wyłącza automatyczne przejście przez `sudo`.

## Kompatybilność wsteczna

Pojedynczy argument pozycyjny nadal oznacza interwał:

```bash
zswap-log 2
```

## Zmienne środowiskowe

- `ZSWAP_LOG_DIR` — katalog logów używany, jeśli nie podano `--log-dir`; jest walidowany tak samo jak jawny `--log-dir`.

## Logika katalogu logów

Kolejność wyboru:

1. `--log-dir DIR`
2. `ZSWAP_LOG_DIR`
3. dla `sudo`: `~/.local/state/zswap-logger` użytkownika wywołującego
4. w innym przypadku: `/var/log/zswap-logger`

Skrypt odrzuca ścieżki względne oraz ścieżki zawierające komponenty będące symlinkami. Jawny katalog z `--log-dir` lub `ZSWAP_LOG_DIR` może zostać utworzony, jeśli nie istnieje, ale po utworzeniu/walidacji musi należeć do `root` albo użytkownika wywołującego przez `sudo` i nie może być zapisywalny dla grupy ani innych użytkowników.

## Zachowanie

- jeśli nie jesteś rootem i nie podasz `--no-auto-sudo`, skrypt sam przejdzie przez `sudo`
- jeśli `debugfs` nie jest zamontowane, skrypt spróbuje je zamontować
- po zakończeniu dopisuje podsumowanie do logu
- w TTY czyści ekran i pokazuje prostą tabelę z bieżącym stanem

## Przykłady

```bash
zswap-log
zswap-log 2
zswap-log --interval 1
sudo zswap-log --log-dir /tmp/zswap-tests
zswap-log --no-auto-sudo
```
