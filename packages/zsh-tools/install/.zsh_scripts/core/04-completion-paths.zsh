# Shared completion-path identity for the pre-loader and bounded registration.
# Callers localize reply/REPLY; both logical and physical paths matter because
# Stow and owners may expose the same directory/digest through different links.
__grz_completion_paths() {
  emulate -L zsh
  setopt typesetsilent
  local runtime_root="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}"
  local default_root="$HOME/.zsh_scripts"
  runtime_root="${runtime_root:a}"
  default_root="${default_root:a}"
  reply=(
    "$runtime_root/completion/helpers"
    "$runtime_root/completion/functions"
    "$runtime_root/completion/bin"
    "$runtime_root/completion"
    "$runtime_root/.completion"
  )
  if [[ "$runtime_root" != "$default_root" ]]; then
    reply+=(
      "$default_root/completion/helpers"
      "$default_root/completion/functions"
      "$default_root/completion/bin"
      "$default_root/completion"
      "$default_root/.completion"
    )
  fi
}

__grz_completion_match_root() {
  emulate -L zsh
  setopt typesetsilent
  local entry="$1" root digest base
  local logical="${entry:a}" physical="${entry:A}"
  base="${logical%.zwc}"
  shift
  REPLY=''
  for root in "$@"; do
    digest="$root.zwc"
    if [[ "$logical" == "$root" || "$logical" == "$digest" ||
          "$physical" == "${root:A}" || "$physical" == "${digest:A}" ||
          ( "$logical" == *.zwc && "${base:A}" == "${root:A}" ) ]]; then
      REPLY="$root"
      return 0
    fi
  done
  return 1
}

# A helper sourced through a file symlink may record the external target as its
# source. Match complete helper files too, not only their parent directories.
__grz_completion_match_helper_source() {
  emulate -L zsh
  setopt typesetsilent
  local source_file="$1" root helper candidate
  shift
  [[ "$source_file" == /* ]] || return 1
  __grz_completion_match_root "${source_file:h}" "$@" && return 0
  for root in "$@"; do
    for helper in compinit compaudit compdump compinstall; do
      candidate="$root/$helper"
      if [[ "${source_file:a}" == "$candidate" || "${source_file:A}" == "${candidate:A}" ]]; then
        REPLY="$root"
        return 0
      fi
    done
  done
  return 1
}
