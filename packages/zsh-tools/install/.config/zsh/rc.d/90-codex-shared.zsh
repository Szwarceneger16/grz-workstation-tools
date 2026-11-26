# Reuse the login-shell integration for interactive Zsh sessions.
if [[ -r "$HOME/.config/profile.d/90-codex-shared.sh" ]]; then
    source "$HOME/.config/profile.d/90-codex-shared.sh"
fi
