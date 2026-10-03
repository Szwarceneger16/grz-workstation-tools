#!/usr/bin/env zsh
emulate -LR zsh
set -euo pipefail

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

  source "$fpath_file"
  source "$completion_file"

  [[ -v _comp_setup ]] || fail "standalone compinit did not initialize completion"
  [[ "${_comps[zshreloadcomp]-}" == "_zshreloadcomp" ]] ||
    fail "standalone compinit did not register zshreloadcomp"
  [[ "${_comps[pr-open-comments-copyq]-}" == "_pr-open-comments" ]] ||
    fail "standalone compinit did not register a multi-command #compdef"
  [[ "${_comps[runtime-bin-probe]-}" == "_runtime_bin_probe" ]] ||
    fail "standalone compinit did not register completion/bin"
)

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

  # Simulate stale default-runtime fpath entries left by earlier startup state.
  fpath=(
    "$default_functions"
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
    [[ "$fpath_entry" == "$default_functions" ]] &&
      fail "default runtime functions remained in fpath with a custom root"
  done

  [[ "${_comps[custom-root-probe]-}" == "_custom_root_probe" ]] ||
    fail "custom runtime #compdef was not registered"

  unset CUSTOM_ROOT_PROBE_SOURCE
  _custom_root_probe
  [[ "${CUSTOM_ROOT_PROBE_SOURCE:-}" == custom ]] ||
    fail "custom runtime completion autoloaded from the wrong root"
)

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

# A deletion failure must keep the current shell and return non-zero.
if (
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/reload-failure-home"
  export HOME
  typeset -g _comp_dumpfile="$tmp_root/unremovable-dump"
  mkdir -p "$HOME" "$_comp_dumpfile" "$tmp_root/failure-bin"

  cat > "$tmp_root/failure-bin/zsh" <<EOF
#!/bin/sh
printf '%s\n' invoked > "$tmp_root/reload-failure-invoked"
EOF
  chmod +x "$tmp_root/failure-bin/zsh"
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

print -- "ok - zsh completion lifecycle"
