#!/usr/bin/env bash
set -Eeuo pipefail

# Read-only check that ~/.zshrc and ~/.profile carry the rc.d / profile.d loader
# blocks so the installed fragments actually run. Does not modify anything.

REPO_ROOT="${GRZ_REPO_ROOT:?GRZ_REPO_ROOT is required}"
TARGET_DIR="${STOW_TARGET:-$HOME}"

if STOW_TARGET="$TARGET_DIR" "$REPO_ROOT/scripts/ensure-rcd-loaders" --check; then
  printf 'ok - zsh-tools rc.d/profile.d loaders present in %s\n' "$TARGET_DIR"
else
  printf 'not ok - zsh-tools loaders missing in %s (run: ./run.sh install zsh-tools)\n' "$TARGET_DIR" >&2
  exit 1
fi
