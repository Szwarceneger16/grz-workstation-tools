zshreloadcomp() {
  builtin emulate -L 'zsh'

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  local dump zsh_executable
  local zdotdir="${ZDOTDIR:-$HOME}"
  local default_cache_dump="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump"
  local -aU dumps candidates
  local -a shell_flags

  # Resolve only an external interpreter, before removing any dump. A session
  # function/alias called zsh must not take over exec and terminate the shell.
  if ! zsh_executable="$(builtin whence -p 'zsh')" ||
      [[ -z "$zsh_executable" || ! -f "$zsh_executable" || ! -x "$zsh_executable" ]]; then
    print -u2 -- 'zshreloadcomp: cannot find an executable Zsh in PATH'
    return 1
  fi
  zsh_executable="${zsh_executable:a}"

  [[ -n ${_comp_dumpfile:-} ]] && dumps+=("$_comp_dumpfile")
  [[ -n ${ZSH_COMPDUMP:-} ]] && dumps+=("$ZSH_COMPDUMP")
  dumps+=("$zdotdir/.zcompdump" "$default_cache_dump")

  # A relative path retains no record of compinit's original working directory.
  # Validate every source before unlinking anything or expanding legacy globs.
  for dump in "$HOME" "${dumps[@]}"; do
    if [[ "$dump" != /* ]]; then
      print -u2 -- "zshreloadcomp: cannot safely locate a relative dump path: $dump"
      print -u2 -- 'Use absolute completion dump/cache paths before restarting.'
      return 1
    fi
  done

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

  # Local emulation preserves LOGIN/INTERACTIVE. Explicit -i is needed for
  # interactive shells whose stdin is a pipe or file.
  [[ -o login ]] && shell_flags+=(-l)
  if [[ -o interactive ]]; then
    shell_flags+=(-i)
  else
    shell_flags+=(+i)
  fi
  builtin exec command -- "$zsh_executable" "${shell_flags[@]}"
}
