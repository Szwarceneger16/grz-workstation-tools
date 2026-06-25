# pr-open-comments

Fetch unresolved, non-outdated GitHub PR review comments and print a compact Markdown report for AI-assisted review work.

## Usage

```sh
pr-open-comments <PR_URL|PR_NUMBER> [latest|all]
pr-open-comments-copyq <PR_URL|PR_NUMBER> [latest|all]
```

## Arguments

- `<PR_URL|PR_NUMBER>` — GitHub pull request URL, or a PR number when run inside a GitHub repository.
- `latest` — default; return unresolved, non-outdated comments from the latest review batch.
- `all` — return all unresolved, non-outdated review comments.

## Examples

```sh
pr-open-comments https://github.com/owner/repo/pull/123
pr-open-comments 123
pr-open-comments 123 all
pr-open-comments-copyq 123
```

## CopyQ

`pr-open-comments-copyq` stores the generated Markdown in the CopyQ tab configured by `PR_COMMENTS_COPYQ_TAB`.

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
