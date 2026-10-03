# ~/.zsh_scripts/core/90-completion_init.zsh
source "${${(%):-%x}:A:h}/04-completion-paths.zsh" || return $?

zstyle ':completion:*:*:-command-:*:functions'  ignored-patterns '__*' '*__impl'
zstyle ':completion:*:*:-command-:*:parameters' ignored-patterns '__*'
zstyle ':completion:*:*:-command-:*:commands'   ignored-patterns '*__impl'

zstyle ':completion:*:*:-command-:*:*' tag-order 'functions:-non-comp *' functions
zstyle ':completion:*:functions-non-comp' ignored-patterns '_*'

# Audit before initialization and reconcile cached state afterwards. With an
# existing owner, only the managed roots are scanned; no second compinit runs.
() {
  emulate -L zsh
  setopt typesetsilent
  setopt extendedglob

  local completion_root physical_root audit_path file name bad key value table source_file source_root REPLY
  local audit_marker='__grz_compaudit_not_run__'
  local -i audit_rc=0 audit_failed=0 insecure=0 file_insecure=0 init_rc=0
  local -a reply fields managed_paths completion_roots audit_roots original_fpath audit_search_fpath safe_fpath undefined_functions
  local -aU ordered_roots
  local -a _i_wdirs _i_wfiles _i_files _i_addfiles
  local _i_check=yes _i_fail=ign _i_q _i_line _i_file
  local -A seen blocked blocked_sources unsafe_roots insecure_files prior_comps prior_services prior_patterns prior_postpatterns

  __grz_completion_paths
  managed_paths=("${reply[@]}")
  completion_roots=("${(@)reply[1,3]}")
  # Check both the installation path and its physical target. A writable link
  # parent can provide a digest even when the target directory itself is safe.
  for completion_root in "${completion_roots[@]}"; do
    audit_roots+=("$completion_root")
    physical_root="${completion_root:A}"
    [[ "$physical_root" == "$completion_root" ]] || audit_roots+=("$physical_root")
  done

  # The pre-loader defers managed fpath exposure. Repeat identity filtering here
  # for owners that insert aliases afterwards; never retain an alias's separate
  # implicit digest. Preserve their managed-directory order using audited paths.
  original_fpath=("${fpath[@]}")
  for completion_root in "${original_fpath[@]}"; do
    if __grz_completion_match_root "$completion_root" "${managed_paths[@]}"; then
      if [[ -d "$completion_root" ]] && (( completion_roots[(Ie)$REPLY] )); then
        ordered_roots+=("$REPLY")
      fi
    else
      audit_search_fpath+=("$completion_root")
    fi
  done
  ordered_roots+=("${completion_roots[@]}")
  fpath=("${audit_search_fpath[@]}")

  zmodload zsh/parameter
  for name in compinit compaudit compdump compinstall; do
    source_file="${functions_source[$name]-}"
    [[ -n "$source_file" ]] || continue
    if __grz_completion_match_helper_source "$source_file" "${managed_paths[@]}"; then
      unfunction -- "$name"
    fi
  done
  _i_wdirs=("$audit_marker")
  _i_wfiles=("$audit_marker")

  # Load all initialization helpers while fpath excludes managed code. Defined
  # owner functions survive +X. Missing providers become harmless definitions,
  # preventing deferred lookup from falling back to managed paths after audit.
  autoload -rUz compinit compaudit compdump compinstall
  for name in compinit compaudit compdump compinstall; do
    builtin autoload +X "$name" 2>/dev/null || true
  done
  undefined_functions=("${(@f)$(builtin functions -u +)}")
  for name in compinit compaudit compdump compinstall; do
    if (( undefined_functions[(Ie)$name] )); then
      unfunction -- "$name"
      functions[$name]='return 1'
    fi
  done
  compaudit "${audit_roots[@]}" >/dev/null 2>&1 || audit_rc=$?

  if (( audit_rc > 1 ||
        _i_wdirs[(I)$audit_marker] ||
        _i_wfiles[(I)$audit_marker] )); then
    audit_failed=1
  fi

  # Use one file identity policy for inventory, cached functions and scanning.
  # compaudit may report a logical installation path while functions_source
  # points at the symlink target (or vice versa).
  for file in "${_i_wfiles[@]}"; do
    insecure_files[${file:a}]=1
    insecure_files[${file:A}]=1
  done
  for completion_root in "${completion_roots[@]}"; do
    physical_root="${completion_root:A}"
    insecure=$audit_failed
    for bad in "${_i_wdirs[@]}"; do
      for audit_path in "$completion_root" "$physical_root" "${completion_root:h}" "${physical_root:h}" "$completion_root.zwc" "$physical_root.zwc"; do
        if [[ "${bad:a}" == "${audit_path:a}" || "${bad:A}" == "${audit_path:A}" ]]; then
          insecure=1
        fi
      done
    done
    (( insecure )) && unsafe_roots[$completion_root]=1

    # Inventory names without reading insecure metadata. Compiled companions
    # also invalidate their function's name, including symlinked companions.
    for file in "$completion_root"/_*(N-.); do
      name="${${file:t}%.zwc}"
      audit_path="$file.zwc"
      file_insecure=$(( $+insecure_files[${file:a}] || $+insecure_files[${file:A}] ||
                        $+insecure_files[${audit_path:a}] || $+insecure_files[${audit_path:A}] ))
      if (( insecure || file_insecure )); then
        blocked[$name]=1
        # Associate a source and its companion before comparing loaded aliases.
        # A symlinked companion can have a completely different target name.
        source_file="${file%.zwc}"
        audit_path="$source_file.zwc"
        blocked_sources[${source_file:a}]=1
        blocked_sources[${source_file:A}]=1
        blocked_sources[${audit_path:a}]=1
        blocked_sources[${audit_path:A}]=1
        if (( file_insecure )); then
          insecure_files[${source_file:a}]=1
          insecure_files[${source_file:A}]=1
          insecure_files[${audit_path:a}]=1
          insecure_files[${audit_path:A}]=1
        fi
      fi
    done
  done

  for completion_root in "${ordered_roots[@]}"; do
    (( $+unsafe_roots[$completion_root] )) || safe_fpath+=("$completion_root")
  done
  # compaudit assigned fpath to its audit arguments through dynamic scope.
  # Restore the trusted search path and keep it until compinit completes.
  fpath=("${audit_search_fpath[@]}")

  # Loaded/pinned functions can outlive their source files. Digest source paths
  # and directory/file aliases must use the same identity as fpath filtering.
  for name file in "${(@kv)functions_source}"; do
    [[ "$file" == /* ]] || continue
    source_root=''
    if __grz_completion_match_root "${file:h}" "${managed_paths[@]}"; then
      source_root="$REPLY"
      physical_root="${source_root:A}"
      source_file="${file:h}"
      audit_path="$source_root.zwc"
      completion_root="$physical_root.zwc"
      # Default/legacy roots are not selected, and an alias-only digest is not
      # among the logical/physical companions audited above. Revoke their
      # preloaded code even when the selected directory itself is secure.
      if (( ! completion_roots[(Ie)$source_root] )) ||
          [[ "${source_file:A}" != "$physical_root" &&
             "${source_file:A}" != "${audit_path:A}" &&
             "${source_file:A}" != "${completion_root:A}" ]]; then
        blocked[$name]=1
      fi
    fi
    audit_path="$file.zwc"
    if (( $+unsafe_roots[$source_root] || $+blocked_sources[${file:a}] || $+blocked_sources[${file:A}] ||
          $+blocked_sources[${audit_path:a}] || $+blocked_sources[${audit_path:A}] || $+insecure_files[${file:a}] || $+insecure_files[${file:A}] ||
          $+insecure_files[${audit_path:a}] || $+insecure_files[${audit_path:A}] )); then
      blocked[$name]=1
    fi
  done

  if (( ! $+functions[compdef] )); then
    compinit -i || init_rc=$?
  fi
  if (( ! init_rc )); then
    fpath=("${safe_fpath[@]}" "${audit_search_fpath[@]}")
  fi

  # Even missing initialization helpers must reach quarantine. compinit normally
  # declares these tables; declare them without clearing existing owner state.
  typeset -gHA _comps _services _patcomps _postpatcomps _compautos

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

  (( init_rc )) && return $init_rc

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
      audit_path="$file.zwc"
      (( $+seen[$name] || $+insecure_files[${file:a}] || $+insecure_files[${file:A}] ||
         $+insecure_files[${audit_path:a}] || $+insecure_files[${audit_path:A}] )) && continue
      seen[$name]=1

      fields=()
      IFS=$' \t' read -rA fields < "$file" || true
      # Pin secure files to their audited directory. Merely skipping an
      # insecure earlier copy still lets a name-only autoload choose it.
      source_file="${functions_source[$name]-}"
      source_root=''
      if [[ "$source_file" == /* ]] && __grz_completion_match_root "${source_file:h}" "${managed_paths[@]}"; then
        source_root="$REPLY"
      fi
      # Preserve an owner's explicit implementation outside either runtime,
      # including definitions without a source file.
      # Loaded or pinned files from the current/default managed roots must be
      # refreshed; blocked names always take the audited replacement.
      if (( ! $+functions[$name] || (undefined_functions[(Ie)$name] && ! ${#source_file}) ||
            $+blocked[$name] || ${#source_root} )); then
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
