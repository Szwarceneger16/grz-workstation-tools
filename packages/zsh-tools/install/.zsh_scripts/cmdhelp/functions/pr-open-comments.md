# pr-open-comments

Fetch GitHub PR review comments and print a compact Markdown report for AI-assisted review work.

## Usage

```sh
pr-open-comments [latest|all|all-unresolved|all-resolved]
pr-open-comments <PR_URL|PR_NUMBER> [latest|all|all-unresolved|all-resolved]
pr-open-comments-copyq [latest|all|all-unresolved|all-resolved]
pr-open-comments-copyq <PR_URL|PR_NUMBER> [latest|all|all-unresolved|all-resolved]
```

## Arguments

- `<PR_URL|PR_NUMBER>` — GitHub pull request URL, or a PR number when run inside a GitHub repository. When omitted, the PR is inferred from the current branch via `gh pr view`.
- `latest` — default; return unresolved, non-outdated comments from the latest review batch.
- `all` — return every review thread, including resolved and outdated threads.
- `all-unresolved` — return all unresolved, non-outdated review comments.
- `all-resolved` — return all resolved, non-outdated review comments.

## Examples

```sh
# Auto-detect PR from the current branch
pr-open-comments
pr-open-comments all
pr-open-comments all-unresolved
pr-open-comments all-resolved

# Explicit PR URL or number
pr-open-comments https://github.com/owner/repo/pull/123
pr-open-comments 123
pr-open-comments 123 all
pr-open-comments 123 all-unresolved
pr-open-comments 123 all-resolved
pr-open-comments-copyq 123 all
```

## CopyQ

`pr-open-comments-copyq` stores the generated Markdown in the CopyQ tab configured by `PR_COMMENTS_COPYQ_TAB` and sets the active system clipboard.

Default tab:

```sh
PR_comments
```

Override:

```sh
export PR_COMMENTS_COPYQ_TAB="AI_PR_comments"
```

Large outputs:

```sh
export PR_COMMENTS_COPYQ_ARG_LIMIT=900000
```

If the generated report is larger than this limit, `pr-open-comments-copyq` stores the Markdown under `${XDG_CACHE_HOME:-$HOME/.cache}/pr-open-comments` and adds a CopyQ item pointing to that file.

## Dependencies

- `gh`
- `jq`
- `copyq` for `pr-open-comments-copyq`
