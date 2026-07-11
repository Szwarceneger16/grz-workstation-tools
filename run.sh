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

stow_target_is_home() {
  [[ "${target:A}" == "${HOME:A}" ]]
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

  verify_user_live_units "$package" || return 1

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

load_user_units_metadata() {
  local package="$1"
  local manifest="$repo_root/packages/$package/user-units.manifest"
  local line unit extra
  local line_no=0
  typeset -ga user_units
  user_units=()

  [[ -f "$manifest" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_no=$(( line_no + 1 ))
    [[ -z "$line" || "$line" == \#* ]] && continue
    unit=""
    extra=""
    read -r unit extra <<< "$line"

    [[ -n "$unit" && -z "$extra" ]] ||
      die "invalid user-units manifest line $manifest:$line_no"
    [[ "$unit" != */* ]] ||
      die "user-units manifest must list unit names, not paths $manifest:$line_no: $unit"
    [[ "$unit" != -* ]] ||
      die "user-units manifest unit must not start with '-': $manifest:$line_no: $unit"

    case "$unit" in
      *.service|*.timer|*.path|*.socket|*.target) ;;
      *) die "unsupported unit type in user-units manifest $manifest:$line_no: $unit" ;;
    esac

    if is_template_unit_name "$unit" && [[ "$unit" != *.service ]]; then
      die "user-units manifest must list concrete template instances, not template units $manifest:$line_no: $unit"
    fi

    user_units+=("$unit")
  done < "$manifest"
}

is_template_unit_name() {
  local unit="$1"
  [[ "$unit" == *@.* && "${${unit%.*}#*@}" == "" ]]
}

template_unit_name_for_instance() {
  local unit="$1"
  if [[ "$unit" == *@*.* && "$unit" != *.mount ]] && ! is_template_unit_name "$unit"; then
    print -r -- "${unit%%@*}@.${unit##*.}"
  fi
}

unit_name_matches_template() {
  local unit="$1" template="$2"
  [[ "$unit" == "${template%%@.*}@"*".${template##*.}" ]]
}

systemd_directive_value() {
  local key="$1" file="$2" value
  value="$(
    grep -m1 "^[[:space:]]*${key}[[:space:]]*=" "$file" 2>/dev/null |
      sed "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//" || :
  )"
  value="${value%"${value##*[![:space:]]}"}"
  print -r -- "$value"
}

systemd_truthy_directive() {
  local key="$1" file="$2" value
  value="$(systemd_directive_value "$key" "$file")"
  value="${value%%#*}"
  value="${value%%;*}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  case "${(L)value}" in
    yes|true|1|on) return 0 ;;
  esac
  return 1
}

socket_accept_service_base() {
  local unit="$1" unit_file="$2" socket_base
  if is_template_unit_name "${unit_file:t}"; then
    print -r -- "${unit_file:t:r}"
  else
    socket_base="${unit%.socket}"
    print -r -- "${socket_base%%@*}@"
  fi
}

unit_has_install_section() {
  local unit_file="$1"
  grep -qE '^[[:space:]]*\[Install\]' "$unit_file" 2>/dev/null
}

resolve_unit_file_path() {
  local unit_dir="$1" unit="$2" unit_file template_file
  unit_file="$unit_dir/$unit"
  template_file="$(template_unit_name_for_instance "$unit")"
  if [[ ! -f "$unit_file" && -n "$template_file" ]]; then
    unit_file="$unit_dir/$template_file"
  fi
  print -r -- "$unit_file"
}

# systemd resolves an exact unit name against its whole user unit load path
# before ever falling back to a template, so a shadow check must be exhaustive
# across that path. A hand-maintained list can never keep up (it also includes
# *.control/*.attached/transient/generator dirs and XDG_DATA_DIRS/XDG_CONFIG_DIRS-
# derived directories that vary by desktop environment), so ask systemd itself.
user_unit_search_paths() {
  local -a paths
  local line raw
  command -v systemd-analyze >/dev/null 2>&1 ||
    die "systemd-analyze is required to determine the user unit search path"
  raw="$(systemd-analyze --user unit-paths)" ||
    die "failed to query the user unit search path via systemd-analyze"
  paths=()
  for line in "${(@f)raw}"; do
    if [[ "$line" == "$HOME"/* ]]; then
      line="$target/${line#"$HOME"/}"
    fi
    paths+=("$line")
  done
  print -rl -- "${paths[@]}"
}

find_shadowing_user_unit_path() {
  local unit="$1" dir
  for dir in "${(@f)$(user_unit_search_paths)}"; do
    if [[ -e "$dir/$unit" || -L "$dir/$unit" ]]; then
      print -r -- "$dir/$unit"
      return 0
    fi
  done
  return 1
}

# System-unit counterpart to user_unit_search_paths above: systemd resolves an
# exact unit name against its whole system unit load path before falling back
# to a template, so the shadow check below must search all of these too. Ask
# systemd itself (see user_unit_search_paths) rather than hard-coding a list.
system_unit_search_paths() {
  command -v systemd-analyze >/dev/null 2>&1 ||
    die "systemd-analyze is required to determine the system unit search path"
  systemd-analyze unit-paths ||
    die "failed to query the system unit search path via systemd-analyze"
}

find_shadowing_system_unit_path() {
  local unit="$1" dir
  for dir in "${(@f)$(system_unit_search_paths)}"; do
    if [[ -e "$dir/$unit" || -L "$dir/$unit" ]]; then
      print -r -- "$dir/$unit"
      return 0
    fi
  done
  return 1
}

stop_user_template_instances() {
  local package="$1" unit="$2"
  local pattern="${unit/@./@*.}"
  local line instance
  for line in "${(@f)$(systemctl --user list-units --all --no-legend --plain -- "$pattern" 2>/dev/null)}"; do
    instance="${${(z)line}[1]}"
    [[ -n "$instance" ]] || continue
    print -- "Stopping $instance (Accept=yes connection instance of $unit)"
    systemctl --user stop "$instance" ||
      die "failed to stop user $instance for $package"
  done
}

unit_set_declares_unit() {
  local want="$1" name
  [[ -n "${unit_set[$want]-}" ]] && return 0
  if is_template_unit_name "$want"; then
    for name in "${(@k)unit_set}"; do
      unit_name_matches_template "$name" "$want" && return 0
    done
  fi
  return 1
}

systemd_unescape_instance() {
  local instance="$1"
  if [[ -n "$instance" ]] && command -v systemd-escape >/dev/null 2>&1; then
    systemd-escape --unescape -- "$instance"
  else
    print -r -- "$instance"
  fi
}

activation_bases_for_unit() {
  local unit_dir="$1" unit="$2"
  local unit_file managed_target unit_instance unit_instance_unescaped

  unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
  unit_instance=""
  [[ "$unit" == *@*.* ]] && unit_instance="${${unit%.*}#*@}"
  unit_instance_unescaped="$(systemd_unescape_instance "$unit_instance")"

  case "$unit" in
    *.timer|*.path)
      managed_target="$(systemd_directive_value Unit "$unit_file")"
      if [[ -n "$managed_target" ]]; then
        [[ -n "$unit_instance" ]] && managed_target="${managed_target//\%i/$unit_instance}"
        [[ -n "$unit_instance" ]] && managed_target="${managed_target//\%I/$unit_instance_unescaped}"
        print -r -- "${managed_target%.service}"
      else
        print -r -- "${unit%.*}"
      fi
      ;;
    *.socket)
      managed_target="$(systemd_directive_value Service "$unit_file")"
      if [[ -n "$managed_target" ]]; then
        [[ -n "$unit_instance" ]] && managed_target="${managed_target//\%i/$unit_instance}"
        [[ -n "$unit_instance" ]] && managed_target="${managed_target//\%I/$unit_instance_unescaped}"
        print -r -- "${managed_target%.service}"
      elif systemd_truthy_directive Accept "$unit_file"; then
        # Accept=yes sockets instantiate the template service per connection;
        # they never start the plain, non-template foo.service.
        print -r -- "$(socket_accept_service_base "$unit" "$unit_file")"
      else
        print -r -- "${unit%.socket}"
      fi
      ;;
  esac
}

activate_user_units() {
  local package="$1"
  local unit unit_file unit_dir dest_name base instance_path
  local verify_failures=0
  typeset -A activation_bases

  load_user_units_metadata "$package"
  (( ${#user_units[@]} > 0 )) || return 0

  if ! stow_target_is_home; then
    print -- "Skipping user unit activation for $package because STOW_TARGET is not HOME: $target"
    return 0
  fi

  command -v systemctl >/dev/null 2>&1 ||
    die "systemctl is required to activate user units for $package"

  unit_dir="$repo_root/packages/$package/install/.config/systemd/user"
  activation_bases=()
  for unit in "${user_units[@]}"; do
    unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
    # systemd resolves unit names through its own search path, so verify the
    # live stow link actually points at this package's file before mutating
    # anything by name (a stale link or a same-named unit elsewhere could
    # otherwise be enabled/started instead).
    dest_name="${unit_file:t}"
    if [[ "$dest_name" != "$unit" ]]; then
      # This instance is only backed by a template file in the package.
      # systemd searches for the exact instance name across its whole unit
      # load path before falling back to the template, so a stale/foreign
      # unit file anywhere on that path would silently shadow the template
      # we're about to verify/activate.
      if instance_path="$(find_shadowing_user_unit_path "$unit")"; then
        print -u2 -- "not ok - stale exact-instance unit shadows template: $instance_path"
        verify_failures=$(( verify_failures + 1 ))
      fi
    fi
    verify_stow_link "$unit_file" "$target/.config/systemd/user/$dest_name" ".config/systemd/user/$dest_name" ||
      verify_failures=$(( verify_failures + 1 ))
    for base in "${(@f)$(activation_bases_for_unit "$unit_dir" "$unit")}"; do
      [[ -n "$base" ]] && activation_bases[$base]=1
    done
  done

  (( verify_failures == 0 )) ||
    die "cannot activate $package: $verify_failures user unit stow-link verification failure(s)"

  print -- "Reloading user systemd manager for $package"
  systemctl --user daemon-reload ||
    die "failed to reload user systemd manager for $package"

  for unit in "${user_units[@]}"; do
    case "$unit" in
      *.timer)
        # Trigger unit: enable only when installable, then restart so a
        # changed unit file's config is applied with one start transition.
        unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
        if unit_has_install_section "$unit_file"; then
          print -- "Enabling (user) $unit"
          systemctl --user enable "$unit" ||
            die "failed to enable user $unit for $package"
        fi
        print -- "Restarting (user) $unit"
        systemctl --user restart "$unit" ||
          die "failed to restart user $unit for $package"
        ;;
      *.path|*.socket)
        # Trigger units: start, and enable only when installable. Unlike
        # timers, restarting an already-active socket/path tears down its live
        # fd/watch, so activation is intentionally start-only.
        unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
        if unit_has_install_section "$unit_file"; then
          print -- "Enabling (user) $unit"
          systemctl --user enable "$unit" ||
            die "failed to enable user $unit for $package"
        fi
        print -- "Starting (user) $unit"
        systemctl --user start "$unit" ||
          die "failed to start user $unit for $package"
        ;;
      *.service)
        if [[ -n "${activation_bases[${unit%.service}]+x}" ]]; then
          print -- "Skipping $unit (managed by a path, socket, or timer unit)"
        else
          unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
          # Only enable units that declare [Install]; enabling a unit without
          # it is a hard systemctl error and would abort start-only services.
          if unit_has_install_section "$unit_file"; then
            print -- "Enabling (user) $unit"
            systemctl --user enable "$unit" ||
              die "failed to enable user $unit for $package"
          fi
          print -- "Starting (user) $unit"
          systemctl --user start "$unit" ||
            die "failed to start user $unit for $package"
        fi
        ;;
      *.target|*.mount)
        if [[ -n "${activation_bases[$unit]+x}" ]]; then
          print -- "Skipping $unit (managed by a timer unit)"
        else
          unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
          if unit_has_install_section "$unit_file"; then
            print -- "Enabling and starting (user) $unit"
            systemctl --user enable --now "$unit" ||
              die "failed to enable/start user $unit for $package"
          else
            print -- "Starting (user) $unit"
            systemctl --user start "$unit" ||
              die "failed to start user $unit for $package"
          fi
        fi
        ;;
    esac
  done
}

# Verifies the live user unit at ~/.config/systemd/user actually belongs to
# this package before deactivate_user_units disables/stops it by name,
# mirroring the ownership check activate_user_units performs (verify_stow_link
# plus the stale-exact-instance-shadow check) before activation. A failed check
# here is fatal for the whole uninstall, for the same reason every other
# systemctl failure in deactivate_user_units is fatal: parse_uninstall still
# goes on to remove the package's stow links afterward, so silently skipping
# this unit would leave it live and running after its package files are gone.
verify_user_unit_owned_for_deactivation() {
  local unit_dir="$1" unit="$2"
  local unit_file dest_name instance_path

  unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
  dest_name="${unit_file:t}"
  if [[ "$dest_name" != "$unit" ]]; then
    if instance_path="$(find_shadowing_user_unit_path "$unit")"; then
      die "cannot deactivate $unit for $package: stale exact-instance unit shadows template: $instance_path"
    fi
  fi

  verify_stow_link "$unit_file" "$target/.config/systemd/user/$dest_name" ".config/systemd/user/$dest_name" ||
    die "cannot deactivate $unit for $package: live unit does not belong to $package"
}

deactivate_user_units() {
  local package="$1"
  local unit unit_dir unit_file base
  typeset -A activation_bases

  load_user_units_metadata "$package"
  (( ${#user_units[@]} > 0 )) || return 0

  if ! stow_target_is_home; then
    print -- "Skipping user unit deactivation for $package because STOW_TARGET is not HOME: $target"
    return 0
  fi

  command -v systemctl >/dev/null 2>&1 ||
    die "systemctl is required to deactivate user units for $package"

  unit_dir="$repo_root/packages/$package/install/.config/systemd/user"
  activation_bases=()
  for unit in "${user_units[@]}"; do
    for base in "${(@f)$(activation_bases_for_unit "$unit_dir" "$unit")}"; do
      [[ -n "$base" ]] && activation_bases[$base]=1
    done
  done

  for unit in "${user_units[@]}"; do
    case "$unit" in
      *.timer|*.path|*.socket) ;;
      *) continue ;;
    esac
    verify_user_unit_owned_for_deactivation "$unit_dir" "$unit"
    # Only disable units activation could have enabled (those with [Install]);
    # start-only trigger units were never enabled, and `disable` on a static
    # unit fails or removes user-created symlinks this tool never made.
    unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
    if unit_has_install_section "$unit_file"; then
      print -- "Disabling (user) $unit"
      systemctl --user disable --now "$unit" ||
        die "failed to disable/stop user $unit for $package"
    else
      print -- "Stopping (user) $unit"
      systemctl --user stop "$unit" ||
        die "failed to stop user $unit for $package"
    fi
  done
  # Reverse declaration order (${(Oa)...}) so dependents declared after their
  # dependencies (e.g. app.service after db.service) are torn down first;
  # this is a plain index-order reversal, not an alphabetical sort. Kept in
  # parity with deactivate_units in scripts/system-copy-select.
  for unit in "${(Oa)user_units[@]}"; do
    case "$unit" in
      *.timer|*.path|*.socket) continue ;;
    esac
    is_template_unit_name "$unit" && {
      verify_user_unit_owned_for_deactivation "$unit_dir" "$unit"
      stop_user_template_instances "$package" "$unit"
      print -- "Skipping $unit (template service managed by an Accept=yes socket)"
      continue
    }
    verify_user_unit_owned_for_deactivation "$unit_dir" "$unit"
    case "$unit" in
      *.service)
        if [[ -n "${activation_bases[${unit%.service}]+x}" ]]; then
          print -- "Stopping $unit (managed by a path, socket, or timer unit)"
          systemctl --user stop "$unit" ||
            die "failed to stop user $unit for $package"
          continue
        fi
        ;;
      *.target|*.mount)
        if [[ -n "${activation_bases[$unit]+x}" ]]; then
          print -- "Stopping $unit (managed by a path, socket, or timer unit)"
          systemctl --user stop "$unit" ||
            die "failed to stop user $unit for $package"
          continue
        fi
        ;;
    esac
    # Standalone unit: only disable it if activation could have enabled it
    # (an [Install] section is present), otherwise just stop it, matching the
    # start-only handling in activate_user_units.
    unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
    if unit_has_install_section "$unit_file"; then
      print -- "Disabling (user) $unit"
      systemctl --user disable --now "$unit" ||
        die "failed to disable/stop user $unit for $package"
    else
      print -- "Stopping (user) $unit"
      systemctl --user stop "$unit" ||
        die "failed to stop user $unit for $package"
    fi
  done
}

verify_user_live_units() {
  local package="$1"
  local unit unit_path unit_dir unit_file dest_name template_path instance_path
  local failures=0
  typeset -Ua unit_paths
  unit_paths=()

  load_user_units_metadata "$package"
  (( ${#user_units[@]} > 0 )) || return 0

  unit_dir="$repo_root/packages/$package/install/.config/systemd/user"

  for unit in "${user_units[@]}"; do
    unit_path="$target/.config/systemd/user/$unit"
    if is_template_unit_name "$unit"; then
      if [[ ! -e "$unit_path" ]]; then
        print -u2 -- "not ok - missing live user systemd unit: $unit_path"
        failures=$(( failures + 1 ))
      else
        print -- "warn - skipping instanceless template verification for user unit: $unit"
      fi
      continue
    fi
    unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
    dest_name="${unit_file:t}"
    if [[ "$dest_name" != "$unit" ]]; then
      # This instance is only backed by a template file in the package.
      # systemd searches for the exact instance name across its whole unit
      # load path before falling back to the template, so a stale/foreign
      # unit file anywhere on that path would silently shadow the template
      # we're about to verify, mirroring the shadow check in activate_user_units.
      if instance_path="$(find_shadowing_user_unit_path "$unit")"; then
        print -u2 -- "not ok - stale exact-instance unit shadows template: $instance_path"
        failures=$(( failures + 1 ))
        continue
      fi
      template_path="$target/.config/systemd/user/$dest_name"
      if [[ -e "$template_path" ]]; then
        # Verify by the concrete instance name, not the bare template path:
        # systemd-analyze --user resolves the name through the search path and
        # instantiates $unit, so %i-dependent references are checked against the
        # manifest instance rather than the documented test_instance placeholder.
        unit_paths+=("$unit")
        continue
      fi
    fi
    if [[ ! -e "$unit_path" ]]; then
      print -u2 -- "not ok - missing live user systemd unit: $unit_path"
      failures=$(( failures + 1 ))
      continue
    fi
    unit_paths+=("$unit_path")
  done

  (( failures == 0 )) || return 1

  if ! stow_target_is_home; then
    print -- "warn - skipping systemd-analyze --user verify for $package because STOW_TARGET is not HOME"
    return 0
  fi

  command -v systemd-analyze >/dev/null 2>&1 || {
    print -u2 -- "warn - systemd-analyze is unavailable; skipped live user systemd verification for $package"
    return 0
  }

  # systemctl --user prints a status word (running, degraded, starting, ...)
  # to stdout whenever it can reach a user manager, regardless of its own
  # exit code; only empty output or the literal "offline" status mean no
  # manager is reachable at all (e.g. no D-Bus user session in a CI
  # container, cron, or sudo session), in which case systemd-analyze --user
  # verify would hard-fail on a RuntimeDirectory lookup rather than perform a
  # static verification. Other non-"running" states (degraded, maintenance,
  # starting, stopping) still have a live manager and should still be verified.
  local user_manager_status
  user_manager_status="$(systemctl --user is-system-running 2>/dev/null)" || true
  case "$user_manager_status" in
    ""|offline)
      print -- "warn - skipping systemd-analyze --user verify for $package because no live user systemd manager is reachable"
      return 0
      ;;
  esac

  print -- "Verifying live user systemd units for $package"
  systemd-analyze --user verify "${unit_paths[@]}" || {
    print -u2 -- "not ok - live user systemd unit verification failed: $package"
    return 1
  }
}

test_user_units() {
  local package="$1"
  local install_dir="$repo_root/packages/$package/install"
  local unit unit_source f base
  local failures=0
  typeset -A unit_set
  unit_set=()

  load_user_units_metadata "$package"

  for unit in "${user_units[@]}"; do
    unit_set[$unit]=1
    unit_source="$(resolve_unit_file_path "$install_dir/.config/systemd/user" "$unit")"
    if [[ ! -f "$unit_source" ]]; then
      print -u2 -- "not ok - user-units.manifest entry has no repo unit file: $package $unit"
      failures=$(( failures + 1 ))
    fi
  done

  for f in "$install_dir"/.config/systemd/user/*(N.); do
    base="${f:t}"
    case "$base" in
      *.service|*.timer|*.path|*.socket|*.mount|*.target)
        # A template file (foo@.timer) is covered by any declared instance
        # (foo@daily.timer), mirroring check_user_layer in scripts/check-repo.
        if ! unit_set_declares_unit "$base"; then
          print -u2 -- "not ok - user systemd unit not in user-units.manifest: $package $base"
          failures=$(( failures + 1 ))
        fi
        ;;
    esac
  done

  return $(( failures > 0 ))
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
  local unit unit_path unit_dir unit_file dest_name template_path instance_path
  local failures=0
  typeset -Ua unit_paths
  unit_paths=()

  load_system_units_metadata "$package"
  (( ${#system_units[@]} > 0 )) || return 0

  unit_dir="$repo_root/packages/$package/system-install/etc/systemd/system"

  for unit in "${system_units[@]}"; do
    unit_path="/etc/systemd/system/$unit"
    if is_template_unit_name "$unit"; then
      if [[ ! -f "$unit_path" || -L "$unit_path" ]]; then
        print -u2 -- "not ok - missing live systemd unit for verification: $unit_path"
        failures=$(( failures + 1 ))
      else
        print -- "warn - skipping instanceless template verification for system unit: $unit"
      fi
      continue
    fi
    unit_file="$(resolve_unit_file_path "$unit_dir" "$unit")"
    dest_name="${unit_file:t}"
    if [[ "$dest_name" != "$unit" ]]; then
      # This instance is only backed by a template file in the package.
      # systemd resolves unit-name arguments through the whole system unit
      # load path before falling back to the template, so a stale/foreign
      # unit file anywhere on that path (not just /etc/systemd/system) would
      # silently shadow the template we're about to verify, mirroring the
      # shadow check in verify_user_live_units and the activation-time guard in
      # scripts/system-copy-select.
      if instance_path="$(find_shadowing_system_unit_path "$unit")"; then
        print -u2 -- "not ok - stale exact-instance unit shadows template: $instance_path"
        failures=$(( failures + 1 ))
        continue
      fi
      template_path="/etc/systemd/system/$dest_name"
      if [[ -f "$template_path" && ! -L "$template_path" ]]; then
        # Verify by the concrete instance name so %i-dependent references are
        # checked against the manifest instance, not the test_instance default.
        unit_paths+=("$unit")
        continue
      fi
    fi
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
  local unit_dir="$install_dir/etc/systemd/system"
  local base="${unit_source:t}"
  local line unit_ref instance inst_suffix inst_suffix_unescaped resolved resolved_file matched
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

    if [[ "$unit_ref" == *%[iI]* && "$base" == *@*.* ]]; then
      if is_template_unit_name "$base"; then
        matched=0
        for instance in "${system_units[@]}"; do
          unit_name_matches_template "$instance" "$base" || continue
          matched=1
          inst_suffix="${${instance%.*}#*@}"
          inst_suffix_unescaped="$(systemd_unescape_instance "$inst_suffix")"
          resolved="${unit_ref//\%i/$inst_suffix}"
          resolved="${resolved//\%I/$inst_suffix_unescaped}"
          resolved_file="$(resolve_unit_file_path "$unit_dir" "$resolved")"
          if [[ ! -f "$resolved_file" ]]; then
            print -u2 -- "not ok - repo timer Unit target missing from package: ${unit_source#$install_dir/}: $resolved (instance $instance)"
            failures=$(( failures + 1 ))
          fi
        done
        continue
      fi
      inst_suffix="${${base%.*}#*@}"
      inst_suffix_unescaped="$(systemd_unescape_instance "$inst_suffix")"
      unit_ref="${unit_ref//\%i/$inst_suffix}"
      unit_ref="${unit_ref//\%I/$inst_suffix_unescaped}"
    fi

    if [[ ! -f "$(resolve_unit_file_path "$unit_dir" "$unit_ref")" ]]; then
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

  load_system_units_metadata "$package"

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

  test_user_units "$package" || {
    print -u2 -- "not ok - $package has user-units.manifest test failure(s)"
    return 1
  }
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

run_check_repo_for_packages() {
  typeset -Ua packages
  packages=("$@")
  (( ${#packages[@]} > 0 )) || return 0
  "$repo_root/scripts/check-repo" -- "${packages[@]}"
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

  select_user_packages "$selector"
  select_system_packages "$selector"
  # System packages are validated by scripts/system-copy-select's own
  # check-repo preflight inside run_system_activation below; checking them
  # here too would run check-repo twice for the same packages.
  run_check_repo_for_packages "${selected_user_packages[@]}"

  run_system_activation "$selector"

  for package in "${selected_user_packages[@]}"; do
    activate_user_units "$package"
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

  local any_user_units=0

  select_user_packages "$selector"
  # Preflight the manifests before touching anything, mirroring activation
  # (run_check_repo_for_packages in parse_activate). A user unit file omitted
  # from user-units.manifest would otherwise be left running after
  # deactivate_user_units skips it and run_stow_action removes its file; under
  # set -euo pipefail this aborts uninstall before any deactivation or unlink.
  run_check_repo_for_packages "${selected_user_packages[@]}"
  for package in "${selected_user_packages[@]}"; do
    deactivate_user_units "$package"
    (( ${#user_units[@]} > 0 )) && any_user_units=1
  done
  run_system_action uninstall "$selector" "$verbose"
  run_stow_action uninstall "$selector" "$verbose"

  if (( any_user_units )) && stow_target_is_home && command -v systemctl >/dev/null 2>&1; then
    print -- "Reloading user systemd manager after uninstall"
    systemctl --user daemon-reload ||
      print -u2 -- "warning: failed to reload user systemd manager after uninstall (ignored)"
  fi
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
