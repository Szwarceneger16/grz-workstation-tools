#!/usr/bin/env zsh
# kswapd-vmstat-summary.sh
# Różnice liczników pgscan_kswapd* / pgsteal_kswapd* z /proc/vmstat.

emulate -L zsh
setopt nounset

# wspólny bootstrap helpa z istniejącej logiki ~/.zsh_scripts/core
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
typeset -F scan_thr=${3:-256}
typeset -F steal_thr=${4:-50}

integer reports=$(( duration / interval ))
(( reports < 1 )) && reports=1

typeset -i PAGE_SIZE
PAGE_SIZE=$(getconf PAGESIZE 2>/dev/null || echo 4096)

have_counters() {
  grep -Eq '^(pgscan_kswapd(\S*)|pgsteal_kswapd(\S*))' /proc/vmstat
}

read_kswapd_counters() {
  emulate -L zsh

  local scan steal
  scan=$(awk '
    /^pgscan_kswapd[[:space:]]/ {print $2; found=1}
    END{ if(!found) exit 1 }' /proc/vmstat 2>/dev/null)
  if [[ -z "${scan}" ]]; then
    scan=$(awk '/^pgscan_kswapd_/{s+=$2}END{print s+0}' /proc/vmstat 2>/dev/null)
  fi

  steal=$(awk '
    /^pgsteal_kswapd[[:space:]]/ {print $2; found=1}
    END{ if(!found) exit 1 }' /proc/vmstat 2>/dev/null)
  if [[ -z "${steal}" ]]; then
    steal=$(awk '/^pgsteal_kswapd_/{s+=$2}END{print s+0}' /proc/vmstat 2>/dev/null)
  fi

  print -r -- "${scan:-0} ${steal:-0}"
}

to_mib() {
  emulate -L zsh
  typeset -F pps=$1
  awk -v pps="$pps" -v psz="$PAGE_SIZE" 'BEGIN{ printf("%.3f", (pps*psz)/(1024*1024)) }'
}

if ! have_counters; then
  print -r -- "Brak liczników kswapd w /proc/vmstat (pgscan_kswapd*/pgsteal_kswapd*)."
  exit 1
fi

typeset -i s0 st0 s1 st1
read s0 st0 <<<"$(read_kswapd_counters)"
sleep "$interval"

typeset -F min_scan=1e18 max_scan=0 sum_scan=0
typeset -F min_steal=1e18 max_steal=0 sum_steal=0
integer count=0 above_scan=0 above_steal=0
typeset -F eff_sum=0 eff_min=1e18 eff_max=0
integer eff_count=0

typeset -F approx_secs=$(( reports * interval ))
print -r -- "⏱  Start: interval=${interval}s, duration≈${approx_secs}s, thresholds: scan≥${scan_thr} p/s (~$(to_mib "$scan_thr") MiB/s), steal≥${steal_thr} p/s (~$(to_mib "$steal_thr") MiB/s)."

integer i
for (( i=1; i<=reports; i++ )); do
  read s1 st1 <<<"$(read_kswapd_counters)"

  typeset -i dscan=$(( s1 - s0 ))
  typeset -i dsteal=$(( st1 - st0 ))
  (( dscan < 0 )) && dscan=0
  (( dsteal < 0 )) && dsteal=0

  typeset -F scan_ps=$(( dscan / interval ))
  typeset -F steal_ps=$(( dsteal / interval ))

  (( scan_ps < min_scan )) && min_scan=$scan_ps
  (( scan_ps > max_scan )) && max_scan=$scan_ps
  sum_scan=$(( sum_scan + scan_ps ))

  (( steal_ps < min_steal )) && min_steal=$steal_ps
  (( steal_ps > max_steal )) && max_steal=$steal_ps
  sum_steal=$(( sum_steal + steal_ps ))

  (( scan_ps >= scan_thr )) && (( above_scan++ ))
  (( steal_ps >= steal_thr )) && (( above_steal++ ))

  if (( scan_ps > 0 )); then
    typeset -F eff=$(( steal_ps / scan_ps ))
    (( eff < eff_min )) && eff_min=$eff
    (( eff > eff_max )) && eff_max=$eff
    eff_sum=$(( eff_sum + eff ))
    (( eff_count++ ))
  fi

  (( count++ ))
  s0=$s1
  st0=$st1
  sleep "$interval"
done

typeset -F avg_scan=$(( sum_scan / count ))
typeset -F avg_steal=$(( sum_steal / count ))
typeset -F pct_scan=$(( 100.0 * above_scan / count ))
typeset -F pct_steal=$(( 100.0 * above_steal / count ))
typeset -F total_secs=$(( count * interval ))
typeset -F avg_eff=0
(( eff_count > 0 )) && avg_eff=$(( eff_sum / eff_count ))

print
print -r -- "Samples: $count  (≈${total_secs}s)   PAGE_SIZE=${PAGE_SIZE}B"
printf "SCAN  pages/s:  min=%.2f  avg=%.2f  max=%.2f   |  MiB/s: min=%s  avg=%s  max=%s\n" \
  "$min_scan" "$avg_scan" "$max_scan" \
  "$(to_mib "$min_scan")" "$(to_mib "$avg_scan")" "$(to_mib "$max_scan")"

printf "STEAL pages/s:  min=%.2f  avg=%.2f  max=%.2f   |  MiB/s: min=%s  avg=%s  max=%s\n" \
  "$min_steal" "$avg_steal" "$max_steal" \
  "$(to_mib "$min_steal")" "$(to_mib "$avg_steal")" "$(to_mib "$max_steal")"

printf "Time ≥ thresholds:  scan(≥%s p/s)=%.2f%%   steal(≥%s p/s)=%.2f%%\n" \
  "$scan_thr" "$pct_scan" "$steal_thr" "$pct_steal"

if (( eff_count > 0 )); then
  printf "Reclaim efficiency (steal/scan):  samples=%d  min=%.2f  avg=%.2f  max=%.2f\n" \
    "$eff_count" "$eff_min" "$avg_eff" "$eff_max"
else
  print -r -- "Reclaim efficiency (steal/scan): brak próbek z scan > 0"
fi
