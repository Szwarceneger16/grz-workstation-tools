# mise interactive-shell integration.
# Runs after grz-workstation-tools PATH finalization.

if [[ -x "$HOME/.local/bin/mise" ]]; then
  eval "$("$HOME/.local/bin/mise" activate zsh)"
elif (( $+commands[mise] )); then
  eval "$(mise activate zsh)"
fi
