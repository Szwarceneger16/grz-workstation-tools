# simplified_netrole

Narzędzia do pracy serwisowej z fizycznymi adapterami Ethernet USB: przenoszą wybrany
interfejs do izolowanego network namespace, konfigurują adresację (statyczna / DHCP probe)
i uruchamiają odizolowany profil Firefoksa do paneli routerów/AP/CPE. Pełny opis: `README.md`.

## Zawartość

- `simplified_netrole` — główny orkiestrator (wybór interfejsu, namespace, cleanup)
- `usb-netns-clean` — awaryjny/ręczny cleanup namespace
- `simplified_netrole_utils/netrole-netns-network` — konfiguracja sieci w namespace
- `simplified_netrole_utils/netrole-firefox-window` — izolowany profil/okno Firefoksa

## Ścieżki po instalacji (stow)

```text
~/.local/bin/simplified_netrole
~/.local/bin/usb-netns-clean
~/.local/bin/simplified_netrole_utils/netrole-firefox-window
~/.local/bin/simplified_netrole_utils/netrole-netns-network
```

## Instalacja

```sh
./run.sh install simplified_netrole
```

Wymaga `~/.local/bin` na `PATH`. Runtime wymaga m.in. `iproute2`, `NetworkManager`,
`python3`, `dhclient`, Firefoksa (szczegóły w `README.md`).
