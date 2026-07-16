# Final PATH normalization.
# Sourced last among core/*.zsh (60-grz-workstation-tools-post.zsh's `core/*.zsh(N)`
# loop, ordered by filename), after Oh My Zsh and every other core/plugin has
# had a chance to prepend/append its own PATH entries.
#
# Goals:
# - keep user custom commands first
# - keep Volta before system node/npm/corepack/pnpm
# - keep ~/.local/bin available but below Volta
# - remove duplicate PATH entries
# - remove obsolete bare PNPM_HOME from PATH
# - keep pnpm 11 global binary directory as PNPM_HOME/bin

export VOLTA_HOME="${VOLTA_HOME:-$HOME/.volta}"
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"

typeset -a __grz_path_original
typeset -a __grz_path_normalized
typeset -A __grz_path_seen
typeset __grz_path_item
typeset __grz_volta_bin
typeset __grz_pnpm_bin

__grz_path_original=("${(@s/:/)PATH}")
__grz_path_normalized=()
__grz_volta_bin="$VOLTA_HOME/bin"
__grz_pnpm_bin="$PNPM_HOME/bin"

__grz_path_add() {
  local __grz_dir="$1"

  [[ -n "$__grz_dir" ]] || return 0
  [[ -n "${__grz_path_seen[$__grz_dir]:-}" ]] && return 0

  __grz_path_normalized+=("$__grz_dir")
  __grz_path_seen[$__grz_dir]=1
}

__grz_path_add_existing() {
  local __grz_dir="$1"

  [[ -d "$__grz_dir" ]] || return 0
  __grz_path_add "$__grz_dir"
}

# Hard priority section.
__grz_path_add_existing "$HOME/.local/my-custom-bin"
__grz_path_add_existing "$__grz_volta_bin"
__grz_path_add_existing "$HOME/.local/bin"

# Preserve the rest of inherited PATH order, but without duplicates and without
# entries that are intentionally managed above/below.
for __grz_path_item in "${__grz_path_original[@]}"; do
  [[ -n "$__grz_path_item" ]] || continue

  case "$__grz_path_item" in
    "$HOME/.local/my-custom-bin") continue ;;
    "$__grz_volta_bin") continue ;;
    "$HOME/.local/bin") continue ;;
    "$PNPM_HOME") continue ;;
    "$__grz_pnpm_bin") continue ;;
  esac

  __grz_path_add "$__grz_path_item"
done

# pnpm 11 global package binaries live here.
__grz_path_add_existing "$__grz_pnpm_bin"

export PATH="${(j/:/)__grz_path_normalized}"

unfunction __grz_path_add __grz_path_add_existing 2>/dev/null || true
unset __grz_path_original \
      __grz_path_normalized \
      __grz_path_seen \
      __grz_path_item \
      __grz_volta_bin \
      __grz_pnpm_bin
