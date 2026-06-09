# git fetch remote branch
gfr() {
  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    render_cmd_help gfr
    return $?
  fi

  if [[ $# -ne 1 || -z "$1" ]]; then
    print -u2 "Usage: gfr <branch>"
    print -u2 "Try: gfr --help"
    return 2
  fi

  local branch="$1"

  git fetch origin "$branch:$branch"
}
