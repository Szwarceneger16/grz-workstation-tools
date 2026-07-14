# gfr

`gfr` — zachowana nazwa zgodnościowa dla `fr`.

## Użycie

```bash
gfr <branch>
gfr -h
gfr --help
```

## Co robi

Wywołuje:

```bash
fr <branch>
```

Pobiera branch z `origin` do lokalnego brancha o tej samej nazwie, aktualizuje `origin/<branch>` i ustawia upstream lokalnego brancha.

Kanoniczną nazwą funkcji jest:

```bash
fr <branch>
```

## Przykład

```bash
gfr feature/foo
```
