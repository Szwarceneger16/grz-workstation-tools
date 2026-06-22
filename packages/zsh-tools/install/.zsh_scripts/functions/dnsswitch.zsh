dnsswitch() {
  emulate -L zsh -o pipefail

  local action="${1:-status}"
  local conf_file="/etc/systemd/resolved.conf.d/99-dnsswitch.conf"
  local temp_file=""
  local status_excerpt=""

  local -A profile_lines
  profile_lines=()

  profile_lines[auto]=''
  profile_lines[mullvad]='DNS=194.242.2.2#dns.mullvad.net 2a07:e340::2#dns.mullvad.net'
  profile_lines[mullvad-adblock]='DNS=194.242.2.3#adblock.dns.mullvad.net 2a07:e340::3#adblock.dns.mullvad.net'
  profile_lines[mullvad-base]='DNS=194.242.2.4#base.dns.mullvad.net 2a07:e340::4#base.dns.mullvad.net'
  profile_lines[mullvad-extended]='DNS=194.242.2.5#extended.dns.mullvad.net 2a07:e340::5#extended.dns.mullvad.net'
  profile_lines[mullvad-family]='DNS=194.242.2.6#family.dns.mullvad.net 2a07:e340::6#family.dns.mullvad.net'
  profile_lines[mullvad-all]='DNS=194.242.2.9#all.dns.mullvad.net 2a07:e340::9#all.dns.mullvad.net'
  profile_lines[quad9]='DNS=9.9.9.9#dns.quad9.net 149.112.112.112#dns.quad9.net 2620:fe::fe#dns.quad9.net 2620:fe::9#dns.quad9.net'
  profile_lines[cloudflare]='DNS=1.1.1.1#cloudflare-dns.com 1.0.0.1#cloudflare-dns.com 2606:4700:4700::1111#cloudflare-dns.com 2606:4700:4700::1001#cloudflare-dns.com'

  case "$action" in
    -h|--help|help)
      cmdhelp dnsswitch
      return 0
      ;;
    list)
      printf '%s\n' \
        auto \
        mullvad \
        mullvad-adblock \
        mullvad-base \
        mullvad-extended \
        mullvad-family \
        mullvad-all \
        quad9 \
        cloudflare
      return 0
      ;;
    status|current)
      if ! command -v resolvectl >/dev/null 2>&1; then
        print -u2 -- 'dnsswitch: brak polecenia resolvectl.'
        return 1
      fi

      status_excerpt="$(resolvectl status 2>/dev/null | sed -n '1,/^Link /p' | sed '$d')"
      if [[ -z "$status_excerpt" ]]; then
        resolvectl status
      else
        print -r -- "$status_excerpt"
      fi
      return 0
      ;;
  esac

  if ! command -v resolvectl >/dev/null 2>&1; then
    print -u2 -- 'dnsswitch: brak polecenia resolvectl.'
    return 1
  fi

  if ! systemctl is-active --quiet systemd-resolved; then
    print -u2 -- 'dnsswitch: systemd-resolved nie jest aktywny.'
    return 1
  fi

  if [[ ! -L /etc/resolv.conf ]] || [[ "$(readlink -f /etc/resolv.conf 2>/dev/null)" != "/run/systemd/resolve/stub-resolv.conf" ]]; then
    print -u2 -- 'dnsswitch: /etc/resolv.conf nie wskazuje na /run/systemd/resolve/stub-resolv.conf.'
    print -u2 -- 'dnsswitch: najpierw napraw tryb stub resolvera, potem wróć do przełączania profili.'
    return 1
  fi

  if [[ "$action" != 'auto' ]] && (( ! ${+profile_lines[$action]} )); then
    print -u2 -- "dnsswitch: nieznany profil: $action"
    print -u2 -- 'Użyj: dnsswitch list'
    return 1
  fi

  if [[ "$action" == 'auto' ]]; then
    sudo rm -f -- "$conf_file" \
      /etc/systemd/resolved.conf.d/90-dnsswitch.conf || return 1
  else
    temp_file="$(mktemp)" || return 1
cat > "$temp_file" <<EOFCONF
[Resolve]
DNS=
FallbackDNS=
Domains=

${profile_lines[$action]}
DNSSEC=no
DNSOverTLS=yes
Domains=~.
EOFCONF
    sudo install -m 0644 "$temp_file" "$conf_file" || {
      rm -f -- "$temp_file"
      return 1
    }
    rm -f -- "$temp_file"
  fi

  sudo systemctl restart systemd-resolved || return 1
  resolvectl flush-caches || return 1

  print --
  print -- "Aktywny profil: $action"
  print --
  resolvectl status | sed -n '1,/^Link /p' | sed '$d'
  print --
  print -- 'Uwaga: sekcja Link może dalej pokazywać DNS z DHCP (np. 192.168.1.1).'
  print -- 'Przy Domains=~. i Global DNS to globalny resolver obsługuje zwykłe zapytania.'
}
