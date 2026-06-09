# ~/.zsh_scripts/core/00-paths.zsh

[[ ":$PATH:" == *":$HOME/.local/my-custom-bin:"* ]] || export PATH="$HOME/.local/my-custom-bin:$PATH"
[[ ":$PATH:" == *":$HOME/.local/bin:"* ]] || export PATH="$PATH:$HOME/.local/bin"
