# ~/.zsh_scripts/core/90-completion_init.zsh

zstyle ':completion:*:*:-command-:*:functions'  ignored-patterns '__*' '*__impl'
zstyle ':completion:*:*:-command-:*:parameters' ignored-patterns '__*'
zstyle ':completion:*:*:-command-:*:commands'   ignored-patterns '*__impl'

zstyle ':completion:*:*:-command-:*:*' tag-order 'functions:-non-comp *' functions
zstyle ':completion:*:functions-non-comp' ignored-patterns '_*'

# Keep zsh-tools standalone, but do not unconditionally take over completion
# after another owner has already initialized it.
if (( ! $+functions[compdef] )); then
  autoload -Uz compinit
  compinit -i
elif [[ ${_comps[zshreloadcomp]-} != _zshreloadcomp ]]; then
  # A completion owner exists, but its loaded state does not contain this
  # package's sentinel mapping. This can happen when compinit -C trusts a dump
  # created before the zsh-tools completion directories were installed.
  #
  # -D forces a full in-memory scan without reading or writing a dump file, so
  # we repair the current session without taking ownership of the other
  # manager's dump lifecycle.
  autoload -Uz compinit
  compinit -D -i
fi
