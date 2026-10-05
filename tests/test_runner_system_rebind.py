"""WP-6 proof, CLI and failure tests: only disposable roots, never sudo."""
import contextlib
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('system_rebind', str(ROOT / 'scripts/rebind-system-package'))
spec = importlib.util.spec_from_loader(loader.name, loader)
engine = importlib.util.module_from_spec(spec)
loader.exec_module(engine)


class SystemRebindTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='test-system-rebind-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repo, self.old, self.target = [self.base / name for name in ('new checkout', 'old checkout', 'system')]
        self.journals = self.base / 'journals'
        self.journals.mkdir()
        self.paths = ['etc/demo/a', 'etc/demo/b']
        self.ids = f'{os.geteuid()} {os.getegid()}'
        for repo, content in ((self.repo, 'new'), (self.old, 'old')):
            package = repo / 'packages/demo'
            package.mkdir(parents=True)
            for relative in self.paths:
                path = package / 'system-install' / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content + ':' + relative)
            self.write_manifest(repo)
        (self.repo / 'manifests').mkdir()
        self.target.mkdir()
        for relative in self.paths:
            target = self.target / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.source(self.old, relative).read_bytes())
            target.chmod(0o640)
        # A developer's group-writable umask must not weaken the production
        # parent-ownership assertion. Make only our disposable root safe.
        for folder, dirs, files in os.walk(self.target):
            Path(folder).chmod(0o755)

    def source(self, repo, relative):
        return repo / 'packages/demo/system-install' / relative

    def write_manifest(self, repo, mode='0640'):
        (repo / 'packages/demo/system-install.manifest').write_text(
            ''.join(f'{relative} {mode} {self.ids}\n' for relative in self.paths))

    def plan(self):
        return engine.prepare(self.repo, self.target, 'demo', [self.old])

    def apply(self, snapshot=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            engine.apply(self.repo, self.target, 'demo', [self.old], snapshot or self.plan(), self.journals)

    def state(self):
        result = {}
        for relative in self.paths:
            path = self.target / relative
            if path.is_symlink():
                result[relative] = ('link', os.readlink(path))
            elif path.is_file():
                result[relative] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode),
                                    path.stat().st_uid, path.stat().st_gid)
            else:
                result[relative] = None
        return result

    def result(self):
        records = list(self.journals.glob('runner-system-rebind-*/progress.json'))
        self.assertEqual(len(records), 1)
        self.assertEqual(stat.S_IMODE(records[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(records[0].parent.stat().st_mode), 0o700)
        return records[0].parent, json.loads(records[0].read_text())

    def test_legacy_proof_apply_backup_and_idempotence(self):
        old = self.state()
        snapshot = self.plan()
        self.assertEqual([row['class'] for row in snapshot['rows']], ['REBINDABLE'] * 2)
        self.apply(snapshot)
        for relative in self.paths:
            self.assertEqual((self.target / relative).read_bytes(), self.source(self.repo, relative).read_bytes())
        journal, result = self.result()
        self.assertEqual(result['status'], 'committed')
        self.assertEqual(result['recovery'], [])
        for index, relative in enumerate(self.paths):
            self.assertEqual((journal / f'{index}.before').read_bytes(), old[relative][0])
            self.assertEqual(stat.S_IMODE((journal / f'{index}.before').stat().st_mode), 0o600)
        identities = [(self.target / relative).stat().st_ino for relative in self.paths]
        self.apply()
        self.assertEqual(identities, [(self.target / relative).stat().st_ino for relative in self.paths])
        self.assertEqual(len(list(self.journals.iterdir())), 1)
        self.assertFalse(list(self.target.rglob('.runner-system-*')))

    def test_metadata_transition_requires_exact_old_metadata(self):
        self.write_manifest(self.repo, '0600')
        self.apply()
        self.assertTrue(all(stat.S_IMODE((self.target / path).stat().st_mode) == 0o600 for path in self.paths))

    def test_drift_is_conflict_and_full_preflight_changes_nothing(self):
        (self.target / self.paths[-1]).write_text('other writer data')
        before = self.state()
        plan = self.plan()
        self.assertEqual(plan['rows'][-1]['class'], 'FOREIGN')
        with self.assertRaises(engine.Refusal):
            self.apply(plan)
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_missing_is_distinct_and_not_an_implicit_install(self):
        (self.target / self.paths[-1]).unlink()
        before = self.state()
        plan = self.plan()
        self.assertEqual(plan['rows'][-1]['class'], 'MISSING')
        with self.assertRaises(engine.Refusal):
            self.apply(plan)
        self.assertEqual(self.state(), before)

    def test_metadata_drift_is_not_legacy_proof(self):
        (self.target / self.paths[-1]).chmod(0o600)
        self.assertEqual(self.plan()['rows'][-1]['class'], 'FOREIGN')

    def test_symlink_directory_fifo_and_hardlink_destinations_are_refused(self):
        path = self.target / self.paths[-1]
        for kind in ('symlink', 'directory', 'fifo', 'hardlink'):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == 'symlink':
                    path.symlink_to(self.source(self.old, self.paths[-1]))
                elif kind == 'directory':
                    path.mkdir()
                elif kind == 'fifo':
                    os.mkfifo(path)
                else:
                    os.link(self.target / self.paths[0], path)
                plan = self.plan()
                self.assertIn(self.paths[-1], plan['conflicts'])
                with self.assertRaises(engine.Refusal):
                    self.apply(plan)
                path.rmdir() if kind == 'directory' else path.unlink()
                path.write_bytes(self.source(self.old, self.paths[-1]).read_bytes())
                path.chmod(0o640)

    def test_unsafe_parent_and_source_symlink_are_refused(self):
        parent = self.target / 'etc/demo'
        moved = self.target / 'etc/moved'
        parent.rename(moved)
        parent.symlink_to(moved)
        plan = self.plan()
        self.assertEqual(len(plan['conflicts']), 2)
        parent.unlink()
        moved.rename(parent)
        source = self.source(self.repo, self.paths[0])
        source.unlink()
        source.symlink_to(self.source(self.old, self.paths[0]))
        with self.assertRaises(OSError):
            self.plan()

    def test_source_root_symlink_and_overlapping_roots_are_refused(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.old)
        for roots in ([alias], [self.repo], [self.old, self.old], [self.old, self.old / 'nested']):
            with self.subTest(roots=roots), self.assertRaises((engine.Refusal, OSError)):
                engine.prepare(self.repo, self.target, 'demo', roots)

    def test_source_and_target_races_after_approval_have_zero_writes(self):
        for source in (True, False):
            snapshot = self.plan()
            path = self.source(self.repo, self.paths[-1]) if source else self.target / self.paths[-1]
            old = path.read_bytes()
            path.write_text('concurrent contents')
            before = self.state()
            with self.assertRaises(engine.Refusal):
                self.apply(snapshot)
            self.assertEqual(self.state(), before)
            path.write_bytes(old)

    def test_parent_identity_change_invalidates_approval(self):
        snapshot = self.plan()
        parent = self.target / 'etc/demo'
        parent.rename(self.target / 'etc/previous')
        parent.mkdir(mode=0o755)
        for relative in self.paths:
            target = self.target / relative
            target.write_bytes(self.source(self.old, relative).read_bytes())
            target.chmod(0o640)
        before = self.state()
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)

    def test_policy_and_manifest_races_invalidate_approval(self):
        for path in (self.repo / 'manifests/protected-system-paths.txt',
                     self.old / 'packages/demo/system-install.manifest'):
            snapshot = self.plan()
            before = self.state()
            original = path.read_bytes() if path.exists() else None
            path.write_bytes((original or b'') + b'# new reviewed policy\n')
            with self.assertRaises(engine.Refusal):
                self.apply(snapshot)
            self.assertEqual(self.state(), before)
            path.unlink() if original is None else path.write_bytes(original)

    def test_protected_paths_and_unsupported_globs_fail_closed(self):
        for pattern in ('etc/demo', 'etc/demo/*', 'etc/(demo|other)/*',
                        'etc/account[[:digit:]]', 'etc/[=a=]', 'etc/[[.a.]]',
                        'etc/<1-9>', 'etc/demo(#qN)', 'etc/demo~other',
                        'etc/{demo,other}', 'etc/[!a]', 'etc/[^a]', 'etc/[',
                        'etc/demo]', 'etc/[z-a]', 'etc/[0-z]', 'etc/**/demo',
                        'etc//demo', 'etc/./demo', 'etc/demo\\*'):
            (self.repo / 'manifests/protected-system-paths.txt').write_text(pattern + '\n')
            with self.assertRaises(engine.Refusal):
                self.plan()

    @unittest.skipUnless(shutil.which('zsh'), 'Zsh is required for policy equivalence')
    def test_supported_globs_match_zsh_policy_semantics(self):
        patterns = ('etc/demo/*', 'etc/demo/?', 'etc/demo/[ab]', 'etc/demo/[a-z]',
                    'etc/demo/[A-Z0-9]', 'etc/demo/[a-cx-z]', 'etc/demo/a')
        values = ('etc/demo/a', 'etc/demo/b', 'etc/demo/d', 'etc/demo/z',
                  'etc/demo/5', 'etc/demo/Z', 'etc/demo/ab', 'etc/demo/a/b')
        for pattern in patterns:
            engine.protected_glob(pattern)
            for value in values:
                with self.subTest(pattern=pattern, value=value):
                    zsh = subprocess.run(['zsh', '-fc',
                        'pattern=$1; value=$2; [[ "$value" == ${~pattern} ]]',
                        'policy-test', pattern, value], timeout=10)
                    self.assertIn(zsh.returncode, (0, 1))
                    self.assertEqual(engine.fnmatch.fnmatchcase(value, pattern), zsh.returncode == 0)

    def test_setid_requires_current_exact_approval_for_old_and_new_modes(self):
        self.write_manifest(self.repo, '4640')
        with self.assertRaises(engine.Refusal):
            self.plan()
        (self.repo / 'manifests/allow-setid-system-paths.txt').write_text('\n'.join(self.paths) + '\n')
        self.apply()
        self.assertTrue(all(stat.S_IMODE((self.target / path).stat().st_mode) == 0o4640 for path in self.paths))

    def test_config_destinations_are_excluded_before_payload_read(self):
        forbidden = self.target / 'etc/demo/private-config'
        forbidden.parent.mkdir(parents=True, exist_ok=True)
        forbidden.write_text('fixture private data')
        declaration = f'etc/demo/private-config 0600 {self.ids}\n'
        (self.repo / 'packages/demo/system-config.manifest').write_text(declaration)
        original = engine.read
        def no_config(path, **kwargs):
            self.assertNotEqual(path, forbidden)
            return original(path, **kwargs)
        with mock.patch.object(engine, 'read', side_effect=no_config):
            self.apply()
        self.assertEqual(forbidden.read_text(), 'fixture private data')
        (self.repo / 'packages/demo/system-config.manifest').write_text(f'{self.paths[0]} 0600 {self.ids}\n')
        with self.assertRaises(engine.Refusal), mock.patch.object(engine, 'read', side_effect=no_config):
            self.plan()

    def test_undeclared_source_and_manifest_traversal_are_refused(self):
        extra = self.source(self.repo, 'etc/demo/undeclared')
        extra.write_text('fixture')
        with self.assertRaises(engine.Refusal):
            self.plan()
        extra.unlink()
        for relative in ('../escape', '/absolute', 'etc//demo/a', 'etc/./demo/a'):
            (self.repo / 'packages/demo/system-install.manifest').write_text(f'{relative} 0640 {self.ids}\n')
            with self.assertRaises(engine.Refusal):
                self.plan()

    def test_old_only_paths_are_unverified_residue_and_untouched(self):
        relative = 'etc/demo/removed'
        self.source(self.old, relative).write_text('old residue')
        with (self.old / 'packages/demo/system-install.manifest').open('a') as stream:
            stream.write(f'{relative} 0640 {self.ids}\n')
        residue = self.target / relative
        residue.write_text('independent residue')
        snapshot = self.plan()
        self.assertEqual(snapshot['residue'], [relative])
        self.apply(snapshot)
        self.assertEqual(residue.read_text(), 'independent residue')

    def test_failure_on_second_file_restores_first_and_second(self):
        before = self.state()
        original = engine.move
        def fail_second(fd, source, destination):
            if destination == 'b' and source.endswith('.new'):
                raise OSError('fixture publication failure')
            return original(fd, source, destination)
        with mock.patch.object(engine, 'move', side_effect=fail_second), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')
        self.assertFalse(list(self.target.rglob('.runner-system-*')))

    def test_quarantine_race_preserves_concurrent_content(self):
        original = engine.move
        def writer(fd, source, destination):
            if source == 'a' and destination.endswith('.old'):
                (self.target / self.paths[0]).write_text('concurrent owner contents')
            return original(fd, source, destination)
        with mock.patch.object(engine, 'move', side_effect=writer), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual((self.target / self.paths[0]).read_text(), 'concurrent owner contents')
        self.assertEqual((self.target / self.paths[1]).read_bytes(), self.source(self.old, self.paths[1]).read_bytes())
        self.assertEqual(self.result()[1]['status'], 'recovery-required')

    def test_no_clobber_publication_preserves_writer_and_displaced_backup(self):
        original = engine.move
        def writer(fd, source, destination):
            if destination == 'a' and source.endswith('.new'):
                (self.target / self.paths[0]).write_text('new concurrent file')
            return original(fd, source, destination)
        with mock.patch.object(engine, 'move', side_effect=writer), self.assertRaises(OSError):
            self.apply()
        self.assertEqual((self.target / self.paths[0]).read_text(), 'new concurrent file')
        self.assertEqual(self.result()[1]['status'], 'recovery-required')
        self.assertTrue(list(self.target.rglob('*.old')))

    def test_writer_after_publication_is_not_overwritten_by_rollback(self):
        original = engine.move
        def writer(fd, source, destination):
            result = original(fd, source, destination)
            if destination == 'a' and source.endswith('.new'):
                (self.target / self.paths[0]).write_text('retained writer contents')
            return result
        with mock.patch.object(engine, 'move', side_effect=writer), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual((self.target / self.paths[0]).read_text(), 'retained writer contents')
        self.assertEqual(self.result()[1]['status'], 'recovery-required')

    def test_source_change_during_transaction_rolls_back_owned_files(self):
        before = self.state()
        original = engine.move
        def change_source(fd, source, destination):
            result = original(fd, source, destination)
            if destination == 'a' and source.endswith('.new'):
                self.source(self.repo, self.paths[1]).write_text('source changed')
            return result
        with mock.patch.object(engine, 'move', side_effect=change_source), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')

    def test_signals_after_quarantine_or_publication_restore_owned_files(self):
        before = self.state()
        for signum, boundary in ((signal.SIGINT, 'quarantine'), (signal.SIGTERM, 'publication')):
            original = engine.move
            previous = signal.signal(signum, engine.interrupted)
            delivered = False
            def interrupt(fd, source, destination):
                nonlocal delivered
                result = original(fd, source, destination)
                point = (destination.endswith('.old') if boundary == 'quarantine'
                         else destination == 'a' and source.endswith('.new'))
                if point and not delivered:
                    delivered = True
                    os.kill(os.getpid(), signum)
                return result
            try:
                with mock.patch.object(engine, 'move', side_effect=interrupt), self.assertRaises(engine.Refusal):
                    self.apply()
            finally:
                signal.signal(signum, previous)
            self.assertTrue(delivered)
            self.assertEqual(self.state(), before)
            for child in self.journals.iterdir():
                shutil.rmtree(child)

    def test_target_lock_contention_fails_without_writes(self):
        before = self.state()
        with engine.directory(self.target) as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.apply()
        self.assertEqual(self.state(), before)

    def test_unsupported_xattrs_and_read_errors_do_not_become_missing(self):
        with mock.patch.object(engine.os, 'listxattr', return_value=['user.fixture']):
            with self.assertRaises(engine.Refusal):
                self.plan()
        original = engine.read
        def denied(path, **kwargs):
            if path == self.target / self.paths[0]:
                raise PermissionError('fixture unreadable target')
            return original(path, **kwargs)
        with mock.patch.object(engine, 'read', side_effect=denied):
            self.assertEqual(self.plan()['rows'][0]['class'], 'FOREIGN')

    def test_live_root_write_requires_explicit_privilege(self):
        with mock.patch.object(engine.os, 'geteuid', return_value=12345):
            with self.assertRaisesRegex(engine.Refusal, 'privileged'):
                engine.apply(self.repo, Path('/'), 'demo', [self.old], {}, self.journals)

    def test_aggregate_selectors_and_missing_legacy_are_refused(self):
        for package in ('all', 'all-system', 'all-user', '..'):
            with self.assertRaises(engine.Refusal):
                engine.prepare(self.repo, self.target, package, [self.old])
        with self.assertRaises(engine.Refusal):
            engine.prepare(self.repo, self.target, 'demo', [])
        with self.assertRaises(FileNotFoundError):
            engine.prepare(self.repo, self.target, 'demo', [self.base / 'missing'])
        for target in (self.repo, self.old, self.base):
            with self.assertRaises(engine.Refusal):
                engine.prepare(self.repo, target, 'demo', [self.old])

    def test_missing_renameat2_has_no_unsafe_fallback(self):
        before = self.state()
        with mock.patch.object(engine.ctypes, 'CDLL', return_value=object()):
            with self.assertRaisesRegex(engine.Refusal, 'renameat2'):
                self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')

    def test_partial_stage_failure_retains_explicit_recovery_evidence(self):
        before = self.state()
        original = engine.write_at
        def incomplete(fd, name, data, mode, uid, gid):
            if name.endswith('.new'):
                original(fd, name, data[:2], mode, uid, gid)
                raise OSError('fixture incomplete write')
            return original(fd, name, data, mode, uid, gid)
        with mock.patch.object(engine, 'write_at', side_effect=incomplete), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'recovery-required')
        self.assertTrue(list(self.target.rglob('*.new')))

    def test_final_policy_change_rolls_back_all_owned_files(self):
        before = self.state()
        original = engine.move
        def changed_policy(fd, source, destination):
            result = original(fd, source, destination)
            if destination == 'b' and source.endswith('.new'):
                (self.repo / 'manifests/protected-system-paths.txt').write_text('# changed at final boundary\n')
            return result
        with mock.patch.object(engine, 'move', side_effect=changed_policy), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')

    def test_writable_or_foreign_parent_blocks_before_any_target_write(self):
        before = self.state()
        parent = self.target / 'etc/demo'
        parent.chmod(0o777)
        self.assertEqual(len(self.plan()['conflicts']), 2)
        with self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_prepared_stage_replacement_is_not_accepted_as_current_source(self):
        original = engine.write_at
        def replaced(fd, name, data, mode, uid, gid):
            result = original(fd, name, data, mode, uid, gid)
            if name.endswith('.new'):
                os.unlink(name, dir_fd=fd)
                original(fd, name, b'foreign staging contents', mode, uid, gid)
            return result
        before = self.state()
        with mock.patch.object(engine, 'write_at', side_effect=replaced), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'recovery-required')


