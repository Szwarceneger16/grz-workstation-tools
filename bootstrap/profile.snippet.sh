# shellcheck shell=sh
# shellcheck disable=SC1090
# >>> profile.d loader (managed) >>>
# Sources ~/.config/profile.d/*.sh at login. Managed by grz-workstation-tools
# shell-bootstrap. Safe to remove this block.
if [ -d "$HOME/.config/profile.d" ]; then
  for profile_file in "$HOME"/.config/profile.d/*.sh; do
    [ -r "$profile_file" ] && . "$profile_file"
  done
fi
# <<< profile.d loader (managed) <<<
