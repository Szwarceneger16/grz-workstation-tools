#!/usr/bin/env zsh
emulate -L zsh
set -euo pipefail

script_name="${0:t}"
repo_root="${0:A:h}"
stow_dir="$repo_root/stow"
ignore_all_file="$repo_root/manifests/ignore-all-install.txt"
target="${GRZ_STOW_TARGET:-${STOW_TARGET:-$HOME}}"
run_sudo_cleanup=0

finish_run_sudo_session() {
  (( run_sudo_cleanup )) || return 0
  command -v sudo >/dev/null 2>&1 || return 0
  sudo -k
  run_sudo_cleanup=0
  return 0
}

trap finish_run_sudo_session EXIT

usage() {
  print -u2 -- "usage: $script_name install [--verbose] [--verify] [--test] all|all-user|all-system|<package>"
  print -u2 -- "       $script_name uninstall [--verbose] all|all-user|all-system|<package>"
  print -u2 -- "       $script_name activate all|all-user|all-system|<package>"
  print -u2 -- "       $script_name verify all|all-user|all-system|<package>"
  print -u2 -- "       $script_name test all|all-user|all-system|<package>"
}

die() {
  print -u2 -- "$script_name: $*"
  exit 1
}

validate_package_name() {
  local package="$1"
  [[ "$package" =~ '^[A-Za-z0-9._-]+$' ]] || die "invalid package name: $package"
}

package_has_user_install() {
  local package="$1"
  [[ -e "$stow_dir/$package" && -d "$repo_root/packages/$package/install" ]]
}

package_has_system_install() {
  local package="$1"
  [[ -d "$repo_root/packages/$package/system-install" ]]
}

validate_any_package() {
  local package="$1"
  validate_package_name "$package"
  package_has_user_install "$package" || package_has_system_install "$package" || die "unknown package: $package"
}

