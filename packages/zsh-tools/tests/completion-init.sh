#!/usr/bin/env zsh
emulate -LR zsh
set -euo pipefail
unset ZDOTDIR ZSH_COMPDUMP XDG_CACHE_HOME ZSH_TOOLS_ROOT _comp_dumpfile

repo_root="${GRZ_REPO_ROOT:?GRZ_REPO_ROOT is required}"
fpath_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/core/05-fpath.zsh"
completion_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/core/90-completion_init.zsh"
reload_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/functions/zshreloadcomp.zsh"
completion_functions="$repo_root/packages/zsh-tools/install/.zsh_scripts/completion/functions"

fail() {
  print -u2 -- "not ok - $*"
  exit 1
}

prepare_home() {
  local home_dir="$1"
  local completion_root="$home_dir/.zsh_scripts/completion"

  mkdir -p "$completion_root/bin" "$completion_root/helpers"
  ln -s "$completion_functions" "$completion_root/functions"
  cat > "$completion_root/bin/_runtime_bin_probe" <<'EOF'
#compdef runtime-bin-probe
_arguments '*:value:'
EOF
}

tmp_root="$(mktemp -d)"
trap 'rm -rf -- "$tmp_root"' EXIT

# Exercise the actual rc.d ordering, with helpers pinned before the pre-loader
# and aliases reintroduced by an owner afterwards. Stow-like directory links,
# physical/logical writable parents, explicit digests and alias-only digests
# share the same identity. A secure root becomes available only after auditing.
for runtime_case in default custom; do
  for root_kind in helpers functions bin; do
    for security_case in secure root physical-parent logical-parent; do
      (
        emulate -LR zsh
        set -euo pipefail
        HOME="$tmp_root/pre-post-$runtime_case-$root_kind-$security_case"
        export HOME
        unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
        unfunction compdef compinit compaudit compdump compinstall 2>/dev/null || true
        local runtime_root="$HOME/.zsh_scripts"
        if [[ "$runtime_case" == custom ]]; then
          ZSH_TOOLS_ROOT="$HOME/custom-runtime"
          export ZSH_TOOLS_ROOT
          runtime_root="$ZSH_TOOLS_ROOT"
        fi
        mkdir -p "$runtime_root/core" "$runtime_root/completion/"{helpers,functions,bin} "$HOME/physical-parent/root" "$HOME/aliases"
        local core_file
        for core_file in 00-paths.zsh 04-completion-paths.zsh 05-fpath.zsh 90-completion_init.zsh; do
          ln -s "$repo_root/packages/zsh-tools/install/.zsh_scripts/core/$core_file" "$runtime_root/core/$core_file"
        done
        local selected_root="$runtime_root/completion/$root_kind"
        rmdir "$selected_root"
        ln -s "$HOME/physical-parent/root" "$selected_root"
        local dir_alias="$HOME/aliases/directory" digest_alias="$HOME/aliases/digest.zwc"
        ln -s "$selected_root" "$dir_alias"
        print -rl -- '#compdef pre-probe' 'typeset -g PRE_PROBE_SOURCE=audited' > "$selected_root/_pre_probe"
        print -rl -- '#autoload' 'typeset -g DELETED_ALIAS_EXECUTED=yes' > "$selected_root/_alias_deleted"
        local helper_name
        for helper_name in compinit compaudit compdump compinstall; do
          print -rl -- 'typeset -g UNTRUSTED_HELPER_EXECUTED=yes' 'return 2' > "$selected_root/$helper_name"
        done
        zcompile -Uz "$selected_root.zwc" "$selected_root/"{_pre_probe,compinit,compaudit,compdump,compinstall}
        ln -s "$selected_root.zwc" "$digest_alias"
        # This digest belongs to the alias spelling, not to the audited root.
        zcompile -Uz "$dir_alias.zwc" "$selected_root/_alias_deleted"
        fpath=("$dir_alias.zwc" "$fpath[@]")
        autoload -Uz _alias_deleted
        _alias_deleted
        unset DELETED_ALIAS_EXECUTED
        rm -- "$selected_root/_alias_deleted"
        autoload -Uz "$dir_alias/compinit" "$digest_alias/compaudit" "$dir_alias/compdump" "$digest_alias/compinstall"
        # A file link can hide a helper's managed origin in functions_source.
        print -r -- 'compaudit() { typeset -g UNTRUSTED_HELPER_EXECUTED=yes; return 2; }' > "$HOME/elsewhere-compaudit"
        rm -- "$selected_root/compaudit"
        ln -s "$HOME/elsewhere-compaudit" "$selected_root/compaudit"
        source "$HOME/elsewhere-compaudit"
        fpath=("$dir_alias" "$digest_alias" "$selected_root" "$selected_root.zwc" "$fpath[@]")
        case "$security_case" in
          root) chmod 777 "${selected_root:A}" ;;
          physical-parent) chmod 777 "$HOME/physical-parent" ;;
          logical-parent) chmod 777 "$runtime_root/completion" ;;
        esac
        source "$repo_root/packages/zsh-tools/install/.config/zsh/rc.d/20-grz-workstation-tools-pre.zsh"
        local entry
        for entry in "$dir_alias" "$digest_alias" "$dir_alias.zwc" "$selected_root.zwc" "$runtime_root/completion/"{helpers,functions,bin}; do
          (( ! fpath[(Ie)$entry] )) || fail "pre-loader exposed an unaudited completion path"
        done
        autoload -Uz compinit
        compinit -D -i || fail "external owner could not initialize from trusted fpath"
        [[ -z ${UNTRUSTED_HELPER_EXECUTED-} ]] || fail "an initialization helper ran before auditing"
        # An owner can add aliases after the pre-loader. The post-loader must
        # exclude them before resolving its auditor, and not restore aliases.
        fpath=("$dir_alias" "$digest_alias" "$dir_alias.zwc" "$selected_root.zwc" "$fpath[@]")
        unfunction compaudit
        autoload -Uz "$digest_alias/compaudit"
        _comps[deleted-alias]=_alias_deleted
        source "$repo_root/packages/zsh-tools/install/.config/zsh/rc.d/60-grz-workstation-tools-post.zsh"
        [[ -z ${UNTRUSTED_HELPER_EXECUTED-} ]] || fail "post-loader resolved an auditor through a managed alias"
        for entry in "$dir_alias" "$digest_alias" "$dir_alias.zwc" "$selected_root.zwc"; do
          (( ! fpath[(Ie)$entry] )) || fail "post-loader retained a managed alias or explicit digest"
        done
        [[ -z ${_comps[deleted-alias]-} ]] || fail "post-loader retained an unaudited alias-only digest mapping"
        _alias_deleted && fail "a deleted alias-only digest function survived cleanup"
        [[ -z ${DELETED_ALIAS_EXECUTED-} ]] || fail "an unaudited alias-only digest executed"
        if [[ "$security_case" == secure ]]; then
          [[ ${_comps[pre-probe]-} == _pre_probe ]] || fail "secure completion was not registered after audit"
          _pre_probe
          [[ ${PRE_PROBE_SOURCE-} == audited ]] || fail "secure completion did not use its audited file"
        else
          (( ! fpath[(Ie)$selected_root] )) || fail "post-loader exposed an insecure root/parent"
          [[ -z ${_comps[pre-probe]-} && -z ${_comps[deleted-alias]-} ]] || fail "post-loader retained an insecure alias mapping"
          _alias_deleted && fail "deleted alias-digest function survived quarantine"
          [[ -z ${DELETED_ALIAS_EXECUTED-} ]] || fail "deleted alias-digest code executed after quarantine"
        fi
      )
    done
  done
