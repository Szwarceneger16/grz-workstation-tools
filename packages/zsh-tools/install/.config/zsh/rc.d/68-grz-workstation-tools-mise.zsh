# mise interactive-shell integration.
# Runs after grz-workstation-tools PATH finalization.
# The vendored completion requires mise's __complete_word__ endpoint.

typeset __grz_mise_bin
unset __GRZ_MISE_BIN

if [[ -x "$HOME/.local/bin/mise" ]]; then
  __grz_mise_bin="$HOME/.local/bin/mise"
elif (( $+commands[mise] )); then
  __grz_mise_bin="${commands[mise]}"
fi

if [[ -n "${__grz_mise_bin:-}" ]]; then
  if MISE_SELF_UPDATE_AVAILABLE=false "$__grz_mise_bin" help __complete_word__ >/dev/null 2>&1; then
    # Keep the validated executable for completion. This is intentionally a
    # non-exported shell variable: child processes do not need package internals.
    typeset -g __GRZ_MISE_BIN="$__grz_mise_bin"

    # A nested shell can inherit mise's old baseline PATH from a pre-migration
    # parent. Rebuild activation from the already-sanitized current PATH.
    unset __MISE_ORIG_PATH
    eval "$(MISE_SELF_UPDATE_AVAILABLE=false "$__grz_mise_bin" activate zsh)"
  else
    print -u2 -- "grz-workstation-tools: mise with __complete_word__ support is required"
  fi
fi

unset __grz_mise_bin
