# git worktree add
gwadd() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

  if [[ $# -ne 1 || -z "$1" ]]; then
      print -u2 "Usage: gwadd <branch>"
      print -u2 "Try: gwadd --help"
      return 2
  fi

  local branch="$1"
  local target="$HOME/repos/.worktree/$branch"

  gwta "$target" "$branch" || return $?

  local env_src="$PWD/.env.lint.local"
  if [ -f "$env_src" ] && [ ! -e "$target/.env.lint.local" ]; then
    ln -s "$env_src" "$target/.env.lint.local"
  fi
}
