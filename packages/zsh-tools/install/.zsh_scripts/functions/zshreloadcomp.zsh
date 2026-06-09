zshreloadcomp() {
  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  source "$HOME/.zshrc" &&
  rm -f "$HOME"/.zcompdump*(N) &&
  autoload -Uz compinit &&
  compinit -i
}
