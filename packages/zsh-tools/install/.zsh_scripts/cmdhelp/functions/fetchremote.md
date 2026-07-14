# fetchremote

`fetchremote` — zachowana nazwa zgodnościowa dla `fr`.

## Użycie

```bash
fetchremote <branch>
fetchremote -h
fetchremote --help
```

## Co robi

Wywołuje:

```bash
fr <branch>
```

Pobiera branch z `origin` do lokalnego brancha o tej samej nazwie, aktualizuje `origin/<branch>` i ustawia upstream lokalnego brancha.

Nowe skrypty i funkcje powinny używać krótszej nazwy:

```bash
fr <branch>
```

## Przykład

```bash
fetchremote feature/foo
```
