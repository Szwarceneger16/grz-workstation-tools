get_app_mem() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

  local pat="${1}"

  # Zbierz PID-y + pełne linie z pgrep -af
  local line pid
  while IFS= read -r line; do
    pid="${line%% *}"    # PID to pierwsze pole
    # Pełny cmdline (nul -> spacje)
    local cmd
    cmd="$(tr '\0' ' ' < /proc/"$pid"/cmdline 2>/dev/null)"

    # Szukaj --max-old-space-size
    local maxold
    maxold="$(printf '%s' "$cmd" | grep -o -- '--max-old-space-size=[0-9]\+' || true)"

    # NODE_OPTIONS z /proc/<pid>/environ (nul -> nowe linie)
    local nodeopts
    nodeopts="$(tr '\0' '\n' < /proc/"$pid"/environ 2>/dev/null | grep -m1 '^NODE_OPTIONS=' || true)"

    printf 'PID=%s | max-old=%s | %s\nCMD: %s\n\n' \
      "$pid" "${maxold:--}" "${nodeopts:-NODE_OPTIONS=}" "$cmd"
  done < <(pgrep -af "$pat")
}
