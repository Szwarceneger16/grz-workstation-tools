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

MISE_MIN_VERSION="2026.10.3"

version_at_least() {
  local actual="$1" required="$2"
  local a_major a_minor a_patch r_major r_minor r_patch
  IFS=. read -r a_major a_minor a_patch <<<"$actual"
  IFS=. read -r r_major r_minor r_patch <<<"$required"

  [[ "$a_major" =~ ^[0-9]+$ && "$a_minor" =~ ^[0-9]+$ && "$a_patch" =~ ^[0-9]+$ ]] || return 1
  [[ "$r_major" =~ ^[0-9]+$ && "$r_minor" =~ ^[0-9]+$ && "$r_patch" =~ ^[0-9]+$ ]] || return 1

  if (( a_major != r_major )); then
    (( a_major > r_major ))
  elif (( a_minor != r_minor )); then
    (( a_minor > r_minor ))
  else
    (( a_patch >= r_patch ))
  fi
}

mise_bin="$TARGET_DIR/.local/bin/mise"
if [[ ! -x "$mise_bin" ]]; then
  mise_bin="$(command -v mise 2>/dev/null || true)"
fi
if [[ -z "$mise_bin" ]]; then
  printf 'not ok - mise >= %s is required for zsh-tools runtime/completion\n' "$MISE_MIN_VERSION" >&2
  exit 1
fi

mise_version="$(MISE_SELF_UPDATE_AVAILABLE=false "$mise_bin" --version 2>/dev/null | awk '{print $1}')"
if ! version_at_least "$mise_version" "$MISE_MIN_VERSION"; then
  printf 'not ok - mise %s is too old; zsh-tools requires >= %s\n' \
    "${mise_version:-unknown}" "$MISE_MIN_VERSION" >&2
  exit 1
fi

printf 'ok - mise %s satisfies zsh-tools minimum %s\n' "$mise_version" "$MISE_MIN_VERSION"
