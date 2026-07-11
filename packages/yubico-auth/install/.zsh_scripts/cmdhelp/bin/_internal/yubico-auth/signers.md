# yubico-auth signers

Pokazuje i weryfikuje zaufanych sygnatariuszy wydań Yubico.

## Użycie

```bash
yubico-auth signers
yubico-auth signers --check
yubico-auth signers --guide
yubico-auth signers --help
```

## Opcje

- `--check` — porównaj lokalnie zaufaną listę odcisków z aktualną listą Yubico
- `--guide` — otwórz instrukcję ręcznej aktualizacji listy sygnatariuszy

## Co robi

Bez opcji wypisuje lokalnie zaufane odciski sygnatariuszy. Weryfikacja wydań
(`yubico-auth upgrade`) akceptuje podpis od **dowolnego** z tych kluczy, przez
`gpgv` względem keyringu:

```text
~/.local/share/yubico-authenticator/trust/yubico-release-signers.gpg
```

Lista pochodzi ze strony podpisów Yubico:

```text
https://developers.yubico.com/Software_Projects/Software_Signing.html
```

Gdy Yubico zmieni listę sygnatariuszy, `yubico-auth check` zgłosi rozjazd i wyśle
powiadomienie. Aby zobaczyć, jak zaktualizować listę ręcznie:

```bash
yubico-auth signers --guide
```
