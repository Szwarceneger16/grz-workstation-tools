# git worktree fetch remote
gwfr() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

    fetchremote $1
    gwadd $1
}
