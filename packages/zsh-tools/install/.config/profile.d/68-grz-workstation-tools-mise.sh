# mise shims for login shells and GUI/IDE processes that do not execute
# interactive `mise activate zsh`.
#
# Resolution follows mise's directory contract:
# MISE_SHIMS_DIR > MISE_DATA_DIR > XDG_DATA_HOME/default data directory.

# Remove every exact occurrence of one PATH entry while preserving the order
# and spelling of all other entries.
_grz_profile_path_remove() {
    _grz_profile_remove="$1"
    while case ":$PATH:" in *":$_grz_profile_remove:"*) true ;; *) false ;; esac; do
        case "$PATH" in
            "$_grz_profile_remove")
                PATH=
                ;;
            "$_grz_profile_remove":*)
                PATH=${PATH#"$_grz_profile_remove":}
                ;;
            *:"$_grz_profile_remove":*)
                _grz_profile_before=${PATH%%:"$_grz_profile_remove":*}
                _grz_profile_after=${PATH#*:"$_grz_profile_remove":}
                PATH="$_grz_profile_before:$_grz_profile_after"
                ;;
            *:"$_grz_profile_remove")
                PATH=${PATH%:"$_grz_profile_remove"}
                ;;
        esac
    done
}

# Hard cutover: do not let a login/GUI environment inherited from an older
# session keep Volta reachable. Handle both the default and a custom VOLTA_HOME.
_grz_profile_volta_bin="${VOLTA_HOME:-$HOME/.volta}/bin"
_grz_profile_path_remove "$HOME/.volta/bin"
if [ "$_grz_profile_volta_bin" != "$HOME/.volta/bin" ]; then
    _grz_profile_path_remove "$_grz_profile_volta_bin"
fi
unset VOLTA_HOME _grz_profile_volta_bin

if [ -n "${MISE_SHIMS_DIR:-}" ]; then
    _grz_profile_mise_shims="$MISE_SHIMS_DIR"
else
    _grz_profile_mise_data_dir="${MISE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mise}"
    _grz_profile_mise_shims="$_grz_profile_mise_data_dir/shims"
    unset _grz_profile_mise_data_dir
fi

if [ -d "$_grz_profile_mise_shims" ]; then
    _grz_profile_path_remove "$_grz_profile_mise_shims"
    PATH="$_grz_profile_mise_shims${PATH:+:$PATH}"
fi

unset _grz_profile_mise_shims

# pnpm global package executables are independent of the pnpm CLI provider.
# Remove inherited copies first, then append exactly one lowest-priority entry.
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
_grz_profile_pnpm_bin="$PNPM_HOME/bin"
_grz_profile_path_remove "$_grz_profile_pnpm_bin"
PATH="${PATH:+$PATH:}$_grz_profile_pnpm_bin"

unset _grz_profile_remove \
      _grz_profile_before \
      _grz_profile_after \
      _grz_profile_pnpm_bin
unset -f _grz_profile_path_remove 2>/dev/null || true

export PATH
