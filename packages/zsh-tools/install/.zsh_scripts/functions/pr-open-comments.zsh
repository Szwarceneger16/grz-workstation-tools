pr-open-comments() {
  emulate -L zsh

  local pr="$1"
  local mode="${2:-latest}" # latest albo all
  local owner repo number remote_url repo_path tmp threads_tmp pr_tmp page_tmp
  local cursor has_next page_count jq_status

  if [[ -z "$pr" ]]; then
    echo "Usage: pr-open-comments <PR_URL|PR_NUMBER> [latest|all]" >&2
    return 2
  fi

  if [[ "$mode" != "latest" && "$mode" != "all" ]]; then
    echo "Expected mode: latest or all, got: $mode" >&2
    return 2
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "Missing dependency: gh" >&2
    return 1
  fi

  if ! command -v jq >/dev/null 2>&1; then
    echo "Missing dependency: jq" >&2
    return 1
  fi

  if [[ "$pr" =~ '^https://github.com/([^/]+)/([^/]+)/pull/([0-9]+)' ]]; then
    owner="${match[1]}"
    repo="${match[2]}"
    number="${match[3]}"
  elif [[ "$pr" =~ '^[0-9]+$' ]]; then
    number="$pr"
    remote_url="$(git remote get-url origin 2>/dev/null)" || {
      echo "Cannot infer repo: not inside a git repo or no origin remote." >&2
      return 1
    }

    repo_path="$(printf '%s\n' "$remote_url" \
      | sed -E 's#^git@github\.com:##; s#^https?://github\.com/##; s#^ssh://git@github\.com/##; s#\.git$##')"

    owner="${repo_path%%/*}"
    repo="${repo_path#*/}"

    if [[ -z "$owner" || -z "$repo" || "$owner" == "$repo" || "$repo_path" != */* ]]; then
      echo "Cannot infer GitHub owner/repo from origin remote: $remote_url" >&2
      return 1
    fi
  else
    echo "Expected GitHub PR URL or PR number, got: $pr" >&2
    return 2
  fi

  tmp="$(mktemp -t pr-review-threads.XXXXXX.json)"
  threads_tmp="$(mktemp -t pr-review-thread-nodes.XXXXXX.json)"
  pr_tmp="$(mktemp -t pr-review-pr.XXXXXX.json)"
  page_tmp="$(mktemp -t pr-review-page.XXXXXX.json)"

  : > "$threads_tmp"
  cursor="null"
  has_next="true"
  page_count=0

  while [[ "$has_next" == "true" ]]; do
    gh api graphql \
      -f owner="$owner" \
      -f name="$repo" \
      -F number="$number" \
      -F cursor="$cursor" \
      -f query='
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      title
      url
      headRefName
      headRefOid
      reviewThreads(first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          originalLine
          comments(first: 30) {
            nodes {
              id
              databaseId
              author { login }
              body
              createdAt
              updatedAt
              url
              path
              line
              originalLine
              diffHunk
              pullRequestReview {
                databaseId
                submittedAt
                url
                author { login }
              }
            }
          }
        }
      }
    }
  }
}
' > "$page_tmp" || {
      rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp"
      return 1
    }

    if (( page_count == 0 )); then
      jq '.data.repository.pullRequest | {title, url, headRefName, headRefOid}' "$page_tmp" > "$pr_tmp" || {
        rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp"
        return 1
      }
    fi

    jq -c '.data.repository.pullRequest.reviewThreads.nodes[]' "$page_tmp" >> "$threads_tmp" || {
      rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp"
      return 1
    }

    has_next="$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage' "$page_tmp")"
    cursor="$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor // "null"' "$page_tmp")"
    (( page_count++ ))
  done

  jq -n --slurpfile pr "$pr_tmp" --slurpfile threads "$threads_tmp" '
    {
      data: {
        repository: {
          pullRequest: ($pr[0] + {reviewThreads: {nodes: $threads}})
        }
      }
    }
  ' > "$tmp" || {
    rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp"
    return 1
  }

  rm -f "$threads_tmp" "$pr_tmp" "$page_tmp"

  jq -r --arg mode "$mode" '
    def clean_title:
      split("\n")
      | map(gsub("\\*"; ""))
      | map(gsub("</?sub>"; ""))
      | map(gsub("!\\[[^\\]]*\\]\\([^)]*\\)[[:space:]]*"; ""))
      | map(gsub("^[[:space:]>#*\\-]+"; ""))
      | map(gsub("^[[:space:]]+"; ""))
      | map(gsub("[[:space:]]+$"; ""))
      | map(select(length > 0))
      | .[0] // "Untitled review comment"
      | if length > 120 then .[0:117] + "..." else . end;

    .data.repository.pullRequest as $pr
    | (
        $pr.reviewThreads.nodes
        | map({
            id,
            isResolved,
            isOutdated,
            path,
            line: (.line // .originalLine),
            rootAuthor: (.comments.nodes[0].author.login // "unknown"),
            rootCreatedAt: (.comments.nodes[0].createdAt // ""),
            reviewId: (.comments.nodes[0].pullRequestReview.databaseId // null),
            reviewSubmittedAt: (.comments.nodes[0].pullRequestReview.submittedAt // .comments.nodes[0].createdAt // ""),
            url: (.comments.nodes[0].url // ""),
            title: ((.comments.nodes[0].body // "") | clean_title),
            body: (.comments.nodes[0].body // ""),
            comments: .comments.nodes
          })
        | map(select(.isResolved == false and .isOutdated == false))
      ) as $open

    | (
        $open
        | sort_by(.reviewSubmittedAt, .rootCreatedAt)
        | reverse
        | .[0].reviewId // null
      ) as $latestReviewId

    | (
        if ($mode == "all") then
          $open | sort_by(.reviewSubmittedAt, .rootCreatedAt) | reverse
        else
          if $latestReviewId == null then
            $open | sort_by(.reviewSubmittedAt, .rootCreatedAt) | reverse
          else
            $open
            | map(select(.reviewId == $latestReviewId))
            | sort_by(.reviewSubmittedAt, .rootCreatedAt)
            | reverse
          end
        end
      ) as $selected

    | "## Latest unresolved PR review comments\n"
      + "\nPR: " + $pr.url
      + "\nTitle: " + $pr.title
      + "\nHead: " + $pr.headRefName + " / " + $pr.headRefOid
      + "\nFilter: unresolved + non-outdated + " + (if $mode == "all" then "all open threads" else "latest review batch" end)
      + "\nSelected: " + ($selected | length | tostring)
      + "\nOlder open threads outside latest batch: "
      + (
          if $mode == "all" or $latestReviewId == null then
            "0"
          else
            ($open | map(select(.reviewId != $latestReviewId)) | length | tostring)
          end
        )
      + "\n"
      + (
          $selected
          | to_entries
          | map(
              "\n---\n"
              + "\n### " + ((.key + 1) | tostring) + ". " + .value.title
              + "\n"
              + "\n**File:** `" + (.value.path // "?") + ":" + ((.value.line // 0) | tostring) + "`"
              + "\n**Reviewer:** " + (.value.rootAuthor // "unknown")
              + "\n**Review ID:** " + ((.value.reviewId // "none") | tostring)
              + "\n**Created:** " + (.value.rootCreatedAt // "")
              + "\n**URL:** " + (.value.url // "")
              + "\n"
              + "\n**Comment body:**\n"
              + "\n```markdown\n"
              + (.value.body // "")
              + "\n```\n"
            )
          | join("")
        )
  ' "$tmp"
  jq_status=$?

  rm -f "$tmp"
  return $jq_status
}

pr-open-comments-copyq() {
  emulate -L zsh

  local tab="${PR_COMMENTS_COPYQ_TAB:-PR_comments}"
  local output tmp

  if ! command -v copyq >/dev/null 2>&1; then
    echo "Missing dependency: copyq" >&2
    return 1
  fi

  output="$(pr-open-comments "$@")" || return $?

  tmp="$(mktemp -t pr-open-comments.XXXXXX.md)"
  printf '%s\n' "$output" > "$tmp"

  # Ensure CopyQ is running.
  if ! copyq tab "$tab" size >/dev/null 2>&1; then
    copyq >/dev/null 2>&1 &
    sleep 0.7
  fi

  # Add markdown output as a new top item in the dedicated tab.
  if ! copyq tab "$tab" add - < "$tmp"; then
    rm -f "$tmp"
    echo "Failed to add item to CopyQ tab: $tab" >&2
    return 1
  fi

  rm -f "$tmp"

  # Focus/select newest item and make it the active system clipboard item.
  copyq tab "$tab" select 0 >/dev/null 2>&1
  copyq tab "$tab" show >/dev/null 2>&1

  echo "Copied PR comments to CopyQ tab '$tab' and focused item 0."
}

# Replace old generic clipboard helper with CopyQ behavior.
pr-open-comments-copy() {
  pr-open-comments-copyq "$@"
}
