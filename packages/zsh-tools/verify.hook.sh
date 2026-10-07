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

mise_bin="$TARGET_DIR/.local/bin/mise"
if [[ ! -f "$mise_bin" || ! -x "$mise_bin" ]]; then
  # An alternate home does not inherit the caller's private tool directories.
  # Resolve only its custom bin and the standard shared system bin directories.
  if [[ "$TARGET_DIR" -ef "$HOME" ]]; then
    mise_bin="$(type -P mise 2>/dev/null || true)"
  else
    mise_bin="$(PATH="$TARGET_DIR/.local/my-custom-bin:/usr/local/bin:/usr/bin:/bin" \
      type -P mise 2>/dev/null || true)"
  fi
fi
# Apply the physical-path check to every candidate, including .local/bin.
if [[ ! "$TARGET_DIR" -ef "$HOME" && -n "$mise_bin" ]]; then
  resolved_mise="$(readlink -f -- "$mise_bin" || true)"
  resolved_home="$(readlink -f -- "$HOME" || true)"
  resolved_target="$(readlink -f -- "$TARGET_DIR" || true)"
  case "$resolved_mise" in
    "$resolved_target"/*) ;; # The selected target may itself be under HOME.
    "$resolved_home"/*) mise_bin= ;;
  esac
fi
if [[ -z "$mise_bin" || ! -f "$mise_bin" || ! -x "$mise_bin" ]]; then
  printf 'not ok - mise with __complete_word__ support is required for zsh-tools runtime/completion\n' >&2
  exit 1
fi

if ! HOME="$TARGET_DIR" MISE_SELF_UPDATE_AVAILABLE=false MISE_DISABLE_UPDATE_WARNING=true "$mise_bin" help __complete_word__ >/dev/null 2>&1; then
  printf 'not ok - mise lacks the __complete_word__ capability required by zsh-tools completion\n' >&2
  exit 1
fi

printf 'ok - mise completion capability satisfies zsh-tools runtime/completion contract\n'
