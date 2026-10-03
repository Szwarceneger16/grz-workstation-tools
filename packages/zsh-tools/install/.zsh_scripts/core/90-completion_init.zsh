# ~/.zsh_scripts/core/90-completion_init.zsh

zstyle ':completion:*:*:-command-:*:functions'  ignored-patterns '__*' '*__impl'
zstyle ':completion:*:*:-command-:*:parameters' ignored-patterns '__*'
zstyle ':completion:*:*:-command-:*:commands'   ignored-patterns '*__impl'

zstyle ':completion:*:*:-command-:*:*' tag-order 'functions:-non-comp *' functions
zstyle ':completion:*:functions-non-comp' ignored-patterns '_*'

# Initialize completion only when nobody has claimed it yet, or when our fpath
# was added after an already-completed compinit and therefore needs one rescan.
# If another completion owner appeared after 05-fpath, our paths were already
# visible to it and a second compinit would only disturb its lifecycle.
if (( ! $+functions[compdef] || ${_grz_zsh_tools_fpath_added_after_compinit:-0} )); then
  autoload -Uz compinit
  compinit -i
  typeset -gi _grz_zsh_tools_fpath_added_after_compinit=0
fi
