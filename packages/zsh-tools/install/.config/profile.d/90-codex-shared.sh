# Opt in to the shared local Codex App Server using the existing environment.d file.
# Read only the two supported assignments; environment.d is not shell code.
_grz_codex_file="$HOME/.config/environment.d/90-codex-shared.conf"
if [ -r "$_grz_codex_file" ]; then
    _grz_codex_url=
    _grz_codex_force=
    while IFS= read -r _grz_codex_line || [ -n "$_grz_codex_line" ]; do
        case "$_grz_codex_line" in
            CODEX_APP_SERVER_WS_URL=*) _grz_codex_url=${_grz_codex_line#*=} ;;
            CODEX_APP_SERVER_FORCE_CLI=*) _grz_codex_force=${_grz_codex_line#*=} ;;
        esac
    done < "$_grz_codex_file"

    _grz_codex_expected="ws+unix://localhost$HOME/.codex/app-server-control/app-server-control.sock:/rpc"
    case "$_grz_codex_url" in
        'ws+unix://localhost${HOME}/.codex/app-server-control/app-server-control.sock:/rpc'|\
        'ws+unix://localhost$HOME/.codex/app-server-control/app-server-control.sock:/rpc')
            _grz_codex_url=$_grz_codex_expected ;;
    esac
    if [ "$_grz_codex_url" = "$_grz_codex_expected" ] && [ "$_grz_codex_force" = 0 ]; then
        export CODEX_APP_SERVER_WS_URL="$_grz_codex_url"
        export CODEX_APP_SERVER_FORCE_CLI=0
    fi
    unset _grz_codex_url _grz_codex_force _grz_codex_line _grz_codex_expected
fi
unset _grz_codex_file
