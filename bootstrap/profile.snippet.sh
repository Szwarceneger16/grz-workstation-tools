# Load per-module profile fragments.
if [ -d "$HOME/.config/profile.d" ]; then
  for profile_file in "$HOME"/.config/profile.d/*.sh; do
    [ -r "$profile_file" ] && . "$profile_file"
  done
fi
