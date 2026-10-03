# ~/.zsh_scripts/core/90-completion_init.zsh

zstyle ':completion:*:*:-command-:*:functions'  ignored-patterns '__*' '*__impl'
zstyle ':completion:*:*:-command-:*:parameters' ignored-patterns '__*'
zstyle ':completion:*:*:-command-:*:commands'   ignored-patterns '*__impl'

zstyle ':completion:*:*:-command-:*:*' tag-order 'functions:-non-comp *' functions
zstyle ':completion:*:functions-non-comp' ignored-patterns '_*'

# Keep zsh-tools standalone, but do not run a second full compinit scan when
# another completion owner already exists.
if (( ! $+functions[compdef] )); then
  autoload -Uz compinit
  compinit -i
else
  # Register only #compdef metadata from this runtime's completion/functions
  # directory. This mirrors compinit's bounded #compdef handling, so stale
  # external dumps do not force a full fpath rescan on every shell startup.
  # compdef -n preserves any existing user/manager mapping.
  () {
    emulate -L zsh
    setopt extendedglob

    local completion_root="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}/completion/functions"
    local file name
    local -a fields

    for file in "$completion_root"/^([^_]*|*[;|&]*|*~|*.zwc)(N-.); do
      fields=()
      IFS=$' \t' read -rA fields < "$file" || continue
      [[ ${fields[1]-} == '#compdef' ]] || continue
      shift fields
      (( ${#fields[@]} )) || continue
      name="${file:t}"

      if [[ ${fields[1]} = -[pPkK](n|) ]]; then
        compdef ${fields[1]}na "$name" "${(@)fields[2,-1]}"
      else
        compdef -na "$name" "${fields[@]}"
      fi
    done
  }
fi