done

# Standalone zsh-tools must initialize completion and register mappings across
# the runtime completion directories.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/standalone"
  export HOME
  unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
  prepare_home "$HOME"
  unfunction compdef compinit 2>/dev/null || true

  fields=(owner-metadata)
  reply=(owner-reply)
  REPLY=owner-result

  source "$fpath_file"
  source "$completion_file"

  [[ ${fields[*]} == owner-metadata && ${reply[*]} == owner-reply && $REPLY == owner-result ]] ||
    fail "completion initialization clobbered owner metadata variables"

  [[ -v _comp_setup ]] || fail "standalone compinit did not initialize completion"
  [[ "${_comps[zshreloadcomp]-}" == "_zshreloadcomp" ]] ||
    fail "standalone compinit did not register zshreloadcomp"
  [[ "${_comps[pr-open-comments-copyq]-}" == "_pr-open-comments" ]] ||
    fail "standalone compinit did not register a multi-command #compdef"
  [[ "${_comps[runtime-bin-probe]-}" == "_runtime_bin_probe" ]] ||
    fail "standalone compinit did not register completion/bin"
)

# Standalone initialization must keep trusted helpers even when every managed
# root passes compaudit and contains conflicting directory/digest helper files.
for runtime_case in default custom; do
  (
    emulate -LR zsh
    set -euo pipefail
    HOME="$tmp_root/standalone-trusted-$runtime_case"
    export HOME
    unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
    unfunction compdef compinit compaudit compdump compinstall 2>/dev/null || true
    local runtime_root="$HOME/.zsh_scripts"
    if [[ "$runtime_case" == custom ]]; then
      ZSH_TOOLS_ROOT="$HOME/custom-runtime"
      export ZSH_TOOLS_ROOT
      runtime_root="$ZSH_TOOLS_ROOT"
    fi
    local helpers="$runtime_root/completion/helpers"
    mkdir -p "$helpers" "$runtime_root/completion/"{functions,bin}
    print -rl -- '#compdef trusted-init-probe' 'return 0' > "$helpers/_trusted_init_probe"
    local helper
    for helper in compinit compaudit compdump compinstall; do
      print -rl -- 'typeset -g UNTRUSTED_HELPER_EXECUTED=yes' 'return 2' > "$helpers/$helper"
    done
    zcompile -Uz "$helpers.zwc" "$helpers/"{compinit,compaudit,compdump,compinstall}
    source "$fpath_file"
    source "$completion_file"
    [[ ${_comps[trusted-init-probe]-} == _trusted_init_probe ]] || fail "standalone trusted initialization failed to register an audited completion"
    [[ -z ${UNTRUSTED_HELPER_EXECUTED-} ]] || fail "standalone initialization executed a managed helper"
    zmodload zsh/parameter
    for helper in compinit compaudit compdump compinstall; do
      [[ ${functions_source[$helper]-} != "$helpers/"* && ${functions_source[$helper]-} != "$helpers.zwc/"* ]] ||
        fail "initialization left a helper pinned to a managed provider"
    done
  )
done

# With an existing owner, bounded registration must cover all runtime completion
# directories. Existing mappings must win because it mirrors compinit's -n.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/existing-owner"
  export HOME
  unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
  prepare_home "$HOME"
  unfunction compdef compinit 2>/dev/null || true

  autoload -Uz compinit
  compinit -D -i
  _comps[zshreloadcomp]="_user_override"

  source "$fpath_file"
  source "$completion_file"

  [[ "${_comps[zshreloadcomp]-}" == "_user_override" ]] ||
    fail "bounded registration overwrote an existing completion mapping"
  [[ "${_comps[pr-open-comments-copyq]-}" == "_pr-open-comments" ]] ||
    fail "bounded registration did not add current function mappings"
  [[ "${_comps[runtime-bin-probe]-}" == "_runtime_bin_probe" ]] ||
    fail "bounded registration did not add completion/bin mappings"
)

# A later owner may trust a dump created before the runtime completion
# directories were exposed. Bounded registration must add only runtime metadata:
# an unrelated fpath completion remains absent, proving that no full rescan ran.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/stale-dump"
  export HOME
  unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
  prepare_home "$HOME"
  unfunction compdef compinit 2>/dev/null || true

  local stale_dump="$HOME/stale.zcompdump"
  local unrelated_dir="$HOME/unrelated-completions"
  mkdir -p "$unrelated_dir"
  cat > "$unrelated_dir/_unrelated_probe" <<'EOF'
#compdef unrelated-probe
_arguments '*:value:'
EOF

  autoload -Uz compinit
  compinit -d "$stale_dump" -i

  source "$fpath_file"
  fpath=("$unrelated_dir" "$fpath[@]")

  compinit -C -d "$stale_dump" -i
  [[ -z ${_comps[zshreloadcomp]-} ]] ||
    fail "stale dump unexpectedly contained zsh-tools mappings"
  [[ -z ${_comps[runtime-bin-probe]-} ]] ||
    fail "stale dump unexpectedly contained completion/bin mappings"
  [[ -z ${_comps[unrelated-probe]-} ]] ||
    fail "stale dump unexpectedly contained the unrelated mapping"

  source "$completion_file"

  [[ "${_comps[zshreloadcomp]-}" == "_zshreloadcomp" ]] ||
    fail "bounded stale-dump recovery did not register zsh-tools"
  [[ "${_comps[pr-open-comments-copyq]-}" == "_pr-open-comments" ]] ||
    fail "bounded stale-dump recovery missed a multi-command #compdef"
  [[ "${_comps[runtime-bin-probe]-}" == "_runtime_bin_probe" ]] ||
    fail "bounded stale-dump recovery missed completion/bin"
  [[ -z ${_comps[unrelated-probe]-} ]] ||
    fail "stale-dump recovery performed an unintended full fpath rescan"
)

# Bounded registration must preserve compinit's security filtering and basename
# shadowing. A mocked compaudit result lets this regression deterministically
# exercise insecure-root and insecure-file handling without privileged chown.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/security-and-shadow"
  export HOME
  unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
  unfunction compdef compinit compaudit 2>/dev/null || true

  local helpers="$HOME/.zsh_scripts/completion/helpers"
  local function_dir="$HOME/.zsh_scripts/completion/functions"
  local bin="$HOME/.zsh_scripts/completion/bin"
  mkdir -p "$helpers" "$function_dir" "$bin"

  cat > "$bin/_security_shadow" <<'EOF'
#compdef insecure-shadow-command
_security_shadow() { typeset -g SECURITY_SHADOW_SOURCE=insecure; }
_security_shadow "$@"
EOF

  cat > "$function_dir/_security_shadow" <<'EOF'
#compdef secure-shadow-command
_security_shadow() { typeset -g SECURITY_SHADOW_SOURCE=secure; }
_security_shadow "$@"
EOF

  cat > "$function_dir/_insecure_file_probe" <<'EOF'
#compdef insecure-file-command
_arguments '*:value:'
EOF

  cat > "$helpers/_dedup_probe" <<'EOF'
