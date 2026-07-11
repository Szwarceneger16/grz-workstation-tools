# git worktree add
gwadd() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

  local branch="$1"
  local target="$HOME/repos/.worktree/$branch"

  gwta "$target" "$branch"

  local env_src="$PWD/.env.lint.local"
  if [ -f "$env_src" ] && [ ! -e "$target/.env.lint.local" ]; then
    ln -s "$env_src" "$target/.env.lint.local"
  fi
}
