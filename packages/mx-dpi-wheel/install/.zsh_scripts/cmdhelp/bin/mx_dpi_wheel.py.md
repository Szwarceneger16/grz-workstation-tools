# mx_dpi_wheel.py

## Nazwa
`mx_dpi_wheel.py` — interaktywny wheel-overlay do zmiany DPI myszy Logitech MX Master 3S przez prywatny klawisz modyfikujący i kółko myszy.

## Składnia
```bash
mx_dpi_wheel.py
```

## Co robi
Skrypt działa jako stale uruchomiony proces GUI pod X11.

Po wciśnięciu prywatnego klawisza o keycodzie `202` przechwytuje wejście myszy i czeka na scroll kółkiem.

Gdy przewiniesz kółkiem przy wciśniętym modyfikatorze:
- pokazuje okrągły overlay w miejscu kursora
- przełącza się między predefiniowanymi poziomami DPI
- po puszczeniu modyfikatora (wykrywanym przez krótki timeout ciszy) zapisuje wybór do cache
- jeśli DPI faktycznie się zmieniło, ustawia je przez `solaar config ... dpi ...`
- wysyła powiadomienie o sukcesie albo błędzie

## Aktualna konfiguracja zaszyta w skrypcie
### Urządzenie
```text
MX Master 3S
```

### Dostępne poziomy DPI
```text
1200, 1600, 1800, 2200, 2800
```

### Klawisz modyfikujący
```text
MOD_KEYCODE = 202
```

To nie jest standardowy skrót klawiaturowy po nazwie. Skrypt łapie surowy keycode z X11.

### Sterowanie kółkiem
```text
Button 4 = scroll up
Button 5 = scroll down
```

### Timeout i debounce
```text
SCROLL_DEBOUNCE_MS = 60
MOD_TIMEOUT_MS = 250
```

### Overlay
```text
WINDOW_SIZE = 360
RADIUS = 140
ANIM_FPS = 45
ANIM_EASE = 0.08
```

### Cache ostatniego wyboru
Plik:
```text
$XDG_CACHE_HOME/mx_dpi_wheel_state.json
```

lub, gdy `XDG_CACHE_HOME` nie istnieje:
```text
$HOME/.cache/mx_dpi_wheel_state.json
```

## Jak działa wybór DPI
### Start trybu
Przy pierwszym `KeyPress` dla keycode `202` skrypt:
- zapisuje aktualną pozycję kursora
- zaznacza tryb pending
- łapie pointer przez `grab_pointer()`

### Pierwszy scroll
Dopiero pierwszy scroll pokazuje overlay.

### Przełączanie wartości
Każdy scroll przesuwa indeks po liście DPI cyklicznie:
- w górę → `+1`
- w dół → `-1`

### Zatwierdzenie
Nie ma jawnej obsługi `KeyRelease`. Koniec trybu jest wykrywany po braku aktywności klawisza przez `MOD_TIMEOUT_MS`.

To ważne: skrypt specjalnie ignoruje `KeyRelease`, bo według komentarza keycode `202` może „pulsować”.

## Kiedy DPI jest naprawdę ustawiane
Po zamknięciu overlay skrypt:
- zawsze zapisuje aktualny indeks do pliku stanu
- **nie wywołuje** `solaar`, jeśli nie było scrolla albo wybrany indeks jest taki sam jak na początku
- wywołuje `solaar` dopiero wtedy, gdy nastąpiła realna zmiana

Ustawienie DPI dzieje się w osobnym wątku, żeby GUI nie blokowało się na wywołaniu `solaar`.

## Polecenie używane do zmiany DPI
```bash
solaar config "MX Master 3S" dpi <wartość>
```

## Wymagania
- Python 3
- X11
- `python-xlib`
- `PyGObject` / GTK 3 (`gi`, `Gtk`, `Gdk`, `GLib`)
- `solaar`
- `notify-send`

## Przykłady
### Standardowe uruchomienie
```bash
mx_dpi_wheel.py
```

### Typowe użycie
1. Uruchamiasz skrypt w tle.
2. Wciskasz prywatny klawisz zmapowany na keycode `202`.
3. Kręcisz kółkiem, żeby wybrać DPI.
4. Po chwili bez aktywności wybór zostaje zatwierdzony.

## Uwagi
- To rozwiązanie jest praktycznie zaprojektowane pod X11; skrypt korzysta bezpośrednio z `Xlib.display()` i `grab_key()`.
- Overlay jest rysowany jako przezroczyste okno GTK typu notification i nie łapie focusa.
- W razie wyjątku skrypt próbuje oddać pointer i schować overlay, a następnie pokazuje powiadomienie z błędem.
