#!/usr/bin/env zsh
emulate -LR zsh
set -euo pipefail

repo_root="${GRZ_REPO_ROOT:?GRZ_REPO_ROOT is required}"
fpath_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/core/05-fpath.zsh"
completion_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/core/90-completion_init.zsh"
reload_file="$repo_root/packages/zsh-tools/install/.zsh_scripts/functions/zshreloadcomp.zsh"

fail() {
  print -u2 -- "not ok - $*"
  exit 1
}

tmp_root="$(mktemp -d)"
trap 'rm -rf -- "$tmp_root"' EXIT

# Our fpath is present before a later completion owner appears: do not run a
# second compinit. This models managers that defer their own initialization.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/preinit"
  mkdir -p "$HOME"
  unset _comp_setup _grz_zsh_tools_fpath_added_after_compinit
  unfunction compdef compinit 2>/dev/null || true

  source "$fpath_file"
  (( _grz_zsh_tools_fpath_added_after_compinit == 0 )) ||
    fail "pre-init fpath was incorrectly marked late"

  compdef() { :; }
  source "$completion_file"

  (( ! $+functions[compinit] )) ||
    fail "completion owner was overridden by a redundant compinit"
)

# With no completion owner, zsh-tools must initialize completion itself.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/standalone"
  mkdir -p "$HOME"
  unset _comp_setup _grz_zsh_tools_fpath_added_after_compinit
  unfunction compdef compinit 2>/dev/null || true

  source "$fpath_file"
  source "$completion_file"

  [[ -v _comp_setup ]] || fail "standalone compinit did not initialize completion"
  (( $+functions[compdef] )) || fail "standalone compinit did not define compdef"
)

# If completion was initialized before our fpath was added, one rescan must make
# a newly exposed package completion visible.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/late"
  mkdir -p "$HOME/.zsh_scripts/completion/functions"
  unset _comp_setup _grz_zsh_tools_fpath_added_after_compinit
  unfunction compdef compinit 2>/dev/null || true

  autoload -Uz compinit
  compinit -d "$HOME/preexisting.zcompdump" -i

  cat > "$HOME/.zsh_scripts/completion/functions/_grz_completion_probe" <<'EOF'
#compdef grz-completion-probe
_grz_completion_probe() { _message probe; }
_grz_completion_probe "$@"
EOF

  source "$fpath_file"
  (( _grz_zsh_tools_fpath_added_after_compinit == 1 )) ||
    fail "late fpath was not detected"

  source "$completion_file"

  [[ "${_comps[grz-completion-probe]-}" == "_grz_completion_probe" ]] ||
    fail "late package completion was not registered"
  (( _grz_zsh_tools_fpath_added_after_compinit == 0 )) ||
    fail "late-fpath state was not cleared after rescan"
)

# zshreloadcomp must clear known dump locations and start a clean Zsh process,
# not source .zshrc and call compinit again in the current process.
(
  emulate -LR zsh
  set -euo pipefail
  HOME="$tmp_root/reload-home"
  XDG_CACHE_HOME="$tmp_root/reload-cache"
  ZSH_COMPDUMP="$tmp_root/custom/zcompdump"
  export HOME XDG_CACHE_HOME ZSH_COMPDUMP

  mkdir -p "$HOME" "$XDG_CACHE_HOME/zsh" "${ZSH_COMPDUMP:h}" "$tmp_root/fake-bin"
  touch "$ZSH_COMPDUMP" "$ZSH_COMPDUMP.zwc" "$HOME/.zcompdump-old"
  touch "$XDG_CACHE_HOME/zsh/compdump" "$XDG_CACHE_HOME/zsh/compdump.zwc"

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
[[ ! -e "$tmp_root/custom/zcompdump" && ! -e "$tmp_root/custom/zcompdump.zwc" ]] ||
  fail "configured completion dump was not removed"
[[ ! -e "$tmp_root/reload-home/.zcompdump-old" ]] ||
  fail "legacy completion dump was not removed"
[[ ! -e "$tmp_root/reload-cache/zsh/compdump" && ! -e "$tmp_root/reload-cache/zsh/compdump.zwc" ]] ||
  fail "default cache completion dump was not removed"

print -- "ok - zsh completion initialization ownership"
