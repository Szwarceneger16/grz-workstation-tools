# mise shims for login shells and GUI/IDE processes that do not execute
# interactive `mise activate zsh`.
#
# Resolution follows mise's directory contract:
# MISE_SHIMS_DIR > MISE_DATA_DIR > XDG_DATA_HOME/default data directory.

if [ -n "${MISE_SHIMS_DIR:-}" ]; then
    mise_shims="$MISE_SHIMS_DIR"
else
    mise_data_dir="${MISE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mise}"
    mise_shims="$mise_data_dir/shims"
    unset mise_data_dir
fi

if [ -d "$mise_shims" ]; then
    case ":$PATH:" in
        *":$mise_shims:"*) ;;
        *) PATH="$mise_shims:$PATH" ;;
    esac
fi

unset mise_shims
export PATH
