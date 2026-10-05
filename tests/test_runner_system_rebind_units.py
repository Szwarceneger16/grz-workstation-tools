"""System-unit policy gates use disposable sources and installed roots only."""
import shutil
import subprocess
import unittest
from unittest import mock

import test_runner_system_rebind as system

engine = system.engine


class SystemUnitPolicyTests(unittest.TestCase):
    setUp = system.SystemRebindTests.setUp
    source = system.SystemRebindTests.source
    write_manifest = system.SystemRebindTests.write_manifest
    plan = system.SystemRebindTests.plan
    apply = system.SystemRebindTests.apply
    state = system.SystemRebindTests.state
    result = system.SystemRebindTests.result

    def units(self, files, declarations=None, directory='etc/systemd/system'):
        for name, text in files.items():
            path = directory + '/' + name
            self.paths.append(path)
            for repo, content in ((self.repo, text), (self.old, '[Unit]\nDescription=Legacy fixture\n')):
                source = self.source(repo, path)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(content)
                self.write_manifest(repo)
            installed = self.target / path
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_bytes(self.source(self.old, path).read_bytes())
            installed.chmod(0o640)
            for parent in installed.parents:
                if parent.is_relative_to(self.target):
                    parent.chmod(0o755)
        if declarations is not None:
            (self.repo / 'packages/demo/system-units.manifest').write_text(declarations)

    def checker(self):
        scripts = self.repo / 'scripts'
        scripts.mkdir(exist_ok=True)
        for name in ('check-repo', 'system-copy-select'):
            shutil.copy2(system.ROOT / 'scripts' / name, scripts / name)
        shutil.copy2(system.ROOT / 'run.sh', self.repo / 'run.sh')
        return subprocess.run(['zsh', '-f', str(scripts / 'check-repo'), '--', 'demo'],
                              capture_output=True, text=True, timeout=20)

    def refusal_without_writes(self):
        before = self.state()
        with self.assertRaisesRegex(engine.Refusal, 'unit|trigger|socket|Unit|manifest separator'), \
                mock.patch.object(engine, 'write_at', wraps=engine.write_at) as writes:
            self.apply()
        writes.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_every_supported_undeclared_unit_type_is_refused(self):
        for kind in ('service', 'timer', 'path', 'socket', 'mount', 'target'):
            with self.subTest(kind=kind):
                self.setUp()
                self.units({'demo.' + kind: '[Unit]\nDescription=Fixture\n'})
                self.refusal_without_writes()

    def test_declared_service_is_migrated_without_running_repository_code(self):
        self.units({'demo.service': '[Service]\nExecStart=/bin/true\n'}, 'demo.service\n')
        # An input checkout is data: a package hook or checker must never be
        # executed by the standalone helper, including its privileged path.
        scripts = self.repo / 'scripts'
        scripts.mkdir()
        (scripts / 'check-repo').write_text('exit 99\n')
        self.apply()
        self.assertEqual((self.target / self.paths[-1]).read_bytes(),
                         self.source(self.repo, self.paths[-1]).read_bytes())

    def test_missing_reverse_unit_declaration_and_malformed_rows_fail_closed(self):
        for declaration in ('missing.service\n', 'demo.service\ndemo.service\n',
                            '-demo.service\n', 'etc/demo.service\n', 'demo.slice\n',
                            'demo@.timer\n', 'demo.service extra\n', 'demo.service\r\n',
                            'demo.service\u2028other.service\n'):
            with self.subTest(declaration=repr(declaration)):
                self.setUp()
                self.units({'demo.service': '[Service]\n'}, declaration)
                self.refusal_without_writes()

    def test_template_service_requires_concrete_instance_or_accept_socket(self):
        self.units({'worker@.service': '[Service]\n'}, 'worker@.service\n')
        self.refusal_without_writes()
        (self.repo / 'packages/demo/system-units.manifest').write_text('worker@alpha.service\n')
        self.apply()

    def test_implicit_trigger_requires_repo_service_and_manifest_coverage(self):
        for kind in ('timer', 'path', 'socket'):
            for service_present in (False, True):
                with self.subTest(kind=kind, service_present=service_present):
                    self.setUp()
                    files = {'demo.' + kind: '[Unit]\n'}
                    if service_present:
                        files['demo.service'] = '[Service]\n'
                    self.units(files, 'demo.' + kind + '\n')
                    self.refusal_without_writes()

    def test_explicit_trigger_target_requires_declaration(self):
        for kind, directive in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
            with self.subTest(kind=kind):
                self.setUp()
                self.units({'demo.' + kind: f'[{kind.title()}]\n{directive}=worker.service\n',
                            'worker.service': '[Service]\n'}, 'demo.' + kind + '\n')
                self.refusal_without_writes()

    def test_accept_socket_needs_declared_service_template_and_no_service_override(self):
        for declarations, override in (('demo.socket\n', ''),
                                       ('demo.socket\ndemo@alpha.service\n', ''),
                                       ('demo.socket\ndemo@.service\n', 'Service=demo@.service\n')):
            with self.subTest(declarations=declarations, override=override):
                self.setUp()
                self.units({'demo.socket': '[Socket]\nAccept=yes\n' + override,
                            'demo@.service': '[Service]\n'}, declarations)
                self.refusal_without_writes()

    def test_valid_trigger_template_and_accept_socket_contracts_match_check_repo(self):
        cases = [
            ({'demo.timer': '[Timer]\n', 'demo.service': '[Service]\n'}, 'demo.timer\ndemo.service\n'),
            ({'demo.path': '[Path]\nUnit=worker.service\n', 'worker.service': '[Service]\n'},
             'demo.path\nworker.service\n'),
            ({'demo.socket': '[Socket]\nAccept=yes\n', 'demo@.service': '[Service]\n'},
             'demo.socket\ndemo@.service\n'),
            ({'demo@.timer': '[Timer]\nUnit=worker@%i.service\n', 'worker@.service': '[Service]\n'},
             'demo@alpha.timer\ndemo@beta.timer\nworker@alpha.service\nworker@beta.service\n'),
            ({'demo@.path': '[Path]\n', 'demo@.service': '[Service]\n'},
             'demo@alpha.path\ndemo@alpha.service\n'),
            ({'demo@.timer': '[Timer]\nUnit=worker@%I.service\n', 'worker@.service': '[Service]\n'},
             'demo@\\x78.timer\nworker@x.service\n'),
            ({'demo.mount': '[Mount]\n', 'demo.target': '[Unit]\n'}, 'demo.mount\ndemo.target\n'),
        ]
        for files, declarations in cases:
            with self.subTest(declarations=declarations):
                self.setUp()
                self.units(files, declarations)
                if shutil.which('zsh'):
                    result = self.checker()
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.apply()

    def test_template_trigger_checks_every_declared_instance(self):
        self.units({'demo@.timer': '[Timer]\nUnit=worker@%i.service\n',
                    'worker@.service': '[Service]\n'},
                   'demo@alpha.timer\ndemo@beta.timer\nworker@alpha.service\n')
        self.refusal_without_writes()

    @unittest.skipUnless(shutil.which('zsh'), 'requires Zsh for authoritative comparison')
    def test_invalid_selected_contracts_are_rejected_by_both_validators(self):
        cases = [({'demo.service': '[Service]\n'}, ''),
                 ({'demo.service': '[Service]\n'}, 'demo.service\nmissing.service\n'),
                 ({'demo.timer': '[Timer]\n'}, 'demo.timer\n'),
                 ({'demo.socket': '[Socket]\nAccept=yes\n', 'demo@.service': '[Service]\n'},
                  'demo.socket\ndemo@alpha.service\n'),
                 ({'demo@.service': '[Service]\n'}, 'demo@.service\n')]
        for files, declarations in cases:
            with self.subTest(declarations=declarations):
                self.setUp()
                self.units(files, declarations)
                self.assertNotEqual(self.checker().returncode, 0)
                self.refusal_without_writes()

    def test_other_package_unit_errors_do_not_block_selected_package(self):
        bad = self.repo / 'packages/unselected/system-install/etc/systemd/system'
        bad.mkdir(parents=True)
        (bad / 'bad.service').write_text('[Service]\n')
        self.apply()

    def test_alternate_load_directories_dropins_and_unsupported_suffixes_are_refused(self):
        for directory, name in (('usr/lib/systemd/system', 'demo.service'),
                                ('usr/local/lib/systemd/system', 'demo.service'),
                                ('lib/systemd/system', 'demo.service'),
                                ('run/systemd/system', 'demo.service'),
                                ('etc/systemd/system/demo.service.d', 'override.conf'),
                                ('etc/systemd/system', 'demo.slice')):
            with self.subTest(directory=directory, name=name):
                self.setUp()
                self.units({name: '[Service]\n'}, directory=directory)
                self.refusal_without_writes()

    def test_repeated_or_continued_target_directives_are_refused(self):
        for value in ('Unit=worker.service\nUnit=demo.service\n', 'Unit=worker.service\\\n'):
            with self.subTest(value=value):
                self.setUp()
                self.units({'demo.timer': '[Timer]\n' + value, 'worker.service': '[Service]\n',
                            'demo.service': '[Service]\n'},
                           'demo.timer\nworker.service\ndemo.service\n')
                self.refusal_without_writes()

    def test_unit_manifest_changes_after_approval_stop_before_any_journal_or_write(self):
        self.units({'demo.service': '[Service]\n'}, 'demo.service\n')
        snapshot = self.plan()
        before = self.state()
        (self.repo / 'packages/demo/system-units.manifest').write_text('# Changed declaration bytes\ndemo.service\n')
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_adding_unit_manifest_after_approval_invalidates_its_recorded_absence(self):
        snapshot = self.plan()
        before = self.state()
        (self.repo / 'packages/demo/system-units.manifest').write_text('# New manifest\n')
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_unit_manifest_symlink_is_refused(self):
        self.units({'demo.service': '[Service]\n'})
        external = self.base / 'external-unit-manifest'
        external.write_text('demo.service\n')
        (self.repo / 'packages/demo/system-units.manifest').symlink_to(external)
        before = self.state()
        with self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_unit_manifest_change_after_first_publication_rolls_back(self):
        self.units({'demo.service': '[Service]\n'}, 'demo.service\n')
        before = self.state()
        move = engine.move
        def changed(fd, source, destination):
            result = move(fd, source, destination)
            if source.endswith('.new'):
                (self.repo / 'packages/demo/system-units.manifest').write_text('')
            return result
        with mock.patch.object(engine, 'move', side_effect=changed), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')

    def test_direct_cli_and_run_sh_inspection_preview_apply_share_unit_gate(self):
        self.units({'demo.service': '[Service]\n'})
        scripts = self.repo / 'scripts'
        scripts.mkdir()
        shutil.copy2(system.ROOT / 'scripts/rebind-system-package', scripts / 'rebind-system-package')
        shutil.copy2(system.ROOT / 'run.sh', self.repo / 'run.sh')
        (self.repo / 'runner.conf').write_text('RUNNER_ID=fixture\nRUNNER_ENV_PREFIX=FIXTURE\n')
        (self.repo / 'stow').mkdir()
        before = self.state()
        for routed in (False, True):
            for flags in (['--inspect'], ['--dry-run'], ['--yes']):
                with self.subTest(routed=routed, flags=flags):
                    if routed:
                        command = ['zsh', '-f', str(self.repo / 'run.sh'),
                                   'verify' if flags == ['--inspect'] else 'install',
                                   '--rebind-system', '--from-repo', str(self.old),
                                   '--system-root', str(self.target), 'demo']
                        if flags != ['--inspect']:
                            command += flags
                    else:
                        command = ['python3', '-I', str(scripts / 'rebind-system-package'),
                                   '--repo', str(self.repo), '--system-root', str(self.target),
                                   '--from-repo', str(self.old), '--package', 'demo', *flags]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('systemd unit not in system-units.manifest', result.stderr)
                    self.assertEqual(self.state(), before)
                    self.assertEqual(list(self.journals.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
