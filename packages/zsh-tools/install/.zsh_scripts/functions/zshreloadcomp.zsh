zshreloadcomp() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  local dump
  local zdotdir="${ZDOTDIR:-$HOME}"
  local default_cache_dump="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump"
  local -aU dumps candidates
  local -a shell_flags

  [[ -n ${_comp_dumpfile:-} ]] && dumps+=("$_comp_dumpfile")
  [[ -n ${ZSH_COMPDUMP:-} ]] && dumps+=("$ZSH_COMPDUMP")
  dumps+=("$zdotdir/.zcompdump" "$default_cache_dump")

  for dump in "${dumps[@]}"; do
    candidates+=("$dump" "$dump.zwc")
  done
  candidates+=("$HOME"/.zcompdump*(N) "$zdotdir"/.zcompdump*(N))

  # Apply one policy to explicit paths, compiled companions and both legacy
  # globs. Test each path independently: a .zwc can itself be a directory or
  # sink, and a removable symlink can point to a directory or be dangling.
  for dump in "${candidates[@]}"; do
    [[ -f "$dump" || -L "$dump" ]] || continue
    if ! command rm -f -- "$dump"; then
      print -u2 -- "zshreloadcomp: failed to remove completion dump: $dump"
      return 1
    fi
  done

  # Capture invocation modes before any option localization. Explicit -i is
  # needed for interactive shells whose stdin is a pipe or file.
  [[ -o login ]] && shell_flags+=(-l)
  if [[ -o interactive ]]; then
    shell_flags+=(-i)
  else
    shell_flags+=(+i)
  fi
  exec zsh "${shell_flags[@]}"
}
