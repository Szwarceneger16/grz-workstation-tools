# git worktree add (path-based; branch name is derived from the path)
# OMZ's git plugin defines `gwta` as a bare `git worktree add` alias (caller
# supplies path AND branch explicitly); unalias it so this richer function
# (derives branch from path, creates local/tracking branch as needed) wins
# instead of tripping zsh's "defining function based on alias" parser error.
(( $+aliases[gwta] )) && unalias gwta
gwta() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

    if [[ $# -lt 1 || $# -gt 2 || -z "$1" ]]; then
        print -u2 "Usage: gwta <ścieżka> [branch]"
        print -u2 "Try: gwta --help"
        return 2
    fi

    local target="$1"
    local branch="${2:-${target:t}}"

    mkdir -p -- "${target:h}"

    if git show-ref --verify --quiet "refs/heads/$branch"; then
        git worktree add "$target" "$branch"
    elif git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
        git worktree add "$target" -b "$branch" "origin/$branch"
    else
        git worktree add "$target" -b "$branch"
    fi
}
