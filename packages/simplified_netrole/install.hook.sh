#!/usr/bin/env bash
set -Eeuo pipefail

# Runs after stow on `./run.sh install simplified_netrole`. User-level only, no
# privilege elevation (check-repo forbids that token in hooks). Two jobs:
#   1. Seed ~/.config/simplified-netrole/config.json from the shipped example
#      if it doesn't exist yet, so a fresh install has a config to edit.
#   2. Print the next steps for the system-level guard (needs root, so the user
#      runs netrole-apply-eth-labels themselves after filling in real MACs).

REPO_ROOT="${GRZ_REPO_ROOT:?GRZ_REPO_ROOT is required}"
TARGET_DIR="${STOW_TARGET:-$HOME}"

example="$REPO_ROOT/packages/simplified_netrole/install/.local/share/simplified-netrole/config.example.json"
config_dir="$TARGET_DIR/.config/simplified-netrole"
config_file="$config_dir/config.json"

seeded=0
if [[ -e "$config_file" || -L "$config_file" ]]; then
  : # istniejący config (lub symlink) — nie dotykamy
elif [[ -L "$config_dir" ]]; then
  printf 'warning - %s jest symlinkiem, pomijam seed configu\n' "$config_dir" >&2
elif [[ ! -f "$example" ]]; then
  printf 'warning - brak przykładowego configu: %s\n' "$example" >&2
else
  mkdir -p -- "$config_dir"
  # zapis atomowy, bez podążania za ewentualnym symlinkiem podmienionym w wyścigu
  tmp="$(mktemp "$config_dir/.config.json.XXXXXX")"
  cat -- "$example" > "$tmp"
  mv -T -- "$tmp" "$config_file"
  seeded=1
fi

printf 'ok - simplified_netrole user files stowed in %s\n' "$TARGET_DIR"
if (( seeded )); then
  printf 'ok - seeded default config: %s\n' "$config_file"
fi

cat <<EOF
--
Guard USB-Ethernet (część systemowa, wymaga uprawnień roota — ten hook tego nie robi):
  1. Wpisz realne MAC-i adapterów w: $config_file
     (pola "mac"; nazwy interfejsów w "linkName", np. nr-usba0)
  2. Zainstaluj generyczny guard (system-install):
       ./run.sh install simplified_netrole   # kopiuje /usr/local/sbin/netrole-usb-eth-guard
  3. Wygeneruj i wdróż reguły udev + pliki .link z configu (poprosi o hasło roota):
       netrole-apply-eth-labels
     Podgląd bez zmian: netrole-apply-eth-labels --print
--
EOF
