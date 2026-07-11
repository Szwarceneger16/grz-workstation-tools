# flameshot-ocr-copyq

## Nazwa
`flameshot-ocr-copyq` — zrzut zaznaczonego obszaru ekranu, OCR przez Tesseract i zapis wyniku do schowka / CopyQ.

## Składnia
```bash
flameshot-ocr-copyq
```

## Co robi
Skrypt uruchamia interaktywny wybór obszaru przez `flameshot`, a następnie:
- przekazuje obraz do `tesseract`
- rozpoznaje tekst w językach `pol+eng`
- kopiuje wynik do schowka
- zapisuje wynik do zakładki `OCR` w CopyQ
- pokazuje powiadomienie o wyniku operacji

## Aktualna konfiguracja w skrypcie
### Języki OCR
```text
pol+eng
```

### Zapis do CopyQ
Włączony.

### Nazwa zakładki CopyQ
```text
OCR
```

## Zachowanie
### Gdy użytkownik anuluje wybór obszaru
Skrypt kończy się bez błędu.

### Gdy OCR nic nie rozpozna
Pokazuje powiadomienie:
```text
OCR: Nie rozpoznano tekstu.
```

i kończy się kodem `1`.

### Gdy OCR się powiedzie
- tekst trafia do schowka
- tekst trafia do zakładki `OCR` w CopyQ
- pojawia się powiadomienie o sukcesie

## Wymagania
- `flameshot`
- `tesseract`
- pakiety językowe Tesseract dla `pol` i `eng`
- `copyq`
- `notify-send`

## Przykłady
### Standardowe użycie
```bash
flameshot-ocr-copyq
```

Po uruchomieniu zaznaczasz obszar na ekranie, a rozpoznany tekst trafia do schowka i do zakładki `OCR` w CopyQ.

## Uwagi
- Skrypt nie przyjmuje opcji CLI.
- Języki OCR i zapis do zakładki CopyQ są obecnie ustawione na sztywno w zmiennych skryptu.
- To narzędzie jest wygodne do szybkiego wyciągania tekstu z obrazów, terminala, dialogów, PDF-ów wyświetlanych na ekranie itp.
