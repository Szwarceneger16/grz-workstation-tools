pr-open-comments() {
  emulate -L zsh

  local pr="$1"
  local mode="${2:-latest}" # latest albo all
  local owner repo number remote_url repo_path tmp threads_tmp pr_tmp page_tmp
  local cursor has_next page_count jq_status

  if [[ "$pr" == "-h" || "$pr" == "--help" ]]; then
    if command -v cmdhelp >/dev/null 2>&1; then
      cmdhelp pr-open-comments && return 0
    fi

    echo "pr-open-comments - fetch unresolved GitHub PR review comments"
    echo
    echo "Usage:"
    echo "  pr-open-comments [PR_URL|PR_NUMBER] [latest|all]"
    echo "  pr-open-comments [latest|all]"
    echo "  pr-open-comments-copyq [PR_URL|PR_NUMBER] [latest|all]"
    echo
    echo "Modes:"
    echo "  latest  Fetch unresolved non-outdated comments from the latest review batch."
    echo "  all     Fetch all unresolved non-outdated comments."
    return 0
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "Missing dependency: gh" >&2
    return 1
  fi

  if ! command -v jq >/dev/null 2>&1; then
    echo "Missing dependency: jq" >&2
    return 1
  fi

  # Resolve PR target → owner, repo, number.
  # Three paths: (1) auto-detect from current branch, (2) explicit URL, (3) explicit number.
  if [[ -z "$pr" || "$pr" == "latest" || "$pr" == "all" ]]; then
    [[ "$pr" == "latest" || "$pr" == "all" ]] && [[ -z "$2" ]] && mode="$pr"

    local pr_json
    pr_json="$(gh pr view --json number,headRepository 2>/dev/null)" || {
      echo "Cannot infer PR for current branch." >&2
      echo "Hint: run this inside a branch with an open PR, or pass PR URL/number e.g.:" >&2
      echo "  pr-open-comments https://github.com/owner/repo/pull/123" >&2
      echo "  pr-open-comments 123" >&2
      echo "  pr-open-comments all" >&2
      return 2
    }

    number="$(jq -r .number <<< "$pr_json")"
    owner="$(jq -r .headRepository.owner.login <<< "$pr_json")"
    repo="$(jq -r .headRepository.name <<< "$pr_json")"

    if [[ -z "$number" || "$number" == "null" || -z "$owner" || "$owner" == "null" || -z "$repo" || "$repo" == "null" ]]; then
      echo "Cannot infer PR for current branch: gh returned incomplete data." >&2
      return 2
    fi
  elif [[ "$pr" =~ '^https://github.com/([^/]+)/([^/]+)/pull/([0-9]+)' ]]; then
    owner="${match[1]}"
    repo="${match[2]}"
    number="${match[3]}"
  elif [[ "$pr" =~ '^[0-9]+$' ]]; then
    number="$pr"
    remote_url="$(git remote get-url origin 2>/dev/null)" || {
      echo "Cannot infer repo: not inside a git repo or no origin remote." >&2
      return 1
    }

    repo_path="$remote_url"

    # Strip URL query/fragment if present.
    repo_path="${repo_path%%\?*}"
    repo_path="${repo_path%%#*}"

    # Normalize common Git remote forms while accepting arbitrary SSH host aliases:
    #   git@alias:owner/repo.git
    #   ssh://git@alias/owner/repo.git
    #   https://host/owner/repo.git
    #   owner/repo.git
    if [[ "$repo_path" == *"://"* ]]; then
      repo_path="${repo_path#*://}"
      repo_path="${repo_path#*@}"
      repo_path="${repo_path#*/}"
    elif [[ "$repo_path" == *@*:* ]]; then
      repo_path="${repo_path#*:}"
    elif [[ "$repo_path" == *:* && "$repo_path" != */* ]]; then
      echo "Cannot infer GitHub owner/repo from origin remote: $remote_url" >&2
      return 1
    fi

    repo_path="${repo_path%.git}"

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

  if [[ "$mode" != "latest" && "$mode" != "all" ]]; then
    echo "Expected mode: latest or all, got: $mode" >&2
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
          comments(first: 100) {
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
    (( ++page_count ))
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
    def trim:
      gsub("^[[:space:]]+"; "")
      | gsub("[[:space:]]+$"; "");

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

    def clean_comment_body:
      (split("\n") | map(gsub("\\r$"; ""))) as $lines
      | (
          if (($lines[0] // "") | test("^\\*\\*<sub><sub>!\\[[^\\]]*Badge\\]\\([^)]*\\)</sub></sub>[[:space:]]+.*\\*\\*$")) then
            $lines[1:]
          else
            $lines
          end
        )
      | map(select(((. | trim) | test("^Useful\\? React with")) | not))
      | while(length > 0 and ((.[0] | trim) == ""); .[1:])
      | while(length > 0 and ((.[-1] | trim) == ""); .[0:-1])
      | join("\n");

    .data.repository.pullRequest as $pr
    | (
        $pr.reviewThreads.nodes
        | map({
            id,
            isResolved,
            isOutdated,
            path,
            line: (.line // .originalLine),
            location: (
              (.path // "?")
              + (
                  if (.line // .originalLine) == null then
                    " (file-level)"
                  else
                    ":" + ((.line // .originalLine) | tostring)
                  end
                )
            ),
            rootAuthor: (.comments.nodes[0].author.login // "unknown"),
            rootCreatedAt: (.comments.nodes[0].createdAt // ""),
            reviewId: (.comments.nodes[0].pullRequestReview.databaseId // null),
            reviewSubmittedAt: (.comments.nodes[0].pullRequestReview.submittedAt // .comments.nodes[0].createdAt // ""),
            url: (.comments.nodes[0].url // ""),
            title: ((.comments.nodes[0].body // "") | clean_title),
            body: (.comments.nodes[0].body // ""),
            commentText: (
              .comments.nodes
              | map((.body // "") | clean_comment_body)
              | map(select(length > 0))
              | join("

Reply:
")
            ),
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

    | "## Latest unresolved PR review comments"
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
              + "### " + ((.key + 1) | tostring) + ". " + .value.title
              + "\nFile: " + (.value.location // "?")
              + "\nURL: " + (.value.url // "")
              + "\n"
              + (.value.commentText // "")
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

  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    pr-open-comments --help
    return $?
  fi

  local tab="${PR_COMMENTS_COPYQ_TAB:-PR_comments}"
  local output tmp size limit cache_dir saved copy_payload

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
  # For very large reports, avoid passing megabytes through argv.
  size="$(wc -c < "$tmp" | tr -d '[:space:]')"
  limit="${PR_COMMENTS_COPYQ_ARG_LIMIT:-900000}"

  if (( size > limit )); then
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/pr-open-comments"
    mkdir -p "$cache_dir" || {
      rm -f "$tmp"
      echo "Failed to create cache directory: $cache_dir" >&2
      return 1
    }

    saved="$cache_dir/pr-comments-$(date +%Y%m%d-%H%M%S).md"
    cp "$tmp" "$saved" || {
      rm -f "$tmp"
      echo "Failed to save large PR comments output to: $saved" >&2
      return 1
    }

    copy_payload="PR comments output is too large for safe CopyQ argv insertion. Markdown saved to: $saved"

    if ! copyq tab "$tab" add "$copy_payload"; then
      rm -f "$tmp"
      echo "Failed to add pointer item to CopyQ tab: $tab" >&2
      return 1
    fi
  else
    copy_payload="$output"

    if ! copyq tab "$tab" add "$copy_payload"; then
      rm -f "$tmp"
      echo "Failed to add item to CopyQ tab: $tab" >&2
      return 1
    fi
  fi

  rm -f "$tmp"

  # Set the active system clipboard without opening the CopyQ window.
  if ! copyq copy "$copy_payload"; then
    echo "Failed to set system clipboard with CopyQ" >&2
    return 1
  fi

  echo "Copied PR comments to system clipboard and CopyQ tab '$tab'."
}

