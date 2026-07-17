# simplified_netrole

Narzędzia do pracy serwisowej z fizycznymi adapterami Ethernet USB: przenoszą wybrany
interfejs do izolowanego network namespace, konfigurują adresację (statyczna / DHCP probe)
i uruchamiają odizolowany profil Firefoksa do paneli routerów/AP/CPE. Pełny opis: `README.md`.

## Zawartość

- `simplified_netrole` — główny orkiestrator (wybór interfejsu, namespace, cleanup)
- `usb-netns-clean` — awaryjny/ręczny cleanup namespace
- `simplified_netrole_utils/netrole-netns-network` — konfiguracja sieci w namespace
- `simplified_netrole_utils/netrole-firefox-window` — izolowany profil/okno Firefoksa
- `netrole-apply-eth-labels` — generuje z configu reguły udev + pliki `.link`
  (stała nazwa i guard dla adapterów USB-Eth); wymaga sudo
- `netrole-usb-eth-guard` — systemowy guard hotplugu (część `system-install`,
  instalowany do `/usr/local/sbin`, root)

## Ścieżki po instalacji

Użytkownik (stow → `~`):

```text
~/.local/bin/simplified_netrole
~/.local/bin/usb-netns-clean
~/.local/bin/simplified_netrole_utils/netrole-firefox-window
~/.local/bin/simplified_netrole_utils/netrole-netns-network
~/.local/bin/netrole-apply-eth-labels
~/.local/share/simplified-netrole/config.example.json
```

System (`system-install`, root, przez sudo):

```text
/usr/local/sbin/netrole-usb-eth-guard        # generyczny, wersjonowany
```

Generowane z configu przez `netrole-apply-eth-labels` (poza repo — zawierają MAC-i):

```text
/etc/udev/rules.d/99-netrole-usb-eth-labels.rules
/etc/systemd/network/09-<linkName>.link
```

## Instalacja

```sh
./run.sh install simplified_netrole   # część user (stow) + system (sudo: guard)
```

Część systemowa poprosi o hasło sudo. Po instalacji wpisz realne MAC-i adapterów
w `~/.config/simplified-netrole/config.json` (pola `mac`/`linkName`) i uruchom
`netrole-apply-eth-labels` (poprosi o sudo), aby wdrożyć reguły udev i pliki `.link`.

Wymaga `~/.local/bin` na `PATH`. Runtime wymaga m.in. `iproute2`, `NetworkManager`,
`python3`, `dhclient`, Firefoksa (szczegóły w `README.md`).
