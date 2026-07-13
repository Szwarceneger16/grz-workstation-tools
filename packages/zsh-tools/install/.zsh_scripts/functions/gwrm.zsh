# git worktree remove

gwrm() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

    gwtrm "$1" && gbd "$1"
}
