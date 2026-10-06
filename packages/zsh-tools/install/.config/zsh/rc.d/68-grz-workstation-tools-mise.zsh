# mise interactive-shell integration.
# Runs after grz-workstation-tools PATH finalization.
# The vendored completion requires mise >= 2026.10.3.

typeset __grz_mise_bin __grz_mise_version

if [[ -x "$HOME/.local/bin/mise" ]]; then
  __grz_mise_bin="$HOME/.local/bin/mise"
elif (( $+commands[mise] )); then
  __grz_mise_bin="${commands[mise]}"
fi

if [[ -n "${__grz_mise_bin:-}" ]]; then
  __grz_mise_version="$("$__grz_mise_bin" --version 2>/dev/null)"
  __grz_mise_version="${__grz_mise_version%% *}"
  autoload -Uz is-at-least

  if [[ -n "$__grz_mise_version" ]] && is-at-least 2026.10.3 "$__grz_mise_version"; then
    # A nested shell can inherit mise's old baseline PATH from a pre-migration
    # parent. Rebuild activation from the already-sanitized current PATH.
    unset __MISE_ORIG_PATH
    eval "$("$__grz_mise_bin" activate zsh)"
  else
    print -u2 -- "grz-workstation-tools: mise >= 2026.10.3 required; found ${__grz_mise_version:-unknown}"
  fi
fi

unset __grz_mise_bin __grz_mise_version
