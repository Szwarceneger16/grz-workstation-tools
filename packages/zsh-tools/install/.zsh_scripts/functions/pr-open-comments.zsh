__pr_open_comments_fetch_thread_comments() {
  emulate -L zsh

  local thread_id="$1"
  local out="$2"
  local cursor has_next page_count total_count page_tmp comments_tmp

  if [[ -z "$thread_id" || -z "$out" ]]; then
    echo "Internal error: missing thread id or output path for comment pagination." >&2
    return 1
  fi

  page_tmp="$(mktemp -t pr-review-comments-page.XXXXXX.json)"
  comments_tmp="$(mktemp -t pr-review-comments-nodes.XXXXXX.json)"

  : > "$comments_tmp"
  cursor="null"
  has_next="true"
  page_count=0
  total_count=0

  while [[ "$has_next" == "true" ]]; do
    gh api graphql \
      -f threadId="$thread_id" \
      -F cursor="$cursor" \
      -f query='
query($threadId: ID!, $cursor: String) {
  node(id: $threadId) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $cursor) {
        totalCount
        pageInfo {
          hasNextPage
          endCursor
        }
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
' > "$page_tmp" || {
      rm -f "$page_tmp" "$comments_tmp"
      return 1
    }

    if (( page_count == 0 )); then
      total_count="$(jq -r '.data.node.comments.totalCount // 0' "$page_tmp")" || {
        rm -f "$page_tmp" "$comments_tmp"
        return 1
      }
    fi

    jq -c '.data.node.comments.nodes[]?' "$page_tmp" >> "$comments_tmp" || {
      rm -f "$page_tmp" "$comments_tmp"
      return 1
    }

    has_next="$(jq -r '.data.node.comments.pageInfo.hasNextPage // false' "$page_tmp")" || {
      rm -f "$page_tmp" "$comments_tmp"
      return 1
    }
    cursor="$(jq -r '.data.node.comments.pageInfo.endCursor // "null"' "$page_tmp")" || {
      rm -f "$page_tmp" "$comments_tmp"
      return 1
    }
    (( ++page_count ))
  done

  jq -n --slurpfile comments "$comments_tmp" --argjson totalCount "$total_count" '
    {
      totalCount: $totalCount,
      pageInfo: {
        hasNextPage: false,
        endCursor: null
      },
      nodes: $comments
    }
  ' > "$out" || {
    rm -f "$page_tmp" "$comments_tmp"
    return 1
  }

  rm -f "$page_tmp" "$comments_tmp"
}

