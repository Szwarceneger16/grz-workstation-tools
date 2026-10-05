"""Systemd Accept booleans agree across validation and lifecycle selection."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_runner_review_regressions as shell
import test_runner_system_rebind_units as unit_fixtures

ROOT = Path(__file__).resolve().parents[1]
# systemd's parse_boolean() is case-insensitive for all twelve spellings.
TRUE = ('1', 'yes', 'y', 'true', 't', 'on', 'YES', 'Y', 'TrUe', 'T', 'ON')
FALSE = ('0', 'no', 'n', 'false', 'f', 'off', 'NO', 'N', 'FaLsE', 'F', 'OFF')


class AcceptUnitPolicyTests(unittest.TestCase):
    setUp = unit_fixtures.SystemUnitPolicyTests.setUp
    source = unit_fixtures.SystemUnitPolicyTests.source
    write_manifest = unit_fixtures.SystemUnitPolicyTests.write_manifest
    plan = unit_fixtures.SystemUnitPolicyTests.plan
    apply = unit_fixtures.SystemUnitPolicyTests.apply
    state = unit_fixtures.SystemUnitPolicyTests.state
    result = unit_fixtures.SystemUnitPolicyTests.result
    units = unit_fixtures.SystemUnitPolicyTests.units
    checker = unit_fixtures.SystemUnitPolicyTests.checker
    refusal_without_writes = unit_fixtures.SystemUnitPolicyTests.refusal_without_writes

    def test_all_true_spellings_reject_service_override_in_both_validators(self):
        for value in TRUE:
            with self.subTest(value=value):
                self.setUp()
                self.units({'demo.socket': f'[Socket]\nAccept={value}\nService=demo.service\n',
                            'demo.service': '[Service]\n'}, 'demo.socket\ndemo.service\n')
                self.refusal_without_writes()
                if shutil.which('zsh'):
                    self.assertNotEqual(self.checker().returncode, 0)

    def test_all_true_spellings_require_template_instead_of_plain_service(self):
        for value in TRUE:
            with self.subTest(value=value):
                self.setUp()
                self.units({'demo.socket': f'[Socket]\nAccept={value}\n',
                            'demo.service': '[Service]\n'}, 'demo.socket\ndemo.service\n')
                self.refusal_without_writes()
                if shutil.which('zsh'):
                    self.assertNotEqual(self.checker().returncode, 0)

    def test_all_true_spellings_allow_declared_accept_template(self):
        for value in TRUE:
            with self.subTest(value=value):
                self.setUp()
                self.units({'demo.socket': f'[Socket]\nAccept={value}\n',
                            'demo@.service': '[Service]\n'}, 'demo.socket\ndemo@.service\n')
                if shutil.which('zsh'):
                    checked = self.checker()
                    self.assertEqual(checked.returncode, 0, checked.stderr)
                self.apply()

    def test_all_false_spellings_allow_nonaccepting_service(self):
        for value in (*FALSE, ''):
            with self.subTest(value=value):
                self.setUp()
                # No directive means the systemd default, Accept=no.
                accept = f'Accept={value}\n' if value else ''
                self.units({'demo.socket': '[Socket]\n' + accept + 'Service=demo.service\n',
                            'demo.service': '[Service]\n'}, 'demo.socket\ndemo.service\n')
                if shutil.which('zsh'):
                    checked = self.checker()
                    self.assertEqual(checked.returncode, 0, checked.stderr)
                self.apply()

    @unittest.skipUnless(shutil.which('zsh'), 'requires Zsh for user-layer gate')
    def test_user_unit_gate_also_rejects_short_true_spellings_with_service_override(self):
        for value in ('y', 't', 'Y', 'T'):
            with self.subTest(value=value):
                self.setUp()
                package = self.repo / 'packages/demo'
                install = package / 'install/.config/systemd/user'
                install.mkdir(parents=True)
                (install / 'demo.socket').write_text(f'[Socket]\nAccept={value}\nService=demo.service\n')
                (install / 'demo.service').write_text('[Service]\n')
                (package / 'user-units.manifest').write_text('demo.socket\ndemo.service\n')
                stow = self.repo / 'stow'
                stow.mkdir()
                (stow / 'demo').symlink_to('../packages/demo/install')
                checked = self.checker()
                self.assertNotEqual(checked.returncode, 0)
                self.assertIn('Accept=yes together with Service=', checked.stderr)


@unittest.skipUnless(shutil.which('zsh'), 'requires Zsh for lifecycle selection')
class AcceptLifecycleTests(unittest.TestCase):
    function = shell.ExistingReviewFixTests.function

    def test_truth_predicates_and_socket_activation_bases_use_all_systemd_spellings(self):
        with tempfile.TemporaryDirectory(prefix='accept-policy-') as directory:
            root = Path(directory)
            socket = root / 'demo.socket'
            for script in ('run.sh', 'scripts/system-copy-select', 'scripts/check-repo'):
                functions = '\n'.join(self.function(script, name) for name in
                                      ('systemd_directive_value', 'systemd_truthy_directive'))
                lifecycle = script != 'scripts/check-repo'
                if lifecycle:
                    functions += '\n' + '\n'.join(self.function(script, name) for name in
                        ('activation_bases_for_unit', 'socket_accept_service_base', 'is_template_unit_name',
                         'systemd_target_specifiers_supported'))
                source = functions + '''
systemd_unescape_instance() { print -r -- "$1"; }
resolve_unit_file_path() { print -r -- "$1/$2"; }
if systemd_truthy_directive Accept "$1/demo.socket"; then print true; else print false; fi
'''
                if lifecycle:
                    source += '\nactivation_bases_for_unit "$1" demo.socket\n'
                for value in (*TRUE, *FALSE, ''):
                    with self.subTest(script=script, value=value):
                        socket.write_text('[Socket]\n' + (f'Accept={value}\n' if value else ''))
                        result = subprocess.run(['zsh', '-f', '-c', source, 'fixture', str(root)],
                                                env={'PATH': os.environ['PATH'], 'HOME': str(root)},
                                                text=True, capture_output=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        expected = ['true' if value in TRUE else 'false']
                        if lifecycle:
                            expected.append('demo@' if value in TRUE else 'demo')
                        self.assertEqual(result.stdout.splitlines(), expected)


if __name__ == '__main__':
    unittest.main()
