# ~/.zsh_scripts/core/10-help_render.zsh

render_md_help() {
  emulate -L zsh

  local help_file="${1:-}"
  local output_mode="${2:-stdout}"

  if [[ -z "$help_file" ]]; then
    print -u2 -- "ERR: render_md_help: brak ścieżki do pliku helpa"
    return 1
  fi

  if [[ ! -f "$help_file" ]]; then
    print -u2 -- "ERR: render_md_help: plik nie istnieje: $help_file"
    return 1
  fi

  case "$output_mode" in
    stdout|less) ;;
    *)
      print -u2 -- "ERR: render_md_help: nieprawidłowy tryb: $output_mode"
      print -u2 -- "ERR: dozwolone: stdout | less"
      return 1
      ;;
  esac

  if command -v glow >/dev/null 2>&1; then
    if [[ "$output_mode" == "less" ]]; then
      glow -p "$help_file"
    else
      glow "$help_file"
    fi
    return $?
  fi

  if command -v bat >/dev/null 2>&1; then
    if [[ "$output_mode" == "less" ]]; then
      bat --color=always --paging=never --style=plain --language=markdown "$help_file" | less -R
    else
      bat --paging=never --style=plain --language=markdown "$help_file"
    fi
    return $?
  fi

  if command -v pandoc >/dev/null 2>&1; then
    if [[ "$output_mode" == "less" ]]; then
      pandoc -f markdown -t plain "$help_file" | less
    else
      pandoc -f markdown -t plain "$help_file"
    fi
    return $?
  fi

  if [[ "$output_mode" == "less" ]]; then
    command cat "$help_file" | less
  else
    command cat "$help_file"
  fi
}

render_cmd_help() {
  render_md_help "$@"
}
