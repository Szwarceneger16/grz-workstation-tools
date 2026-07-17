# simplified_netrole

`simplified_netrole` to mały pakiet narzędzi do pracy serwisowej z fizycznymi adapterami Ethernet USB na Linuksie.

Główna idea:

- wybierasz fizyczny interfejs Ethernet, np. `nr-usba0` albo `nr-usbc0`,
- skrypt przenosi go do osobnego network namespace, np. `usbwan-1`,
- wewnątrz namespace interfejs zawsze nazywa się `eth0`,
- helper konfiguruje adresację statyczną / DHCP / testy,
- helper Firefoksa uruchamia osobny profil przeglądarki w tym namespace,
- po zakończeniu skrypt sprząta namespace i oddaje kartę do hosta.

To narzędzie jest przeznaczone głównie do wygodnego i względnie bezpiecznego dostępu do paneli routerów/AP/CPE bez mieszania ich sieci z główną konfiguracją hosta.

---

## Spis treści

- [Struktura pakietu](#struktura-pakietu)
- [Do czego to jest](#do-czego-to-jest)
- [Czego to nie robi](#czego-to-nie-robi)
- [Wymagania](#wymagania)
- [Instalacja / układ plików](#instalacja--układ-plików)
- [Etykiety i guard USB-Ethernet](#etykiety-i-guard-usb-ethernet)
- [Szybki start](#szybki-start)
- [Główny workflow](#główny-workflow)
- [Konfiguracja JSON](#konfiguracja-json)
- [Profile per interfejs](#profile-per-interfejs)
- [Tryby DHCP](#tryby-dhcp)
- [dnsServers](#dnsservers)
- [Adresy statyczne i trasy](#adresy-statyczne-i-trasy)
- [openUrls i Firefox](#openurls-i-firefox)
- [Wyjątki certyfikatów HTTPS](#wyjątki-certyfikatów-https)
- [Komendy](#komendy)
- [Opis plików w pakiecie](#opis-plików-w-pakiecie)
- [Gdzie czego szukać w kodzie](#gdzie-czego-szukać-w-kodzie)
- [Pliki runtime](#pliki-runtime)
- [Sprzątanie / cleanup](#sprzątanie--cleanup)
- [Typowe scenariusze](#typowe-scenariusze)
- [Troubleshooting](#troubleshooting)
- [Uwagi bezpieczeństwa](#uwagi-bezpieczeństwa)
- [Notatki projektowe](#notatki-projektowe)

---

## Struktura pakietu

Aktualna struktura:

```text
.
├── install
│   └── .local
│       ├── bin
│       │   ├── simplified_netrole
│       │   ├── netrole-apply-eth-labels
│       │   ├── simplified_netrole_utils
│       │   │   ├── netrole-firefox-window
│       │   │   └── netrole-netns-network
│       │   └── usb-netns-clean
│       └── share
│           └── simplified-netrole
│               └── config.example.json
├── install.hook.sh
├── system-install
│   └── usr/local/sbin/netrole-usb-eth-guard
├── system-install.manifest
└── README.md
```

Znaczenie plików:

```text
simplified_netrole
  Główna komenda. Orkiestruje wybór interfejsu, namespace, konfigurację sieci,
  Firefoksa i cleanup.

simplified_netrole_utils/netrole-netns-network
  Helper konfiguracji sieci wewnątrz namespace. Czyta config JSON, ustawia IP,
  robi DHCP probe, testuje IP i zapisuje openUrls do runtime file.

simplified_netrole_utils/netrole-firefox-window
  Helper Firefoksa. Tworzy/aktualizuje izolowany profil Firefoksa i uruchamia
  okno przeglądarki w namespace z przekazanymi URL-ami.

netrole-apply-eth-labels
  Generuje z ~/.config/simplified-netrole/config.json regułę udev i pliki .link
  (stała nazwa nr-* + odpalenie guarda po hotplugu) i wdraża je do /etc (sudo).
  Patrz sekcja "Etykiety i guard USB-Ethernet".

usb-netns-clean
  Narzędzie cleanup. Sprząta namespace, zabija procesy w namespace i próbuje
  oddać interfejsy do hosta.

netrole-usb-eth-guard  (system-install → /usr/local/sbin)
  Generyczny guard hotplugu. Po podłączeniu adaptera "odbiera" go
  NetworkManagerowi (autoconnect no, disconnect, flush), zostawiając link UP,
  żeby NM widział go jako disconnected, nie unavailable.
```

---

## Do czego to jest

`simplified_netrole` jest do takich zadań:

- szybki dostęp do paneli lokalnych urządzeń sieciowych,
- testowanie AP/routerów/CPE na różnych podsieciach,
- praca z urządzeniami bez DHCP,
- praca z urządzeniami, które mają panel np. pod `192.168.10.1`, `192.168.10.2`, `192.168.10.3`,
- odizolowanie testowej karty Ethernet od hostowego NetworkManagera,
- uruchamianie oddzielnych okien/profili Firefoksa per namespace,
- równoległa praca na kilku adapterach USB Ethernet.

Przykład mentalny:

```text
host Linux Mint
├── normalna sieć hosta: enp4s0f1 / Wi-Fi / Internet
├── usbwan-1 namespace
│   └── eth0 = dawny nr-usbc0
│       ├── 192.168.1.50/24
│       └── 192.168.10.50/24
└── usbwan-2 namespace
    └── eth0 = dawny nr-usba0
        ├── 192.168.1.51/24
        └── 192.168.10.51/24
```

---

## Czego to nie robi

To nie jest pełny lab systemowy jak VM/KVM.

Nie zakładaj, że to narzędzie dobrze testuje:

- pełne `systemd`,
- pełny NetworkManager wewnątrz izolowanego systemu,
- realny DHCP server działający jako osobny system,
- trwałe zmiany systemowe w gościu,
- scenariusze, w których chcesz bezpiecznie psuć cały system.

Do agresywnych testów systemowych lepsze jest KVM/libvirt + snapshot.

To narzędzie jest hostowym helperem do izolowania fizycznych kart i uruchamiania przeglądarki w danym network namespace.

---

## Wymagania

Minimalnie:

```text
bash
iproute2: ip, ip netns
sudo
NetworkManager / nmcli
Firefox
python3
dhclient
runuser
```

Na Linux Mint / Ubuntu typowo:

```bash
sudo apt install iproute2 network-manager firefox python3 isc-dhcp-client util-linux
```

Znaczenie:

```text
iproute2
  Tworzy namespace, przenosi interfejsy, ustawia IP i trasy.

NetworkManager / nmcli
  Skrypt odłącza interfejs USB od hostowego NetworkManagera przed przeniesieniem.

Firefox
  Uruchamiany w namespace jako użytkownik docelowy.

python3
  Helper używa go do parsowania JSON-a i wyliczania sieci z CIDR.

dhclient
  Używane w trybach DHCP.
```

---

## Instalacja / układ plików

Pakiet jest przygotowany pod instalację do:

```text
~/.local/bin
```

Docelowy układ po instalacji:

```text
~/.local/bin/simplified_netrole
~/.local/bin/usb-netns-clean
~/.local/bin/simplified_netrole_utils/netrole-firefox-window
~/.local/bin/simplified_netrole_utils/netrole-netns-network
~/.local/bin/netrole-apply-eth-labels
~/.local/share/simplified-netrole/config.example.json
```

Instalacja przez Stow (zalecana, z katalogu głównego repozytorium):

```bash
./run.sh install simplified_netrole
```

Instalacja obejmuje też część **systemową** (`system-install`) — guard
`/usr/local/sbin/netrole-usb-eth-guard` kopiowany przez sudo. Zobacz sekcję
[Etykiety i guard USB-Ethernet](#etykiety-i-guard-usb-ethernet), żeby dokończyć
konfigurację sprzętu.

Deinstalacja:

```bash
netrole-apply-eth-labels --remove                # usuwa wygenerowane reguły udev + .link (rób to PRZED odinstalowaniem pakietu)
./run.sh uninstall simplified_netrole            # usuwa część user + guard
```

Pliki są zarządzane przez GNU Stow — nie kopiuj ich ręcznie do `$HOME`, żeby uniknąć konfliktów przy przyszłych aktualizacjach lub deinstalacji.

Po instalacji katalog `~/.local/bin` musi być na `PATH`.

---

## Etykiety i guard USB-Ethernet

Zanim `simplified_netrole` przeniesie kartę do namespace, adapter USB-Ethernet
powinien mieć **stałą nazwę** (konwencja `nr-*`, np. `nr-usba0`) i nie być
przejmowany przez hostowy NetworkManager. Załatwiają to trzy elementy:

- `/usr/local/sbin/netrole-usb-eth-guard` — generyczny guard (część
  `system-install`, wersjonowany, instalowany przez `./run.sh install`).
- `/etc/systemd/network/09-<linkName>.link` — mapuje MAC → stała nazwa.
- `/etc/udev/rules.d/99-netrole-usb-eth-labels.rules` — etykiety + odpalenie
  guarda po `ACTION=="add"`.

Pliki `.link` i reguła udev zawierają **MAC-i konkretnego sprzętu**, więc nie są
w repo — generuje je `netrole-apply-eth-labels` z Twojego lokalnego configu.

### Konfiguracja

1. Otwórz config i wpisz realne MAC-i (`~/.local/share/simplified-netrole/config.example.json`
   to wzorzec; realny plik to `~/.config/simplified-netrole/config.json`, seedowany
   przy instalacji):

   ```jsonc
   "NR_USBA0": {
     "mac": "aa:bb:cc:dd:ee:01",   // przykład — wpisz REALNY MAC swojego adaptera
     "linkName": "nr-usba0",        // stała nazwa (musi pasować do ^nr-[a-z0-9]+$)
     "role": "USB-A",
     "dhcpMode": "probe", ...        // pola sieciowe używa netrole-netns-network
   }
   ```

   MAC znajdziesz np.: `ip -o link show | grep -i <coś>` albo
   `nmcli -g GENERAL.HWADDR device show <iface>`.

2. Podgląd (bez zmian w systemie):

   ```bash
   netrole-apply-eth-labels --print
   ```

3. Wdrożenie (poprosi o sudo — zapisuje `/etc/...` i przeładowuje udev):

   ```bash
   netrole-apply-eth-labels
   ```

4. Podłącz adapter ponownie. Nazwa `.link` i guard zadziałają na hotplug; log:

   ```bash
   journalctl -t netrole-usb-eth-guard
   nmcli device        # interfejs powinien być "disconnected", nie "unavailable"
   ```

Usunięcie wygenerowanych plików: `netrole-apply-eth-labels --remove`.

> Uwaga: `netrole-apply-eth-labels` odmówi wdrożenia, dopóki w configu jest
> placeholderowy MAC `00:00:00:00:00:00`.

---

## Szybki start

Normalne uruchomienie:

```bash
simplified_netrole
```

Jeśli skrypt potrzebuje roota, potrafi ponownie uruchomić się przez `sudo`.

Ręcznie z katalogu repo:

```bash
cd ~/repos/grz-workstation-tools/packages/simplified_netrole
./install/.local/bin/simplified_netrole
```

Edycja configu:

```bash
simplified_netrole --editconfig
```

Pokazanie ścieżki configu:

```bash
simplified_netrole --config-path
```

Awaryjny cleanup:

```bash
sudo usb-netns-clean
```

---

## Główny workflow

Po uruchomieniu `simplified_netrole` dzieje się mniej więcej to:

```text
1. Skrypt ustala realnego użytkownika:
   REAL_USER, REAL_HOME, REAL_UID.

2. Wybiera najniższy wolny slot:
   usbwan-1, usbwan-2, usbwan-3, ...

3. Pokazuje fizyczne interfejsy Ethernet.

4. Wybierasz interfejs, np. nr-usbc0.

5. Skrypt:
   - sprawdza, czy interfejs istnieje,
   - ostrzega przed interfejsem internal/PCI,
   - odłącza interfejs od hostowego NetworkManagera,
   - tworzy namespace, np. usbwan-1,
   - przenosi interfejs do namespace,
   - zmienia jego nazwę w namespace na eth0.

6. Uruchamia helper netrole-netns-network:
   - czyta config JSON,
   - proponuje ustawienia dla profilu interfejsu,
   - ustawia /etc/netns/usbwan-1/resolv.conf (z configu lub domyślnie 1.1.1.1/8.8.8.8),
   - ustawia statyczne IP,
   - robi test ping,
   - opcjonalnie robi DHCP probe,
   - zapisuje openUrls do /run/simplified-netrole/<NS>/open-urls.

7. Uruchamia helper netrole-firefox-window:
   - w tym samym namespace,
   - jako realny użytkownik,
   - z profilem Firefoksa dla slotu,
   - z URL-ami z openUrls.

8. Po zakończeniu / Ctrl+C:
   - cleanup przenosi eth0 z namespace z powrotem do hosta,
   - przywraca nazwę interfejsu,
   - usuwa namespace,
   - zostawia adapter USB na hoście jako rozłączony/autoconnect=no.
```

---

## Konfiguracja JSON

Config jest lokalny dla użytkownika:

```text
~/.config/simplified-netrole/config.json
```

Uwaga: helper sieciowy działa jako root, ale config rozwiązuje przez `SUDO_USER`, więc przy normalnym:

```bash
sudo simplified_netrole
```

config nadal jest brany z home użytkownika, np.:

```text
/home/<user>/.config/simplified-netrole/config.json
```

Przykładowy config:

```json
{
  "_defaults": {
    "dhcpTimeout": 8,
    "onOffer": "add",
    "dnsServers": ["1.1.1.1", "8.8.8.8"]
  },
  "NR_USBA0": {
    "dhcpMode": "probe",
    "staticAddrs": ["192.168.1.51/24", "192.168.10.51/24"],
    "testIps": ["192.168.1.1", "192.168.10.2"],
    "openUrls": ["http://192.168.10.1/", "http://192.168.10.2/"]
  },
  "NR_USBC0": {
    "dhcpMode": "probe",
    "staticAddrs": ["192.168.1.50/24", "192.168.10.50/24"],
    "testIps": ["192.168.1.1", "192.168.10.3"],
    "openUrls": ["http://192.168.10.1/", "http://192.168.10.3/"],
    "dnsServers": ["192.168.1.1"]
  }
}
```

Walidacja JSON-a:

```bash
python3 -m json.tool ~/.config/simplified-netrole/config.json >/dev/null
```

Jeśli komenda nic nie wypisze, JSON jest poprawny składniowo.

---

## Profile per interfejs

Config jest kluczowany po oryginalnej nazwie fizycznego interfejsu, nie po runtime slocie `usbwan-1`.

Przykład:

```text
nr-usba0 -> NR_USBA0
nr-usbc0 -> NR_USBC0
```

Dlaczego tak:

```text
usbwan-1 / usbwan-2 to tylko wolne sloty runtime.
Dziś nr-usbc0 może dostać usbwan-1, a jutro usbwan-2.
Interfejs nr-usbc0 jest stabilniejszym kluczem niż slot.
```

Helper pokazuje przy starcie:

```text
Klucz profilu: nr-usbc0
Suffix configu: NR_USBC0
Plik configu: /home/<user>/.config/simplified-netrole/config.json
```

Jeśli wartości są w configu, możesz wciskać `Enter`, aby ich użyć.

---

## Tryby DHCP

Pole:

```json
"dhcpMode": "probe"
```

Obsługiwane tryby:

```text
try
  Próbuje DHCP przez dhcpTimeout sekund.
  Jeśli DHCP nie odpowie, idzie dalej.

probe
  Pyta DHCP, ale nie przełącza automatycznie konfiguracji.
  Jeśli DHCP znajdzie ofertę, pyta co zrobić.

off
  Nie pyta DHCP.
  Ustawia tylko statyczne adresy, jeśli są podane.

required
  DHCP musi się udać.
  Jeśli się nie uda, helper kończy się błędem.

skip
  Pomija konfigurację sieci.
```

Najwygodniejszy tryb do paneli lokalnych AP/routerów:

```json
"dhcpMode": "probe"
```

Wtedy można jednocześnie:

- mieć statyczne IP do paneli,
- sprawdzić, czy w sieci jest DHCP,
- opcjonalnie dodać adres z DHCP jako dodatkowy.

---

## onOffer

Pole globalne:

```json
"_defaults": {
  "onOffer": "add"
}
```

Określa domyślną akcję, gdy `dhcpMode=probe` znajdzie ofertę DHCP.

Wartości:

```text
add
  Dodaj adres z DHCP jako dodatkowy adres na eth0.

static / s
  Zostań przy aktualnych/statycznych adresach.

dhcp / d
  Przełącz całkowicie na DHCP i usuń statyczne adresy.

ask
  Zawsze pytaj.
```

Praktyczna rekomendacja:

```json
"onOffer": "add"
```

Dzięki temu po wykryciu DHCP można wcisnąć `Enter` i dodać adres jako dodatkowy, bez kasowania statycznych adresów serwisowych.

---

## dnsServers

Pole (opcjonalne, w `_defaults` lub per-profil):

```json
"dnsServers": ["1.1.1.1", "8.8.8.8"]
```

Helper zapisuje to do `/etc/netns/<NS>/resolv.conf` przed konfiguracją IP.

Jeśli pola nie ma w configu ani nie podano `--dns`, używane są domyślne serwery:

```text
1.1.1.1
8.8.8.8
```

Per-profil nadpisuje `_defaults`:

```json
{
  "_defaults": {
    "dnsServers": ["1.1.1.1", "8.8.8.8"]
  },
  "NR_USBC0": {
    "dnsServers": ["192.168.1.1"]
  }
}
```

W trybie interaktywnym helper pyta o DNS po wyborze trybu DHCP i adresów statycznych.
Wciśnięcie `Enter` używa wartości z configu, `-` pomija (zostawia domyślne).

Z CLI:

```bash
netrole-netns-network --namespace usbwan-1 --iface eth0 --dns 192.168.1.1 --dns 8.8.8.8
```

### DNS z oferty DHCP

Jeśli DHCP zwróci serwery DNS w opcji `domain-name-servers`, helper je wykrywa i pyta
czy je przyjąć — niezależnie od tego co jest w configu.

W trybie `probe` (po wyborze co zrobić z ofertą IP):

```text
DNS z oferty DHCP: 192.168.1.1
Użyć DNS z DHCP? [T/n, Enter=T]:
```

W trybach `try` i `required` (gdy DHCP się uda) DNS z leasu jest przyjmowany
automatycznie bez pytania.

Priorytet DNS (od najwyższego):
1. DNS z DHCP (jeśli DHCP się udało i zwróciło DNS)
2. `--dns` z CLI
3. `dnsServers` z configu (per-profil lub `_defaults`)
4. Domyślne: `1.1.1.1`, `8.8.8.8`

---

## Adresy statyczne i trasy

Pole:

```json
"staticAddrs": [
  "192.168.1.50/24",
  "192.168.10.50/24"
]
```

Helper robi z tego:

```bash
ip addr add 192.168.1.50/24 dev eth0
ip route replace 192.168.1.0/24 dev eth0 src 192.168.1.50

ip addr add 192.168.10.50/24 dev eth0
ip route replace 192.168.10.0/24 dev eth0 src 192.168.10.50
```

Gateway nie jest potrzebny do komunikacji z urządzeniem w tej samej podsieci.

Przykład:

```text
eth0: 192.168.10.50/24
panel: 192.168.10.3

Ruch do 192.168.10.3 idzie lokalnie po eth0.
Default gateway nie jest potrzebny.
```

---

## testIps

Pole:

```json
"testIps": [
  "192.168.1.1",
  "192.168.10.3"
]
```

Helper wykonuje dla każdego adresu:

```bash
ping -c 1 -W 1 <IP>
ip neigh show dev eth0
```

To pomaga szybko zobaczyć:

```text
REACHABLE
  Host odpowiedział.

INCOMPLETE
  ARP/neighbor nie odpowiedział.

100% packet loss
  Brak odpowiedzi na ping. Panel HTTP może jednak czasem działać, jeśli ICMP jest blokowany.
```

---

## openUrls i Firefox

Pole:

```json
"openUrls": [
  "http://192.168.10.1/",
  "http://192.168.10.3/"
]
```

To jest źródło prawdy dla tego, co ma otworzyć Firefox.

Nie używamy już wykrywania gatewaya jako URL-a do otwarcia, bo w trybie serwisowym panel urządzenia nie musi być default gatewayem.

Flow:

```text
config.json
  -> netrole-netns-network
  -> /run/simplified-netrole/<NS>/open-urls
  -> simplified_netrole
  -> argumenty do netrole-firefox-window
  -> Firefox: start page + openUrls
```

Plik runtime:

```text
/run/simplified-netrole/usbwan-1/open-urls
```

Przykładowa zawartość:

```text
http://192.168.10.1/
http://192.168.10.3/
```

Firefox dostaje URL-e jako argumenty:

```bash
netrole-firefox-window usbwan-1 eth0 \
  http://192.168.10.1/ \
  http://192.168.10.3/
```

---

## Firefox start page

`netrole-firefox-window` zawsze tworzy stronę startową, np.:

```text
~/.cache/netrole-firefox/pages/<label>/start.html
```

Strona pokazuje:

```text
Profile
Interface
Runtime iface
MAC
WM_CLASS
Open URLs
```

Jeśli widzisz na tej stronie:

```text
Open URLs: brak
```

to znaczy, że helper Firefoksa nie dostał URL-i jako argumentów. Wtedy sprawdź:

```bash
sudo cat /run/simplified-netrole/usbwan-1/open-urls
```

oraz miejsce w `simplified_netrole`, które odpala `netrole-firefox-window`.

---

## Wyjątki certyfikatów HTTPS

Lokalne panele często używają self-signed certów. Wtedy Firefox pokazuje ostrzeżenie:

```text
Warning: Security Risk
MOZILLA_PKIX_ERROR_SELF_SIGNED_CERT
```

W profilach netrole preferencje Firefoksa powinny ułatwiać pracę labową:

```js
user_pref("browser.xul.error_pages.expert_bad_cert", true);
user_pref("security.certerrors.permanentOverride", true);

user_pref("dom.security.https_only_mode", false);
user_pref("dom.security.https_only_mode_ever_enabled", false);
user_pref("dom.security.https_first", false);
user_pref("dom.security.https_first_schemeless", false);
```

Po pierwszym kliknięciu:

```text
Proceed to 192.168.x.x
```

wyjątek powinien zostać zapamiętany w tym profilu Firefoksa.

Nie kasować tych plików profilu:

```text
cert_override.txt
cert9.db
key4.db
pkcs11.txt
```

Czyszczenie `sessionstore*` jest OK i nie usuwa wyjątków certyfikatów.

Ważne: wyjątki są per profil Firefoksa. Jeśli ten sam panel otworzysz z innego profilu, Firefox może zapytać ponownie.

---

## Komendy

### Normalne uruchomienie

```bash
simplified_netrole
```

### Uruchomienie z repo

```bash
cd ~/repos/grz-workstation-tools/packages/simplified_netrole
./install/.local/bin/simplified_netrole
```

### Edycja configu

```bash
simplified_netrole --editconfig
```

Otwiera:

```text
~/.config/simplified-netrole/config.json
```

przez `code`.

### Pokazanie ścieżki configu

```bash
simplified_netrole --config-path
```

### Manualne otwarcie profilu Firefoksa

```bash
simplified_netrole browser usbwan-1 eth0
```

Z ręcznymi URL-ami:

```bash
simplified_netrole browser usbwan-1 eth0 \
  http://192.168.10.1/ \
  http://192.168.10.3/
```

### Cleanup

```bash
sudo usb-netns-clean
```

### Zostawienie namespace po zakończeniu

```bash
AUTO_CLEANUP=0 simplified_netrole
```

Wtedy ręcznie sprzątasz:

```bash
sudo usb-netns-clean
```

### Sprawdzenie namespace

```bash
sudo ip netns list
```

### Sprawdzenie adresów w namespace

```bash
sudo ip netns exec usbwan-1 ip -br addr
sudo ip netns exec usbwan-1 ip route
```

### Test HTTP w namespace

```bash
sudo ip netns exec usbwan-1 curl -I --connect-timeout 5 http://192.168.10.1/ || true
```

---

## Opis plików w pakiecie

### `simplified_netrole`

Główna komenda.

Odpowiada za:

```text
root escalation
ustalenie REAL_USER/REAL_HOME/REAL_UID
wybór wolnego slotu usbwan-N
wybór fizycznego interfejsu
safety checks dla interfejsu
przygotowanie interfejsu na hoście
utworzenie namespace
przeniesienie interfejsu do namespace
uruchomienie helpera konfiguracji sieci
uruchomienie helpera Firefoksa
cleanup po zakończeniu
```

### `simplified_netrole_utils/netrole-netns-network`

Helper konfiguracji sieci.

Odpowiada za:

```text
czytanie ~/.config/simplified-netrole/config.json
mapowanie profile key -> suffix configu
zapis /etc/netns/<NS>/resolv.conf (dnsServers z configu lub 1.1.1.1/8.8.8.8)
ustawianie adresów statycznych
tworzenie tras lokalnych
testowanie IP
DHCP try/probe/off/required
dodanie DHCP jako dodatkowy adres
zapis openUrls do /run/simplified-netrole/<NS>/open-urls
```

### `simplified_netrole_utils/netrole-firefox-window`

Helper Firefoksa.

Odpowiada za:

```text
parsowanie argumentów PROFILE_NAME IFACE [URL...]
zbudowanie etykiety okna/profilu z profilu, interfejsu i MAC
wygenerowanie start.html
wygenerowanie user.js/prefs.js
wyczyszczenie sessionstore
uruchomienie Firefoksa z osobnym profilem
otwarcie start page + URL-i z openUrls
```

### `usb-netns-clean`

Narzędzie awaryjnego i ręcznego cleanupu.

Odpowiada za:

```text
zabijanie procesów w namespace
zabijanie dhclient dla namespace
przeniesienie eth0 z namespace do hosta
przywrócenie nazwy interfejsu, jeśli da się ją ustalić
usunięcie namespace
zostawienie adaptera USB jako disconnected/autoconnect=no
```

---

## Gdzie czego szukać w kodzie

### W `simplified_netrole`

Szukaj funkcji:

```text
_simplified_netrole_script_dir
  Ustala katalog skryptu.

_simplified_netrole_firefox_helper
  Zwraca ścieżkę do helpera Firefoksa.

_simplified_netrole_open_browser
  Tryb ręczny: simplified_netrole browser PROFILE IFACE [URL...].

netrole_config_owner_user / netrole_config_path / netrole_edit_config
  Obsługa --editconfig i --config-path.

_simplified_netrole_netns_network_helper
  Zwraca ścieżkę do helpera sieciowego.

configure_network_in_namespace
  Odpala netrole-netns-network z --namespace, --iface, --profile-key.

setup_ns
  Tworzy namespace, przenosi interfejs i odpala konfigurację sieci.

launch_firefox
  Wczytuje /run/simplified-netrole/<NS>/open-urls i przekazuje je do Firefoksa.

cleanup_one / cleanup_all
  Sprzątanie namespace i interfejsów.

wait_before_cleanup
  Czeka, aby użytkownik mógł pracować w Firefoxie przed cleanupem.
```

### W `netrole-netns-network`

Szukaj funkcji:

```text
parse_args
  Obsługa --namespace, --iface, --profile-key, --config.

profile_suffix
  Zamienia np. nr-usbc0 na NR_USBC0.

resolve_config_file
  Ustala ~/.config/simplified-netrole/config.json realnego użytkownika.

json_config_scalar / json_config_array
  Czyta wartości z JSON-a.

interactive_menu
  Menu DHCP/static/skip/dns i propozycje z configu.

write_resolv_conf
  Zapisuje /etc/netns/<NS>/resolv.conf z dnsServers (lub domyślnie 1.1.1.1/8.8.8.8).

apply_static_addrs
  Ustawia IP i trasy lokalne.

test_ips
  Robi ping i pokazuje neighbor state.

probe_dhcp
  Robi DHCP probe z timeoutem.

add_dhcp_offer_as_extra_addr
  Dodaje DHCP jako dodatkowy adres.

switch_to_real_dhcp
  Przełącza namespace całkowicie na DHCP.

write_open_urls_runtime_file
  Zapisuje openUrls do /run/simplified-netrole/<NS>/open-urls.

configure_network
  Główna orkiestracja helpera sieciowego.
```

### W `netrole-firefox-window`

Szukaj sekcji:

```text
argument parsing
  PROFILE_NAME IFACE [URL...]

START_PAGE generation
  Tworzy start.html.

user.js generation
  Preferencje Firefoksa dla profilu netrole.

session cleanup
  Czyści sessionstore, ale nie certyfikaty.

FIREFOX_ARGS
  Buduje argumenty do firefox.
```

---

## Pliki runtime

### `/run/simplified-netrole/<NS>/open-urls`

Tworzony przez `netrole-netns-network`.

Przykład:

```text
/run/simplified-netrole/usbwan-1/open-urls
```

Zawiera URL-e, które mają zostać otwarte przez Firefox.

### `/run/netrole-dhcp-probe-<NS>/dhclient.log`

Log z DHCP probe.

Przykład:

```text
/run/netrole-dhcp-probe-usbwan-1/dhclient.log
```

Przydatne, gdy DHCP nie znalazło oferty albo helper nie wykrył maski/routera.

### `/run/simplified-netrole/<NS>/firefox.log`

Log helpera Firefoksa.

Przykład:

```text
/run/simplified-netrole/usbwan-1/firefox.log
```

Jeśli Firefox nie startuje, główny skrypt pokazuje ten log.

### Profile Firefoksa

Przykład:

```text
~/.local/share/netrole/firefox-profiles/usbwan-1
```

Profil jest trwały. Dzięki temu Firefox może pamiętać wyjątki certyfikatów dla danego profilu.

---

## Sprzątanie / cleanup

Normalnie `simplified_netrole` sprząta po sobie.

Przy `Ctrl+C` również powinien wykonać cleanup przez trap.

Ręczne sprzątanie:

```bash
sudo usb-netns-clean
```

Po cleanupie sprawdź:

```bash
sudo ip netns list
ip -br link
nmcli device status
```

Oczekiwane:

```text
namespace usbwan-N znika
interfejs wraca na hosta jako nr-usba0 / nr-usbc0
adapter USB zostaje rozłączony/autoconnect=no
```

---

## Typowe scenariusze

### AP bez DHCP, panel w `192.168.10.x`

Config:

```json
"NR_USBC0": {
  "dhcpMode": "off",
  "staticAddrs": [
    "192.168.10.50/24"
  ],
  "testIps": [
    "192.168.10.3"
  ],
  "openUrls": [
    "http://192.168.10.3/"
  ]
}
```

Efekt:

```text
brak DHCP
ustawiane tylko IP statyczne
Firefox otwiera panel AP
```

### AP/router z DHCP, ale chcesz zachować IP serwisowe

Config:

```json
"NR_USBC0": {
  "dhcpMode": "probe",
  "staticAddrs": [
    "192.168.1.50/24",
    "192.168.10.50/24"
  ],
  "testIps": [
    "192.168.1.1",
    "192.168.10.3"
  ],
  "openUrls": [
    "http://192.168.10.1/",
    "http://192.168.10.3/"
  ]
}
```

Wybór po DHCP:

```text
a / add
```

Efekt:

```text
zostają statyczne IP
dochodzi adres z DHCP jako dodatkowy
Firefox otwiera openUrls z configu
```

### Dwie karty USB Ethernet

Przykład:

```json
"NR_USBA0": {
  "dhcpMode": "probe",
  "staticAddrs": [
    "192.168.1.51/24",
    "192.168.10.51/24"
  ],
  "testIps": [
    "192.168.1.1",
    "192.168.10.2"
  ],
  "openUrls": [
    "http://192.168.10.1/",
    "http://192.168.10.2/"
  ]
},
"NR_USBC0": {
  "dhcpMode": "probe",
  "staticAddrs": [
    "192.168.1.50/24",
    "192.168.10.50/24"
  ],
  "testIps": [
    "192.168.1.1",
    "192.168.10.3"
  ],
  "openUrls": [
    "http://192.168.10.1/",
    "http://192.168.10.3/"
  ]
}
```

Uwaga: jeśli oba adaptery są podłączone do tej samej fizycznej sieci L2, nie dawaj im tego samego statycznego IP.

---

## Troubleshooting

### `Open URLs: brak` na stronie startowej Firefoksa

Znaczenie:

```text
netrole-firefox-window nie dostał URL-i jako argumentów
```

Sprawdź, czy helper sieciowy zapisał plik:

```bash
sudo cat /run/simplified-netrole/usbwan-1/open-urls
```

Jeśli plik istnieje i zawiera URL-e, problem jest w `launch_firefox` w `simplified_netrole`.

Szukaj:

```bash
grep -nE 'launch_firefox|open-urls|OPEN_URLS|netrole-firefox-window' \
  install/.local/bin/simplified_netrole
```

### `IFACE: unbound variable`

Przyczyna:

```text
netrole-firefox-window używa IFACE, ale ustawia tylko iface małymi literami
albo używa IFACE przed parsowaniem argumentów
```

Początek helpera powinien ustawiać:

```bash
PROFILE_NAME="${1:?}"
IFACE="${2:?}"

shift 2

OPEN_URLS=("$@")
```

### DHCP wisi na `DHCPDISCOVER`

Stary błąd: główny skrypt odpalał DHCP obowiązkowo.

Nowy model:

```text
dhcpMode=try/probe/off/required
dhcpTimeout=8
```

Jeśli urządzenie nie ma DHCP, użyj:

```json
"dhcpMode": "off"
```

albo:

```json
"dhcpMode": "probe"
```

### DHCP znajduje IP, ale nie ma default route

To jest normalne przy `onOffer=add`, bo adres z DHCP jest dodawany jako dodatkowy, a nie jako pełna konfiguracja DHCP.

Do paneli lokalnych default route zwykle nie jest potrzebny. Do otwierania paneli używaj `openUrls`, nie gateway detection.

### Ping do panelu nie odpowiada, ale HTTP działa

Niektóre urządzenia blokują ICMP albo odpowiadają niestabilnie.

Sprawdź HTTP:

```bash
sudo ip netns exec usbwan-1 curl -I --connect-timeout 5 http://192.168.10.3/ || true
```

### Cert warning wraca mimo kliknięcia Proceed

Sprawdź:

```bash
ls -l ~/.local/share/netrole/firefox-profiles/usbwan-1/cert_override.txt \
      ~/.local/share/netrole/firefox-profiles/usbwan-1/cert9.db \
      ~/.local/share/netrole/firefox-profiles/usbwan-1/key4.db \
      ~/.local/share/netrole/firefox-profiles/usbwan-1/pkcs11.txt 2>/dev/null
```

Nie wolno kasować katalogu profilu, jeśli wyjątki mają zostać.

Pamiętaj: wyjątek jest per profil i per cert fingerprint. Jeśli urządzenie wygeneruje nowy cert, Firefox zapyta ponownie.

### Config nie jest widoczny pod sudo

Helper używa `SUDO_USER`, więc normalnie powinien czytać:

```text
/home/<user>/.config/simplified-netrole/config.json
```

Sprawdź w logu helpera:

```text
Plik configu: ...
Config: załadowany / brak
```

### Namespace został po błędzie

Sprzątnij ręcznie:

```bash
sudo usb-netns-clean
```

albo sprawdź:

```bash
sudo ip netns list
```

---

## Uwagi bezpieczeństwa

To narzędzie przenosi fizyczne interfejsy sieciowe między hostem a namespace.

Uważaj szczególnie na:

```text
enp4s0f1
wlp3s0
interfejsy PCI/internal
aktywny interfejs hosta z Internetem
```

Skrypt pokazuje ostrzeżenie dla prawdopodobnych interfejsów internal/PCI. Typowe bezpieczne interfejsy do tego workflow to nazwane adaptery USB:

```text
nr-usba0
nr-usbc0
```

Nie używaj tego narzędzia do interfejsu, przez który aktualnie utrzymujesz krytyczne połączenie z Internetem lub zdalną sesję.

Dla testów, które mają realnie zmieniać system, NetworkManager, DHCP server, NAT, bridge lub systemd, używaj KVM/libvirt i snapshotów.

---

## Notatki projektowe

### Dlaczego config jest per interfejs, nie per `usbwan-N`

`usbwan-N` to slot runtime. Jest dobry do namespace i profilu tymczasowego, ale nie jest stabilnym kluczem konfiguracji.

Stabilny klucz to nazwa fizycznego adaptera:

```text
nr-usba0
nr-usbc0
```

Dlatego config używa:

```text
NR_USBA0
NR_USBC0
```

### Dlaczego openUrls zamiast gateway detection

W starym modelu Firefox próbował otwierać gateway wykryty z routingu.

To było błędne dla trybu serwisowego, bo:

```text
panel AP może być pod 192.168.10.3
ale default gateway może nie istnieć
albo może być pod 192.168.1.1
albo panel nie musi być gatewayem
```

Teraz źródłem prawdy są jawne URL-e:

```json
"openUrls": [
  "http://192.168.10.1/",
  "http://192.168.10.3/"
]
```

### Dlaczego Firefox profile są per slot

Aktualny model:

```text
usbwan-1 -> profile usbwan-1
usbwan-2 -> profile usbwan-2
```

Zaleta:

```text
proste mapowanie namespace -> Firefox profile
```

Wada:

```text
wyjątki certyfikatów są per slot, nie per fizyczny adapter
```

Możliwa przyszła zmiana:

```text
profil Firefoksa per profile key / interfejs, np. nr-usba0, nr-usbc0
```

Na razie config jest per interfejs, a profile Firefoksa są per slot.

### Dlaczego helpery są osobno

`simplified_netrole` powinien pozostać orkiestratorem.

Szczegóły są w helperach:

```text
netrole-netns-network
  cała logika IP/DHCP/config/openUrls

netrole-firefox-window
  cała logika profilu i startu Firefoksa
```

To ułatwia debugowanie i ręczne testy.

---

## Minimalna checklista po zmianach w kodzie

Po każdej zmianie:

```bash
cd ~/repos/grz-workstation-tools/packages/simplified_netrole

python3 -m json.tool ~/.config/simplified-netrole/config.json >/dev/null

bash -n install/.local/bin/simplified_netrole
bash -n install/.local/bin/simplified_netrole_utils/netrole-netns-network
bash -n install/.local/bin/simplified_netrole_utils/netrole-firefox-window
bash -n install/.local/bin/usb-netns-clean
```

Oczekiwany efekt: brak outputu.

Szybki grep kontrolny:

```bash
grep -RInE 'GATEWAY_URL|NETROLE_FIREFOX_OPEN_GATEWAY|URL="\$\{3:-\}"|Pobieram adres przez DHCP' \
  install/.local/bin || true
```

Oczekiwane: brak starych mechanizmów gateway URL / obowiązkowego DHCP w głównym flow.

---

## Aktualny skrót mentalny

```text
simplified_netrole
  wybiera kartę i namespace
  przenosi kartę do namespace
  odpala netrole-netns-network
  czyta open-urls z /run
  odpala netrole-firefox-window z URL-ami

netrole-netns-network
  czyta ~/.config/simplified-netrole/config.json
  ustawia IP/DHCP/testy
  zapisuje /run/simplified-netrole/<NS>/open-urls

netrole-firefox-window
  przyjmuje PROFILE IFACE [URL...]
  tworzy start page
  uruchamia Firefox z osobnym profilem

usb-netns-clean
  awaryjnie sprząta namespace i oddaje interfejsy do hosta
```
