# dnsswitch

Szybkie przełączanie systemowego DNS w Linux Mint / Ubuntu z użyciem `systemd-resolved` i szyfrowania **DNS over TLS (DoT)**.

Ta komenda jest dopasowana do architektury:

- funkcja shellowa w `~/.zsh_scripts/functions`
- help w `~/.zsh_scripts/cmdhelp/functions`
- completion w `~/.zsh_scripts/completion/functions`

## Użycie

```bash
dnsswitch status
dnsswitch list
dnsswitch auto
dnsswitch mullvad
dnsswitch mullvad-adblock
dnsswitch mullvad-base
dnsswitch mullvad-extended
dnsswitch mullvad-family
dnsswitch mullvad-all
dnsswitch quad9
dnsswitch cloudflare
```

## Profile

- `auto` — usuwa globalny override i wraca do DNS z DHCP / routera
- `mullvad` — czysty Mullvad DNS
- `mullvad-adblock` — Mullvad z blokowaniem reklam / trackerów
- `mullvad-base` — Mullvad Base
- `mullvad-extended` — rozszerzone blokowanie
- `mullvad-family` — profil rodzinny
- `mullvad-all` — najmocniejsze blokowanie
- `quad9` — dobry fallback diagnostyczny
- `cloudflare` — drugi szybki fallback diagnostyczny

## Co dokładnie robi

Komenda zapisuje albo usuwa plik:

```text
/etc/systemd/resolved.conf.d/99-dnsswitch.conf
```

Następnie:

1. restartuje `systemd-resolved`
2. czyści cache przez `resolvectl flush-caches`
3. pokazuje skrócony `resolvectl status`

## Ważna uwaga o statusie

To, że w sekcji `Link` nadal widzisz DNS z DHCP, np. `192.168.1.1`, **nie oznacza błędu**.

Jeżeli w sekcji `Global` masz własny DNS i `Domains=~.`, to zwykłe zapytania idą przez globalny resolver. Sekcja `Link` tylko pokazuje, co interfejs dostał z DHCP.

## Wymagania

- aktywny `systemd-resolved`
- `/etc/resolv.conf` ma wskazywać na:

```text
/run/systemd/resolve/stub-resolv.conf
```

## Typowy workflow

```bash
dnsswitch mullvad-base
dnsswitch quad9
dnsswitch cloudflare
dnsswitch auto
```

## Po czym poznasz, że działa

Po przełączeniu `dnsswitch status` powinno pokazać nowy serwer w sekcji `Global`, np.:

```text
Current DNS Server: 194.242.2.4#base.dns.mullvad.net
```
