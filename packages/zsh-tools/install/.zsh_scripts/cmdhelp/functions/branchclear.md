# branchclear

Remove local Git branches whose configured upstream is '[gone]', but only when
deletion can be justified. This function works with GitHub's **Squash and merge**
workflow, including a local branch that is an *older ancestor* of the PR's final
head commit.

## Usage

~~~sh
branchclear
branchclear --force
branchclear --help
~~~

## Safe mode (default)

1. Fetch/prune origin and find local branches tracking deleted upstreams.
2. Keep the current branch and require a valid default branch (origin/HEAD,
   falling back to origin/main or origin/master).
3. Prove safety if the local tip is already an ancestor of the default branch,
   or a simulated merge produces exactly the default branch's tree.
4. Otherwise, for branches tracking origin on github.com, optionally query
   merged GitHub PRs with the authenticated **GitHub CLI (gh)**. Deletion is
   allowed only if:
   - The PR head belongs to this exact repository and has the same branch name.
   - The merged PR targets the default branch.
   - Its merge commit is reachable from the fetched default branch.
   - The local branch tip is an ancestor of the PR's final head SHA.
   - If needed, refs/pull/N/head is fetched and its SHA verified against
     the API. A failed API call or inaccessible PR ref does not grant approval.
5. Check any linked worktree **after** proving safety. Keep worktrees containing
   modified, untracked, or ignored files. Remove only clean linked worktrees.
6. Check that the local branch SHA has not changed during verification, then
   delete its local reference. Remote branches are never deleted.

A conflict reported by merge-tree is **not** proof of unmerged changes after
a squash. If an authenticated GitHub PR cannot independently justify deletion,
the branch and linked worktree remain intact and the reason is printed.

No PR verification is attempted without an authenticated gh, on non-GitHub
remotes, or for upstreams other than origin. Pure Git ancestry/no-op checks
still work without gh. The GitHub check makes authenticated, read-only API
requests and may fetch the PR's head into FETCH_HEAD; it does not checkout
code or execute PR content.

## Force mode

branchclear --force explicitly overrides merge verification for '[gone]'
branches. It may **delete unmerged commits** and forcibly remove associated
worktrees, including uncommitted/untracked/ignored files. It does not affect
the currently checked out branch. Do not use this as a workaround for API
failure or merge conflicts.

## Troubleshooting

- Merge conflicts with no verified merged PR: check gh auth status and the
  corresponding merged PR, or leave the branch for manual inspection.
- Linked worktree contains changes: preserve or move its data and handle that
  worktree explicitly before retrying.
- Branch tip changed during verification: retry after other Git operations
  have stopped.
- No valid origin default branch: repair origin/HEAD or fetch the intended
  origin/main/origin/master rather than guessing from the current branch.
