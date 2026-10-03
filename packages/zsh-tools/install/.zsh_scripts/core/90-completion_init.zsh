# ~/.zsh_scripts/core/90-completion_init.zsh

zstyle ':completion:*:*:-command-:*:functions'  ignored-patterns '__*' '*__impl'
zstyle ':completion:*:*:-command-:*:parameters' ignored-patterns '__*'
zstyle ':completion:*:*:-command-:*:commands'   ignored-patterns '*__impl'

zstyle ':completion:*:*:-command-:*:*' tag-order 'functions:-non-comp *' functions
zstyle ':completion:*:functions-non-comp' ignored-patterns '_*'

# Audit before initialization and reconcile cached state afterwards. With an
# existing owner, only the managed roots are scanned; no second compinit runs.
() {
  emulate -L zsh
  setopt extendedglob

  local runtime_root="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}"
  local default_root="$HOME/.zsh_scripts"
  runtime_root="${runtime_root:a}"
  default_root="${default_root:a}"
  local completion_root file name bad key value table source_file source_root autoload_root
  local audit_marker='__grz_compaudit_not_run__'
  local -i audit_rc=0 audit_failed=0 insecure=0
  local -a completion_roots fields original_fpath audit_search_fpath safe_fpath undefined_functions
  local -a _i_wdirs _i_wfiles _i_files _i_addfiles
  local _i_check=yes _i_fail=ign _i_q _i_line _i_file
  local -A seen blocked unsafe_roots prior_comps prior_services prior_patterns prior_postpatterns

  completion_roots=(
    "$runtime_root/completion/helpers"
    "$runtime_root/completion/functions"
    "$runtime_root/completion/bin"
  )

  # compaudit uses dynamic scope for these variables and temporarily assigns
  # fpath to its positional arguments. Before invoking it, remove the roots
  # being audited and their explicit directory digests from the autoload
  # search path so an insecure managed root
  # cannot provide the compaudit implementation itself.
  original_fpath=("${fpath[@]}")
  for completion_root in "${original_fpath[@]}"; do
    autoload_root="${completion_root:a}"
    autoload_root="${autoload_root%.zwc}"
    (( completion_roots[(Ie)$autoload_root] )) ||
      audit_search_fpath+=("$completion_root")
  done
  fpath=("${audit_search_fpath[@]}")
  _i_wdirs=("$audit_marker")
  _i_wfiles=("$audit_marker")

  autoload -RUz compaudit
  if (( ! $+functions[compdef] )); then
    # Resolve initialization helpers outside the not-yet-audited runtime.
    autoload -RUz compinit compdump compinstall
  fi
  compaudit "${completion_roots[@]}" >/dev/null 2>&1 || audit_rc=$?

  if (( audit_rc > 1 ||
        _i_wdirs[(I)$audit_marker] ||
        _i_wfiles[(I)$audit_marker] )); then
    audit_failed=1
  fi

  # compaudit also reports parent directories and directory digest files.
  # Neither is an exact fpath entry, but both invalidate the managed root.
  for completion_root in "${completion_roots[@]}"; do
    insecure=$audit_failed
    for bad in "${_i_wdirs[@]}"; do
      if [[ "$bad" == "$completion_root" || "$bad" == "${completion_root:h}" ||
            "$bad" == "$completion_root.zwc" ]]; then
        insecure=1
      fi
    done
    (( insecure )) && unsafe_roots[$completion_root]=1

    # Inventory names without reading insecure metadata. Include compiled
    # companions: an insecure _name.zwc must also block autoload of _name.
    for file in "$completion_root"/_*(N-.); do
      name="${${file:t}%.zwc}"
      if (( insecure || _i_wfiles[(Ie)$file] || _i_wfiles[(Ie)$file.zwc] )); then
        blocked[$name]=1
      fi
    done
  done

  for completion_root in "${original_fpath[@]}"; do
    autoload_root="${completion_root:a}"
    autoload_root="${autoload_root%.zwc}"
    (( $+unsafe_roots[$autoload_root] )) || safe_fpath+=("$completion_root")
  done
  fpath=("${safe_fpath[@]}")

  # Loaded/pinned functions can outlive their source files. Inventorying only
  # files on disk misses a deleted function from a now-quarantined directory.
  zmodload zsh/parameter
  for name file in "${(@kv)functions_source}"; do
    [[ -n "$file" ]] || continue
    source_root="${file:a:h}"
    source_root="${source_root%.zwc}"
    if (( $+unsafe_roots[$source_root] || _i_wfiles[(Ie)$file] || _i_wfiles[(Ie)$file.zwc] )); then
      blocked[$name]=1
    fi
  done

  if (( ! $+functions[compdef] )); then
    compinit -i || return $?
  fi

  # A dump may already have registered or loaded these functions. Removing
  # only new registrations leaves normal, pattern and widget dispatch live.
  # A harmless definition also protects widgets and helper calls retained by
  # the owner. A later secure duplicate can replace it with a pinned autoload.
  for name in "${(@k)blocked}"; do
    unfunction -- "$name" 2>/dev/null
    functions[$name]='return 1'
    unset "_compautos[$name]"
  done
  for table in _comps _patcomps _postpatcomps; do
    for key value in "${(@kvP)table}"; do
      # Pattern mappings can encode a service as =service=function.
      name="${value##*=}"
      if (( $+blocked[$name] )); then
        unset "${table}[$key]"
        [[ "$table" == _comps ]] && unset "_services[$key]"
      fi
    done
  done

  # compdef -n preserves ordinary mappings, but not all pattern/service
  # forms. Snapshot the safe owner mappings and restore them after the scan.
  prior_comps=("${(@kv)_comps}")
  prior_services=("${(@kv)_services}")
  prior_patterns=("${(@kv)_patcomps}")
  prior_postpatterns=("${(@kv)_postpatcomps}")

  # List undefined functions by their autoload attribute, rather than treating
  # every empty source path as an absent definition. Parameter-assigned owner
  # functions also have no source path and must keep their implementation.
  undefined_functions=("${(@f)$(builtin functions -u +)}")

  # Respect the current managed-fpath order, even if an owner rearranged it.
  for completion_root in "${fpath[@]}"; do
    completion_root="${completion_root:a}"
    (( completion_roots[(Ie)$completion_root] )) || continue
    for file in "$completion_root"/^([^_]*|*~|*.zwc)(N-.); do
      name="${file:t}"
      (( $+seen[$name] || _i_wfiles[(Ie)$file] || _i_wfiles[(Ie)$file.zwc] )) && continue
      seen[$name]=1

      fields=()
      IFS=$' \t' read -rA fields < "$file" || true
      # Pin secure files to their audited directory. Merely skipping an
      # insecure earlier copy still lets a name-only autoload choose it.
      source_file="${functions_source[$name]-}"
      source_root="${source_file:a:h}"
      source_root="${source_root%.zwc}"
      # Preserve an owner's explicit implementation outside either runtime,
      # including definitions without a source file.
      # Loaded or pinned files from the current/default managed roots must be
      # refreshed; blocked names always take the audited replacement.
      if [[ "$source_root" == "$default_root/completion/"(helpers|functions|bin) ]] ||
          (( ! $+functions[$name] || (undefined_functions[(Ie)$name] && ! ${#source_file}) ||
             $+blocked[$name] || completion_roots[(Ie)$source_root] )); then
        unfunction -- "$name" 2>/dev/null
        autoload -Uz "$file"
      fi
      [[ ${fields[1]-} == '#compdef' ]] || continue
      shift fields
      (( ${#fields[@]} )) || continue

      if [[ ${fields[1]} = -[pPkK](n|) ]]; then
        compdef ${fields[1]}n "$name" "${(@)fields[2,-1]}"
      else
        compdef -n "$name" "${fields[@]}"
      fi
    done
  done
  _comps=("${(@kv)_comps}" "${(@kv)prior_comps}")
  for key in "${(@k)prior_comps}"; do
    (( $+prior_services[$key] )) || unset "_services[$key]"
  done
  _services=("${(@kv)_services}" "${(@kv)prior_services}")
  _patcomps=("${(@kv)_patcomps}" "${(@kv)prior_patterns}")
  _postpatcomps=("${(@kv)_postpatcomps}" "${(@kv)prior_postpatterns}")
}
