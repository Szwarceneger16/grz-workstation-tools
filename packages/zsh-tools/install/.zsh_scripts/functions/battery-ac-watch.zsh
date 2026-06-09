battery-ac-watch() {
  emulate -L zsh
  setopt localoptions pipefail no_aliases

  local cmd_name='battery-ac-watch'
  local cmd_root="${ZSH_SCRIPTS_ROOT:-$HOME/.zsh_scripts}"
  local help_file="$cmd_root/cmdhelp/functions/${cmd_name}.md"

  local interval='2'
  local battery_name=''
  local battery_dir=''
  local ac_dir=''
  local once='0'

  local -a batteries
  local item=''

  while (( $# )); do
    case "$1" in
      -h|--help)
        if command -v cmdhelp >/dev/null 2>&1; then
          cmdhelp "$cmd_name"
        elif [[ -r "$help_file" ]]; then
          cat "$help_file"
        else
          print -u2 -- "Brak helpa dla: $cmd_name"
        fi
        return 0
        ;;
      -i|--interval)
        shift
        if [[ -z "${1-}" ]]; then
          print -u2 -- "Brak wartości dla opcji --interval."
          return 2
        fi
        interval="$1"
        ;;
      -b|--battery)
        shift
        if [[ -z "${1-}" ]]; then
          print -u2 -- "Brak wartości dla opcji --battery."
          return 2
        fi
        battery_name="$1"
        ;;
      --once)
        once='1'
        ;;
      --)
        shift
        break
        ;;
      -*)
        print -u2 -- "Nieznana opcja: $1"
        print -u2 -- "Użyj: $cmd_name --help"
        return 2
        ;;
      *)
        print -u2 -- "Nieoczekiwany argument: $1"
        print -u2 -- "Użyj: $cmd_name --help"
        return 2
        ;;
    esac
    shift
  done

  if ! [[ "$interval" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    print -u2 -- "Nieprawidłowy interwał: $interval"
    return 2
  fi

  if [[ -n "$battery_name" ]]; then
    battery_dir="/sys/class/power_supply/$battery_name"
  else
    batteries=( /sys/class/power_supply/BAT*(N) )
    if (( ${#batteries} == 0 )); then
      print -u2 -- "Nie znaleziono baterii w /sys/class/power_supply (BAT*)."
      return 1
    fi
    battery_dir="$batteries[1]"
    battery_name="${battery_dir:t}"
  fi

  if [[ ! -d "$battery_dir" ]]; then
    print -u2 -- "Nie znaleziono katalogu baterii: $battery_dir"
    return 1
  fi

  for item in /sys/class/power_supply/*(N); do
    if [[ -r "$item/type" ]] && [[ "$(<"$item/type")" == 'Mains' ]]; then
      ac_dir="$item"
      break
    fi
  done

  local battery_status_file="$battery_dir/status"
  local capacity_file="$battery_dir/capacity"
  local current_file=''
  local now_file=''
  local full_file=''

  if [[ -r "$battery_dir/current_now" ]]; then
    current_file="$battery_dir/current_now"
  elif [[ -r "$battery_dir/power_now" ]]; then
    current_file="$battery_dir/power_now"
  fi

  if [[ -r "$battery_dir/charge_now" ]]; then
    now_file="$battery_dir/charge_now"
  elif [[ -r "$battery_dir/energy_now" ]]; then
    now_file="$battery_dir/energy_now"
  fi

  if [[ -r "$battery_dir/charge_full" ]]; then
    full_file="$battery_dir/charge_full"
  elif [[ -r "$battery_dir/energy_full" ]]; then
    full_file="$battery_dir/energy_full"
  fi

  local current_label='CURRENT_NOW'
  local now_label='CHARGE_NOW'
  local full_label='CHARGE_FULL'

  [[ "$current_file" == */power_now ]] && current_label='POWER_NOW'
  [[ "$now_file" == */energy_now ]] && now_label='ENERGY_NOW'
  [[ "$full_file" == */energy_full ]] && full_label='ENERGY_FULL'

  while true; do
    local ts battery_status capacity_value current_value now_value full_value ac_online note

    ts="$(date '+%F %T')"
    battery_status='[BRAK]'
    capacity_value='[BRAK]'
    current_value='[BRAK]'
    now_value='[BRAK]'
    full_value='[BRAK]'
    ac_online='[BRAK]'
    note=''

    [[ -r "$battery_status_file" ]] && battery_status="$(<"$battery_status_file")"
    [[ -r "$capacity_file" ]] && capacity_value="$(<"$capacity_file")"
    [[ -n "$current_file" && -r "$current_file" ]] && current_value="$(<"$current_file")"
    [[ -n "$now_file" && -r "$now_file" ]] && now_value="$(<"$now_file")"
    [[ -n "$full_file" && -r "$full_file" ]] && full_value="$(<"$full_file")"
    [[ -n "$ac_dir" && -r "$ac_dir/online" ]] && ac_online="$(<"$ac_dir/online")"

    if [[ "$ac_online" == '1' && "$battery_status" == 'Discharging' ]]; then
      note='UWAGA: bateria oddaje energię mimo podłączonego zasilacza.'
    elif [[ "$ac_online" == '1' && "$battery_status" == 'Charging' ]]; then
      note='OK: laptop jest na zasilaczu i bateria jest aktualnie ładowana.'
    elif [[ "$ac_online" == '1' && ( "$battery_status" == 'Not charging' || "$battery_status" == 'Full' || "$battery_status" == 'Unknown' ) ]]; then
      note='OK: laptop jest na zasilaczu, bateria nie jest aktywnie ładowana.'
    elif [[ "$ac_online" == '0' ]]; then
      note='Laptop pracuje bez zasilacza sieciowego.'
    fi

    if command -v clear >/dev/null 2>&1; then
      clear
    else
      print -n -- $'\e[H\e[2J'
    fi

    print -- "battery-ac-watch"
    print -- "TIME: $ts"
    print -- "BATTERY: $battery_name"
    print -- "AC_ONLINE: $ac_online"
    print -- "STATUS: $battery_status"
    print -- "${current_label}: $current_value"
    print -- "${now_label}: $now_value"
    print -- "${full_label}: $full_value"
    if [[ "$capacity_value" == '[BRAK]' ]]; then
      print -- "CAPACITY: $capacity_value"
    else
      print -- "CAPACITY: ${capacity_value}%"
    fi
    [[ -n "$note" ]] && print -- "NOTE: $note"

    if [[ "$once" == '1' ]]; then
      break
    fi

    sleep "$interval"
  done
}