#compdef dedup-first-command
_dedup_probe() { typeset -g DEDUP_PROBE_SOURCE=helpers; }
_dedup_probe "$@"
EOF

  cat > "$function_dir/_dedup_probe" <<'EOF'
#compdef dedup-second-command
_dedup_probe() { typeset -g DEDUP_PROBE_SOURCE=functions; }
_dedup_probe "$@"
EOF

  autoload -Uz compinit
  compinit -D -i

  source "$fpath_file"

  compaudit() {
    _i_wdirs=("$bin")
    _i_wfiles=("$function_dir/_insecure_file_probe")
    return 1
  }

  source "$completion_file"

  [[ -z ${_comps[insecure-shadow-command]-} ]] ||
    fail "bounded registration accepted a completion from an insecure root"
  [[ "${_comps[secure-shadow-command]-}" == "_security_shadow" ]] ||
    fail "secure duplicate did not replace an insecure-root copy"
  [[ -z ${_comps[insecure-file-command]-} ]] ||
    fail "bounded registration accepted an insecure completion file"

  local fpath_entry
  for fpath_entry in "${fpath[@]}"; do
    [[ "$fpath_entry" == "$bin" ]] &&
      fail "insecure managed root remained in fpath"
  done

  unset SECURITY_SHADOW_SOURCE
  _security_shadow
  [[ "${SECURITY_SHADOW_SOURCE:-}" == secure ]] ||
    fail "secure duplicate autoloaded from the insecure root"

  [[ "${_comps[dedup-first-command]-}" == "_dedup_probe" ]] ||
    fail "first secure basename was not registered"
  [[ -z ${_comps[dedup-second-command]-} ]] ||
    fail "shadowed duplicate basename registered an extra command"

  unset DEDUP_PROBE_SOURCE
  _dedup_probe
  [[ "${DEDUP_PROBE_SOURCE:-}" == helpers ]] ||
    fail "deduplicated completion autoloaded from the wrong managed root"
)
# Cached mappings, loaded functions, helper calls and widgets must not retain
# access to an insecure file. A secure duplicate after an insecure file must
# autoload from its audited path even though the insecure directory is retained.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/cached-security"
  export HOME
  unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
  local helpers="$HOME/.zsh_scripts/completion/helpers"
  local function_dir="$HOME/.zsh_scripts/completion/functions"
  local bin="$HOME/.zsh_scripts/completion/bin"
  mkdir -p "$helpers" "$function_dir" "$bin"
  local name
  for name in _cached_bad _cached_duplicate _compiled_bad; do
    print -rl -- "#compdef ${name#_}" 'typeset -g UNSAFE_EXECUTED=yes' > "$helpers/$name"
  done
  print -rl -- '#compdef secure-duplicate' 'typeset -g DUPLICATE_SOURCE=secure' > "$function_dir/_cached_duplicate"
  print -rl -- '#autoload' 'typeset -g UNSAFE_EXECUTED=yes' > "$helpers/_bad_helper"
  touch "$helpers/_compiled_bad.zwc"
  print -rl -- '#autoload' '_loaded_alias() { typeset -g UNSAFE_EXECUTED=yes; }' > "$helpers/_loaded_bad"

  autoload -Uz compinit
  compinit -D -i
  source "$fpath_file"
  _comps[cached-bad]=_cached_bad
  _comps[cached-alias]=_cached_bad
  _services[cached-alias]=cached-service
  _patcomps['cached-*']=_cached_bad
  _postpatcomps['post-*']='=cached-service=_cached_bad'
  _compautos[_bad_helper]=yes
  compdef -K _cached_bad _cached_widget complete-word '^X^B'
  _cached_bad() { typeset -g UNSAFE_EXECUTED=yes; }
  autoload -Uz _bad_helper
  _comps[cached-compiled]=_compiled_bad
  _comps[cached-duplicate]=_cached_duplicate
  source "$helpers/_loaded_bad"
  _comps[cached-alias-implementation]=_loaded_alias

  compaudit() {
    _i_wdirs=()
    _i_wfiles=("$helpers/_cached_bad" "$helpers/_bad_helper" "$helpers/_cached_duplicate" "$helpers/_compiled_bad.zwc" "$helpers/_loaded_bad")
    return 1
  }
  source "$completion_file"

  [[ -z ${_comps[cached-bad]-} && -z ${_comps[cached-alias]-} && -z ${_services[cached-alias]-} ]] ||
    fail "cached insecure command/service mappings survived"
  [[ -z ${_patcomps['cached-*']-} && -z ${_postpatcomps['post-*']-} ]] ||
    fail "cached insecure pattern mappings survived"
  [[ -z ${_compautos[_bad_helper]-} && -z ${_comps[cached-compiled]-} ]] ||
    fail "insecure helper/compiled metadata survived"
  _cached_bad && fail "loaded insecure function remained executable"
  _bad_helper && fail "insecure helper remained autoloadable"
  _compiled_bad && fail "insecure compiled companion remained autoloadable"
  _loaded_alias && fail "an alias defined by an insecure source remained callable"
  [[ -z ${_comps[cached-alias-implementation]-} ]] || fail "an insecure source alias retained a mapping"
  [[ ${widgets[_cached_widget]-} == completion:.complete-word:_cached_bad ]] ||
    fail "widget regression no longer points at the quarantined function"
  [[ -z ${UNSAFE_EXECUTED-} ]] || fail "insecure completion code executed"
  [[ "${_comps[secure-duplicate]-}" == _cached_duplicate ]] ||
    fail "secure duplicate mapping was not registered"
  _cached_duplicate
  [[ ${DUPLICATE_SOURCE-} == secure && -z ${UNSAFE_EXECUTED-} ]] ||
    fail "secure duplicate resolved to an earlier insecure file"
)

# An insecure access path must not poison an independently audited safe path
# to the same source file. Quarantine cached code, then pin the secure duplicate.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/shared-source-duplicate"
  export HOME
  unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
  local bin="$HOME/.zsh_scripts/completion/bin"
  local function_dir="$HOME/.zsh_scripts/completion/functions"
  mkdir -p "$bin" "$function_dir" "$HOME/.zsh_scripts/completion/helpers"
  print -rl -- '#compdef shared-source-probe' 'typeset -g SHARED_SOURCE=safe' > "$function_dir/_shared_source"
  ln -s "$function_dir/_shared_source" "$bin/_shared_source"
  autoload -Uz compinit
  compinit -D -i
  source "$fpath_file"
  autoload -Uz "$bin/_shared_source"
  _shared_source
  unset SHARED_SOURCE
  _comps[shared-source-probe]=_shared_source
  compaudit() {
    _i_wdirs=("$bin")
    _i_wfiles=()
    return 1
  }
  source "$completion_file"
  [[ ${_comps[shared-source-probe]-} == _shared_source ]] || fail "an insecure alias poisoned a secure duplicate's registration"
  _shared_source
  [[ ${SHARED_SOURCE-} == safe ]] || fail "an insecure alias poisoned a secure duplicate's autoload"
)

