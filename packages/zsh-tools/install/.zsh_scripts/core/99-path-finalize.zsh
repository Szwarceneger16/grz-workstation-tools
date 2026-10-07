# Final PATH normalization.
# Sourced last among core/*.zsh (60-grz-workstation-tools-post.zsh's `core/*.zsh(N)`
# loop, ordered by filename), after Oh My Zsh and every other core/plugin has
# had a chance to prepend/append its own PATH entries.
#
# Goals:
# - keep user custom commands first
# - keep ~/.local/bin available
# - preserve the remaining inherited PATH order
# - remove duplicate PATH entries
# - strip inherited Volta paths during the hard cutover
# - keep pnpm global package executables at lowest priority
#
# Runtime/package-manager CLI selection is intentionally handled outside this
# finalizer by later rc.d integration such as mise activation.

# Isolate array/glob semantics and temporaries from caller options and state.
() {
  builtin emulate -L 'zsh'
  setopt typesetsilent
  local -a __grz_path_original __grz_path_normalized
  local -A __grz_path_seen
  local __grz_path_item __grz_path_key __grz_pnpm_bin
  local __grz_default_volta_bin __grz_inherited_volta_bin REPLY

  # Match the POSIX profile's lexical identity policy, including missing dirs.
  __grz_path_normalize() {
    local __grz_dir="$1"
    while [[ "$__grz_dir" == *//* ]]; do
      __grz_dir="${__grz_dir%%//*}/${__grz_dir#*//}"
    done
    while [[ "$__grz_dir" == */./* ]]; do
      __grz_dir="${__grz_dir%%/./*}/${__grz_dir#*/./}"
    done
    while [[ "$__grz_dir" == */. || "$__grz_dir" == ?*/ ]]; do
      if [[ "$__grz_dir" == */. ]]; then
        __grz_dir="${__grz_dir%/.}"
      else
        __grz_dir="${__grz_dir%/}"
      fi
      [[ -n "$__grz_dir" ]] || __grz_dir=/
    done
    REPLY="$__grz_dir"
  }

  export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
  __grz_path_normalize "$HOME/.volta/bin"
  __grz_default_volta_bin="$REPLY"
  __grz_path_normalize "${VOLTA_HOME:-$HOME/.volta}/bin"
  __grz_inherited_volta_bin="$REPLY"
  unset VOLTA_HOME
  __grz_path_normalize "$PNPM_HOME/bin"
  __grz_pnpm_bin="$REPLY"
  __grz_path_original=("${(@s/:/)PATH}")

  __grz_path_add() {
    local __grz_dir="$1"
    [[ -n "$__grz_dir" ]] || return 0
    __grz_path_normalize "$__grz_dir"
    [[ -n "${__grz_path_seen[$REPLY]:-}" ]] && return 0
    __grz_path_normalized+=("$__grz_dir")
    __grz_path_seen[$REPLY]=1
  }

  # Hard priority section.
  [[ ! -d "$HOME/.local/my-custom-bin" ]] || __grz_path_add "$HOME/.local/my-custom-bin"
  [[ ! -d "$HOME/.local/bin" ]] || __grz_path_add "$HOME/.local/bin"

  # Preserve other entries while comparing managed directories canonically.
  for __grz_path_item in "${__grz_path_original[@]}"; do
    __grz_path_normalize "$__grz_path_item"
    __grz_path_key="$REPLY"
    [[ "$__grz_path_key" == "$__grz_default_volta_bin" ||
       "$__grz_path_key" == "$__grz_inherited_volta_bin" ||
       "$__grz_path_key" == "$__grz_pnpm_bin" ]] && continue
    __grz_path_normalize "$PNPM_HOME"
    [[ "$__grz_path_key" == "$REPLY" ]] && continue
    __grz_path_add "$__grz_path_item"
  done

  __grz_path_add "$__grz_pnpm_bin"
  export PATH="${(j/:/)__grz_path_normalized}"
  unfunction __grz_path_add __grz_path_normalize
}
