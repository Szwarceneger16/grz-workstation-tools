#!/usr/bin/env zsh
# kswapd-summary.sh
# CPU% wątków kswapd* (pidstat) – min/avg/max i % próbek ≥ progu.

emulate -L zsh
setopt nounset

# wspólny bootstrap helpa z istniejącej logiki ~/.zsh_scripts/core
typeset -gr _SELF_CMD_NAME="${0:t}"

_show_self_help() {
  emulate -L zsh

  : "${ZSH_SCRIPTS_ROOT:=$HOME/.zsh_scripts}"

  local help_render="$ZSH_SCRIPTS_ROOT/core/10-help_render.zsh"
  local cmdhelp_core="$ZSH_SCRIPTS_ROOT/core/11-cmdhelp.zsh"

  if [[ ! -r "$help_render" || ! -r "$cmdhelp_core" ]]; then
    print -u2 -- "ERR: brak plików core helpa:"
    print -u2 -- "ERR: $help_render"
    print -u2 -- "ERR: $cmdhelp_core"
    return 1
  fi

  source "$help_render" || return 1
  source "$cmdhelp_core" || return 1

  cmdhelp "$_SELF_CMD_NAME" bin
}

case "${1-}" in
  -h|--help|help)
    _show_self_help
    exit $?
    ;;
esac

typeset -F interval=${1:-1}
typeset -F duration=${2:-300}
typeset -F threshold=${3:-1}

integer reports=$(( duration / interval ))
(( reports < 1 )) && reports=1

typeset -F approx_secs=$(( reports * interval ))

if ! command -v pidstat >/dev/null 2>&1; then
  print -r -- "Brak 'pidstat'. Zainstaluj: sudo apt install -y sysstat"
  exit 1
fi

print -r -- "⏱  Start: interval=${interval}s, duration≈${approx_secs}s, threshold≥${threshold}%"

LC_ALL=C sudo -n true 2>/dev/null || true
LC_ALL=C sudo -n pidstat -u -t -p ALL "${interval}" "${reports}" 2>/dev/null \
| awk -v thr="$threshold" -v intv="$interval" '
  BEGIN{
    cpu_col=0; cur_ts=""; cur_sum=0;
    min=1e9; max=0; sum=0; n=0; above=0;
  }
  /%CPU/ && cpu_col==0 {
    for(i=1;i<=NF;i++) if($i=="%CPU") cpu_col=i;
    next
  }
  /^#|^Linux|^Average:/ { next }

  /^[0-9]{2}:[0-9]{2}:[0-9]{2}/ {
    ts=$1
    if (cur_ts!="" && ts!=cur_ts) {
      if (cur_sum<min) min=cur_sum;
      if (cur_sum>max) max=cur_sum;
      sum+=cur_sum; n++;
      if (cur_sum >= thr) above++;
      cur_sum=0;
    }
    cur_ts=ts
    if ($0 ~ /kswapd/) {
      if (cpu_col>0 && cpu_col<=NF) {
        gsub(/,/, ".", $cpu_col)
        cur_sum+=($cpu_col+0)
      }
    }
    next
  }
  END{
    if (cur_ts!="") {
      if (cur_sum<min) min=cur_sum;
      if (cur_sum>max) max=cur_sum;
      sum+=cur_sum; n++;
      if (cur_sum >= thr) above++;
    }
    if (n==0) { print "Brak próbek."; exit 0 }
    avg = sum / n
    pct = (above*100.0)/n
    dur = n*intv
    printf("Samples: %d (≈%.0fs)\n", n, dur)
    printf("kswapd CPU total (%% of one core): min=%.2f  avg=%.2f  max=%.2f\n", min, avg, max)
    printf("Time ≥ %.2f%%: %.2f%% of samples\n", thr, pct)
  }
'
