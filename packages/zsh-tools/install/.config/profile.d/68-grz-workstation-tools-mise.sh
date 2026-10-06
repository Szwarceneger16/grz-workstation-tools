# mise shims for login shells and GUI/IDE processes that do not execute
# interactive `mise activate zsh`.

mise_shims="${MISE_DATA_DIR:-$HOME/.local/share/mise}/shims"

if [ -d "$mise_shims" ]; then
    case ":$PATH:" in
        *":$mise_shims:"*) ;;
        *) PATH="$mise_shims:$PATH" ;;
    esac
fi

unset mise_shims
export PATH
