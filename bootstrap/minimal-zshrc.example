# >>> zsh rc.d loader (managed) >>>
# Sources ~/.config/zsh/rc.d/*.zsh so packages can drop rc fragments there.
# Managed by grz-workstation-tools / shell-bootstrap. Safe to remove this block.
if [[ -d "$HOME/.config/zsh/rc.d" ]]; then
  for zsh_rc_file in "$HOME"/.config/zsh/rc.d/*.zsh(N); do
    source "$zsh_rc_file"
  done
fi
# <<< zsh rc.d loader (managed) <<<
