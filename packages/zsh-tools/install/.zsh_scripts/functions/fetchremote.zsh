# fetch a branch from origin into a same-named local branch
fetchremote() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

    if [[ $# -ne 1 || -z "$1" ]]; then
        print -u2 "Usage: fetchremote <branch>"
        print -u2 "Try: fetchremote --help"
        return 2
    fi

    local branch="$1"

    git fetch origin "$branch:$branch"
}