# File-level findings and loaded implementations may use different spellings.
# Include companion links whose target basename differs from the source file.
for finding_kind in file companion root; do
  for finding_spelling in logical physical; do
    (
      emulate -LR zsh
      set -euo pipefail
      HOME="$tmp_root/file-alias-$finding_kind-$finding_spelling"
      export HOME
      unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
      local helpers="$HOME/.zsh_scripts/completion/helpers"
      local target="$HOME/elsewhere/_origin"
      local companion="$HOME/elsewhere/compiled-cache.zwc"
      mkdir -p "$helpers" "$HOME/.zsh_scripts/completion/"{functions,bin} "${target:h}"
      print -rl -- '#compdef linked-probe' '_physical_alias() { typeset -g UNSAFE_ALIAS_EXECUTED=yes; }' > "$target"
      ln -s "$target" "$helpers/_link_probe"
      zcompile -Uz "$companion" "$helpers/_link_probe"
      ln -s "$companion" "$helpers/_link_probe.zwc"
      autoload -Uz compinit
      compinit -D -i
      source "$fpath_file"
      source "$target"
      _comps[physical-alias]=_physical_alias
      _comps[linked-probe]=_link_probe
      autoload -Uz "$helpers/_link_probe"
      compaudit() {
        _i_wdirs=()
        _i_wfiles=()
        case "$finding_kind" in
          root) _i_wdirs=("$helpers") ;;
          file) _i_wfiles=("$helpers/_link_probe") ;;
          companion) _i_wfiles=("$helpers/_link_probe.zwc") ;;
        esac
        if [[ "$finding_spelling" == physical ]]; then
          _i_wfiles=("${(@)_i_wfiles:A}")
        fi
        return 1
      }
      source "$completion_file"
      [[ -z ${_comps[physical-alias]-} && -z ${_comps[linked-probe]-} ]] || fail "file identity filtering retained an insecure alias mapping"
      _physical_alias && fail "a physical source alias escaped file/companion quarantine"
      _link_probe && fail "a symlinked file/companion escaped quarantine"
      [[ -z ${UNSAFE_ALIAS_EXECUTED-} ]] || fail "insecure symlink-target code executed"
    )
  done
done

# Parent and digest findings invalidate roots too. Audit failure must quarantine
# all managed roots and cached state, rather than restore unsafe fpath entries.
for audit_case in parent digest unavailable; do
  (
    emulate -LR zsh
    set -euo pipefail
    HOME="$tmp_root/audit-$audit_case"
    export HOME
    unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
    local helpers="$HOME/.zsh_scripts/completion/helpers"
    local function_dir="$HOME/.zsh_scripts/completion/functions"
    local bin="$HOME/.zsh_scripts/completion/bin"
    mkdir -p "$helpers" "$function_dir" "$bin"
    print -rl -- '#compdef audit-probe' 'typeset -g UNSAFE_EXECUTED=yes' > "$helpers/_audit_probe"
    print -rl -- '#compdef deleted-probe' 'typeset -g DELETED_EXECUTED=yes' > "$helpers/_deleted_probe"
    autoload -Uz compinit
    compinit -D -i
    source "$fpath_file"
    _comps[audit-probe]=_audit_probe
    autoload -Uz _audit_probe
    fpath=("$helpers/../helpers.zwc" "$fpath[@]")
    autoload -Uz "$helpers/_deleted_probe"
    _deleted_probe
    unset DELETED_EXECUTED
    rm -- "$helpers/_deleted_probe"
    compaudit() {
      _i_wfiles=()
      case "$audit_case" in
        parent) _i_wdirs=("${helpers:h}"); return 1 ;;
        digest) _i_wdirs=("$helpers.zwc"); return 1 ;;
        unavailable) _i_wdirs=(); return 2 ;;
      esac
    }
    source "$completion_file"
    (( ! fpath[(Ie)$helpers] )) || fail "$audit_case left an insecure root on fpath"
    (( ! fpath[(Ie)$helpers/../helpers.zwc] )) || fail "$audit_case left an explicit managed digest on fpath"
    [[ -z ${_comps[audit-probe]-} ]] || fail "$audit_case retained an insecure cached mapping"
    _audit_probe && fail "$audit_case retained an insecure autoload"
    _deleted_probe && fail "$audit_case retained a deleted loaded function from an insecure root"
    [[ -z ${UNSAFE_EXECUTED-} ]] || fail "$audit_case executed insecure code"
    [[ -z ${DELETED_EXECUTED-} ]] || fail "$audit_case executed deleted insecure code"
  )
done

# A real missing helper must not abort before quarantine. autoload -R aborts
# command processing when lookup fails, unlike a resolved-or-deferred -r stub.
for missing_owner in standalone external; do
  (
    emulate -LR zsh
    set -euo pipefail
    HOME="$tmp_root/missing-helper-$missing_owner"
    export HOME
    unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
    local helpers="$HOME/.zsh_scripts/completion/helpers"
    mkdir -p "$helpers" "$HOME/.zsh_scripts/completion/"{functions,bin}
    print -r -- 'typeset -g MISSING_AUDIT_EXECUTED=yes' > "$helpers/_missing_audit_probe"
    unfunction compdef compinit compaudit compdump compinstall 2>/dev/null || true
    if [[ "$missing_owner" == external ]]; then
      autoload -Uz compinit
      compinit -D -i
      _comps[missing-audit-probe]=_missing_audit_probe
    fi
    autoload -Uz "$helpers/_missing_audit_probe"
    _missing_audit_probe
    unset MISSING_AUDIT_EXECUTED
    rm -- "$helpers/_missing_audit_probe"
    unfunction compaudit compinit compdump compinstall 2>/dev/null || true
    fpath=("$helpers")
    local init_status=0
    source "$completion_file" 2> "$HOME/init-error.log" || init_status=$?
    if [[ "$missing_owner" == standalone ]]; then
      (( init_status != 0 )) || fail "missing standalone compinit did not report an initialization error"
    fi
    (( ! fpath[(Ie)$helpers] )) || fail "a missing auditor restored unchecked fpath"
    [[ -z ${_comps[missing-audit-probe]-} ]] || fail "a missing auditor left cached dispatch live"
    _missing_audit_probe && fail "missing helper lookup aborted before loaded-function quarantine"
    [[ -z ${MISSING_AUDIT_EXECUTED-} ]] || fail "unchecked code executed after missing helper lookup"
  )
done

# Exercise upstream compaudit as well as deterministic mocked ownership results.
# A world-writable managed root must be rejected for both initialization owners.
for completion_owner in standalone external; do
  (
    emulate -LR zsh
    set -euo pipefail
    HOME="$tmp_root/real-audit-$completion_owner"
    export HOME
    unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
    local helpers="$HOME/.zsh_scripts/completion/helpers"
    mkdir -p "$helpers" "$HOME/.zsh_scripts/completion/functions" "$HOME/.zsh_scripts/completion/bin"
    print -rl -- '#compdef writable-probe' 'typeset -g UNSAFE_EXECUTED=yes' > "$helpers/_writable_probe"
    unfunction compdef compinit compaudit 2>/dev/null || true
    if [[ "$completion_owner" == external ]]; then
      # Reproduce a dump created by a previous startup before paths were deferred.
      fpath=("$helpers" "$fpath[@]")
      autoload -Uz compinit
      compinit -d "$HOME/owner.dump" -i
      chmod 777 "$helpers"
      compinit -C -d "$HOME/owner.dump"
      [[ ${_comps[writable-probe]-} == _writable_probe ]] ||
        fail "stale owner dump did not preload the insecure mapping"
    else
      chmod 777 "$helpers"
    fi
    source "$fpath_file"
    source "$completion_file"
    (( ! fpath[(Ie)$helpers] )) || fail "real audit left a writable root on fpath"
    [[ -z ${_comps[writable-probe]-} ]] || fail "real audit accepted a writable root"
    _writable_probe && fail "real audit left unsafe code callable"
    [[ -z ${UNSAFE_EXECUTED-} ]] || fail "real audit executed unsafe code"
  )
