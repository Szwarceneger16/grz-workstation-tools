# ~/.zsh_scripts/core/12-cmdhelp_internal.zsh

cmdhelp_render_internal() {
  emulate -L zsh
  setopt local_options no_aliases pipe_fail

  local rel="${1:-}"
  local use_less="${2:-0}"
  local file
  local output_mode="stdout"

  if [[ -z "$rel" ]]; then
    print -u2 -- "cmdhelp_render_internal: brak ścieżki relatywnej"
    return 1
  fi

  if [[ "$rel" == /* ]]; then
    print -u2 -- "cmdhelp_render_internal: ścieżka musi być relatywna względem bin/_internal/"
    return 1
  fi

  if [[ "$rel" == *".."* ]]; then
    print -u2 -- "cmdhelp_render_internal: niedozwolone '..' w ścieżce"
    return 1
  fi

  file="${__CMDHELP_ROOT}/bin/_internal/${rel}"

  if [[ ! -f "$file" ]]; then
    print -u2 -- "cmdhelp_render_internal: plik nie istnieje: $file"
    return 1
  fi

  case "$use_less" in
    1|true|yes) output_mode="less" ;;
    0|false|no|'') output_mode="stdout" ;;
    *)
      print -u2 -- "cmdhelp_render_internal: nieprawidłowa wartość use_less: $use_less"
      return 1
      ;;
  esac

  __cmdhelp_render_file "$file" "$output_mode"
}
