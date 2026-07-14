# fr

`fr` — pobiera branch z `origin` do lokalnego brancha o tej samej nazwie i ustawia tracking na `origin/<branch>`.

## Użycie

```bash
fr <branch>
fr -h
fr --help
```

## Co robi

Dla:

```bash
fr feature/foo
```

wykonuje odpowiednik:

```bash
git fetch origin \
  refs/heads/feature/foo:refs/heads/feature/foo \
  refs/heads/feature/foo:refs/remotes/origin/feature/foo

git branch --set-upstream-to=origin/feature/foo feature/foo
```

W efekcie:

- aktualizuje `origin/<branch>`;
- tworzy albo aktualizuje lokalny `<branch>`;
- ustawia upstream lokalnego brancha na `origin/<branch>`;
- nie przełącza aktualnego brancha.

## Argumenty

### `<branch>`

Nazwa brancha istniejącego na `origin`. Komenda przyjmuje dokładnie jeden argument.

## Przykłady

```bash
fr feature/foo
fr claude/openwrt-restore-safety-we9fh9
```

## Uwagi

- Jeśli branch nie istnieje na `origin`, Git zwróci błąd.
- Aktualizacja lokalnego brancha nie jest wymuszana. Non-fast-forward zostanie odrzucony.
- Git odmówi pobrania bezpośrednio do brancha checkoutowanego w aktualnym albo innym worktree.
- `fr` działa tylko dla remote `origin`.
- `gfr` i `fetchremote` są zachowanymi nazwami zgodnościowymi wywołującymi `fr`.
