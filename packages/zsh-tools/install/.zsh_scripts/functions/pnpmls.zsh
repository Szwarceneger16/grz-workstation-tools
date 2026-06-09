# pnls <pattern> [depth]
# - bez depth: pnpm -w ls (cały workspace/monorepo)
# - z depth: pnpm ls --depth=<depth> (tylko bieżący projekt)
pnpmls() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
      cmdhelp "${funcstack[1]}"
      return $?
  	fi

  if (( $# < 1 )); then
    echo "Użycie: pnls <wzorzec> [głębokość]"
    return 1
  fi

  local pattern="$1"
  local depth="$2"

  if [[ -n "$depth" ]]; then
    # Bieżący projekt, z ograniczoną głębokością
    pnpm ls --depth="$depth" | grep -i --color=auto -- "$pattern"
  else
    # Brak głębokości => całe monorepo (workspace)
    pnpm -w ls | grep -i --color=auto -- "$pattern"
  fi
}
