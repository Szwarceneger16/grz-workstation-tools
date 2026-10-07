# Remove gone-upstream branches only when their history is proven disposable.
# Safe mode never rewrites a branch or discards a worktree with local data.

_branchclear_origin_github_repo() {
  emulate -L zsh
  local url repo

  # Read the declared origin, not "git remote get-url", which expands insteadOf
  # aliases and can hide a GitHub URL mapped to a local test transport.
  url=$(git config --get remote.origin.url 2>/dev/null) || return 1
  case "$url" in
    https://github.com/*) repo="${url#https://github.com/}" ;;
    git@github.com:*) repo="${url#git@github.com:}" ;;
    ssh://git@github.com/*) repo="${url#ssh://git@github.com/}" ;;
    *) return 1 ;;
  esac
  repo="${repo%.git}"
  [[ "$repo" =~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' ]] || return 1
  print -r -- "$repo"
}

_branchclear_merged_pr_number() {
  emulate -L zsh
  local branch="$1" branch_oid="$2" base_ref="$3" repo="$4" base_branch="$5"
  local rows number head_oid head_repo target_branch head_branch merge_oid fetched_oid
  local owner="${repo%%/*}"

  command -v gh >/dev/null 2>&1 || return 1

  # Explicit repository and head owner: never trust a similarly named fork PR.
  # GitHub retains closed PR metadata even after its source branch is deleted.
  rows=$(
    gh api --method GET --paginate "repos/$repo/pulls" \
      -f 'state=closed' -f "head=$owner:$branch" \
      -f "base=$base_branch" -f 'per_page=100' \
      --jq '.[] | select(.merged_at != null) | [.number, (.head.sha // "-"), (.head.repo.full_name // "-"), (.base.ref // "-"), (.head.ref // "-"), (.merge_commit_sha // "-")] | @tsv' \
      2>/dev/null
  ) || return 1
  [[ -n "$rows" ]] || return 1

  while IFS=$'\t' read -r number head_oid head_repo target_branch head_branch merge_oid; do
    [[ "$number" =~ '^[1-9][0-9]*$' ]] || continue
    [[ "$head_oid" =~ '^[0-9a-f]{40}$' ]] || continue
    [[ "$merge_oid" =~ '^[0-9a-f]{40}$' ]] || continue
    [[ "$head_repo" == "$repo" && "$target_branch" == "$base_branch" ]] || continue
    [[ "$head_branch" == "$branch" ]] || continue

    # A merged PR alone is insufficient: its result must still belong to the
    # fetched target history, not just be a closed PR on another base.
    git merge-base --is-ancestor "$merge_oid" "$base_ref" 2>/dev/null || continue

    if ! git cat-file -e "${head_oid}^{commit}" 2>/dev/null; then
      # GitHub preserves refs/pull/N/head after merging/deleting the source.
      # FETCH_HEAD must match the API's exact head; never trust a reused name.
      git fetch --no-tags --quiet origin "refs/pull/$number/head" 2>/dev/null || continue
      fetched_oid=$(git rev-parse --verify -q 'FETCH_HEAD^{commit}' 2>/dev/null) || continue
      [[ "$fetched_oid" == "$head_oid" ]] || continue
    fi

    # Accept an older local tip, but never extra commits beyond the merged PR.
    if git merge-base --is-ancestor "$branch_oid" "$head_oid" 2>/dev/null; then
      print -r -- "$number"
      return 0
    fi
  done <<< "$rows"
  return 1
}

_branchclear_worktree_for() {
  emulate -L zsh
  local branch="$1" line worktree_path=''
  while IFS= read -r line; do
    case "$line" in
      'worktree '*) worktree_path="${line#worktree }" ;;
      'branch '*) [[ "${line#branch }" == "refs/heads/$branch" ]] && {
        print -r -- "$worktree_path"
        return 0
      } ;;
    esac
  done < <(git worktree list --porcelain)
  return 1
}

