"""Pre-mutation service parsing and whole-checkout guards on temporary data."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import test_runner_rebind as user
import test_runner_review_regressions as shell
import test_runner_system_rebind as system
import test_runner_system_rebind_units as unitcases


class ServiceTypePolicyTests(unittest.TestCase):
    setUp = unitcases.SystemUnitPolicyTests.setUp
    source = unitcases.SystemUnitPolicyTests.source
    write_manifest = unitcases.SystemUnitPolicyTests.write_manifest
    units = unitcases.SystemUnitPolicyTests.units
    checker = unitcases.SystemUnitPolicyTests.checker
    state = unitcases.SystemUnitPolicyTests.state

    def test_system_type_gate_refuses_ambiguous_services_before_journal(self):
        for name in ('demo.service', 'demo@.service'):
            for text in ('[Service]\nType=oneshot\nType=simple\n',
                         '[Service]\nType=one\\\nshot\n'):
                with self.subTest(name=name, text=text):
                    self.setUp()
                    declaration = name.replace('@.', '@alpha.')
                    self.units({name: text}, declaration + '\n')
                    before = self.state()
                    with self.assertRaisesRegex(system.engine.Refusal, 'ambiguous system unit directive: Type'):
                        system.engine.prepare(self.repo, self.target, 'demo', [self.old])
                    self.assertEqual(self.state(), before)
                    self.assertEqual(list(self.journals.iterdir()), [])
                    if shutil.which('zsh'):
                        checked = self.checker()
                        self.assertNotEqual(checked.returncode, 0)
                        self.assertIn('invalid or ambiguous systemd contract', checked.stderr)

    @unittest.skipUnless(shutil.which('zsh'), 'requires Zsh')
    def test_user_type_gate_refuses_repeated_and_continued_values(self):
        for name in ('demo.service', 'demo@.service'):
            for text in ('[Service]\nType=oneshot\nType=simple\n',
                         '[Service]\nType=one\\\nshot\n'):
                with self.subTest(name=name, text=text):
                    self.setUp()
                    package = self.repo / 'packages/demo'
                    install = package / 'install/.config/systemd/user'
                    install.mkdir(parents=True)
                    (install / name).write_text(text)
                    (package / 'user-units.manifest').write_text(name.replace('@.', '@alpha.') + '\n')
                    (self.repo / 'stow').mkdir()
                    (self.repo / 'stow/demo').symlink_to('../packages/demo/install')
                    checked = self.checker()
                    self.assertNotEqual(checked.returncode, 0)
                    self.assertIn('invalid or ambiguous systemd contract', checked.stderr)


@unittest.skipUnless(shutil.which('zsh'), 'requires Zsh')
class ServiceTypeLifecycleTests(unittest.TestCase):
    function = shell.ExistingReviewFixTests.function

    def activate(self, script, root, declared, *, rewrite=False):
        name = 'activate_user_units' if script == 'run.sh' else 'activate_units'
        source = self.function(script, 'systemd_directive_value') + '\n' + self.function(script, name) + '''
repo_root="$1"
packages_dir="$1/packages"
target="$1/target"
log="$1/operations"
shift
load_user_units_metadata() { user_units=("${declared[@]}"); }
load_units_metadata() { system_units=("${declared[@]}"); }
stow_target_is_home() { return 0; }
verify_stow_link() { return 0; }
find_shadowing_system_unit_path() { return 1; }
find_shadowing_user_unit_path() { return 1; }
resolve_unit_file_path() {
  local file="$1/$2"
  [[ -f "$file" ]] || file="$1/${2%%@*}@.${2##*.}"
  print -r -- "$file"
}
activation_bases_for_unit() {
  [[ "$2" == *.timer || "$2" == *.path || "$2" == *.socket ]] && print -r -- demo
  return 0
}
unit_has_install_section() { return 0; }
user_manager_reachable() { print -r -- manager-query >> "$log"; return 0; }
enable_user_unit() { print -r -- "enable $*" >> "$log"; }
systemctl() { print -r -- "$*" >> "$log"; }
sudo() {
  print -r -- "$*" >> "$log"
  if [[ "$rewrite" == yes && "$*" == *daemon-reload* ]]; then
    print -r -- '[Service]\nType=simple\nType=oneshot' > "$packages_dir/demo/system-install/etc/systemd/system/demo.service"
  fi
}
die() { print -u2 -- "$*"; exit 65; }
declared=("$@")
'''
        source += 'rewrite=' + ('yes' if rewrite else 'no') + '\n' + name + ' demo\n'
        return subprocess.run(['zsh', '-f', '-c', source, 'fixture', str(root), *declared],
                              env={'PATH': os.environ['PATH'], 'HOME': str(root)},
                              capture_output=True, text=True, timeout=10)

    def fixture(self, root, script, service, text):
        directory = root / 'packages/demo' / ('install/.config/systemd/user' if script == 'run.sh'
                                              else 'system-install/etc/systemd/system')
        directory.mkdir(parents=True, exist_ok=True)
        (directory / service).write_text(text)
        for kind in ('timer', 'path', 'socket'):
            (directory / ('demo.' + kind)).write_text(f'[{kind.title()}]\n')

    def test_all_types_parsed_before_any_service_command_in_any_order(self):
        for script in ('run.sh', 'scripts/system-copy-select'):
            for service in ('demo.service', 'demo@alpha.service'):
                for kind in ('timer', 'path', 'socket'):
                    for first in (False, True):
                        with self.subTest(script=script, service=service, kind=kind, first=first):
                            with tempfile.TemporaryDirectory(prefix='type-preflight-') as directory:
                                root = Path(directory)
                                file = service.replace('@alpha.', '@.')
                                self.fixture(root, script, file, '[Service]\nType=oneshot\nType=simple\n')
                                declared = [service, 'demo.' + kind] if first else ['demo.' + kind, service]
                                result = self.activate(script, root, declared)
                                self.assertEqual(result.returncode, 65, result.stderr)
                                self.assertIn('invalid or ambiguous systemd contract', result.stderr)
                                self.assertFalse((root / 'operations').exists(), result.stdout)

    def test_system_activation_uses_cached_type_after_manager_reload(self):
        with tempfile.TemporaryDirectory(prefix='type-cache-') as directory:
            root = Path(directory)
            self.fixture(root, 'scripts/system-copy-select', 'demo.service', '[Service]\nType = oneshot\n')
            result = self.activate('scripts/system-copy-select', root,
                                   ['demo.timer', 'demo.service'], rewrite=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            operations = (root / 'operations').read_text().splitlines()
            self.assertEqual(operations, ['-n systemctl daemon-reload', '-n systemctl enable demo.timer',
                                         '-n systemctl restart demo.timer', '-n systemctl start demo.service'])


class SystemCheckoutBoundaryTests(unittest.TestCase):
    setUp = system.SystemRebindTests.setUp
    source = system.SystemRebindTests.source
    write_manifest = system.SystemRebindTests.write_manifest

    def test_live_root_refuses_every_source_checkout_not_only_package_tree(self):
        self.repo = self.repo.rename(self.base / 'new-checkout')
        self.old = self.old.rename(self.base / 'old-checkout')
        for root in (self.repo, self.old):
            for relative in ('run.sh', '.git/config', 'packages/unrelated/config'):
                with self.subTest(root=root, relative=relative):
                    destination = root / relative
                    self.paths = [str(destination).lstrip('/')]
                    for source_root in (self.repo, self.old):
                        shutil.rmtree(source_root / 'packages/demo/system-install')
                        source = self.source(source_root, self.paths[0])
                        source.parent.mkdir(parents=True, exist_ok=True)
                        source.write_text('approved old bytes' if source_root == self.old else 'new bytes')
                        self.write_manifest(source_root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text('approved old bytes')
                    destination.chmod(0o640)
                    before = destination.read_bytes()
                    # Read-only live-root planning; no root mutation, permissions
                    # mocked solely because the disposable checkout is user-owned.
                    with mock.patch.object(system.engine, 'safe_target_parents'), \
                         self.assertRaisesRegex(system.engine.Refusal, 'destination overlaps source checkout'):
                        system.engine.prepare(self.repo, Path('/'), 'demo', [self.old])
                    self.assertEqual(destination.read_bytes(), before)
                    self.assertEqual(list(self.journals.iterdir()), [])

    def test_destination_parent_alias_to_checkout_is_a_conflict(self):
        original = system.engine.read
        for root in (self.repo, self.old):
            with self.subTest(root=root):
                def aliased(path, *args, **kwargs):
                    state, data = original(path, *args, **kwargs)
                    if path == self.target / self.paths[0]:
                        info = root.stat()
                        state['parents'][-1][1:3] = [info.st_dev, info.st_ino]
                    return state, data
                with mock.patch.object(system.engine, 'read', side_effect=aliased):
                    snapshot = system.engine.prepare(self.repo, self.target, 'demo', [self.old])
                self.assertEqual(snapshot['rows'][0]['class'], 'FOREIGN')
                self.assertIn(self.paths[0], snapshot['conflicts'])


class UserCheckoutBoundaryTests(unittest.TestCase):
    setUp = user.RebindTests.setUp
    link = user.RebindTests.link

    def test_checkout_links_are_protected_in_normal_forced_and_recovery_plans(self):
        directory = self.base / '.local/share/repos'
        directory.mkdir(parents=True)
        self.repo = self.repo.rename(directory / 'new-checkout')
        self.old = self.old.rename(directory / 'old-checkout')
        for root in (self.repo, self.old):
            for modes in ({}, {'force_links': True}, {'recover_dangling': True}):
                if root == self.old and modes.get('recover_dangling'):
                    continue  # recovery admits an absent root, never this existing tree
                with self.subTest(root=root, modes=modes):
                    rel = str(root.relative_to(self.base)) + '/internal-link'
                    for source_root in (self.repo, self.old):
                        file = source_root / 'packages/demo/install' / rel
                        file.parent.mkdir(parents=True, exist_ok=True)
                        file.write_text('fixture')
                    destination = root / 'internal-link'
                    if destination.is_symlink():
                        destination.unlink()
                    destination.symlink_to(self.old / 'stow/demo' / rel)
                    before = os.readlink(destination)
                    roots = [self.old]
                    if modes.get('recover_dangling'):
                        lost = self.base / 'missing checkout'
                        roots = [lost]
                        destination.unlink()
                        destination.symlink_to(lost / 'stow/demo' / rel)
                        before = os.readlink(destination)
                    with self.assertRaisesRegex(user.engine.Refusal, 'destination overlaps source checkout'):
                        user.engine.plan(self.repo, self.base, 'demo', roots, **modes)
                    self.assertEqual(os.readlink(destination), before)

    def test_rename_legacy_leaf_and_batch_preflight_cannot_remove_checkout_link(self):
        directory = self.base / '.local/share/repos'
        directory.mkdir(parents=True)
        self.repo = self.repo.rename(directory / 'new-checkout')
        self.old = self.old.rename(directory / 'old-checkout')
        rel = str(self.old.relative_to(self.base)) + '/internal-link'
        legacy = self.old / 'packages/demo/install' / rel
        legacy.parent.mkdir(parents=True)
        legacy.write_text('legacy fixture')
        destination = self.old / 'internal-link'
        destination.symlink_to(self.old / 'stow/demo' / rel)
        before = os.readlink(destination)
        for renamed in (False, True):
            with self.subTest(renamed=renamed):
                if renamed:
                    (self.repo / 'packages/demo/rebind-paths.manifest').write_text(
                        rel + ' ' + self.files[0] + '\n')
                with self.assertRaisesRegex(user.engine.Refusal, 'destination overlaps source checkout'):
                    user.engine.plan(self.repo, self.base, 'demo', [self.old])
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    _, prepared, failures = user.engine.prepare_batch(self.repo, self.base, [self.old])
                self.assertEqual(prepared, {})
                self.assertIn('destination overlaps source checkout', failures['demo'])
                self.assertEqual(os.readlink(destination), before)

    def test_user_destination_parent_alias_to_checkout_is_refused(self):
        original = user.engine.identity
        for root in (self.repo, self.old):
            with self.subTest(root=root):
                def aliased(path):
                    entry = original(path)
                    if path == self.target / '.local/bin':
                        return original(root)[:2] + entry[2:]
                    return entry
                with mock.patch.object(user.engine, 'identity', side_effect=aliased), \
                     self.assertRaisesRegex(user.engine.Refusal, 'destination physically overlaps a source checkout'):
                    user.engine.plan(self.repo, self.target, 'demo', [self.old])


if __name__ == '__main__':
    unittest.main()
