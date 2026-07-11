# git worktree add (path-based; branch name is derived from the path)
gwta() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

    if [[ $# -ne 1 || -z "$1" ]]; then
        print -u2 "Usage: gwta <ścieżka>"
        print -u2 "Try: gwta --help"
        return 2
    fi

    local target="$1"
    local branch="${target:t}"

    if git show-ref --verify --quiet "refs/heads/$branch"; then
        git worktree add "$target" "$branch"
    elif git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
        git worktree add "$target" -b "$branch" "origin/$branch"
    else
        git worktree add "$target" -b "$branch"
    fi
}