branchclear() {
  emulate -L zsh
  local mode='safe' base_ref='' base_branch='' github_repo=''
  local current_branch branch tracking_status upstream_remote branch_ref branch_oid base_tree
  local merge_base_oid merged_tree_oid merge_rc reason note pr_number
  local worktree_dir worktree_status observed_oid inside_worktree

  if (( $# > 1 )); then
    print -u2 -- 'Usage: branchclear [--force|--help]'
    return 2
  fi
  case "${1-}" in
    -h|--help) cmdhelp "${funcstack[1]}"; return $? ;;
    -f|--force) mode='force' ;;
    '') ;;
    *) print -u2 -- 'Usage: branchclear [--force|--help]'; return 2 ;;
  esac

  inside_worktree=$(git rev-parse --is-inside-work-tree 2>/dev/null) || inside_worktree=''
  if [[ "$inside_worktree" != 'true' ]]; then
    print -u2 -- 'branchclear: not inside a Git working tree.'
    return 1
  fi
  git fetch --prune origin || return 1

  current_branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null) || current_branch=''
  base_ref=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null) || base_ref=''
  if [[ -z "$base_ref" ]]; then
    for base_ref in origin/main origin/master; do
      git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null 2>&1 && break
    done
  fi
  git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null 2>&1 || {
    print -u2 -- 'branchclear: no valid origin default branch; refusing cleanup.'
    return 1
  }
  base_branch="${base_ref#origin/}"
  base_tree=$(git rev-parse --verify "$base_ref^{tree}") || return 1
  github_repo=$(_branchclear_origin_github_repo) || github_repo=''

  while IFS=$'\t' read -r branch tracking_status upstream_remote; do
    [[ "$tracking_status" == '[gone]' ]] || continue
    [[ -n "$branch" && "$branch" != "$current_branch" ]] || continue
    branch_ref="refs/heads/$branch"
    branch_oid=$(git rev-parse --verify -q "$branch_ref^{commit}") || continue

    reason='' note='' pr_number=''
    if [[ "$mode" == 'force' ]]; then
      reason='explicit --force'
    elif git merge-base --is-ancestor "$branch_oid" "$base_ref" 2>/dev/null; then
      reason="ancestor of $base_ref"
    else
      merge_base_oid=$(git merge-base "$base_ref" "$branch_ref" 2>/dev/null)
      if [[ -z "$merge_base_oid" ]]; then
        note="no merge base with $base_ref"
      else
        merged_tree_oid=$(
          git merge-tree --write-tree --merge-base="$merge_base_oid" \
            "$base_ref" "$branch_ref" 2>/dev/null
        )
        merge_rc=$?
        if (( merge_rc == 0 )); then
          if [[ "$merged_tree_oid" == "$base_tree" ]]; then
            reason="no-op merge into $base_ref"
          else
            note="changes differ from $base_ref"
          fi
        elif (( merge_rc == 1 )); then
          note="merge conflicts against $base_ref"
        else
          note="merge-tree failed (exit $merge_rc)"
        fi
      fi

      if [[ -z "$reason" && "$upstream_remote" == 'origin' && -n "$github_repo" ]]; then
        if pr_number=$(_branchclear_merged_pr_number \
          "$branch" "$branch_oid" "$base_ref" "$github_repo" "$base_branch"); then
          reason="verified merged GitHub PR #$pr_number"
        fi
      fi
    fi

    if [[ -z "$reason" ]]; then
      [[ -n "$note" ]] || note='not provably merged'
      print -r -- "Skipping '$branch': $note; no verified merged PR (requires authenticated gh for GitHub origins)."
      continue
    fi

    # Do not alter linked worktrees until the branch has passed the proof.
    worktree_dir=$(_branchclear_worktree_for "$branch") || worktree_dir=''
    if [[ -n "$worktree_dir" && "$mode" == 'safe' ]]; then
      worktree_status=$(git -C "$worktree_dir" status --porcelain --ignored --untracked-files=all 2>/dev/null) || {
        print -r -- "Skipping '$branch': cannot inspect linked worktree $worktree_dir."
        continue
      }
      if [[ -n "$worktree_status" ]]; then
        print -r -- "Skipping '$branch': linked worktree contains changes or untracked/ignored files: $worktree_dir."
        continue
      fi
    fi

    # The branch may have advanced while gh/network checks were in flight.
    observed_oid=$(git rev-parse --verify -q "$branch_ref^{commit}") || observed_oid=''
    if [[ "$observed_oid" != "$branch_oid" ]]; then
      print -r -- "Skipping '$branch': branch tip changed during verification."
      continue
    fi

    if [[ -n "$worktree_dir" ]]; then
      if [[ "$mode" == 'force' ]]; then
        git worktree remove --force --force -- "$worktree_dir" || {
          print -r -- "Skipping '$branch': unable to force-remove worktree $worktree_dir."
          continue
        }
      else
        git worktree remove -- "$worktree_dir" || {
          print -r -- "Skipping '$branch': unable to remove worktree $worktree_dir."
          continue
        }
      fi
    fi

    observed_oid=$(git rev-parse --verify -q "$branch_ref^{commit}") || observed_oid=''
    if [[ "$observed_oid" != "$branch_oid" ]]; then
      print -r -- "Skipping '$branch': branch tip changed before deletion."
      continue
    fi

    if git branch -D -- "$branch"; then
      print -r -- "Deleted '$branch' ($reason)."
    else
      print -r -- "Skipping '$branch': Git refused deletion."
    fi
  done < <(
    git for-each-ref \
      --format='%(refname:short)%09%(upstream:track)%09%(upstream:remotename)' refs/heads
  )
}
