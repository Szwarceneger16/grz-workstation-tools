make_icon_set() {
  local src_file="$1"
  local icon_name="$2"
  local size_px
  local icon_dir
  local -a icon_sizes=(16 24 32 48 64 128 256 512)

  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  if [[ -z "$src_file" || -z "$icon_name" ]]; then
    echo "ERR: użycie: make_icon_set <plik_źródłowy> <nazwa_ikony>" >&2
    return 1
  fi

  if [[ ! -f "$src_file" ]]; then
    echo "ERR: brak pliku: $src_file" >&2
    return 1
  fi

  echo "INFO: sprawdzam plik źródłowy"
  file "$src_file" || return 1
  identify -ping "$src_file" || {
    echo "ERR: ImageMagick nie potrafi odczytać pliku źródłowego" >&2
    return 1
  }

  for size_px in "${icon_sizes[@]}"; do
    icon_dir="$HOME/.local/share/icons/hicolor/${size_px}x${size_px}/apps"
    mkdir -p "$icon_dir" || return 1

    /usr/bin/convert "$src_file" -resize "${size_px}x${size_px}" "$icon_dir/${icon_name}.png" || {
      echo "ERR: nie udało się wygenerować rozmiaru ${size_px}x${size_px} dla ${icon_name}" >&2
      return 1
    }
  done

  echo "OK: wygenerowano wszystkie rozmiary ikon dla ${icon_name}"
}
