# gwfr

`gwfr` — pobiera branch z `origin`, tworzy śledzący go lokalny branch i od razu dodaje dla niego worktree.

Nazwa rozwija się jako **git worktree fetch remote**.

## Użycie

```bash
gwfr <branch>
gwfr -h
gwfr --help
```

## Co robi

`gwfr` wywołuje kolejno:

1. `fr <branch>` — pobiera branch, aktualizuje `origin/<branch>` i ustawia upstream lokalnego brancha;
2. `gwadd <branch>` — tworzy worktree dla lokalnego brancha.

Worktree powstaje pod:

```text
~/repos/.worktree/<branch>
```

Dodatkowe zachowanie, takie jak linkowanie `.env.lint.local`, jest dziedziczone z `gwadd`.

## Przykłady

```bash
gwfr feature/foo
gwfr claude/openwrt-restore-safety-we9fh9
```

Dla brancha zawierającego `/` powstanie odpowiadająca mu zagnieżdżona ścieżka, na przykład:

```text
~/repos/.worktree/claude/openwrt-restore-safety-we9fh9
```

## Uwagi

- Branch musi istnieć na `origin`.
- `gwfr` nie przechodzi automatycznie do utworzonego katalogu.
- Jeśli branch jest już checkoutowany w innym worktree, Git odmówi utworzenia kolejnego worktree dla tego samego lokalnego brancha.
