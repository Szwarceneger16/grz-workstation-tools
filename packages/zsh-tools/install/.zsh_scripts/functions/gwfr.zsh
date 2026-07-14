# git worktree fetch remote
gwfr() {
  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  if [[ $# -ne 1 || -z "$1" ]]; then
    print -u2 "Usage: gwfr <branch>"
    print -u2 "Try: gwfr --help"
    return 2
  fi

  local branch="$1"

  fr "$branch" || return $?
  gwadd "$branch"
}
