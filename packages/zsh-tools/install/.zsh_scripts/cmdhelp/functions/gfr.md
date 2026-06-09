# gfr

`gfr` — pobiera branch z `origin`, tworząc albo aktualizując lokalny branch o tej samej nazwie.

Uruchamia:

```bash
git fetch origin <branch>:<branch>
```

Czyli:

- pobiera `origin/<branch>`;
- zapisuje go do lokalnego brancha `<branch>`;
- nie przełącza aktualnego brancha.

## Użycie

```bash
gfr <branch>
gfr -h
gfr --help
```

## Argumenty

### `<branch>`

Nazwa brancha do pobrania z `origin`.

Komenda przyjmuje dokładnie jeden argument.

## Przykład

```bash
gfr codex/add-missing-functionality-to-applet.js
```

## Efekt

Po poprawnym wykonaniu masz lokalny branch o tej samej nazwie, gotowy do użycia przez `checkout`, `switch` albo `worktree`.

Przykładowo:

```bash
git switch codex/add-missing-functionality-to-applet.js
```

albo:

```bash
git worktree add ../repo-codex-add-missing-functionality codex/add-missing-functionality-to-applet.js
```

## Uwagi

- Jeśli branch nie istnieje na `origin`, Git zwróci błąd.
- Jeśli jesteś aktualnie na branchu `<branch>`, Git może odmówić nadpisania aktualnie checkoutowanego brancha.
- `gfr` nie robi `checkout`, `switch` ani `pull`.
- `gfr` działa tylko dla remote `origin`.

## Odpowiednik w Git

```bash
git fetch origin <branch>:<branch>
```