done

# Explicit directory digests must not supply initialization/audit helpers, even
# if an owner adds them after 05-fpath. Loaded digest functions use a .zwc
# directory in functions_source and must be quarantined after source deletion.
for runtime_case in default custom; do
  for completion_owner in standalone external; do
    for root_kind in helpers functions bin; do
      (
        emulate -LR zsh
        set -euo pipefail
        HOME="$tmp_root/explicit-digest-$runtime_case-$completion_owner-$root_kind"
        export HOME
        unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
        unfunction compdef compinit compaudit compdump compinstall 2>/dev/null || true
        local runtime_root="$HOME/.zsh_scripts"
        if [[ "$runtime_case" == custom ]]; then
          ZSH_TOOLS_ROOT="$HOME/custom-runtime"
          export ZSH_TOOLS_ROOT
          runtime_root="$ZSH_TOOLS_ROOT"
        fi
        mkdir -p "$runtime_root/completion/"{helpers,functions,bin}
        local digest_root="$runtime_root/completion/$root_kind"
        print -rl -- '#compdef digest-probe' 'typeset -g UNSAFE_EXECUTED=yes' > "$digest_root/_digest_probe"
        print -rl -- '#autoload' 'typeset -g DELETED_DIGEST_EXECUTED=yes' > "$digest_root/_digest_deleted"
        local helper_name
        for helper_name in compaudit compinit compdump compinstall; do
          print -rl -- 'typeset -g DIGEST_HELPER_EXECUTED=yes' 'return 2' > "$digest_root/$helper_name"
        done
        zcompile -Uz "$digest_root.zwc" "$digest_root/"{_digest_probe,_digest_deleted,compaudit,compinit,compdump,compinstall}
        if [[ "$completion_owner" == external ]]; then
          autoload -Uz compinit
          compinit -D -i
        fi
        # Both initial normalization and a later owner insertion are exercised.
        fpath=("$digest_root/../$root_kind.zwc" "$fpath[@]")
        source "$fpath_file"
        (( ! fpath[(Ie)$digest_root/../$root_kind.zwc] )) || fail "05-fpath retained an explicit managed digest"
        fpath=("$digest_root/../$root_kind.zwc" "$fpath[@]")
        autoload -Uz _digest_deleted
        _digest_deleted
        zmodload zsh/parameter
        [[ "${functions_source[_digest_deleted]:a}" == "$digest_root.zwc/_digest_deleted" ]] ||
          fail "fixture did not load the function from its directory digest"
        unset DELETED_DIGEST_EXECUTED
        rm -- "$digest_root/_digest_deleted"
        chmod 777 "$digest_root"
        unfunction compaudit 2>/dev/null || true
        source "$completion_file"
        [[ -z ${DIGEST_HELPER_EXECUTED-} ]] || fail "managed digest supplied an initialization/audit helper"
        (( ! fpath[(Ie)$digest_root/../$root_kind.zwc] )) || fail "audit retained an explicit insecure digest"
        [[ -z ${_comps[digest-probe]-} ]] || fail "audit retained a mapping from an insecure digest root"
        _digest_deleted && fail "audit retained a deleted function loaded from an insecure digest"
        [[ -z ${DELETED_DIGEST_EXECUTED-} ]] || fail "audit executed deleted digest code"
      )
    done
  done
done

# compdef -n alone does not preserve pattern and command=service overrides.
# Managed roots may also have been reordered by the external owner.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/owner-overrides"
  export HOME
  unset ZSH_TOOLS_ROOT _comp_setup _comp_dumpfile
  local helpers="$HOME/.zsh_scripts/completion/helpers"
  local function_dir="$HOME/.zsh_scripts/completion/functions"
  local bin="$HOME/.zsh_scripts/completion/bin"
  mkdir -p "$helpers" "$function_dir" "$bin"
  print -rl -- '#compdef -p owner-*' 'return 0' > "$helpers/_owner_pattern"
  print -rl -- '#compdef -P post-*' 'return 0' > "$helpers/_owner_postpattern"
  print -rl -- '#compdef owner-command=new-service' 'return 0' > "$helpers/_owner_service"
  print -rl -- '#compdef owner-plain=new-service' 'return 0' > "$helpers/_owner_plain"
  print -rl -- '#compdef owner-file' 'return 0' > "$helpers/_owner_file"
  print -rl -- '#compdef owner-empty' 'return 0' > "$helpers/_owner_empty"
  print -rl -- '#compdef owner-pinned' 'return 0' > "$helpers/_owner_pinned"
  print -rl -- '#compdef helpers-command' 'typeset -g ORDER_SOURCE=helpers' > "$helpers/_order_probe"
  print -rl -- '#compdef bin-command' 'typeset -g ORDER_SOURCE=bin' > "$bin/_order_probe"
  autoload -Uz compinit
  compinit -D -i
  _patcomps['owner-*']=_user_override
  _postpatcomps['post-*']=_user_override
  # Parameter-assigned functions have no source path; this is different from
  # an unresolved autoload stub, which also has an empty functions_source.
  functions[_owner_service]='typeset -g OWNER_IMPLEMENTATION=preserved'
  zmodload zsh/parameter
  [[ -z ${functions_source[_owner_service]-} ]] || fail "owner fixture unexpectedly has a source path"
  _owner_file() { typeset -g OWNER_FILE_IMPLEMENTATION=preserved; }
  functions[_owner_empty]=''
  local owner_dir="$HOME/owner-functions"
  mkdir -p "$owner_dir"
  print -r -- 'typeset -g OWNER_PINNED_IMPLEMENTATION=preserved' > "$owner_dir/_owner_pinned"
  autoload -Uz "$owner_dir/_owner_pinned"
  [[ ${functions_source[_owner_pinned]-} == "$owner_dir/_owner_pinned" ]] || fail "owner fixture did not pin its source file"
  local empty_body="${functions[_owner_empty]}"
  autoload -Uz _order_probe
  [[ -z ${functions_source[_order_probe]-} ]] || fail "autoload fixture unexpectedly has a source path"
  _comps[owner-command]=_owner_service
  _comps[owner-file]=_owner_file
  _comps[owner-empty]=_owner_empty
  _comps[owner-pinned]=_owner_pinned
  _services[owner-command]=old-service
  _comps[owner-plain]=_user_override
  source "$fpath_file"
  fpath=("$bin" "${(@)fpath:#$bin}")
  source "$completion_file"
  [[ ${_patcomps['owner-*']-} == _user_override && ${_postpatcomps['post-*']-} == _user_override ]] ||
    fail "bounded registration overwrote pattern overrides"
  [[ ${_comps[owner-command]-} == _owner_service && ${_services[owner-command]-} == old-service ]] ||
    fail "bounded registration overwrote a service override"
  _owner_pinned
  [[ ${OWNER_PINNED_IMPLEMENTATION-} == preserved ]] || fail "bounded registration replaced an owner-pinned autoload"
  _owner_file
  [[ ${OWNER_FILE_IMPLEMENTATION-} == preserved ]] || fail "bounded registration replaced a file-backed owner function"
  [[ ${functions[_owner_empty]} == "$empty_body" ]] || fail "bounded registration replaced an empty owner definition"
  _owner_service
  [[ ${OWNER_IMPLEMENTATION-} == preserved ]] || fail "bounded registration replaced an owner's explicit implementation"
  [[ ${_comps[owner-plain]-} == _user_override && -z ${_services[owner-plain]-} ]] ||
    fail "bounded registration attached a new service to an existing plain override"
  [[ ${_comps[bin-command]-} == _order_probe && -z ${_comps[helpers-command]-} ]] ||
    fail "basename shadowing ignored the current managed fpath order"
  _order_probe
  [[ ${ORDER_SOURCE-} == bin ]] || fail "reordered root autoload chose the wrong copy"
)