load_ignored_packages() {
  local line package
  typeset -gA ignored_packages
  ignored_packages=()

  [[ -f "$ignore_all_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    package="$line"
    validate_any_package "$package"
    ignored_packages[$package]=1
  done < "$ignore_all_file"
}

select_user_packages() {
  local selector="$1"
  local package_path package
  typeset -ga selected_user_packages
  selected_user_packages=()

  case "$selector" in
    all|all-user)
      load_ignored_packages
      for package_path in "$stow_dir"/*(N); do
        package="${package_path:t}"
        [[ "$selector" == "all" && -n "${ignored_packages[$package]-}" ]] && continue
        selected_user_packages+=("$package")
      done
      [[ "$selector" == "all-user" ]] &&
        { (( ${#selected_user_packages[@]} > 0 )) || die "no user packages selected from: $stow_dir"; }
      ;;
    all-system)
      ;;
    *)
      validate_any_package "$selector"
      if package_has_user_install "$selector"; then
        selected_user_packages=("$selector")
      fi
      ;;
  esac
}

select_system_packages() {
  local selector="$1"
  local package_path package
  typeset -ga selected_system_packages
  selected_system_packages=()

  case "$selector" in
    all|all-system)
      load_ignored_packages
      for package_path in "$repo_root"/packages/*/system-install(N/); do
        package="${package_path:h:t}"
        [[ "$selector" == "all" && -n "${ignored_packages[$package]-}" ]] && continue
        selected_system_packages+=("$package")
      done
      if [[ "$selector" == "all-system" ]]; then
        (( ${#selected_system_packages[@]} > 0 )) || die "no system packages selected from: $repo_root/packages"
      fi
      ;;
    all-user)
      ;;
    *)
      validate_any_package "$selector"
      if package_has_system_install "$selector"; then
        selected_system_packages=("$selector")
      fi
      ;;
  esac
}

is_install_meta_file() {
  local rel_path="$1"

  case "$rel_path" in
    .gitkeep|*/.gitkeep|.stow-local-ignore|*/.stow-local-ignore)
      return 0
      ;;
  esac

  return 1
}

verify_stow_link() {
  local source="$1"
  local dest="$2"
  local rel_path="$3"
  local resolved_dest resolved_source

  if [[ ! -e "$dest" && ! -L "$dest" ]]; then
    print -u2 -- "not ok - missing installed path: $rel_path -> $dest"
    return 1
  fi

  if [[ ! -L "$dest" ]]; then
    print -u2 -- "not ok - installed path is not a symlink: $rel_path -> $dest"
    return 1
  fi

  resolved_dest="$(readlink -f -- "$dest" 2>/dev/null)" || {
    print -u2 -- "not ok - cannot resolve installed symlink: $rel_path -> $dest"
    return 1
  }
  resolved_source="$(readlink -f -- "$source" 2>/dev/null)" || {
    print -u2 -- "not ok - cannot resolve package source: $rel_path -> $source"
    return 1
  }

  if [[ "$resolved_dest" != "$resolved_source" ]]; then
    print -u2 -- "not ok - installed symlink points elsewhere: $rel_path"
    print -u2 -- "         expected: $resolved_source"
    print -u2 -- "         actual:   $resolved_dest"
    return 1
  fi
}

system_verify_sudo_active=0

ensure_system_verify_sudo() {
  (( system_verify_sudo_active )) && return 0
  command -v sudo >/dev/null 2>&1 || {
    print -u2 -- "not ok - sudo is required to compare unreadable system files"
    return 1
  }

  print -- "Verifying unreadable root-owned system file content with sudo"
  if (( run_sudo_cleanup )); then
    sudo -n -v || {
      print -u2 -- "not ok - sudo timestamp expired before system verification"
      return 1
    }
  else
    sudo -v || return 1
  fi
  system_verify_sudo_active=1
}

finish_system_verify_sudo() {
  (( system_verify_sudo_active )) || return 0
  sudo -k
  system_verify_sudo_active=0
  return 0
}

compare_system_content() {
  local source="$1"
  local dest="$2"

  if [[ -r "$dest" ]]; then
    cmp -s -- "$source" "$dest"
    return $?
  fi

  ensure_system_verify_sudo || return 2
  sudo -n cmp -s -- "$source" "$dest"
}

verify_user_package() {
  local package="$1"
  local install_dir="$repo_root/packages/$package/install"
  local source rel_path dest hook
  local failures=0
  typeset -a sources

  [[ -d "$target" ]] || die "target directory does not exist: $target"

  print -- "Verifying user package: $package"
  sources=("$install_dir"/**/*(DN.) "$install_dir"/**/*(DN@))

  for source in "${sources[@]}"; do
    rel_path="${source#$install_dir/}"
    is_install_meta_file "$rel_path" && continue
    dest="$target/$rel_path"
    verify_stow_link "$source" "$dest" "$rel_path" || failures=$(( failures + 1 ))
  done

  if (( failures > 0 )); then
    print -u2 -- "not ok - $package has $failures stow verification failure(s)"
    return 1
  fi

  hook="$repo_root/packages/$package/verify.hook.sh"
  if [[ -f "$hook" ]]; then
    [[ -x "$hook" ]] || die "verify hook is not executable: $hook"
    GRZ_REPO_ROOT="$repo_root" GRZ_PACKAGE="$package" STOW_TARGET="$target" "$hook"
  fi

  print -- "ok - user package verified: $package"
}

verify_system_file() {
  local source="$1"
  local rel_path="$2"
  local expected_mode="$3"
  local expected_owner="$4"
  local expected_group="$5"
  local dest="/$rel_path"
  local actual_mode actual_owner actual_group owner_group
  local owner_stat_format="%U" group_stat_format="%G"
  local cmp_status=0
  typeset -a _sudo=()

  if [[ ! -e "$dest" && ! -L "$dest" ]]; then
    ensure_system_verify_sudo || return 2
    sudo -n stat -- "$dest" >/dev/null 2>&1 || {
      print -u2 -- "not ok - missing system path: $dest"
      return 1
    }
    _sudo=(sudo -n)
  fi

  if (( ${#_sudo[@]} > 0 )); then
    local dest_type
    dest_type="$("${_sudo[@]}" stat -c '%F' -- "$dest" 2>/dev/null)" || {
      print -u2 -- "not ok - cannot stat system path: $dest"
      return 1
    }
    [[ "$dest_type" == "regular file" ]] || {
      print -u2 -- "not ok - system path is not a regular file: $dest"
      return 1
    }
  elif [[ ! -f "$dest" || -L "$dest" ]]; then
    print -u2 -- "not ok - system path is not a regular file: $dest"
    return 1
  fi

  if [[ "$expected_owner" =~ '^[0-9]+$' ]]; then
    owner_stat_format="%u"
  fi
  if [[ "$expected_group" =~ '^[0-9]+$' ]]; then
    group_stat_format="%g"
  fi

  actual_owner="$("${_sudo[@]}" stat -c "$owner_stat_format" -- "$dest" 2>/dev/null)" || {
    print -u2 -- "not ok - cannot stat owner/group: $dest"
    return 1
  }
  actual_group="$("${_sudo[@]}" stat -c "$group_stat_format" -- "$dest" 2>/dev/null)" || {
    print -u2 -- "not ok - cannot stat owner/group: $dest"
    return 1
  }
  owner_group="$actual_owner:$actual_group"
  if [[ "$owner_group" != "$expected_owner:$expected_group" ]]; then
    print -u2 -- "not ok - system path owner/group mismatch: $dest"
    print -u2 -- "         expected: $expected_owner:$expected_group"
    print -u2 -- "         actual:   $owner_group"
    return 1
  fi

  actual_mode="$("${_sudo[@]}" stat -c '%a' -- "$dest" 2>/dev/null)" || {
    print -u2 -- "not ok - cannot stat system mode: $dest"
    return 1
  }
  if [[ "$actual_mode" != "$expected_mode" ]]; then
    print -u2 -- "not ok - system path mode mismatch: $dest"
    print -u2 -- "         expected: $expected_mode"
    print -u2 -- "         actual:   $actual_mode"
    return 1
  fi

  compare_system_content "$source" "$dest" || cmp_status=$?
  case "$cmp_status" in
    0)
      ;;
    1)
      print -u2 -- "not ok - system path content differs from repo: $dest"
      return 1
      ;;
    *)
      print -u2 -- "not ok - cannot compare system path content: $dest"
      return 1
      ;;
  esac
}

normalize_mode() {
  local mode="$1"

  [[ "$mode" =~ '^[0-7]{3,4}$' ]] || return 1
  while [[ ${#mode} -gt 1 && "$mode" == 0* ]]; do
    mode="${mode#0}"
  done
  print -- "$mode"
}

load_system_target_metadata() {
  local package="$1"
  local install_dir="$repo_root/packages/$package/system-install"
  local manifest="$repo_root/packages/$package/system-install.manifest"
  local line rel_path mode owner group extra normalized_mode
  local line_no=0
  typeset -gA target_modes target_owners target_groups
  target_modes=()
  target_owners=()
  target_groups=()

  [[ -f "$manifest" ]] || die "missing system install manifest: $manifest"

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_no=$(( line_no + 1 ))
    [[ -z "$line" || "$line" == \#* ]] && continue

    rel_path=""
    mode=""
    owner=""
    group=""
    extra=""
    read -r rel_path mode owner group extra <<< "$line"

    [[ -n "$rel_path" && -n "$mode" && -n "$owner" && -n "$group" && -z "$extra" ]] ||
      die "invalid manifest line $manifest:$line_no"
    [[ "$rel_path" != /* && "$rel_path" != *../* && "$rel_path" != ../* && "$rel_path" != *.. ]] ||
      die "invalid manifest path $manifest:$line_no: $rel_path"
    [[ "$owner" =~ '^[A-Za-z_][A-Za-z0-9_-]*$|^[0-9]+$' ]] ||
      die "invalid manifest owner $manifest:$line_no: $owner"
    [[ "$group" =~ '^[A-Za-z_][A-Za-z0-9_-]*$|^[0-9]+$' ]] ||
      die "invalid manifest group $manifest:$line_no: $group"
    normalized_mode="$(normalize_mode "$mode")" ||
      die "invalid manifest mode $manifest:$line_no: $mode"
    [[ -z "${target_modes[$rel_path]-}" ]] ||
      die "duplicate manifest path $manifest:$line_no: $rel_path"
    [[ -f "$install_dir/$rel_path" ]] ||
      die "manifest path has no repo file $manifest:$line_no: $rel_path"

    target_modes[$rel_path]="$normalized_mode"
    target_owners[$rel_path]="$owner"
    target_groups[$rel_path]="$group"
  done < "$manifest"
}

run_user_activate_hook() {
  local package="$1"
  local hook="$repo_root/packages/$package/user-activate.hook.sh"
  [[ -f "$hook" ]] || return 0
  [[ -x "$hook" ]] || die "user-activate hook is not executable: $hook"
  if [[ "$target" != "$HOME" ]]; then
    print -- "Skipping user-activate hook for $package because STOW_TARGET is not HOME: $target"
    return 0
  fi
  GRZ_REPO_ROOT="$repo_root" GRZ_PACKAGE="$package" STOW_TARGET="$target" "$hook"
}

run_user_deactivate_hook() {
  local package="$1"
  local hook="$repo_root/packages/$package/user-deactivate.hook.sh"
  [[ -f "$hook" ]] || return 0
  [[ -x "$hook" ]] || die "user-deactivate hook is not executable: $hook"
  if [[ "$target" != "$HOME" ]]; then
    print -- "Skipping user-deactivate hook for $package because STOW_TARGET is not HOME: $target"
    return 0
  fi
  GRZ_REPO_ROOT="$repo_root" GRZ_PACKAGE="$package" STOW_TARGET="$target" "$hook"
}

load_system_config_metadata() {
  local package="$1"
  local manifest="$repo_root/packages/$package/system-config.manifest"
  local line rel_path mode owner group extra normalized_mode
  local line_no=0
  typeset -gA config_modes config_owners config_groups
  config_modes=()
  config_owners=()
  config_groups=()

  [[ -f "$manifest" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_no=$(( line_no + 1 ))
    [[ -z "$line" || "$line" == \#* ]] && continue

    rel_path=""
    mode=""
    owner=""
    group=""
    extra=""
    read -r rel_path mode owner group extra <<< "$line"

    [[ -n "$rel_path" && -n "$mode" && -n "$owner" && -n "$group" && -z "$extra" ]] ||
      die "invalid system-config manifest line $manifest:$line_no"
    [[ "$rel_path" != /* && "$rel_path" != *../* && "$rel_path" != ../* && "$rel_path" != *.. ]] ||
      die "invalid system-config manifest path $manifest:$line_no: $rel_path"
    normalized_mode="$(normalize_mode "$mode")" ||
      die "invalid system-config manifest mode $manifest:$line_no: $mode"
    [[ -z "${config_modes[$rel_path]-}" ]] ||
      die "duplicate system-config manifest path $manifest:$line_no: $rel_path"

    config_modes[$rel_path]="$normalized_mode"
    config_owners[$rel_path]="$owner"
    config_groups[$rel_path]="$group"
  done < "$manifest"
}

load_system_units_metadata() {
  local package="$1"
  local manifest="$repo_root/packages/$package/system-units.manifest"
  local line unit extra
  local line_no=0
  typeset -ga system_units
  system_units=()

  [[ -f "$manifest" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_no=$(( line_no + 1 ))
    [[ -z "$line" || "$line" == \#* ]] && continue
    unit=""
    extra=""
    read -r unit extra <<< "$line"
    [[ -n "$unit" && -z "$extra" ]] ||
      die "invalid system-units manifest line $manifest:$line_no"
    [[ "$unit" != */* ]] ||
      die "system-units manifest must list unit names, not paths $manifest:$line_no: $unit"
    case "$unit" in
      *.service|*.timer|*.path|*.socket|*.mount|*.target) ;;
      *) die "unsupported unit type in system-units manifest $manifest:$line_no: $unit" ;;
    esac
    system_units+=("$unit")
  done < "$manifest"
}

verify_system_config_paths() {
  local package="$1"
  local rel_path dest uid mode
  local failures=0

  load_system_config_metadata "$package"
  (( ${#config_modes[@]} > 0 )) || return 0

  ensure_system_verify_sudo || return 1

  for rel_path in "${(@k)config_modes}"; do
    dest="/$rel_path"

    if ! sudo -n test -e "$dest" && ! sudo -n test -L "$dest"; then
      print -u2 -- "not ok - missing required config path: $dest"
      failures=$(( failures + 1 ))
      continue
    fi
    if ! sudo -n test -f "$dest" || sudo -n test -L "$dest"; then
      print -u2 -- "not ok - config path is not a regular file: $dest"
      failures=$(( failures + 1 ))
      continue
    fi
    uid="$(sudo -n stat -c '%u' -- "$dest" 2>/dev/null)" || {
      print -u2 -- "not ok - cannot stat config owner: $dest"
      failures=$(( failures + 1 ))
      continue
    }
    mode="$(sudo -n stat -c '%a' -- "$dest" 2>/dev/null)" || {
      print -u2 -- "not ok - cannot stat config mode: $dest"
      failures=$(( failures + 1 ))
      continue
    }
    if [[ "$uid" != "0" ]]; then
      print -u2 -- "not ok - config path must be owned by root: $dest"
      failures=$(( failures + 1 ))
      continue
    fi
    if (( (8#$mode & 8#077) != 0 )); then
      print -u2 -- "not ok - config path must be root-only, for example mode 0600: $dest"
      failures=$(( failures + 1 ))
      continue
    fi
    print -- "ok - required root-only config path exists: $dest"
  done

  (( failures == 0 )) || return 1
}

verify_system_live_units() {
  local package="$1"
  local unit unit_path
  local failures=0
  typeset -a unit_paths
  unit_paths=()

  load_system_units_metadata "$package"
  (( ${#system_units[@]} > 0 )) || return 0

  for unit in "${system_units[@]}"; do
    unit_path="/etc/systemd/system/$unit"
    if [[ ! -f "$unit_path" || -L "$unit_path" ]]; then
      print -u2 -- "not ok - missing live systemd unit for verification: $unit_path"
      failures=$(( failures + 1 ))
      continue
    fi
    unit_paths+=("$unit_path")
  done

  (( failures == 0 )) || return 1

  command -v systemd-analyze >/dev/null 2>&1 || {
    print -u2 -- "warn - systemd-analyze is unavailable; skipped live systemd verification for $package"
    return 0
  }

  ensure_system_verify_sudo || return 1
  print -- "Verifying live systemd units for $package with sudo"
  sudo -n systemd-analyze verify "${unit_paths[@]}" || {
    print -u2 -- "not ok - live systemd unit verification failed: $package"
    return 1
  }
}

verify_system_package() {
  local package="$1"
  local verify_context="${2:-standalone}"
  local _keep_sudo="${3:-0}"
  local install_dir="$repo_root/packages/$package/system-install"
  local source rel_path
  local failures=0
  typeset -a sources

  print -- "Verifying system package: $package"
  load_system_target_metadata "$package"
  sources=("$install_dir"/**/*(DN.))

  for source in "${sources[@]}"; do
    rel_path="${source#$install_dir/}"
    is_install_meta_file "$rel_path" && continue
    if [[ -z "${target_modes[$rel_path]-}" ]]; then
      print -u2 -- "not ok - missing manifest entry for system file: $package $rel_path"
      failures=$(( failures + 1 ))
      continue
    fi
    verify_system_file "$source" "$rel_path" "${target_modes[$rel_path]}" "${target_owners[$rel_path]}" "${target_groups[$rel_path]}" ||
      failures=$(( failures + 1 ))
  done

  verify_system_config_paths "$package" || failures=$(( failures + 1 ))
  verify_system_live_units "$package" || failures=$(( failures + 1 ))

  if (( failures > 0 )); then
    (( _keep_sudo )) || finish_system_verify_sudo
    print -u2 -- "not ok - $package has $failures system verification failure(s)"
    return 1
  fi

  (( _keep_sudo )) || finish_system_verify_sudo
  print -- "ok - system package verified: $package"
}

test_repo_systemd_execstart() {
  local package="$1"
  local unit_source="$2"
  local install_dir="$repo_root/packages/$package/system-install"
  local line command rel_path executable_source mode
  local failures=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" == ExecStart=* ]] || continue
    command="${line#ExecStart=}"
    command="${command%%[[:space:]]*}"
    while [[ "$command" == [-+!:@]* ]]; do
      command="${command[2,-1]}"
    done

    if [[ "$command" != /* ]]; then
      print -u2 -- "not ok - repo unit ExecStart is not absolute: ${unit_source#$install_dir/}: $line"
      failures=$(( failures + 1 ))
      continue
    fi

    rel_path="${command#/}"
    executable_source="$install_dir/$rel_path"
    if [[ ! -f "$executable_source" ]]; then
      if [[ -f "$command" ]]; then
        continue
      fi
      print -u2 -- "not ok - repo unit ExecStart target missing from package and not found on system: ${unit_source#$install_dir/}: $command"
      failures=$(( failures + 1 ))
      continue
    fi

    mode="${target_modes[$rel_path]-}"
    if [[ -z "$mode" ]]; then
      print -u2 -- "not ok - repo unit ExecStart target missing manifest entry: $package $rel_path"
      failures=$(( failures + 1 ))
      continue
    fi

    if (( (8#$mode & 8#111) == 0 )); then
      print -u2 -- "not ok - repo unit ExecStart target is not executable by manifest mode: $package $rel_path $mode"
      failures=$(( failures + 1 ))
    fi
  done < "$unit_source"

  return "$failures"
}

test_repo_systemd_timer_unit() {
  local package="$1"
  local unit_source="$2"
  local install_dir="$repo_root/packages/$package/system-install"
  local line unit_ref
  local failures=0
  local found_unit=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" == Unit=* ]] || continue
    found_unit=1
    unit_ref="${line#Unit=}"
    if [[ "$unit_ref" == */* ]]; then
      print -u2 -- "not ok - repo timer Unit must be a unit name, not a path: ${unit_source#$install_dir/}: $line"
      failures=$(( failures + 1 ))
      continue
    fi
    if [[ ! -f "$install_dir/etc/systemd/system/$unit_ref" ]]; then
      print -u2 -- "not ok - repo timer Unit target missing from package: ${unit_source#$install_dir/}: $unit_ref"
      failures=$(( failures + 1 ))
    fi
  done < "$unit_source"

  if (( !found_unit )); then
    local default_service="${${unit_source:t}%.timer}.service"
    if [[ ! -f "$install_dir/etc/systemd/system/$default_service" ]]; then
      print -u2 -- "not ok - repo timer has no Unit= and default service is missing from package: ${unit_source#$install_dir/}: $default_service"
      failures=$(( failures + 1 ))
    fi
  fi

  return "$failures"
}

test_repo_systemd_units() {
  local package="$1"
  local install_dir="$repo_root/packages/$package/system-install"
  local unit_source rel_path
  local failures=0
  typeset -a unit_sources

  unit_sources=("$install_dir"/etc/systemd/system/*(N.))
  (( ${#unit_sources[@]} > 0 )) || return 0

  for unit_source in "${unit_sources[@]}"; do
    rel_path="${unit_source#$install_dir/}"
    [[ -n "${target_modes[$rel_path]-}" ]] || {
      print -u2 -- "not ok - repo systemd unit missing manifest entry: $package $rel_path"
      failures=$(( failures + 1 ))
      continue
    }

    case "$unit_source" in
      *.service)
        test_repo_systemd_execstart "$package" "$unit_source" || failures=$(( failures + $? ))
        ;;
      *.timer)
        test_repo_systemd_timer_unit "$package" "$unit_source" || failures=$(( failures + $? ))
        ;;
    esac
  done

  return "$failures"
}

test_system_package() {
  local package="$1"
  local install_dir="$repo_root/packages/$package/system-install"
  local source rel_path
  local failures=0
  typeset -a sources

  print -- "Testing system package repo files: $package"
  load_system_target_metadata "$package"
  sources=("$install_dir"/**/*(DN.))

  for source in "${sources[@]}"; do
    rel_path="${source#$install_dir/}"
    is_install_meta_file "$rel_path" && continue
    if [[ -z "${target_modes[$rel_path]-}" ]]; then
      print -u2 -- "not ok - missing manifest entry for repo system file: $package $rel_path"
      failures=$(( failures + 1 ))
    fi
  done

  test_repo_systemd_units "$package" || failures=$(( failures + $? ))

  if (( failures > 0 )); then
    print -u2 -- "not ok - $package has $failures repo system test failure(s)"
    return 1
  fi

  print -- "ok - system package repo files tested: $package"
}

run_verify() {
  local selector="$1"
  local verify_context="${2:-standalone}"
  local package

  select_user_packages "$selector"
  select_system_packages "$selector"

  (( ${#selected_user_packages[@]} > 0 || ${#selected_system_packages[@]} > 0 )) || die "no packages selected for: $selector"

  for package in "${selected_user_packages[@]}"; do
    verify_user_package "$package"
  done

  for package in "${selected_system_packages[@]}"; do
    verify_system_package "$package" "$verify_context" 1 || { finish_system_verify_sudo; return 1; }
  done
  finish_system_verify_sudo
}

run_tests_for_user_package() {
  local package="$1"
  local test_file
  typeset -a tests

  verify_user_package "$package"

  tests=("$repo_root/packages/$package/tests"/*.sh(N))
  if (( ${#tests[@]} == 0 )); then
    print -- "ok - no tests for $package"
    return 0
  fi

  for test_file in "${tests[@]}"; do
    [[ -x "$test_file" ]] || die "test is not executable: $test_file"
    print -- "Testing: $package ${test_file:t}"
    GRZ_REPO_ROOT="$repo_root" GRZ_PACKAGE="$package" STOW_TARGET="$target" "$test_file"
  done
}

run_test() {
  local selector="$1"
  local package

  select_user_packages "$selector"
  select_system_packages "$selector"

  (( ${#selected_user_packages[@]} > 0 || ${#selected_system_packages[@]} > 0 )) || die "no packages selected for: $selector"

  for package in "${selected_user_packages[@]}"; do
    run_tests_for_user_package "$package"
  done

  for package in "${selected_system_packages[@]}"; do
    test_system_package "$package"
  done
}

selector_stow_arg() {
  local selector="$1"
  case "$selector" in
    all) print -- "all" ;;
    all-user) print -- "all-user" ;;
    *) print -- "$selector" ;;
  esac
}

selector_system_arg() {
  local selector="$1"
  case "$selector" in
    all) print -- "all" ;;
    all-system) print -- "all-system" ;;
    *) print -- "$selector" ;;
  esac
}

run_stow_action() {
  local action="$1"
  local selector="$2"
  local verbose="$3"
  local stow_selector

  select_user_packages "$selector"
  (( ${#selected_user_packages[@]} > 0 )) || return 0

  [[ -d "$target" ]] || die "target directory does not exist: $target"
  stow_selector="$(selector_stow_arg "$selector")"

  if (( verbose )); then
    STOW_TARGET="$target" "$repo_root/scripts/stow-select" "$action" --verbose -- "$stow_selector"
  else
    STOW_TARGET="$target" "$repo_root/scripts/stow-select" "$action" -- "$stow_selector"
  fi
}

run_system_action() {
  local action="$1"
  local selector="$2"
  local verbose="$3"
  local system_selector

  select_system_packages "$selector"
  (( ${#selected_system_packages[@]} > 0 )) || return 0

  system_selector="$(selector_system_arg "$selector")"

  if (( verbose )); then
    run_sudo_cleanup=1
    GRZ_KEEP_SUDO_SESSION=1 "$repo_root/scripts/system-copy-select" "$action" --verbose -- "$system_selector"
  else
    run_sudo_cleanup=1
    GRZ_KEEP_SUDO_SESSION=1 "$repo_root/scripts/system-copy-select" "$action" -- "$system_selector"
  fi
}

run_system_activation() {
  local selector="$1"
  local system_selector

  select_system_packages "$selector"
  (( ${#selected_system_packages[@]} > 0 )) || return 0

  system_selector="$(selector_system_arg "$selector")"
  run_sudo_cleanup=1
  GRZ_KEEP_SUDO_SESSION=1 "$repo_root/scripts/system-copy-select" activate -- "$system_selector"
}

parse_install() {
  local selector=""
  local verbose=0
  local do_verify=0
  local do_test=0

  while (( $# > 0 )); do
    case "$1" in
      --verbose|-v)
        verbose=1
        ;;
      --verify)
        do_verify=1
        ;;
      --test)
        do_test=1
        ;;
      --)
        shift
        (( $# == 1 )) || {
          usage
          exit 64
        }
        [[ -z "$selector" ]] || {
          usage
          exit 64
        }
        selector="$1"
        ;;
      -*)
        die "unknown install option: $1"
        ;;
      *)
        [[ -z "$selector" ]] || {
          usage
          exit 64
        }
        selector="$1"
        ;;
    esac
    shift
  done

  [[ -n "$selector" ]] || {
    usage
    exit 64
  }

  run_stow_action install "$selector" "$verbose"
  run_system_action install "$selector" "$verbose"

  if (( do_verify )); then
    run_verify "$selector" install
  fi
  if (( do_test )); then
    run_test "$selector"
  fi
}

parse_activate() {
  local selector=""
  local package

  while (( $# > 0 )); do
    case "$1" in
      --)
        shift
        (( $# == 1 )) || {
          usage
          exit 64
        }
        [[ -z "$selector" ]] || {
          usage
          exit 64
        }
        selector="$1"
        ;;
      -*)
        die "unknown activate option: $1"
        ;;
      *)
        [[ -z "$selector" ]] || {
          usage
          exit 64
        }
        selector="$1"
        ;;
    esac
    shift
  done

  [[ -n "$selector" ]] || {
    usage
    exit 64
  }

  case "$selector" in
    all|all-user|all-system) ;;
    *) validate_any_package "$selector" ;;
  esac

  run_system_activation "$selector"

  select_user_packages "$selector"
  for package in "${selected_user_packages[@]}"; do
    run_user_activate_hook "$package"
  done
}

parse_uninstall() {
  local selector=""
  local verbose=0
  local package

  while (( $# > 0 )); do
    case "$1" in
      --verbose|-v)
        verbose=1
        ;;
      --)
        shift
        (( $# == 1 )) || {
          usage
          exit 64
        }
        [[ -z "$selector" ]] || {
          usage
          exit 64
        }
        selector="$1"
        ;;
      -*)
        die "unknown uninstall option: $1"
        ;;
      *)
        [[ -z "$selector" ]] || {
          usage
          exit 64
        }
        selector="$1"
        ;;
    esac
    shift
  done

  [[ -n "$selector" ]] || {
    usage
    exit 64
  }

  select_user_packages "$selector"
  for package in "${selected_user_packages[@]}"; do
    run_user_deactivate_hook "$package"
  done
  run_system_action uninstall "$selector" "$verbose"
  run_stow_action uninstall "$selector" "$verbose"
}

command -v readlink >/dev/null 2>&1 || die "readlink is required"
[[ -d "$stow_dir" ]] || die "missing stow directory: $stow_dir"

(( $# >= 2 )) || {
  usage
  exit 64
}

action="$1"
shift

case "$action" in
  install)
    parse_install "$@"
    ;;
  uninstall)
    parse_uninstall "$@"
    ;;
  activate)
    parse_activate "$@"
    ;;
  verify)
    (( $# == 1 )) || {
      usage
      exit 64
    }
    run_verify "$1"
    ;;
  test)
    (( $# == 1 )) || {
      usage
      exit 64
    }
    run_test "$1"
    ;;
  *)
    usage
    exit 64
    ;;
esac
