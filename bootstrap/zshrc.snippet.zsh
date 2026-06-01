# Load per-module Zsh rc files.
if [[ -d "$HOME/.config/zsh/rc.d" ]]; then
  for zsh_rc_file in "$HOME"/.config/zsh/rc.d/*.zsh(N); do
    source "$zsh_rc_file"
  done
fi
