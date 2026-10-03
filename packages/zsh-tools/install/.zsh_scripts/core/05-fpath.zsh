# ~/.zsh_scripts/core/05-fpath.zsh
source "${${(%):-%x}:A:h}/04-completion-paths.zsh" || return $?

() {
  emulate -L zsh
  setopt typesetsilent
  local dir name source_file REPLY
  local -a reply managed_paths remaining_fpath
  __grz_completion_paths
  managed_paths=("${reply[@]}")

  # An external owner initializes between the pre- and post-loader. Keep every
  # managed directory/digest (including aliases and stale default paths) out of
  # that owner's autoload search until 90-completion_init audits them.
  for dir in "${fpath[@]}"; do
    __grz_completion_match_root "$dir" "${managed_paths[@]}" ||
      remaining_fpath+=("$dir")
  done
  typeset -gaU fpath
  fpath=("${remaining_fpath[@]}")

  # A previous autoload may already be pinned to a managed helper. Removing its
  # fpath entry alone does not revoke that source. Keep explicit owner helpers
  # outside the runtime; unpinned stubs will resolve through the cleaned fpath.
  zmodload zsh/parameter
  for name in compinit compaudit compdump compinstall; do
    source_file="${functions_source[$name]-}"
    [[ -n "$source_file" ]] || continue
    if __grz_completion_match_helper_source "$source_file" "${managed_paths[@]}"; then
      unfunction -- "$name"
    fi
  done
}
