# fetch a remote branch into a same-named local branch
fr() {
  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  if [[ $# -ne 1 || -z "$1" ]]; then
    print -u2 "Usage: fr <branch>"
    print -u2 "Try: fr --help"
    return 2
  fi

  local branch="$1"

  if ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
    print -u2 "fr: invalid branch name: $branch"
    return 2
  fi

  git fetch origin \
    "refs/heads/$branch:refs/heads/$branch" \
    "refs/heads/$branch:refs/remotes/origin/$branch" \
    || return $?

  git branch --set-upstream-to="origin/$branch" "$branch"
}
