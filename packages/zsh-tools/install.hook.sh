#!/usr/bin/env bash
set -Eeuo pipefail

# Runs after stow on `./run.sh install zsh-tools`. No package owns ~/.zshrc or
# ~/.profile; this only appends the rc.d / profile.d loader blocks when they are
# missing (idempotent, never rewrites the user's own content). This is what makes
# a clean install self-sufficient without hand-pasting a bootstrap snippet.

REPO_ROOT="${GRZ_REPO_ROOT:?GRZ_REPO_ROOT is required}"
TARGET_DIR="${STOW_TARGET:-$HOME}"

STOW_TARGET="$TARGET_DIR" "$REPO_ROOT/scripts/ensure-rcd-loaders"
printf 'ok - zsh-tools rc.d/profile.d loaders ensured in %s\n' "$TARGET_DIR"
