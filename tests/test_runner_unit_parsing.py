"""Section and specifier regression probes; no live systemd execution."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_runner_review_regressions as shell
import test_runner_system_rebind_units as fixtures

engine = fixtures.engine


class UnitParserPolicyTests(unittest.TestCase):
    setUp = fixtures.SystemUnitPolicyTests.setUp
    source = fixtures.SystemUnitPolicyTests.source
    write_manifest = fixtures.SystemUnitPolicyTests.write_manifest
    plan = fixtures.SystemUnitPolicyTests.plan
    apply = fixtures.SystemUnitPolicyTests.apply
    state = fixtures.SystemUnitPolicyTests.state
    result = fixtures.SystemUnitPolicyTests.result
    units = fixtures.SystemUnitPolicyTests.units
    checker = fixtures.SystemUnitPolicyTests.checker
    refusal_without_writes = fixtures.SystemUnitPolicyTests.refusal_without_writes

    def invalid_both(self):
        self.refusal_without_writes()
        if shutil.which('zsh'):
            self.assertNotEqual(self.checker().returncode, 0)

    def valid_both(self):
        if shutil.which('zsh'):
            checked = self.checker()
            self.assertEqual(checked.returncode, 0, checked.stderr)
        self.apply()

    def test_literal_specifier_declarations_never_authorize_raw_target(self):
        for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
            for specifier in ('%n', '%N', '%p', '%P', '%h', '%H', '%u', '%U', '%m', '%v', '%%', '%'):
                with self.subTest(kind=kind, specifier=specifier):
                    self.setUp()
                    service = specifier + '.service'
                    self.units({'demo.' + kind: f'[{kind.title()}]\n{key}={service}\n',
                                service: '[Service]\n'}, 'demo.' + kind + '\n' + service + '\n')
                    self.invalid_both()

    def test_instance_specifiers_on_non_instance_units_are_refused(self):
        for specifier in ('%i', '%I'):
            with self.subTest(specifier=specifier):
                self.setUp()
                self.units({'demo.timer': f'[Timer]\nUnit=worker@{specifier}.service\n',
                            'worker@.service': '[Service]\n'},
                           'demo.timer\nworker@alpha.service\n')
                self.invalid_both()

    def test_wrong_section_accept_cannot_authorize_template_contract(self):
        for header in ('[Unit]', '[Service]', '[Install]', '[socket]', ''):
            with self.subTest(header=header):
                self.setUp()
                self.units({'demo.socket': header + '\nAccept=yes\n', 'demo@.service': '[Service]\n'},
                           'demo.socket\ndemo@.service\n')
                self.invalid_both()

    def test_wrong_section_targets_cannot_override_actual_implicit_service(self):
        for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
            with self.subTest(kind=kind):
                self.setUp()
                self.units({'demo.' + kind: f'[Unit]\n{key}=worker.service\n',
                            'worker.service': '[Service]\n'}, 'demo.' + kind + '\nworker.service\n')
                self.invalid_both()

    def test_ignored_keys_do_not_override_correct_section_or_count_as_duplicates(self):
        cases = [
            ('socket', '[Unit]\nAccept=no\nService=missing.service\n[Socket]\nAccept=yes\n',
             'demo@.service'),
            ('timer', '[Unit]\nUnit=missing.service\n[Timer]\nUnit=worker.service\n', 'worker.service'),
            ('path', '[Install]\nUnit=missing.service\n[Path]\nUnit=worker.service\n', 'worker.service'),
            ('socket', '[Unit]\nAccept=yes\n[Socket]\nAccept=no\nService=worker.service\n', 'worker.service'),
        ]
        for kind, text, service in cases:
            with self.subTest(kind=kind, text=text):
                self.setUp()
                self.units({'demo.' + kind: text, service: '[Service]\n'},
                           'demo.' + kind + '\n' + service + '\n')
                self.valid_both()

    def test_wrong_section_values_leave_real_default_in_force(self):
        self.units({'demo.socket': '[Unit]\nAccept=yes\nService=missing.service\n',
                    'demo.service': '[Service]\n'}, 'demo.socket\ndemo.service\n')
        self.valid_both()

    def test_physical_header_in_continued_description_is_not_a_section(self):
        for ending in ('\n', '\r\n'):
            for comments in ('', '# ignored comment\n; another comment\n'):
                with self.subTest(ending=repr(ending), comments=comments):
                    self.setUp()
                    text = '[Unit]\nDescription=continued \\\n' + comments + '[Socket]\nAccept=yes\n'
                    self.units({'demo.socket': text.replace('\n', ending), 'demo@.service': '[Service]\n'},
                               'demo.socket\ndemo@.service\n')
                    self.invalid_both()

    def test_even_trailing_backslashes_allow_next_real_section(self):
        self.units({'demo.socket': '[Unit]\nDescription=literal \\\\\n[Socket]\nAccept=yes\n',
                    'demo@.service': '[Service]\n'}, 'demo.socket\ndemo@.service\n')
        self.valid_both()

    def test_continued_or_repeated_contract_directives_fail_closed_in_both_readers(self):
        for text in ('[Socket]\nAccept=yes\nAccept=no\n',
                     '[Socket]\nAccept=yes\n[Unit]\nDescription=other\n[Socket]\nAccept=no\n',
                     '[Socket]\nAccept=yes\\\n', '[Socket]\nService=demo.service\\\n',
                     '[Socket]\nAccept=yes # not a whole-line comment\n',
                     '[Socket]\nAccept=yes; not a whole-line comment\n',
                     '[Socket]\nAccept=garbage\n',
                     '[Socket]\nAccept=yes trailing text\n',
                     '[Socket]\nAccept=garbage on\n',
                     '[Socket]\nAccept=no # reset value is not a comment\n'):
            with self.subTest(text=text):
                self.setUp()
                self.units({'demo.socket': text, 'demo.service': '[Service]\n'},
                           'demo.socket\ndemo.service\n')
                self.invalid_both()

    def test_empty_accept_reset_still_selects_the_nonaccepting_service(self):
        for value in ('', '   ', '\t'):
            with self.subTest(value=value):
                self.setUp()
                self.units({'demo.socket': f'[Socket]\nAccept={value}\n',
                            'demo.service': '[Service]\n'},
                           'demo.socket\ndemo.service\n')
                self.valid_both()

    def test_reopened_sections_comments_and_single_bom_preserve_valid_contract(self):
        for bom in ('', '\ufeff'):
            with self.subTest(bom=bool(bom)):
                self.setUp()
                text = '# comment\n' + bom + '[Socket]\n; Accept=no\nAccept=yes\n[Unit]\nAccept=no\n[Socket]\nListenStream=12345\n'
                self.units({'demo.socket': text, 'demo@.service': '[Service]\n'},
                           'demo.socket\ndemo@.service\n')
                self.valid_both()

    def test_nul_and_malformed_sections_do_not_authorize_contract(self):
        for text in ('[Socket] trailing\nAccept=no\n', '[Socket]\nAccept=no\0yes\n'):
            with self.subTest(text=repr(text)):
                self.setUp()
                self.units({'demo.socket': text, 'demo.service': '[Service]\n'},
                           'demo.socket\ndemo.service\n')
                self.invalid_both()

    def test_uninstantiated_explicit_targets_are_not_authorized_by_template_coverage(self):
        for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
            for trigger in ('demo.' + kind, 'demo@alpha.' + kind, 'demo@.' + kind):
                for target_declarations in ('worker@alpha.service\n',
                                            'worker@alpha.service\nworker@beta.service\n',
                                            'worker@.service\nworker.socket\n'):
                    with self.subTest(kind=kind, trigger=trigger, targets=target_declarations):
                        self.setUp()
                        files = {trigger: f'[{kind.title()}]\n{key}=worker@.service\n',
                                 'worker@.service': '[Service]\n'}
                        if 'worker.socket' in target_declarations:
                            # A legitimate accepting socket may declare this bare
                            # template, but cannot authorize another trigger's target.
                            files['worker.socket'] = '[Socket]\nAccept=yes\n'
                        declaration = trigger.replace('@.', '@alpha.')
                        self.units(files, declaration + '\n' + target_declarations)
                        self.invalid_both()

    def test_exact_concrete_targets_keep_template_file_coverage(self):
        for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
            for trigger, value in (('demo.' + kind, 'worker@alpha.service'),
                                   ('demo@.' + kind, 'worker@%i.service'),
                                   ('demo@.' + kind, 'worker@%I.service')):
                with self.subTest(kind=kind, trigger=trigger, value=value):
                    self.setUp()
                    self.units({trigger: f'[{kind.title()}]\n{key}={value}\n',
                                'worker@.service': '[Service]\n'},
                               trigger.replace('@.', '@alpha.') + '\nworker@alpha.service\n')
                    self.valid_both()

    def test_resolved_targets_need_the_exact_declared_instance(self):
        for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
            for trigger in ('demo@alpha.' + kind, 'demo@.' + kind):
                with self.subTest(kind=kind, trigger=trigger):
                    self.setUp()
                    self.units({trigger: f'[{kind.title()}]\n{key}=worker@%i.service\n',
                                'worker@.service': '[Service]\n'},
                               trigger.replace('@.', '@alpha.') + '\nworker@beta.service\n')
                    self.invalid_both()

    @unittest.skipUnless(shutil.which('zsh'), 'requires Zsh for user-unit gate')
    def test_user_trigger_targets_cannot_borrow_template_file_coverage(self):
        for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
            for accepting_socket in (False, True):
                with self.subTest(kind=kind, accepting_socket=accepting_socket):
                    self.setUp()
                    package = self.repo / 'packages/demo'
                    install = package / 'install/.config/systemd/user'
                    install.mkdir(parents=True)
                    (install / ('demo.' + kind)).write_text(f'[{kind.title()}]\n{key}=worker@.service\n')
                    (install / 'worker@.service').write_text('[Service]\n')
                    declarations = 'demo.' + kind + '\nworker@alpha.service\n'
                    if accepting_socket:
                        (install / 'worker.socket').write_text('[Socket]\nAccept=yes\n')
                        declarations = 'demo.' + kind + '\nworker@.service\nworker.socket\n'
                    (package / 'user-units.manifest').write_text(declarations)
                    stow = self.repo / 'stow'
                    stow.mkdir()
                    (stow / 'demo').symlink_to('../packages/demo/install')
                    self.assertNotEqual(self.checker().returncode, 0)

    @unittest.skipUnless(shutil.which('zsh'), 'requires Zsh for user-unit gate')
    def test_user_unit_gate_applies_sections_and_specifier_refusal(self):
        for text, service in (('[Unit]\nAccept=yes\n', 'demo@.service'),
                              ('[Socket]\nService=%n.service\n', '%n.service')):
            with self.subTest(text=text):
                self.setUp()
                package = self.repo / 'packages/demo'
                install = package / 'install/.config/systemd/user'
                install.mkdir(parents=True)
                (install / 'demo.socket').write_text(text)
                (install / service).write_text('[Service]\n')
                (package / 'user-units.manifest').write_text('demo.socket\n' + service + '\n')
                stow = self.repo / 'stow'
                stow.mkdir()
                (stow / 'demo').symlink_to('../packages/demo/install')
                self.assertNotEqual(self.checker().returncode, 0)


@unittest.skipUnless(shutil.which('zsh'), 'requires Zsh for lifecycle selection')
class UnitParserLifecycleTests(unittest.TestCase):
    function = shell.ExistingReviewFixTests.function

    def invoke(self, script, root, unit, *, type_only=False):
        names = ['systemd_directive_value', 'systemd_target_specifiers_supported',
                 'systemd_truthy_directive', 'activation_bases_for_unit',
                 'socket_accept_service_base', 'is_template_unit_name']
        source = '\n'.join(self.function(script, name) for name in names) + '''
die() { print -u2 -- "$*"; exit 65; }
systemd_unescape_instance() { print -r -- "$1"; }
resolve_unit_file_path() { print -r -- "$1/$2"; }
'''
        source += ('systemd_directive_value Type "$1/$2"' if type_only else
                   'activation_bases_for_unit "$1" "$2"')
        return subprocess.run(['zsh', '-f', '-c', source, 'fixture', str(root), unit],
                              env={'PATH': os.environ['PATH'], 'HOME': str(root)},
                              capture_output=True, text=True, timeout=10)

    def test_lifecycle_uses_real_sections_for_targets_accept_and_service_type(self):
        cases = [('demo.socket', '[Unit]\nAccept=yes\n[Socket]\nAccept=no\n', 'demo'),
                 ('demo.socket', '[Unit]\nAccept=no\n[Socket]\nAccept=yes\n', 'demo@'),
                 ('demo.timer', '[Unit]\nUnit=wrong.service\n[Timer]\nUnit=right.service\n', 'right'),
                 ('demo.path', '[Unit]\nUnit=wrong.service\n[Path]\nUnit=right.service\n', 'right'),
                 ('demo.socket', '[Unit]\nService=wrong.service\n[Socket]\nService=right.service\n', 'right'),
                 ('demo.service', '[Unit]\nType=oneshot\n[Service]\nType=simple\n', 'simple')]
        with tempfile.TemporaryDirectory(prefix='unit-parser-') as directory:
            root = Path(directory)
            for script in ('run.sh', 'scripts/system-copy-select'):
                for unit, text, expected in cases:
                    with self.subTest(script=script, unit=unit):
                        (root / unit).write_text(text)
                        result = self.invoke(script, root, unit, type_only=unit.endswith('.service'))
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), expected)

    def test_lifecycle_refuses_unsupported_specifiers_and_ambiguous_inputs(self):
        with tempfile.TemporaryDirectory(prefix='unit-parser-') as directory:
            root = Path(directory)
            for script in ('run.sh', 'scripts/system-copy-select'):
                for value in ('%n.service', '%p.service', '%%.service', '%i.service', '%I.service'):
                    with self.subTest(script=script, value=value):
                        (root / 'demo.timer').write_text('[Timer]\nUnit=' + value + '\n')
                        result = self.invoke(script, root, 'demo.timer')
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, '')
                (root / 'demo.socket').write_text('[Socket]\nAccept=yes\nAccept=no\n')
                result = self.invoke(script, root, 'demo.socket')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')

    def test_instance_specifiers_remain_supported_in_lifecycle_readers(self):
        with tempfile.TemporaryDirectory(prefix='unit-parser-') as directory:
            root = Path(directory)
            for script in ('run.sh', 'scripts/system-copy-select'):
                for specifier in ('%i', '%I'):
                    with self.subTest(script=script, specifier=specifier):
                        (root / 'demo@alpha.timer').write_text('[Timer]\nUnit=worker@' + specifier + '.service\n')
                        result = self.invoke(script, root, 'demo@alpha.timer')
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), 'worker@alpha')

    def test_lifecycle_refuses_uninstantiated_explicit_template_targets(self):
        with tempfile.TemporaryDirectory(prefix='unit-target-') as directory:
            root = Path(directory)
            for script in ('run.sh', 'scripts/system-copy-select'):
                for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
                    for unit in ('demo.' + kind, 'demo@alpha.' + kind):
                        with self.subTest(script=script, unit=unit):
                            (root / unit).write_text(f'[{kind.title()}]\n{key}=worker@.service\n')
                            result = self.invoke(script, root, unit)
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn('uninstantiated template trigger target', result.stderr)
                            self.assertEqual(result.stdout, '')

    def test_lifecycle_preserves_exact_and_expanded_concrete_targets(self):
        with tempfile.TemporaryDirectory(prefix='unit-target-') as directory:
            root = Path(directory)
            for script in ('run.sh', 'scripts/system-copy-select'):
                for kind, key in (('timer', 'Unit'), ('path', 'Unit'), ('socket', 'Service')):
                    for unit, target in (('demo.' + kind, 'worker@alpha.service'),
                                         ('demo@alpha.' + kind, 'worker@%i.service'),
                                         ('demo@alpha.' + kind, 'worker@%I.service')):
                        with self.subTest(script=script, unit=unit, target=target):
                            (root / unit).write_text(f'[{kind.title()}]\n{key}={target}\n')
                            result = self.invoke(script, root, unit)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertEqual(result.stdout.strip(), 'worker@alpha')

    def test_target_parser_failure_aborts_each_lifecycle_before_service_commands(self):
        for script, name in (('run.sh', 'activate_user_units'), ('run.sh', 'deactivate_user_units'),
                             ('scripts/system-copy-select', 'activate_units'),
                             ('scripts/system-copy-select', 'deactivate_units')):
            with self.subTest(script=script, name=name):
                source = self.function(script, name) + '''
repo_root=/fixture
packages_dir=/fixture/packages
target=/fixture-target
load_user_units_metadata() { user_units=(demo.timer); }
load_units_metadata() { system_units=(demo.timer); }
stow_target_is_home() { return 0; }
user_manager_reachable() { return 0; }
verify_user_unit_owned_for_deactivation() { return 0; }
verify_stow_link() { return 0; }
resolve_unit_file_path() { print -r -- "$1/$2"; }
activation_bases_for_unit() { print -r -- bogus; return 2; }
systemctl() { print -r -- unexpected-service-command; }
sudo() { print -r -- unexpected-privileged-command; }
die() { print -u2 -- "$*"; exit 65; }
''' + name + ' fixture\nprint -r -- unexpected-continuation\n'
                result = subprocess.run(['zsh', '-f', '-c', source],
                                        env={'PATH': os.environ['PATH'], 'HOME': '/nonexistent'},
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 65, result.stderr)
                self.assertIn('failed to resolve trigger targets', result.stderr)
                self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
