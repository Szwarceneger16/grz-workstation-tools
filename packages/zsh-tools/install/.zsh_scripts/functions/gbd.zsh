# git branch delete (safe delete only)
# OMZ's git plugin defines `gbd` as a bare `git branch --delete` alias with no
# argument validation or help; unalias it so this function (which adds both)
# wins instead of tripping zsh's "defining function based on alias" parser error.
(( $+aliases[gbd] )) && unalias gbd
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
