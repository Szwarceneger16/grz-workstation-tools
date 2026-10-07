# mise shims for login shells and GUI/IDE processes that do not execute
# interactive `mise activate zsh`.
# MISE_SHIMS_DIR > MISE_DATA_DIR > XDG_DATA_HOME/default data directory.

# Compare directory spellings without filesystem access: repeated separators,
# /./ components and trailing slashes do not change a directory's identity.
# Do not collapse .. or resolve symlinks, which can change path semantics.
_grz_profile_path_normalize() {
    _grz_profile_normalized="$1"
    while case "$_grz_profile_normalized" in *//*) true ;; *) false ;; esac; do
        _grz_profile_normalized="${_grz_profile_normalized%%//*}/${_grz_profile_normalized#*//}"
    done
    while case "$_grz_profile_normalized" in */./*) true ;; *) false ;; esac; do
        _grz_profile_normalized="${_grz_profile_normalized%%/./*}/${_grz_profile_normalized#*/./}"
    done
    while case "$_grz_profile_normalized" in */.|?*/) true ;; *) false ;; esac; do
        case "$_grz_profile_normalized" in
            */.) _grz_profile_normalized=${_grz_profile_normalized%/.} ;;
            */) _grz_profile_normalized=${_grz_profile_normalized%/} ;;
        esac
        [ -n "$_grz_profile_normalized" ] || _grz_profile_normalized=/
    done
}

# Remove equivalent copies of a managed entry. Retain the spelling, order and
# empty components of every other inherited entry; avoid globbing and IFS leaks.
_grz_profile_path_remove() {
    _grz_profile_path_normalize "$1"
    _grz_profile_remove=$_grz_profile_normalized
    _grz_profile_rest=${PATH-}
    _grz_profile_result=
    _grz_profile_separator=
    while :; do
        _grz_profile_entry=${_grz_profile_rest%%:*}
        _grz_profile_path_normalize "$_grz_profile_entry"
        if [ "$_grz_profile_normalized" != "$_grz_profile_remove" ]; then
            _grz_profile_result="$_grz_profile_result$_grz_profile_separator$_grz_profile_entry"
            _grz_profile_separator=:
        fi
        case "$_grz_profile_rest" in
            *:*) _grz_profile_rest=${_grz_profile_rest#*:} ;;
            *) break ;;
        esac
    done
    PATH=$_grz_profile_result
}

# Hard cutover, including custom VOLTA_HOME and differently spelled PATH copies.
_grz_profile_path_remove "$HOME/.volta/bin"
_grz_profile_path_remove "${VOLTA_HOME:-$HOME/.volta}/bin"
unset VOLTA_HOME

if [ -n "${MISE_SHIMS_DIR:-}" ]; then
    _grz_profile_mise_shims="$MISE_SHIMS_DIR"
else
    _grz_profile_mise_shims="${MISE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mise}/shims"
fi
_grz_profile_path_normalize "$_grz_profile_mise_shims"
_grz_profile_mise_shims=$_grz_profile_normalized
_grz_profile_path_remove "$_grz_profile_mise_shims"
# Reserve the shim entry before mise install/use creates the directory.
PATH="$_grz_profile_mise_shims${PATH:+:$PATH}"

# pnpm global executables are independent of the CLI provider. As in the Zsh
# finalizer, remove the obsolete PNPM_HOME root entry and move bin to the tail.
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
_grz_profile_path_normalize "$PNPM_HOME/bin"
_grz_profile_pnpm_bin=$_grz_profile_normalized
_grz_profile_path_remove "$PNPM_HOME"
_grz_profile_path_remove "$_grz_profile_pnpm_bin"
PATH="${PATH:+$PATH:}$_grz_profile_pnpm_bin"

unset _grz_profile_normalized _grz_profile_remove _grz_profile_rest \
      _grz_profile_result _grz_profile_separator _grz_profile_entry \
      _grz_profile_mise_shims _grz_profile_pnpm_bin
unset -f _grz_profile_path_remove _grz_profile_path_normalize 2>/dev/null || true
export PATH
