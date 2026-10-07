#!/bin/sh
set -eu

repo_root="${GRZ_REPO_ROOT:?GRZ_REPO_ROOT is required}"

exec python3 "$repo_root/tests/test_runner_zsh_tools_mise.py" -v
