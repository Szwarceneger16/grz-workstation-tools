# Aktualizacja listy sygnatariuszy wydań Yubico

`yubico-auth` ufa stałej liście odcisków kluczy OpenPGP, którymi Yubico podpisuje
wydania. Gdy Yubico doda lub usunie sygnatariusza, `yubico-auth check` wykrywa
rozjazd i wysyła powiadomienie. Ten plik opisuje, jak zaktualizować listę ręcznie —
bez czytania kodu.

## 1. Zobacz, co się zmieniło

```bash
yubico-auth signers --check
```

Wypisze odciski oznaczone:

- `+` — nowy sygnatariusz u Yubico, brak go lokalnie,
- `-` — sygnatariusz lokalny, którego nie ma już u Yubico.

## 2. Sprawdź źródło u Yubico

Otwórz oficjalną stronę podpisów i potwierdź aktualną listę:

<https://developers.yubico.com/Software_Projects/Software_Signing.html>

Bierz pod uwagę wyłącznie klucze oznaczone jako aktualnie wydające
("currently releasing code").

## 3. Zaktualizuj tablicę w skrypcie

W repozytorium edytuj tablicę `ALLOWED_SIGNER_FPRS` w pliku:

```text
packages/yubico-auth/install/.local/bin/yubico-auth
```

- każdy wpis to **40 znaków hex bez spacji**, z komentarzem `# Imię Nazwisko`,
- dodaj nowe odciski (`+`), usuń wycofane (`-`),
- zachowaj kolejność/komentarze dla czytelności.

Zatwierdź zmianę i wgraj pakiet stow tak jak zwykle.

## 4. Zaimportuj klucze i odśwież keyring weryfikacyjny

```bash
yubico-auth init
```

`init` pobierze brakujące klucze z keyserwerów i ponownie wyeksportuje keyring
`gpgv`:

```text
~/.local/share/yubico-authenticator/trust/yubico-release-signers.gpg
```

## 5. Potwierdź

```bash
yubico-auth signers --check
```

Powinno zwrócić: `OK: lokalna lista sygnatariuszy zgodna z Yubico.`

## Uwagi bezpieczeństwa

- Ufaj wyłącznie odciskom ze strony podpisów Yubico (HTTPS).
- Weryfikacja wydań przez `gpgv` akceptuje podpis od dowolnego klucza w keyringu,
  dlatego keyring musi zawierać **tylko** aktualnych sygnatariuszy Yubico.
- Nie dodawaj kluczy z niezweryfikowanych źródeł.