# A custom ZSH_TOOLS_ROOT must drive both fpath and bounded registration.
# A mismatched default-runtime copy must not remain available for autoload.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/custom-root-home"
  ZSH_TOOLS_ROOT="$tmp_root/custom-root-runtime"
  export HOME ZSH_TOOLS_ROOT
  unset _comp_setup _comp_dumpfile
  unfunction compdef compinit 2>/dev/null || true

  local custom_functions="$ZSH_TOOLS_ROOT/completion/functions"
  local default_functions="$HOME/.zsh_scripts/completion/functions"
  mkdir -p "$custom_functions" "$ZSH_TOOLS_ROOT/completion/helpers" "$ZSH_TOOLS_ROOT/completion/bin" "$default_functions"

  cat > "$custom_functions/_custom_root_probe" <<'EOF'
#compdef custom-root-probe
_custom_root_probe() {
  typeset -g CUSTOM_ROOT_PROBE_SOURCE=custom
}
_custom_root_probe "$@"
EOF

  cat > "$default_functions/_custom_root_probe" <<'EOF'
#compdef custom-root-probe
_custom_root_probe() {
  typeset -g CUSTOM_ROOT_PROBE_SOURCE=default
}
_custom_root_probe "$@"
EOF

  print -rl -- '#compdef digest-refresh' 'typeset -g DIGEST_REFRESH_SOURCE=default' > "$default_functions/_digest_refresh"
  print -rl -- '#compdef digest-refresh' 'typeset -g DIGEST_REFRESH_SOURCE=custom' > "$custom_functions/_digest_refresh"
  zcompile -Uz "$default_functions.zwc" "$default_functions/_digest_refresh"
  fpath=("$default_functions.zwc" "$fpath[@]")
  autoload -Uz _digest_refresh
  _digest_refresh
  zmodload zsh/parameter
  [[ ${functions_source[_digest_refresh]:a:h} == "$default_functions.zwc" ]] || fail "fixture did not load a default-runtime digest function"
  unset DIGEST_REFRESH_SOURCE
  print -rl -- '#compdef stale-default-only' 'typeset -g STALE_DEFAULT_EXECUTED=yes' > "$default_functions/_stale_default_only"
  autoload -Uz "$default_functions/_stale_default_only"
  _stale_default_only
  unset STALE_DEFAULT_EXECUTED

  # Simulate stale default-runtime fpath entries left by earlier startup state.
  fpath=(
    "$default_functions"
    "$default_functions.zwc"
    "$HOME/.zsh_scripts/completion/helpers.zwc"
    "$HOME/.zsh_scripts/completion/bin.zwc"
    "$HOME/.zsh_scripts/completion.zwc"
    "$HOME/.zsh_scripts/.completion.zwc"
    "$HOME/.zsh_scripts/completion/helpers"
    "$HOME/.zsh_scripts/completion/bin"
    "$fpath[@]"
  )

  autoload -Uz compinit
  compinit -D -i

  source "$fpath_file"
  source "$completion_file"

  [[ "$fpath[1]" == "$ZSH_TOOLS_ROOT/completion/helpers" ]] ||
    fail "custom runtime helpers were not first in fpath"
  [[ "$fpath[2]" == "$ZSH_TOOLS_ROOT/completion/functions" ]] ||
    fail "custom runtime functions were not second in fpath"
  [[ "$fpath[3]" == "$ZSH_TOOLS_ROOT/completion/bin" ]] ||
    fail "custom runtime bin was not third in fpath"

  local fpath_entry
  for fpath_entry in "${fpath[@]}"; do
    [[ "$fpath_entry" == "$HOME/.zsh_scripts/"* ]] &&
      fail "default runtime functions remained in fpath with a custom root"
  done

  [[ "${_comps[custom-root-probe]-}" == "_custom_root_probe" ]] ||
    fail "custom runtime #compdef was not registered"

  [[ -z ${_comps[stale-default-only]-} ]] || fail "a default-only completion retained cached dispatch with a custom root"
  _stale_default_only && fail "a default-only loaded function survived custom runtime selection"
  [[ -z ${STALE_DEFAULT_EXECUTED-} ]] || fail "a default-only completion executed with a custom runtime"
  _digest_refresh
  [[ ${DIGEST_REFRESH_SOURCE-} == custom ]] || fail "custom runtime did not replace a loaded default-runtime digest function"
  unset CUSTOM_ROOT_PROBE_SOURCE
  _custom_root_probe
  [[ "${CUSTOM_ROOT_PROBE_SOURCE:-}" == custom ]] ||
    fail "custom runtime completion autoloaded from the wrong root"
)

# Help and its completion must use the same custom runtime root, including the
# completion's fallback when the core module has not been sourced. Explicit help
# roots retain precedence over the runtime default.
for help_case in core fallback override; do
  (
    emulate -LR zsh
    set -euo pipefail
    HOME="$tmp_root/cmdhelp-$help_case-home"
    ZSH_TOOLS_ROOT="$tmp_root/cmdhelp-$help_case-runtime"
    export HOME ZSH_TOOLS_ROOT
    local selected_root="$ZSH_TOOLS_ROOT"
    if [[ "$help_case" == override ]]; then
      selected_root="$tmp_root/cmdhelp-explicit"
      typeset -g __CMDHELP_ROOT="$selected_root/cmdhelp"
      typeset -g __CMDHELP_FUNCTIONS_ROOT="$selected_root/functions"
    fi
    mkdir -p "$selected_root/cmdhelp/functions" "$selected_root/functions" "$HOME/.zsh_scripts/cmdhelp/functions"
    touch "$selected_root/cmdhelp/functions/custom-topic.md" "$selected_root/functions/custom-entry.zsh" "$HOME/.zsh_scripts/cmdhelp/functions/default-topic.md"
    if [[ "$help_case" != fallback ]]; then
      source "$repo_root/packages/zsh-tools/install/.zsh_scripts/core/11-cmdhelp.zsh"
      [[ $__CMDHELP_ROOT == "$selected_root/cmdhelp" && $__CMDHELP_FUNCTIONS_ROOT == "$selected_root/functions" ]] ||
        fail "cmdhelp core ignored the selected help/runtime root"
      [[ "$(__cmdhelp_collect_topic_names functions)" == custom-topic ]] || fail "cmdhelp read topics from the wrong runtime"
    else
      source "$repo_root/packages/zsh-tools/install/.zsh_scripts/functions/battery-ac-watch.zsh"
      unset ZSH_SCRIPTS_ROOT
      print -r -- runtime-battery-help > "$selected_root/cmdhelp/functions/battery-ac-watch.md"
      [[ "$(battery-ac-watch --help)" == runtime-battery-help ]] || fail "command help fallback ignored the custom runtime"
    fi
    local -a words=(cmdhelp '')
    local -i CURRENT=2
    compadd() { typeset -ga CAPTURED_TOPICS=("${(@P)2}"); }
    source "$repo_root/packages/zsh-tools/install/.zsh_scripts/completion/functions/_cmdhelp"
    (( CAPTURED_TOPICS[(Ie)custom-topic] && CAPTURED_TOPICS[(Ie)custom-entry] )) ||
      fail "cmdhelp completion missed custom runtime topics/entrypoints"
    (( ! CAPTURED_TOPICS[(Ie)default-topic] )) || fail "cmdhelp completion used stale default topics"
  )
