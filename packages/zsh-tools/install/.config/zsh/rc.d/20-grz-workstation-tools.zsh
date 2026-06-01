# Public Zsh tools loader.
# This file is intentionally small and public-safe.

export ZSH_TOOLS_ROOT="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}"

if [[ -d "$ZSH_TOOLS_ROOT/core" ]]; then
  for zsh_core_file in "$ZSH_TOOLS_ROOT"/core/*.zsh(N); do
    source "$zsh_core_file"
  done
fi
