# git worktree add
gwadd() {
  local base=""
  local force_new=0
  local branch=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        cmdhelp "${funcstack[1]}"
        return $?
        ;;
      -t)
        if [[ -z "$2" ]]; then
          print -u2 "gwadd: opcja -t wymaga argumentu (nazwa brancha na origin)"
          return 2
        fi
        base="$2"
        shift 2
        ;;
      -b)
        force_new=1
        shift
        ;;
      -*)
        print -u2 "gwadd: nieznana opcja: $1"
        print -u2 "Try: gwadd --help"
        return 2
        ;;
      *)
        if [[ -n "$branch" ]]; then
          print -u2 "gwadd: zbyt wiele argumentów"
          print -u2 "Try: gwadd --help"
          return 2
        fi
        branch="$1"
        shift
        ;;
    esac
  done

  if [[ -z "$branch" && -z "$base" ]]; then
      print -u2 "Usage: gwadd [-b] [-t <base-branch>] <branch>"
      print -u2 "Try: gwadd --help"
      return 2
  fi

  [[ -z "$branch" ]] && branch="$base"

  local target="$HOME/repos/.worktree/$branch"

  if [[ -n "$base" ]]; then
    if ! git check-ref-format --branch "$base" >/dev/null 2>&1; then
      print -u2 "gwadd: nieprawidłowa nazwa brancha dla -t: $base"
      return 2
    fi

    git fetch origin "refs/heads/${base}:refs/remotes/origin/${base}" || {
      print -u2 "gwadd: nie udało się pobrać '$base' z origin"
      return 1
    }

    if [[ "$branch" == "$base" && $force_new -eq 0 ]]; then
      gwta "$target" "$branch" || return $?
    else
      if git show-ref --verify --quiet "refs/heads/$branch"; then
        print -u2 "gwadd: branch '$branch' już istnieje lokalnie"
        return 1
      fi
      git branch --no-track "$branch" "origin/$base" || return $?
      gwta "$target" "$branch" || return $?
    fi
  elif [[ $force_new -eq 1 ]]; then
    if git show-ref --verify --quiet "refs/heads/$branch"; then
      print -u2 "gwadd: branch '$branch' już istnieje lokalnie"
      return 1
    fi
    git branch "$branch" || return $?
    gwta "$target" "$branch" || return $?
  else
    gwta "$target" "$branch" || return $?
  fi

  local env_src="$PWD/.env.lint.local"
  if [ -f "$env_src" ] && [ ! -e "$target/.env.lint.local" ]; then
    ln -s "$env_src" "$target/.env.lint.local"
  fi
}
