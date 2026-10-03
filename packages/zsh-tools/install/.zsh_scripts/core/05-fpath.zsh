# ~/.zsh_scripts/core/05-fpath.zsh

# Record whether completion had already been initialized before this package
# exposed its completion directories. 90-completion_init.zsh uses this to avoid
# a redundant compinit when another completion owner initializes after our fpath
# is ready, while still rescanning when these directories were added too late.
if [[ ! -v _grz_zsh_tools_fpath_added_after_compinit ]]; then
  if [[ -v _comp_setup ]]; then
    typeset -gi _grz_zsh_tools_fpath_added_after_compinit=1
  else
    typeset -gi _grz_zsh_tools_fpath_added_after_compinit=0
  fi
fi

typeset -gaU fpath

fpath=(
  "$HOME/.zsh_scripts/completion/helpers"
  "$HOME/.zsh_scripts/completion/functions"
  "$HOME/.zsh_scripts/completion/bin"
  ${fpath:#$HOME/.zsh_scripts/completion}
  ${fpath:#$HOME/.zsh_scripts/.completion}
)
