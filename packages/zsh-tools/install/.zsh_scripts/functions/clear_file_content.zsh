  # czyści wskazany plik i otwiera go w nano
  # użycie: clear_file_content /ścieżka/do/pliku

clear_file_content() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

  local f="$1"
  if [[ -z "$f" ]]; then
    echo "Użycie: clear_file_content /ścieżka/do/pliku" >&2
    return 2
  fi

  : > "$f" || return
  nano "$f"
}
