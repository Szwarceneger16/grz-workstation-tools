zshreloadcomp() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  local dump
  local zdotdir="${ZDOTDIR:-$HOME}"
  local default_cache_dump="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump"
  local -aU dumps legacy_dumps

  [[ -n ${_comp_dumpfile:-} ]] && dumps+=("$_comp_dumpfile")
  [[ -n ${ZSH_COMPDUMP:-} ]] && dumps+=("$ZSH_COMPDUMP")
  dumps+=("$zdotdir/.zcompdump" "$default_cache_dump")

  for dump in "${dumps[@]}"; do
    # compinit accepts arbitrary -d paths, including non-file sinks such as
    # /dev/null. There is no stale file to remove in that case.
    if [[ -e "$dump" && ! -f "$dump" && ! -L "$dump" ]]; then
      continue
    fi

    if ! command rm -f -- "$dump" "$dump.zwc"; then
      print -u2 -- "zshreloadcomp: failed to remove completion dump: $dump"
      return 1
    fi
  done

  legacy_dumps=("$HOME"/.zcompdump*(N))
  if (( ${#legacy_dumps[@]} )) && ! command rm -f -- "${legacy_dumps[@]}"; then
    print -u2 -- "zshreloadcomp: failed to remove legacy completion dump(s) under $HOME"
    return 1
  fi

  if [[ "$zdotdir" != "$HOME" ]]; then
    legacy_dumps=("$zdotdir"/.zcompdump*(N))
    if (( ${#legacy_dumps[@]} )) && ! command rm -f -- "${legacy_dumps[@]}"; then
      print -u2 -- "zshreloadcomp: failed to remove completion dump(s) under $zdotdir"
      return 1
    fi
  fi

  if [[ -o login ]]; then
    exec -l zsh
  else
    exec zsh
  fi
}
