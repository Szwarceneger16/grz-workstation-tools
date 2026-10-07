# zsh-tools package

Owns public Zsh runtime files.

Completion initialization and reload behavior are documented in
[`docs/zsh-completion-lifecycle.md`](../../docs/zsh-completion-lifecycle.md).
Mise startup/path behavior and the hard Volta/Corepack cutover are documented in
[`docs/mise-shell-integration.md`](../../docs/mise-shell-integration.md).

Mise PATH/activation regressions are stored in `tests/test_runner_zsh_tools_mise.py`;
CI discovers them through the repository `test_runner_*.py` pattern, while
`packages/zsh-tools/tests/mise-regression.sh` exposes the same suite through
`./run.sh test zsh-tools`.
