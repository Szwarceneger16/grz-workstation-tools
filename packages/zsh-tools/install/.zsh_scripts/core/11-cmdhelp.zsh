# cmdhelp core
# Public API:
#   cmdhelp
#
# Private helpers/variables:
#   everything prefixed with __

if (( ! ${+__CMDHELP_ROOT} )); then
  typeset -gr __CMDHELP_ROOT="${HOME}/.zsh_scripts/cmdhelp"
fi
if (( ! ${+__CMDHELP_FUNCTIONS_ROOT} )); then
  typeset -gr __CMDHELP_FUNCTIONS_ROOT="${HOME}/.zsh_scripts/functions"
fi
if (( ! ${+__CMDHELP_BIN_ROOT} )); then
  typeset -gr __CMDHELP_BIN_ROOT="${HOME}/.local/my-custom-bin"
fi

__get_cmdhelp_root() {
  print -r -- "${__CMDHELP_ROOT}"
}

__cmdhelp_collect_topic_names() {
  emulate -L zsh
  setopt local_options null_glob

  local scope="$1"
  local dir
  local -a dirs files names
  local file name

  case "$scope" in
    functions) dirs=("${__CMDHELP_ROOT}/functions") ;;
    bin)       dirs=("${__CMDHELP_ROOT}/bin") ;;
    auto|'')   dirs=("${__CMDHELP_ROOT}/functions" "${__CMDHELP_ROOT}/bin") ;;
    *)
      return 1
      ;;
  esac

  for dir in "${dirs[@]}"; do
    [[ -d "$dir" ]] || continue
    files+=("$dir"/*.md(N) "$dir"/*.help.zsh(N))
  done

  for file in "${files[@]}"; do
    name="${file:t}"
    name="${name%.help.zsh}"
    name="${name%.md}"
    names+=("$name")
  done

  print -rl -- ${(ou)names}
}

__cmdhelp_help_function_names() {
  __cmdhelp_collect_topic_names functions
}

__cmdhelp_help_bin_names() {
  __cmdhelp_collect_topic_names bin
}

__cmdhelp_managed_function_names() {
  emulate -L zsh
  setopt local_options null_glob

  local -a files names
  local file

  files=("${__CMDHELP_FUNCTIONS_ROOT}"/*.zsh(N))
  for file in "${files[@]}"; do
    names+=("${file:t:r}")
  done

  names+=(cmdhelp)

  print -rl -- ${(ou)names}
}

__cmdhelp_loaded_function_names() {
  emulate -L zsh

  local -a managed loaded
  local name

  managed=("${(@f)$(__cmdhelp_managed_function_names)}")

  for name in "${managed[@]}"; do
    (( $+functions[$name] )) && loaded+=("$name")
  done

  print -rl -- ${(ou)loaded}
}

__cmdhelp_unloaded_function_names() {
  emulate -L zsh

  local -a managed loaded unloaded
  local -A loaded_map
  local name

  managed=("${(@f)$(__cmdhelp_managed_function_names)}")
  loaded=("${(@f)$(__cmdhelp_loaded_function_names)}")

  for name in "${loaded[@]}"; do
    loaded_map[$name]=1
  done

  for name in "${managed[@]}"; do
    [[ -n ${loaded_map[$name]-} ]] || unloaded+=("$name")
  done

  print -rl -- ${(ou)unloaded}
}

__cmdhelp_managed_bin_names() {
  emulate -L zsh
  setopt local_options null_glob

  local -a files names
  local file

  files=("${__CMDHELP_BIN_ROOT}"/*(N))
  for file in "${files[@]}"; do
    [[ -f "$file" || -L "$file" ]] || continue
    [[ -x "$file" ]] || continue
    names+=("${file:t}")
  done

  print -rl -- ${(ou)names}
}

__cmdhelp_active_bin_names() {
  emulate -L zsh

  local -a managed active
  local name resolved expected

  managed=("${(@f)$(__cmdhelp_managed_bin_names)}")

  for name in "${managed[@]}"; do
    resolved="$(whence -p -- "$name" 2>/dev/null)"
    expected="${__CMDHELP_BIN_ROOT}/${name}"

    [[ -n "$resolved" ]] || continue
    [[ "${resolved:A}" == "${expected:A}" ]] || continue

    active+=("$name")
  done

  print -rl -- ${(ou)active}
}

__cmdhelp_inactive_bin_names() {
  emulate -L zsh

  local -a managed active inactive
  local -A active_map
  local name

  managed=("${(@f)$(__cmdhelp_managed_bin_names)}")
  active=("${(@f)$(__cmdhelp_active_bin_names)}")

  for name in "${active[@]}"; do
    active_map[$name]=1
  done

  for name in "${managed[@]}"; do
    [[ -n ${active_map[$name]-} ]] || inactive+=("$name")
  done

  print -rl -- ${(ou)inactive}
}

__cmdhelp_array_diff() {
  emulate -L zsh

  local left_name="$1"
  local right_name="$2"
  local -a left right out
  local -A right_map
  local item

  left=("${(@P)left_name}")
  right=("${(@P)right_name}")

  for item in "${right[@]}"; do
    right_map[$item]=1
  done

  for item in "${left[@]}"; do
    [[ -n ${right_map[$item]-} ]] || out+=("$item")
  done

  print -rl -- ${(ou)out}
}

__cmdhelp_compute_audit_cache() {
  emulate -L zsh

  local -a help_functions help_bin
  local -a loaded_functions active_bin
  local -a managed_functions managed_bin
  local -a unloaded_functions inactive_bin

  help_functions=("${(@f)$(__cmdhelp_help_function_names)}")
  help_bin=("${(@f)$(__cmdhelp_help_bin_names)}")
  loaded_functions=("${(@f)$(__cmdhelp_loaded_function_names)}")
  active_bin=("${(@f)$(__cmdhelp_active_bin_names)}")
  managed_functions=("${(@f)$(__cmdhelp_managed_function_names)}")
  managed_bin=("${(@f)$(__cmdhelp_managed_bin_names)}")
  unloaded_functions=("${(@f)$(__cmdhelp_unloaded_function_names)}")
  inactive_bin=("${(@f)$(__cmdhelp_inactive_bin_names)}")

  typeset -gUa __CMDHELP_HELP_ONLY_FUNCTIONS
  typeset -gUa __CMDHELP_HELP_ONLY_BIN
  typeset -gUa __CMDHELP_MISSING_HELP_FUNCTIONS
  typeset -gUa __CMDHELP_MISSING_HELP_BIN
  typeset -gUa __CMDHELP_UNLOADED_FUNCTIONS
  typeset -gUa __CMDHELP_INACTIVE_BIN

  __CMDHELP_HELP_ONLY_FUNCTIONS=(
    "${(@f)$(__cmdhelp_array_diff help_functions loaded_functions)}"
  )
  __CMDHELP_HELP_ONLY_BIN=(
    "${(@f)$(__cmdhelp_array_diff help_bin active_bin)}"
  )
  __CMDHELP_MISSING_HELP_FUNCTIONS=(
    "${(@f)$(__cmdhelp_array_diff loaded_functions help_functions)}"
  )
  __CMDHELP_MISSING_HELP_BIN=(
    "${(@f)$(__cmdhelp_array_diff active_bin help_bin)}"
  )
  __CMDHELP_UNLOADED_FUNCTIONS=("${unloaded_functions[@]}")
  __CMDHELP_INACTIVE_BIN=("${inactive_bin[@]}")
}

__cmdhelp_issue_counts() {
  emulate -L zsh

  __cmdhelp_compute_audit_cache

  local help_only_count missing_help_count inactive_count total_count

  help_only_count=$(( ${#__CMDHELP_HELP_ONLY_FUNCTIONS} + ${#__CMDHELP_HELP_ONLY_BIN} ))
  missing_help_count=$(( ${#__CMDHELP_MISSING_HELP_FUNCTIONS} + ${#__CMDHELP_MISSING_HELP_BIN} ))
  inactive_count=$(( ${#__CMDHELP_UNLOADED_FUNCTIONS} + ${#__CMDHELP_INACTIVE_BIN} ))
  total_count=$(( help_only_count + missing_help_count + inactive_count ))

  print -r -- "${help_only_count}:${missing_help_count}:${inactive_count}:${total_count}"
}

__cmdhelp_print_audit_summary() {
  emulate -L zsh

  local counts help_only_count missing_help_count inactive_count total_count
  counts="$(__cmdhelp_issue_counts)"

  help_only_count="${counts%%:*}"
  counts="${counts#*:}"
  missing_help_count="${counts%%:*}"
  counts="${counts#*:}"
  inactive_count="${counts%%:*}"
  total_count="${counts##*:}"

  if (( total_count == 0 )); then
    print -r -- "[audit] OK — help, funkcje i bin są spójne."
    return 0
  fi

  print -r -- "[audit] Niespójności: ${total_count} (help bez entrypointu: ${help_only_count}, entrypoint bez helpa: ${missing_help_count}, nieaktywne entrypointy: ${inactive_count}). Uruchom: cmdhelp audit"
  return 1
}

__cmdhelp_print_named_list() {
  emulate -L zsh

  local title="$1"
  shift
  local -a items
  local item

  items=("$@")

  print -r -- "${title}"
  if (( ${#items} == 0 )); then
    print -r -- "  - brak"
    return 0
  fi

  for item in ${(ou)items}; do
    print -r -- "  - ${item}"
  done
}

__cmdhelp_print_audit_report() {
  emulate -L zsh

  __cmdhelp_compute_audit_cache
  __cmdhelp_print_audit_summary
  print

  print -r -- "# Help bez realnego entrypointu"
  __cmdhelp_print_named_list "Functions:" "${__CMDHELP_HELP_ONLY_FUNCTIONS[@]}"
  __cmdhelp_print_named_list "Bin:" "${__CMDHELP_HELP_ONLY_BIN[@]}"
  print

  print -r -- "# Entrypointy bez helpa"
  __cmdhelp_print_named_list "Loaded functions:" "${__CMDHELP_MISSING_HELP_FUNCTIONS[@]}"
  __cmdhelp_print_named_list "Active PATH bin:" "${__CMDHELP_MISSING_HELP_BIN[@]}"
  print

  print -r -- "# Nieaktywne entrypointy"
  __cmdhelp_print_named_list "Function files not loaded:" "${__CMDHELP_UNLOADED_FUNCTIONS[@]}"
  __cmdhelp_print_named_list "Bin files not active on PATH (lub shadowed):" "${__CMDHELP_INACTIVE_BIN[@]}"

  local counts total_count
  counts="$(__cmdhelp_issue_counts)"
  total_count="${counts##*:}"
  (( total_count == 0 ))
}

__cmdhelp_render_file() {
  emulate -L zsh

  local file="$1"
  local use_less="${2:-0}"

  if (( use_less )); then
    if (( $+functions[render_cmd_help] )); then
      render_cmd_help "$file" | less -R
    else
      less -R -- "$file"
    fi
    return $?
  fi

  if (( $+functions[render_cmd_help] )); then
    render_cmd_help "$file"
    return $?
  fi

  cat -- "$file"
}

__cmdhelp_resolve_file() {
  emulate -L zsh

  local name="$1"
  local scope="${2:-auto}"
  local -a candidates
  local base

  case "$scope" in
    functions)
      base="${__CMDHELP_ROOT}/functions/${name}"
      candidates=("${base}.help.zsh" "${base}.md")
      ;;
    bin)
      base="${__CMDHELP_ROOT}/bin/${name}"
      candidates=("${base}.help.zsh" "${base}.md")
      ;;
    auto|'')
      candidates=(
        "${__CMDHELP_ROOT}/functions/${name}.help.zsh"
        "${__CMDHELP_ROOT}/functions/${name}.md"
        "${__CMDHELP_ROOT}/bin/${name}.help.zsh"
        "${__CMDHELP_ROOT}/bin/${name}.md"
      )
      ;;
    *)
      return 1
      ;;
  esac

  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -f "$candidate" ]] && {
      print -r -- "$candidate"
      return 0
    }
  done

  return 1
}

__cmdhelp_list_entrypoints() {
  emulate -L zsh

  local scope="${1:-auto}"
  local -a loaded_functions active_bin

  loaded_functions=("${(@f)$(__cmdhelp_loaded_function_names)}")
  active_bin=("${(@f)$(__cmdhelp_active_bin_names)}")

  case "$scope" in
    functions)
      print -r -- "# Functions"
      if (( ${#loaded_functions} )); then
        print -rl -- ${(ou)loaded_functions}
      else
        print -r -- "(brak)"
      fi
      ;;
    bin)
      print -r -- "# Bin"
      if (( ${#active_bin} )); then
        print -rl -- ${(ou)active_bin}
      else
        print -r -- "(brak)"
      fi
      ;;
    auto|'')
      print -r -- "# Functions"
      if (( ${#loaded_functions} )); then
        print -rl -- ${(ou)loaded_functions}
      else
        print -r -- "(brak)"
      fi

      print
      print -r -- "# Bin"
      if (( ${#active_bin} )); then
        print -rl -- ${(ou)active_bin}
      else
        print -r -- "(brak)"
      fi
      ;;
    *)
      return 1
      ;;
  esac
}

cmdhelp() {
  emulate -L zsh
  setopt local_options no_aliases pipe_fail

  local use_less=0
  local list_mode=0
  local audit_mode=0
  local show_help=0
  local -a positional
  local arg topic scope file

  for arg in "$@"; do
    case "$arg" in
      --less)
        use_less=1
        ;;
      -l|--list|list)
        list_mode=1
        ;;
      audit|--audit)
        audit_mode=1
        ;;
      -h|--help)
        show_help=1
        ;;
      *)
        positional+=("$arg")
        ;;
    esac
  done

  if (( audit_mode )); then
    __cmdhelp_print_audit_report
    return $?
  fi

  if (( show_help )) || (( $# == 0 )); then
    __cmdhelp_print_audit_summary
    print
    file="$(__cmdhelp_resolve_file cmdhelp functions)" || {
      print -u2 -- "cmdhelp: brak pliku helpa dla cmdhelp"
      return 1
    }
    __cmdhelp_render_file "$file" "$use_less"
    return $?
  fi

  if (( list_mode )); then
    scope="${positional[1]-auto}"

    case "$scope" in
      ''|auto|functions|bin) ;;
      *)
        print -u2 -- "cmdhelp: nieprawidłowy zakres listy: ${scope}"
        print -u2 -- "dozwolone: functions | bin"
        return 1
        ;;
    esac

    __cmdhelp_print_audit_summary
    print
    __cmdhelp_list_entrypoints "${scope:-auto}"
    return $?
  fi

  topic="${positional[1]-}"
  scope="${positional[2]-auto}"

  if [[ -z "$topic" ]]; then
    __cmdhelp_print_audit_summary
    print
    file="$(__cmdhelp_resolve_file cmdhelp functions)" || {
      print -u2 -- "cmdhelp: brak pliku helpa dla cmdhelp"
      return 1
    }
    __cmdhelp_render_file "$file" "$use_less"
    return $?
  fi

  case "$scope" in
    ''|auto|functions|bin) ;;
    *)
      print -u2 -- "cmdhelp: nieprawidłowy scope: ${scope}"
      print -u2 -- "dozwolone: functions | bin"
      return 1
      ;;
  esac

  __cmdhelp_print_audit_summary
  print

  file="$(__cmdhelp_resolve_file "$topic" "${scope:-auto}")" || {
    if (( $+functions[$topic] )); then
      print -u2 -- "cmdhelp: funkcja '${topic}' jest dostępna, ale nie ma pliku helpa."
    elif whence -p -- "$topic" >/dev/null 2>&1; then
      print -u2 -- "cmdhelp: komenda '${topic}' jest na PATH, ale nie ma pliku helpa."
    else
      print -u2 -- "cmdhelp: nie znaleziono helpa ani entrypointu dla '${topic}'."
    fi
    print -u2 -- "cmdhelp: uruchom 'cmdhelp audit', aby zobaczyć pełny raport."
    return 1
  }

  __cmdhelp_render_file "$file" "$use_less"
}
