#!/usr/bin/env zsh
emulate -LR zsh
set -euo pipefail

repo_root="${GRZ_REPO_ROOT:?GRZ_REPO_ROOT is required}"
fpath_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/core/05-fpath.zsh"
completion_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/core/90-completion_init.zsh"
reload_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/functions/zshreloadcomp.zsh"
sentinel_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/completion/functions/_zshreloadcomp"

fail() {
  print -u2 -- "not ok - $*"
  exit 1
}

prepare_home() {
  local home_dir="$1"
  mkdir -p "$home_dir/.zsh_scripts/completion/functions"
  ln -s "$sentinel_file" "$home_dir/.zsh_scripts/completion/functions/_zshreloadcomp"
}

tmp_root="$(mktemp -d)"
trap 'rm -rf -- "$tmp_root"' EXIT

# Standalone zsh-tools must initialize completion and register its own sentinel.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/standalone"
  export HOME
  prepare_home "$HOME"
  unset _comp_setup _comp_dumpfile
  unfunction compdef compinit 2>/dev/null || true

  source "$fpath_file"
  source "$completion_file"

  [[ -v _comp_setup ]] || fail "standalone compinit did not initialize completion"
  [[ "${_comps[zshreloadcomp]-}" == "_zshreloadcomp" ]] ||
    fail "standalone compinit did not register the zsh-tools sentinel"
)

# If another owner already scanned the public fpath, 90-completion_init should
# accept the registered sentinel and leave the state intact.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/already-owned"
  export HOME
  prepare_home "$HOME"
  unset _comp_setup _comp_dumpfile
  unfunction compdef compinit 2>/dev/null || true

  source "$fpath_file"
  autoload -Uz compinit
  compinit -D -i

  [[ "${_comps[zshreloadcomp]-}" == "_zshreloadcomp" ]] ||
    fail "pre-existing completion owner did not register the sentinel"

  source "$completion_file"

  [[ "${_comps[zshreloadcomp]-}" == "_zshreloadcomp" ]] ||
    fail "registered sentinel was lost"
)

# A later owner may trust a dump created before the zsh-tools fpath was exposed.
# compinit -C must leave the sentinel absent, and 90-completion_init must repair
# the current session with its dump-independent -D rescan.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/stale-dump"
  export HOME
  prepare_home "$HOME"
  unset _comp_setup _comp_dumpfile
  unfunction compdef compinit 2>/dev/null || true

  local stale_dump="$HOME/stale.zcompdump"

  autoload -Uz compinit
  compinit -d "$stale_dump" -i

  source "$fpath_file"

  compinit -C -d "$stale_dump" -i
  [[ -z ${_comps[zshreloadcomp]-} ]] ||
    fail "stale dump unexpectedly contained the zsh-tools sentinel"

  source "$completion_file"

  [[ "${_comps[zshreloadcomp]-}" == "_zshreloadcomp" ]] ||
    fail "stale-dump recovery did not register the zsh-tools sentinel"
)

# zshreloadcomp must remove the actual active dump, configured/default
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

  mkdir -p     "$HOME"     "$ZDOTDIR"     "$XDG_CACHE_HOME/zsh"     "${ZSH_COMPDUMP:h}"     "${_comp_dumpfile:h}"     "$tmp_root/fake-bin"

  touch     "$_comp_dumpfile"     "$_comp_dumpfile.zwc"     "$ZSH_COMPDUMP"     "$ZSH_COMPDUMP.zwc"     "$HOME/.zcompdump-legacy"     "$ZDOTDIR/.zcompdump-current"     "$XDG_CACHE_HOME/zsh/compdump"     "$XDG_CACHE_HOME/zsh/compdump.zwc"

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

print -- "ok - zsh completion lifecycle"
