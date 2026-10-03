zshreloadcomp() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  local default_compdump="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump"

  if [[ -n ${ZSH_COMPDUMP:-} ]]; then
    rm -f -- "$ZSH_COMPDUMP" "$ZSH_COMPDUMP.zwc"
  fi
  rm -f -- "$HOME"/.zcompdump*(N) "$default_compdump" "$default_compdump.zwc"

  exec zsh
}
