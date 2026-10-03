zshreloadcomp() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  local dump
  local zdotdir="${ZDOTDIR:-$HOME}"
  local default_cache_dump="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump"
  local -aU dumps

  [[ -n ${_comp_dumpfile:-} ]] && dumps+=("$_comp_dumpfile")
  [[ -n ${ZSH_COMPDUMP:-} ]] && dumps+=("$ZSH_COMPDUMP")
  dumps+=("$zdotdir/.zcompdump" "$default_cache_dump")

  for dump in "${dumps[@]}"; do
    rm -f -- "$dump" "$dump.zwc"
  done

  rm -f -- "$HOME"/.zcompdump*(N)
  [[ "$zdotdir" == "$HOME" ]] || rm -f -- "$zdotdir"/.zcompdump*(N)

  exec zsh
}
