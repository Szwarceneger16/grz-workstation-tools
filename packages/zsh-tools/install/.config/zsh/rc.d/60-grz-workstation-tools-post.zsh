# Public Zsh tools post-loader.
# Load remaining core modules and public function entrypoints after Oh My Zsh.

typeset -g ZSH_TOOLS_ROOT="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}"

if [[ -d "$ZSH_TOOLS_ROOT/core" ]]; then
  for zsh_core_file in "$ZSH_TOOLS_ROOT"/core/*.zsh(N); do
    case "${zsh_core_file:t}" in
      00-paths.zsh|05-fpath.zsh) continue ;;
    esac
    source "$zsh_core_file"
  done
fi

if [[ -d "$ZSH_TOOLS_ROOT/functions" ]]; then
  for zsh_function_file in "$ZSH_TOOLS_ROOT"/functions/*.zsh(N); do
    source "$zsh_function_file"
  done
fi
