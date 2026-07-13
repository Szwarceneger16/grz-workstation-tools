# git branch delete (safe delete only)
gbd() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

    if [[ $# -ne 1 || -z "$1" ]]; then
        print -u2 "Usage: gbd <branch>"
        print -u2 "Try: gbd --help"
        return 2
    fi

    git branch -d -- "$1"
}
