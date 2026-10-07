# mise interactive-shell integration, after PATH finalization.
# Check the local completion capability without version/update network lookups.
() {
  builtin emulate -L 'zsh'
  setopt typesetsilent
  local __grz_mise_bin __grz_mise_activation
  local -i __grz_mise_rc
  unset __GRZ_MISE_BIN

  if [[ -f "$HOME/.local/bin/mise" && -x "$HOME/.local/bin/mise" ]]; then
    __grz_mise_bin="$HOME/.local/bin/mise"
  else
    __grz_mise_bin="$(builtin whence -p 'mise')" || return 0
  fi
  [[ -f "$__grz_mise_bin" && -x "$__grz_mise_bin" ]] || return 0
  __grz_mise_bin="${__grz_mise_bin:a}"

  if ! MISE_SELF_UPDATE_AVAILABLE=false MISE_DISABLE_UPDATE_WARNING=true \
      "$__grz_mise_bin" help __complete_word__ >/dev/null 2>&1; then
    print -u2 -- "grz-workstation-tools: mise with __complete_word__ support is required"
    return 1
  fi

  # A nested shell can inherit a pre-migration baseline. Activation must use
  # the sanitized current PATH. Never evaluate partial output from a failure.
  unset __MISE_ORIG_PATH
  if __grz_mise_activation="$(MISE_SELF_UPDATE_AVAILABLE=false MISE_DISABLE_UPDATE_WARNING=true \
      "$__grz_mise_bin" activate 'zsh')"; then
    if eval "$__grz_mise_activation"; then
      # Publish completion's binding only after generation and evaluation pass.
      typeset -g __GRZ_MISE_BIN="$__grz_mise_bin"
    else
      __grz_mise_rc=$?
      print -u2 -- "grz-workstation-tools: mise activation evaluation failed ($__grz_mise_rc)"
      return $__grz_mise_rc
    fi
  else
    __grz_mise_rc=$?
    print -u2 -- "grz-workstation-tools: mise activation generation failed ($__grz_mise_rc)"
    return $__grz_mise_rc
  fi
}
