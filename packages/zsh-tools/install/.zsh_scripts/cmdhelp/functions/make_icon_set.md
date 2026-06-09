# make_icon_set

Generuje komplet ikon `hicolor` z jednego pliku źródłowego.

## Użycie

```bash
make_icon_set <plik_źródłowy> <nazwa_ikony>
make_icon_set [-h|--help]
```

## Argumenty

- `<plik_źródłowy>` — ścieżka do obrazu źródłowego, np. PNG, JPG, WebP, SVG
- `<nazwa_ikony>` — nazwa wynikowej ikony bez rozszerzenia, np. `messenger`

## Co robi

- sprawdza, czy plik istnieje,
- sprawdza metadane obrazu przez `identify -ping`,
- generuje rozmiary:
  - 16
  - 24
  - 32
  - 48
  - 64
  - 128
  - 256
  - 512
- zapisuje wynik do:
  `~/.local/share/icons/hicolor/<ROZMIAR>x<ROZMIAR>/apps/<nazwa_ikony>.png`

## Przykład

    make_icon_set ~/Pictures/messenger.png messenger

## Efekt

Powstaną pliki typu:

- `~/.local/share/icons/hicolor/16x16/apps/messenger.png`
- `~/.local/share/icons/hicolor/24x24/apps/messenger.png`
- `~/.local/share/icons/hicolor/32x32/apps/messenger.png`
- `~/.local/share/icons/hicolor/48x48/apps/messenger.png`
- `~/.local/share/icons/hicolor/64x64/apps/messenger.png`
- `~/.local/share/icons/hicolor/128x128/apps/messenger.png`
- `~/.local/share/icons/hicolor/256x256/apps/messenger.png`
- `~/.local/share/icons/hicolor/512x512/apps/messenger.png`

Potem w pliku `.desktop` używasz:

    Icon=messenger
