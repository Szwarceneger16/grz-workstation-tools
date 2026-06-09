# ~/.zsh_scripts/core/05-fpath.zsh

typeset -gaU fpath

fpath=(
  "$HOME/.zsh_scripts/completion/helpers"
  "$HOME/.zsh_scripts/completion/functions"
  "$HOME/.zsh_scripts/completion/bin"
  ${fpath:#$HOME/.zsh_scripts/completion}
  ${fpath:#$HOME/.zsh_scripts/.completion}
)