@unittest.skipUnless(shutil.which('zsh'), 'Zsh is required for routing tests')
class SystemRebindCliTests(unittest.TestCase):
    source = SystemRebindTests.source
    write_manifest = SystemRebindTests.write_manifest
    state = SystemRebindTests.state

    def setUp(self):
        SystemRebindTests.setUp(self)
        (self.repo / 'scripts').mkdir()
        (self.repo / 'stow').mkdir()
        shutil.copy2(ROOT / 'run.sh', self.repo / 'run.sh')
        shutil.copy2(ROOT / 'scripts/rebind-system-package', self.repo / 'scripts/rebind-system-package')
        (self.repo / 'runner.conf').write_text('RUNNER_ENV_PREFIX=FIXTURE\n')

    def cli(self, action, *args):
        environment = {'PATH': os.environ['PATH'], 'HOME': str(self.base),
                       'STOW_TARGET': str(self.base / 'unused user target'), 'PYTHONDONTWRITEBYTECODE': '1'}
        options = ['--journal-dir', str(self.journals)] if action == 'install' else []
        return subprocess.run(['zsh', str(self.repo / 'run.sh'), action, '--rebind-system',
                               '--from-repo', str(self.old), '--system-root', str(self.target),
                               *options, *args, 'demo'], env=environment, text=True,
                              capture_output=True, timeout=20)

    def test_cli_dry_run_inspection_and_exact_final_result(self):
        before = self.state()
        preview = self.cli('install', '--dry-run')
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn('REBINDABLE', preview.stdout)
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])
        self.assertEqual(self.cli('verify').returncode, 3)
        self.assertEqual(self.state(), before)
        result = self.cli('install', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cli('verify').returncode, 0)
        self.assertFalse((self.base / 'unused user target').exists())

    def test_cli_refuses_implicit_approval_and_mixed_modes_or_hooks(self):
        before = self.state()
        self.assertNotEqual(self.cli('install').returncode, 0)
        for flag in ('--rebind', '--verify', '--test', '--recover-dangling', '--force-links'):
            result = self.cli('install', '--yes', flag)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state(), before)

    def test_cli_never_runs_hooks_system_copy_or_services(self):
        marker = self.base / 'unexpected execution'
        for relative in ('scripts/system-copy-select', 'scripts/stow-select',
                         'packages/demo/install.hook.sh', 'packages/demo/verify.hook.sh'):
            path = self.repo / relative
            path.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            path.chmod(0o755)
        self.assertEqual(self.cli('install', '--yes').returncode, 0)
        self.assertFalse(marker.exists())

    def test_system_options_require_system_mode_and_helper_is_optional(self):
        for action in ('install', 'verify'):
            result = subprocess.run(['zsh', str(self.repo / 'run.sh'), action,
                                     '--rebind', '--system-root', str(self.target), 'demo'],
                                    text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires --rebind-system', result.stderr.replace('require --', 'requires --'))
        (self.repo / 'scripts/rebind-system-package').unlink()
        result = self.cli('install', '--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('optional system rebind helper is not installed', result.stderr)


if __name__ == '__main__':
    unittest.main()
