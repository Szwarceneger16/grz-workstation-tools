# git worktree remove (by branch name)
gwtrm() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

    if [[ $# -ne 1 || -z "$1" ]]; then
        print -u2 "Usage: gwtrm <branch>"
        print -u2 "Try: gwtrm --help"
        return 2
    fi

    local branch="$1"
    local worktree_dir

    worktree_dir=$(
      git worktree list --porcelain |
      awk -v target="refs/heads/$branch" '
        $1=="worktree" { wt=$2 }
        $1=="branch" && $2==target { print wt; exit }
      '
    )

    if [[ -z "$worktree_dir" ]]; then
        print -u2 "Nie znaleziono worktree dla brancha: $branch"
        return 1
    fi

    git worktree remove -- "$worktree_dir"
}
