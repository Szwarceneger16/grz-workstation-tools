# compatibility wrapper for fr
gfr() {
  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    cmdhelp "${funcstack[1]}"
    return $?
  fi

  if [[ $# -ne 1 || -z "$1" ]]; then
    print -u2 "Usage: gfr <branch>"
    print -u2 "Try: gfr --help"
    return 2
  fi

  fr "$1"
}
