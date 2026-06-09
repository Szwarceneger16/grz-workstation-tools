# Public Zsh tools pre-loader.
# Load only path/fpath foundations before Oh My Zsh.

typeset -g ZSH_TOOLS_ROOT="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}"

for zsh_core_file in \
  "$ZSH_TOOLS_ROOT/core/00-paths.zsh" \
  "$ZSH_TOOLS_ROOT/core/05-fpath.zsh"
do
  [[ -r "$zsh_core_file" ]] && source "$zsh_core_file"
done