pr-open-comments() {
  emulate -L zsh

  local pr="$1"
  local mode="${2:-latest}" # latest, all, all-unresolved, all-resolved
  local owner repo number remote_url repo_path tmp threads_tmp pr_tmp page_tmp page_thread_nodes_tmp thread_node_tmp comments_full_tmp
  local cursor has_next page_count jq_status thread_node thread_id thread_comments_has_next page_threads_status

  if [[ "$pr" == "-h" || "$pr" == "--help" ]]; then
    if command -v cmdhelp >/dev/null 2>&1; then
      cmdhelp pr-open-comments && return 0
    fi

    echo "pr-open-comments - fetch GitHub PR review comments"
    echo
    echo "Usage:"
    echo "  pr-open-comments [PR_URL|PR_NUMBER] [latest|all|all-unresolved|all-resolved]"
    echo "  pr-open-comments [latest|all|all-unresolved|all-resolved]"
    echo "  pr-open-comments-copyq [PR_URL|PR_NUMBER] [latest|all|all-unresolved|all-resolved]"
    echo
    echo "Modes:"
    echo "  latest          Fetch unresolved non-outdated comments from the latest review batch."
    echo "  all             Fetch every review thread, regardless of resolved/outdated status."
    echo "  all-unresolved  Fetch all unresolved non-outdated comments."
    echo "  all-resolved    Fetch all resolved non-outdated comments."
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
  if [[ -z "$pr" || "$pr" == "latest" || "$pr" == "all" || "$pr" == "all-unresolved" || "$pr" == "all-resolved" ]]; then
    [[ "$pr" == "latest" || "$pr" == "all" || "$pr" == "all-unresolved" || "$pr" == "all-resolved" ]] && [[ -z "$2" ]] && mode="$pr"

    local pr_json pr_url
    pr_json="$(gh pr view --json url 2>/dev/null)" || {
      echo "Cannot infer PR for current branch." >&2
      echo "Hint: run this inside a branch with an open PR, or pass PR URL/number e.g.:" >&2
      echo "  pr-open-comments https://github.com/owner/repo/pull/123" >&2
      echo "  pr-open-comments 123" >&2
      echo "  pr-open-comments all" >&2
      echo "  pr-open-comments all-unresolved" >&2
      echo "  pr-open-comments all-resolved" >&2
      return 2
    }

    pr_url="$(jq -r .url <<< "$pr_json")"

    if [[ "$pr_url" =~ '^https://github.com/([^/]+)/([^/]+)/pull/([0-9]+)' ]]; then
      owner="${match[1]}"
      repo="${match[2]}"
      number="${match[3]}"
    else
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

  if [[ "$mode" != "latest" && "$mode" != "all" && "$mode" != "all-unresolved" && "$mode" != "all-resolved" ]]; then
    echo "Expected mode: latest, all, all-unresolved, or all-resolved, got: $mode" >&2
    return 2
  fi

  tmp="$(mktemp -t pr-review-threads.XXXXXX.json)"
  threads_tmp="$(mktemp -t pr-review-thread-nodes.XXXXXX.json)"
  pr_tmp="$(mktemp -t pr-review-pr.XXXXXX.json)"
  page_tmp="$(mktemp -t pr-review-page.XXXXXX.json)"
  page_thread_nodes_tmp="$(mktemp -t pr-review-thread-page-nodes.XXXXXX.json)"
  thread_node_tmp="$(mktemp -t pr-review-thread-node.XXXXXX.json)"
  comments_full_tmp="$(mktemp -t pr-review-comments-full.XXXXXX.json)"

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
            totalCount
            pageInfo {
              hasNextPage
              endCursor
            }
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
      rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp" "$page_thread_nodes_tmp" "$thread_node_tmp" "$comments_full_tmp"
      return 1
    }

    if (( page_count == 0 )); then
      jq '.data.repository.pullRequest | {title, url, headRefName, headRefOid}' "$page_tmp" > "$pr_tmp" || {
        rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp" "$page_thread_nodes_tmp" "$thread_node_tmp" "$comments_full_tmp"
        return 1
      }
    fi

    jq -c '.data.repository.pullRequest.reviewThreads.nodes[]' "$page_tmp" > "$page_thread_nodes_tmp" || {
      rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp" "$page_thread_nodes_tmp" "$thread_node_tmp" "$comments_full_tmp"
      return 1
    }

    page_threads_status=0
    while IFS= read -r thread_node; do
      thread_comments_has_next="$(jq -r '.comments.pageInfo.hasNextPage // false' <<< "$thread_node")" || {
        page_threads_status=1
        break
      }

      if [[ "$thread_comments_has_next" == "true" ]]; then
        thread_id="$(jq -r '.id' <<< "$thread_node")" || {
          page_threads_status=1
          break
        }

        print -r -- "$thread_node" > "$thread_node_tmp"

        if ! __pr_open_comments_fetch_thread_comments "$thread_id" "$comments_full_tmp"; then
          page_threads_status=1
          break
        fi

        jq --slurpfile comments "$comments_full_tmp" '.comments = $comments[0]' "$thread_node_tmp" >> "$threads_tmp" || {
          page_threads_status=1
          break
        }
      else
        print -r -- "$thread_node" >> "$threads_tmp"
      fi
    done < "$page_thread_nodes_tmp"

    if (( page_threads_status != 0 )); then
      rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp" "$page_thread_nodes_tmp" "$thread_node_tmp" "$comments_full_tmp"
      return 1
    fi

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
    rm -f "$tmp" "$threads_tmp" "$pr_tmp" "$page_tmp" "$page_thread_nodes_tmp" "$thread_node_tmp" "$comments_full_tmp"
    return 1
  }

  rm -f "$threads_tmp" "$pr_tmp" "$page_tmp" "$page_thread_nodes_tmp" "$thread_node_tmp" "$comments_full_tmp"

  jq -r --arg mode "$mode" '
    def trim:
      gsub("^[[:space:]]+"; "")
      | gsub("[[:space:]]+$"; "");

    def drop_empty_start:
      if length > 0 and ((.[0] | trim) == "") then
        .[1:] | drop_empty_start
      else
        .
      end;

    def drop_empty_end:
      if length > 0 and ((.[-1] | trim) == "") then
        .[0:-1] | drop_empty_end
      else
        .
      end;

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
      | drop_empty_start
      | drop_empty_end
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
              | join("\n\nReply:\n")
            ),
            comments: .comments.nodes,
            commentTotalCount: (.comments.totalCount // (.comments.nodes | length)),
            commentFetchedCount: (.comments.nodes | length),
            commentPageTruncated: (.comments.pageInfo.hasNextPage // false)
          })
      ) as $threads

    | ($threads | map(select(.isResolved == false and .isOutdated == false))) as $open
    | ($threads | map(select(.isResolved == true and .isOutdated == false))) as $resolved

    | (
        $open
        | sort_by(.reviewSubmittedAt, .rootCreatedAt)
        | reverse
        | .[0].reviewId // null
      ) as $latestReviewId

    | (
        if ($mode == "all") then
          $threads | sort_by(.reviewSubmittedAt, .rootCreatedAt) | reverse
        elif ($mode == "all-unresolved") then
          $open | sort_by(.reviewSubmittedAt, .rootCreatedAt) | reverse
        elif ($mode == "all-resolved") then
          $resolved | sort_by(.reviewSubmittedAt, .rootCreatedAt) | reverse
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

    | (
        if ($mode == "all") then
          "all review threads, including resolved and outdated"
        elif ($mode == "all-unresolved") then
          "all unresolved non-outdated threads"
        elif ($mode == "all-resolved") then
          "all resolved non-outdated threads"
        else
          "unresolved non-outdated latest review batch"
        end
      ) as $filterLabel

    | "## PR review comments"
      + "\nPR: " + $pr.url
      + "\nTitle: " + $pr.title
      + "\nHead: " + $pr.headRefName + " / " + $pr.headRefOid
      + "\nMode: " + $mode
      + "\nFilter: " + $filterLabel
      + "\nSelected: " + ($selected | length | tostring)
      + "\nTotal threads: " + ($threads | length | tostring)
      + "\nUnresolved non-outdated: " + ($open | length | tostring)
      + "\nResolved non-outdated: " + ($resolved | length | tostring)
      + "\nPaginated comment threads: "
      + ($threads | map(select(.commentTotalCount > 100)) | length | tostring)
      + "\nTotal comments fetched: "
      + ($threads | map(.commentFetchedCount) | add // 0 | tostring)
      + "\nOlder open threads outside latest batch: "
      + (
          if $mode != "latest" or $latestReviewId == null then
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
              + "\nStatus: " + (if .value.isResolved then "resolved" else "unresolved" end)
              + (if .value.isOutdated then " + outdated" else "" end)
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

