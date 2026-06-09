
# branchclear() {
#     git fetch -p && for branch in $(git for-each-ref --format '%(refname) %(upstream:track)' refs/heads | awk '$2 == "[gone]" {sub("refs/heads/", "", $1); print $1}'); do gwrm $branch; done
# }
branchclear() {
	if [[ "$1" == "-h" || "$1" == "--help" ]]; then
		cmdhelp "${funcstack[1]}"
		return $?
  	fi

  local mode="safe"
  [[ "$1" == "-f" || "$1" == "--force" ]] && mode="force"

  git fetch --prune || return
  git worktree prune >/dev/null 2>&1

  local base_ref current_branch has_merge_tree=0
  local branch_name worktree_dir merge_base_oid base_tree_oid merged_tree_oid temp_dir

  current_branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)

  base_ref=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)
  git rev-parse --verify --quiet "$base_ref" >/dev/null 2>&1 || base_ref=HEAD

  git merge-tree --write-tree HEAD HEAD >/dev/null 2>&1 && has_merge_tree=1

  while IFS= read -r branch_name; do
    [[ -n "$branch_name" ]] || continue
    [[ "$branch_name" == "$current_branch" ]] && continue

    worktree_dir=$(
      git worktree list --porcelain |
      awk -v target="refs/heads/$branch_name" '
        $1=="worktree" { wt=$2 }
        $1=="branch" && $2==target { print wt; exit }
      '
    )

    if [[ -n "$worktree_dir" ]]; then
      if [[ "$mode" == "force" ]]; then
        git worktree remove --force --force -- "$worktree_dir" || {
          echo "Nie mogę usunąć worktree: $worktree_dir — pomijam '$branch_name'."
          continue
        }
      else
        git worktree remove -- "$worktree_dir" || {
          echo "Pomijam '$branch_name' — powiązany worktree nie jest czysty: $worktree_dir"
          continue
        }
      fi
    fi

    if [[ "$mode" == "force" ]]; then
      if git branch -D -- "$branch_name"; then
        echo "Usunięto (force): $branch_name"
      else
        echo "Nie udało się usunąć brancha: $branch_name"
      fi
      continue
    fi

    if git branch -d -- "$branch_name" >/dev/null 2>&1; then
      echo "Usunięto (bezpiecznie): $branch_name"
      continue
    fi

    if (( has_merge_tree )); then
      merge_base_oid=$(git merge-base "$base_ref" "refs/heads/$branch_name") || {
        echo "Pomijam '$branch_name' (brak merge-base z $base_ref)."
        continue
      }

      base_tree_oid=$(git rev-parse "$base_ref^{tree}") || {
        echo "Pomijam '$branch_name' (nie mogę odczytać tree dla $base_ref)."
        continue
      }

      merged_tree_oid=$(
        git merge-tree --write-tree --merge-base="$merge_base_oid" \
          "$base_ref" "refs/heads/$branch_name" 2>/dev/null
      ) || {
        echo "Pomijam '$branch_name' (merge-tree nie powiódł się)."
        continue
      }

      if [[ "$merged_tree_oid" == "$base_tree_oid" ]]; then
        if git branch -D -- "$branch_name"; then
          echo "Usunięto (bezpiecznie, no-op vs $base_ref): $branch_name"
        else
          echo "Nie udało się usunąć brancha: $branch_name"
        fi
        continue
      fi
    else
      temp_dir=$(mktemp -d) || {
        echo "Pomijam '$branch_name' (mktemp nie powiódł się)."
        continue
      }

      if git worktree add --detach --quiet "$temp_dir" "$base_ref" \
        && git -C "$temp_dir" merge --no-commit --no-ff -q "refs/heads/$branch_name" >/dev/null 2>&1 \
        && git -C "$temp_dir" diff --quiet --cached --exit-code; then

        git worktree remove --force -- "$temp_dir" >/dev/null 2>&1 || rm -rf -- "$temp_dir"

        if git branch -D -- "$branch_name"; then
          echo "Usunięto (bezpiecznie, no-op vs $base_ref): $branch_name"
        else
          echo "Nie udało się usunąć brancha: $branch_name"
        fi
        continue
      fi

      git -C "$temp_dir" merge --abort >/dev/null 2>&1 || true
      git worktree remove --force -- "$temp_dir" >/dev/null 2>&1 || rm -rf -- "$temp_dir"
    fi

    echo "Pomijam '$branch_name' — ma unikalne zmiany względem $base_ref."
  done < <(
    git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads |
    awk '$2=="[gone]" { print $1 }'
  )
}
