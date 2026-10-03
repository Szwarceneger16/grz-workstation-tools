# ~/.zsh_scripts/core/05-fpath.zsh

() {
  local runtime_root="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}"
  local default_root="$HOME/.zsh_scripts"
  local dir managed
  local -i skip
  local -a runtime_completion_roots remove_roots remaining_fpath

  runtime_completion_roots=(
    "$runtime_root/completion/helpers"
    "$runtime_root/completion/functions"
    "$runtime_root/completion/bin"
  )

  remove_roots=(
    "${runtime_completion_roots[@]}"
    "$runtime_root/completion"
    "$runtime_root/.completion"
  )

  # When a custom runtime root is selected, also remove the default zsh-tools
  # completion paths from any pre-existing fpath. Otherwise a missing or stale
  # function under the custom root could be autoloaded from the wrong runtime.
  if [[ "$runtime_root" != "$default_root" ]]; then
    remove_roots+=(
      "$default_root/completion/helpers"
      "$default_root/completion/functions"
      "$default_root/completion/bin"
      "$default_root/completion"
      "$default_root/.completion"
    )
  fi

  for dir in "${fpath[@]}"; do
    skip=0
    for managed in "${remove_roots[@]}"; do
      if [[ "$dir" == "$managed" ]]; then
        skip=1
        break
      fi
    done
    (( skip )) || remaining_fpath+=("$dir")
  done

  typeset -gaU fpath
  fpath=("${runtime_completion_roots[@]}" "${remaining_fpath[@]}")
}