done

# Successful reload removes the actual active dump, configured/default
# alternatives, and dumps under a non-HOME ZDOTDIR before replacing the shell.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/reload-home"
  ZDOTDIR="$tmp_root/reload-zdot"
  XDG_CACHE_HOME="$tmp_root/reload-cache"
  ZSH_COMPDUMP="$tmp_root/configured/zcompdump"
  export HOME ZDOTDIR XDG_CACHE_HOME ZSH_COMPDUMP

  typeset -g _comp_dumpfile="$tmp_root/active/custom.dump"

  mkdir -p "$HOME" "$ZDOTDIR" "$XDG_CACHE_HOME/zsh" "${ZSH_COMPDUMP:h}" "${_comp_dumpfile:h}" "$tmp_root/fake-bin"
  touch "$_comp_dumpfile" "$_comp_dumpfile.zwc" "$ZSH_COMPDUMP" "$ZSH_COMPDUMP.zwc" "$HOME/.zcompdump-legacy" "$ZDOTDIR/.zcompdump-current" "$XDG_CACHE_HOME/zsh/compdump" "$XDG_CACHE_HOME/zsh/compdump.zwc"

  cat > "$tmp_root/fake-bin/zsh" <<EOF
#!/bin/sh
printf '%s\n' invoked > "$tmp_root/reload-invoked"
EOF
  chmod +x "$tmp_root/fake-bin/zsh"
  PATH="$tmp_root/fake-bin:$PATH"
  export PATH

  source "$reload_file"
  zshreloadcomp
)

[[ -f "$tmp_root/reload-invoked" ]] ||
  fail "zshreloadcomp did not exec a fresh zsh"
[[ ! -e "$tmp_root/active/custom.dump" && ! -e "$tmp_root/active/custom.dump.zwc" ]] ||
  fail "active _comp_dumpfile was not removed"
[[ ! -e "$tmp_root/configured/zcompdump" && ! -e "$tmp_root/configured/zcompdump.zwc" ]] ||
  fail "configured ZSH_COMPDUMP was not removed"
[[ ! -e "$tmp_root/reload-home/.zcompdump-legacy" ]] ||
  fail "legacy HOME completion dump was not removed"
[[ ! -e "$tmp_root/reload-zdot/.zcompdump-current" ]] ||
  fail "ZDOTDIR completion dump was not removed"
[[ ! -e "$tmp_root/reload-cache/zsh/compdump" && ! -e "$tmp_root/reload-cache/zsh/compdump.zwc" ]] ||
  fail "default cache completion dump was not removed"

# A non-file dump sink such as /dev/null must not block a clean shell
# replacement because there is no persistent dump file to unlink.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/non-file-sink-home"
  export HOME
  typeset -g _comp_dumpfile=/dev/null
  mkdir -p "$HOME" "$tmp_root/non-file-sink-bin"

  cat > "$tmp_root/non-file-sink-bin/zsh" <<EOF
#!/bin/sh
printf '%s\n' invoked > "$tmp_root/non-file-sink-invoked"
EOF
  chmod +x "$tmp_root/non-file-sink-bin/zsh"
  PATH="$tmp_root/non-file-sink-bin:$PATH"
  export PATH

  source "$reload_file"
  zshreloadcomp
)

[[ -f "$tmp_root/non-file-sink-invoked" ]] ||
  fail "non-file compdump sink blocked shell replacement"

# All paths use the same regular-file/symlink policy, including .zwc companions
# and legacy globs. Non-files are retained; dangling/directory symlinks are
# unlinked without touching their targets.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/dump-types-home"
  ZDOTDIR="$tmp_root/dump-types-zdot"
  XDG_CACHE_HOME="$tmp_root/dump-types-cache"
  ZSH_COMPDUMP="$tmp_root/dump-types-active"
  export HOME ZDOTDIR XDG_CACHE_HOME ZSH_COMPDUMP
  _comp_dumpfile="$tmp_root/dump-types-sink"
  mkdir -p "$HOME/.zcompdump" "$HOME/.zcompdump-backups" "$ZDOTDIR/.zcompdump" "$ZDOTDIR/.zcompdump-backups" "$XDG_CACHE_HOME/zsh/compdump.zwc" "$ZSH_COMPDUMP.zwc" "$tmp_root/dump-types-target" "$tmp_root/dump-types-bin"
  mkfifo "$_comp_dumpfile" "$HOME/.zcompdump-fifo" "$ZDOTDIR/.zcompdump-fifo"
  touch "$_comp_dumpfile.zwc" "$ZSH_COMPDUMP" "$XDG_CACHE_HOME/zsh/compdump" "$HOME/.zcompdump-regular" "$ZDOTDIR/.zcompdump-regular"
  ln -s "$tmp_root/dump-types-target" "$HOME/.zcompdump-link-dir"
  ln -s "$tmp_root/dump-types-missing" "$ZDOTDIR/.zcompdump-link-dangling"
  cat > "$tmp_root/dump-types-bin/zsh" <<EOF
#!/bin/sh
printf '%s\n' invoked > "$tmp_root/dump-types-invoked"
EOF
  chmod +x "$tmp_root/dump-types-bin/zsh"
  PATH="$tmp_root/dump-types-bin:$PATH"
  export PATH
  source "$reload_file"
  zshreloadcomp
)
[[ -f "$tmp_root/dump-types-invoked" ]] || fail "non-file cache candidates blocked reload"
for retained in dump-types-home/.zcompdump dump-types-home/.zcompdump-backups dump-types-zdot/.zcompdump dump-types-zdot/.zcompdump-backups dump-types-active.zwc dump-types-cache/zsh/compdump.zwc dump-types-target; do
  [[ -d "$tmp_root/$retained" ]] || fail "reload removed a directory candidate or symlink target"
done
for retained in dump-types-sink dump-types-home/.zcompdump-fifo dump-types-zdot/.zcompdump-fifo; do
  [[ -p "$tmp_root/$retained" ]] || fail "reload removed a non-file sink"
done
for removed in dump-types-sink.zwc dump-types-active dump-types-cache/zsh/compdump dump-types-home/.zcompdump-regular dump-types-zdot/.zcompdump-regular dump-types-home/.zcompdump-link-dir dump-types-zdot/.zcompdump-link-dangling; do
  [[ ! -e "$tmp_root/$removed" && ! -L "$tmp_root/$removed" ]] || fail "reload missed a file or symlink candidate"
