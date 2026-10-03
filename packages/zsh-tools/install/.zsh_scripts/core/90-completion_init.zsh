# ~/.zsh_scripts/core/90-completion_init.zsh

zstyle ':completion:*:*:-command-:*:functions'  ignored-patterns '__*' '*__impl'
zstyle ':completion:*:*:-command-:*:parameters' ignored-patterns '__*'
zstyle ':completion:*:*:-command-:*:commands'   ignored-patterns '*__impl'

zstyle ':completion:*:*:-command-:*:*' tag-order 'functions:-non-comp *' functions
zstyle ':completion:*:functions-non-comp' ignored-patterns '_*'

# Keep zsh-tools standalone, but do not run a second full compinit scan when
# another completion owner already exists.
if (( ! $+functions[compdef] )); then
  autoload -Uz compinit
  compinit -i
else
  # Register only #compdef metadata from the bounded runtime completion
  # directories exposed by 05-fpath.zsh. Preserve compinit's security and
  # basename-shadowing semantics without rescanning unrelated fpath entries.
  () {
    emulate -L zsh
    setopt extendedglob

    local runtime_root="${ZSH_TOOLS_ROOT:-$HOME/.zsh_scripts}"
    local completion_root file name
    local audit_marker='__grz_compaudit_not_run__'
    local -i audit_rc=0
    local -a completion_roots fields original_fpath audit_search_fpath
    local -a _i_wdirs _i_wfiles
    local _i_check=yes _i_fail=ign
    local -A seen

    completion_roots=(
      "$runtime_root/completion/helpers"
      "$runtime_root/completion/functions"
      "$runtime_root/completion/bin"
    )

    # compaudit uses dynamic scope for these variables and temporarily assigns
    # fpath to its positional arguments. Before invoking it, remove the roots
    # being audited from the autoload search path so an insecure managed root
    # cannot provide the compaudit implementation itself.
    original_fpath=("${fpath[@]}")
    audit_search_fpath=(${original_fpath:|completion_roots})
    fpath=("${audit_search_fpath[@]}")
    _i_wdirs=("$audit_marker")
    _i_wfiles=("$audit_marker")

    if (( ! $+functions[compaudit] )); then
      autoload -RUz compaudit
    fi
    compaudit "${completion_roots[@]}" >/dev/null 2>&1 || audit_rc=$?

    if (( audit_rc > 1 ||
          _i_wdirs[(I)$audit_marker] ||
          _i_wfiles[(I)$audit_marker] )); then
      fpath=("${original_fpath[@]}")
      return 0
    fi

    # Match compinit -i: remove insecure managed roots from the live fpath and
    # skip insecure files. A return code of 1 means insecurity was found; it is
    # not itself fatal because the secure subset remains usable.
    fpath=(${original_fpath:|_i_wdirs})

    for completion_root in "${completion_roots[@]}"; do
      (( _i_wdirs[(I)$completion_root] )) && continue

      for file in "$completion_root"/^([^_]*|*[;|&]*|*~|*.zwc)(N-.); do
        name="${file:t}"

        # Mirror compinit: insecure copies do not claim a basename, but the
        # first secure copy in fpath order does and shadows later copies.
        (( $+seen[$name] + _i_wfiles[(I)$file] )) && continue
        seen[$name]=1

        fields=()
        IFS=$' \t' read -rA fields < "$file" || continue
        [[ ${fields[1]-} == '#compdef' ]] || continue
        shift fields
        (( ${#fields[@]} )) || continue

        if [[ ${fields[1]} = -[pPkK](n|) ]]; then
          compdef ${fields[1]}na "$name" "${(@)fields[2,-1]}"
        else
          compdef -na "$name" "${fields[@]}"
        fi
      done
    done
  }
fi