done

# Relative dump/cache configuration has no reliable original working directory.
# Validate the whole batch before deleting an absolute candidate or restarting.
# The active-path case uses actual compinit -d followed by a directory change.
for relative_source in active configured zdot cache; do
  (
    emulate -LR zsh
    set -euo pipefail
    HOME="$tmp_root/relative-$relative_source/home"
    export HOME
    unset ZDOTDIR ZSH_COMPDUMP XDG_CACHE_HOME _comp_dumpfile
    local origin="$tmp_root/relative-$relative_source/origin"
    local destination="$tmp_root/relative-$relative_source/destination"
    mkdir -p "$HOME" "$origin" "$destination/cache/zsh" "$destination/zdot" "$destination/bin"
    touch "$HOME/.zcompdump" "$origin/cache.dump" "$origin/cache.dump.zwc" "$destination/cache.dump" "$destination/cache.dump.zwc" "$destination/cache/zsh/compdump" "$destination/cache/zsh/compdump.zwc" "$destination/zdot/.zcompdump"
    if [[ "$relative_source" == active ]]; then
      cd "$origin"
      autoload -Uz compinit
      compinit -i -d cache.dump
      [[ $_comp_dumpfile == cache.dump ]] || fail "fixture did not retain compinit's relative dump argument"
    else
      _comp_dumpfile="$HOME/.zcompdump"
      case "$relative_source" in
        configured) ZSH_COMPDUMP=cache.dump ;;
        zdot) ZDOTDIR=zdot ;;
        cache) XDG_CACHE_HOME=cache ;;
      esac
    fi
    cd "$destination"
    cat > "$destination/bin/zsh" <<'EOF'
#!/bin/sh
printf '%s\n' invoked > reload-invoked
EOF
    chmod +x "$destination/bin/zsh"
    PATH="$destination/bin:$PATH"
    source "$reload_file"
    if zshreloadcomp 2> "$destination/error.log"; then
      fail "reload accepted an ambiguous relative dump/cache path"
    fi
    [[ ! -e "$destination/reload-invoked" ]] || fail "relative path error replaced the shell"
    [[ "$(< "$destination/error.log")" == *'relative dump path'* ]] || fail "relative path error did not explain its cause"
    local retained=''
    for retained in "$HOME/.zcompdump" "$origin/cache.dump" "$origin/cache.dump.zwc" "$destination/cache.dump" "$destination/cache.dump.zwc" "$destination/cache/zsh/compdump" "$destination/cache/zsh/compdump.zwc" "$destination/zdot/.zcompdump"; do
      [[ -f "$retained" ]] || fail "relative path handling deleted a dump candidate"
    done
    touch "$destination/validated"
  )
  [[ -f "$tmp_root/relative-$relative_source/destination/validated" && ! -e "$tmp_root/relative-$relative_source/destination/reload-invoked" ]] ||
    fail "relative path handling replaced the shell before validation"
done

# A real dump-file deletion failure must keep the current shell and return
# non-zero. Use a fake rm to make the failure deterministic without privilege.
if (
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/reload-failure-home"
  export HOME
  typeset -g _comp_dumpfile="$tmp_root/unremovable.dump"
  mkdir -p "$HOME" "$tmp_root/failure-bin"
  touch "$_comp_dumpfile"

  cat > "$tmp_root/failure-bin/rm" <<'EOF'
#!/bin/sh
exit 1
EOF
  cat > "$tmp_root/failure-bin/zsh" <<EOF
#!/bin/sh
printf '%s\n' invoked > "$tmp_root/reload-failure-invoked"
EOF
  chmod +x "$tmp_root/failure-bin/rm" "$tmp_root/failure-bin/zsh"
  PATH="$tmp_root/failure-bin:$PATH"
  export PATH

  source "$reload_file"
  zshreloadcomp
); then
  fail "zshreloadcomp succeeded despite a dump deletion failure"
fi

[[ ! -e "$tmp_root/reload-failure-invoked" ]] ||
  fail "zshreloadcomp replaced the shell after a dump deletion failure"
# A login shell must remain a login shell after replacement. The initial login
# reads .zprofile before the replacement marker is set; only the replacement
# should therefore create the marker.
login_home="$tmp_root/login-home"
login_zdot="$tmp_root/login-zdot"
login_marker="$tmp_root/login-preserved"
mkdir -p "$login_home" "$login_zdot"
cat > "$login_zdot/.zprofile" <<'EOF'
if [[ ${ZSHRELOADCOMP_REPLACED:-0} == 1 ]]; then
  print -r -- login > "$ZSHRELOADCOMP_LOGIN_MARKER"
fi
EOF

HOME="$login_home" ZDOTDIR="$login_zdot" RELOAD_FILE="$reload_file" ZSHRELOADCOMP_LOGIN_MARKER="$login_marker" zsh -l -c 'source "$RELOAD_FILE"; export ZSHRELOADCOMP_REPLACED=1; zshreloadcomp' </dev/null

[[ -f "$login_marker" ]] ||
  fail "zshreloadcomp did not preserve login-shell mode"

# Verify all LOGIN/INTERACTIVE combinations with a real replacement interpreter
# and redirected stdin. The replacement records modes in .zshenv, and interactive
# cases must additionally reach .zshrc; -c deliberately does not survive exec.
for login_mode in 0 1; do
  for interactive_mode in 0 1; do
    mode_zdot="$tmp_root/modes-$login_mode-$interactive_mode"
    mkdir -p "$mode_zdot"
    cat > "$mode_zdot/.zshenv" <<'EOF'
if [[ ${RELOAD_REPLACED:-0} == 1 ]]; then
  print -r -- "${options[login]}:${options[interactive]}" > "$RELOAD_MODE_MARKER"
fi
EOF
    cat > "$mode_zdot/.zshrc" <<'EOF'
if [[ ${RELOAD_REPLACED:-0} == 1 ]]; then
  print -r -- reached > "$RELOAD_RC_MARKER"
  exit 0
fi
EOF
    mode_flags=()
    expected_login=off
    expected_interactive=off
    if (( login_mode )); then mode_flags+=(-l); expected_login=on; fi
    if (( interactive_mode )); then mode_flags+=(-i); expected_interactive=on; fi
    HOME="$mode_zdot" ZDOTDIR="$mode_zdot" RELOAD_FILE="$reload_file" RELOAD_MODE_MARKER="$mode_zdot/modes" RELOAD_RC_MARKER="$mode_zdot/rc" zsh "${mode_flags[@]}" -c 'source "$RELOAD_FILE"; export RELOAD_REPLACED=1; zshreloadcomp' </dev/null
    [[ "$(<"$mode_zdot/modes")" == "$expected_login:$expected_interactive" ]] ||
      fail "reload changed LOGIN/INTERACTIVE combination $login_mode/$interactive_mode"
    if (( interactive_mode )); then
      [[ -f "$mode_zdot/rc" ]] || fail "interactive replacement skipped .zshrc"
    else
      [[ ! -e "$mode_zdot/rc" ]] || fail "noninteractive replacement loaded .zshrc"
    fi
  done
done

print -- "ok - zsh completion lifecycle"
