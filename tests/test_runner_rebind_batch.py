"""Aggregate rebind, with real projection and disposable installation targets."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import unittest
from unittest import mock

import test_runner_rebind as single

engine = single.engine


class RebindBatchTests(unittest.TestCase):
    command = single.RebindTests.command
    link = single.RebindTests.link
    state = single.RebindTests.state

    def setUp(self):
        single.RebindTests.setUp(self)
        self.add_package('second', ['.local/bin/second'])
        self.add_package('third', ['.local/bin/third'])

    def add_package(self, package, paths, linked=True):
        for root in (self.repo, self.old):
            source = root / 'packages' / package / 'install'
            source.mkdir(parents=True)
            (root / 'stow' / package).symlink_to(f'../packages/{package}/install')
            for relative in paths:
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture\n')
        if linked:
            for relative in paths:
                path = self.target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(self.old / 'stow' / package / relative)

    def prepare(self, explicit=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.prepare_batch(self.repo, self.target, [self.old] if explicit else [])

    def apply(self, prepared=None):
        selection, plans, failures = prepared or self.prepare()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            engine.apply_batch(self.repo, self.target, selection, plans, failures)
        return output.getvalue()

    def progress(self):
        paths = list(self.base.glob('runner-rebind-batch-*/progress.json'))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(paths[0].parent.stat().st_mode & 0o777, 0o700)
        return json.loads(paths[0].read_text())

    def assert_current(self, package, paths):
        for relative in paths:
            self.assertEqual((self.target / relative).resolve(),
                             self.repo / 'packages' / package / 'install' / relative)

    def test_cli_dry_run_preflights_every_package_without_changes(self):
        before = self.state()
        result = self.command('install', '--rebind', '--from-repo', str(self.old), '--dry-run', 'all-user')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Selected user packages: demo, second, third', result.stdout)
        for name in ('demo', 'second', 'third'):
            self.assertIn('Package: ' + name, result.stdout)
            self.assertIn(f'Package result: {name}: preview-only; retained link changes: 0', result.stdout)
        self.assertEqual(self.state(), before)

    def test_cli_batch_succeeds_without_running_hooks_or_system_tools(self):
        marker = self.base / 'unexpected'
        for name in ('demo', 'second', 'third'):
            for hook in ('install.hook.sh', 'verify.hook.sh'):
                path = self.repo / 'packages' / name / hook
                path.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
                path.chmod(0o755)
            system = self.repo / 'packages' / name / 'system-install'
            system.mkdir()
            (system / 'example').write_text('system fixture')
        for tool in ('stow-select', 'system-copy-select'):
            path = self.repo / 'scripts' / tool
            path.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            path.chmod(0o755)
        result = self.command('install', '--rebind', '--from-repo', str(self.old), '--yes', 'all-user')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertIn('Batch completed packages: demo, second, third', result.stdout)
        for name, paths in (('demo', self.files), ('second', ['.local/bin/second']), ('third', ['.local/bin/third'])):
            self.assert_current(name, paths)
        for line in result.stdout.splitlines():
            if line.startswith(('Rollback journal: ', 'Batch recovery journal: ')):
                journal = Path(line.split(': ', 1)[1])
                self.addCleanup(shutil.rmtree, journal.parent, True)

    def test_exclusions_apply_to_mutation_but_inspection_includes_them(self):
        (self.repo / 'manifests').mkdir()
        (self.repo / 'manifests/ignore-all-install.txt').write_text('# fixture policy\nsecond\n')
        before = os.readlink(self.target / '.local/bin/second')
        selection, prepared, failures = self.prepare()
        self.assertEqual(selection['selected'], ['demo', 'third'])
        self.assertEqual(selection['excluded'], ['second'])
        output = self.apply((selection, prepared, failures))
        self.assertIn('Package result: second: excluded; retained link changes: 0', output)
        self.assertEqual(os.readlink(self.target / '.local/bin/second'), before)
        result = self.command('verify', '--rebind', 'all-user')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('3 packages, 1 need migration, 0 failed', result.stdout)

    def test_preflight_conflict_skips_only_affected_package_and_migrates_others(self):
        path = self.target / '.local/bin/second'
        path.unlink()
        path.write_text('owner data')
        before = self.state()
        result = self.command('install', '--rebind', '--from-repo', str(self.old), '--yes', 'all-user')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Package: third', result.stdout)
        self.assertIn('batch completed with package failures: second', result.stderr)
        self.assertIn('Package result: second: blocked; retained link changes: 0', result.stdout)
        for name in ('demo', 'third'):
            self.assertIn(f'Package result: {name}: rebound;', result.stdout)
        self.assert_current('demo', self.files)
        self.assert_current('third', ['.local/bin/third'])
        self.assertEqual(path.read_text(), 'owner data')
        for line in result.stdout.splitlines():
            if line.startswith(('Rollback journal: ', 'Batch recovery journal: ')):
                self.addCleanup(shutil.rmtree, Path(line.split(': ', 1)[1]).parent, True)

    def test_duplicate_and_prefix_overlapping_destinations_are_refused(self):
        for path in self.target.rglob('*'):
            if path.is_symlink():
                path.unlink()
        for relative in ('.local/bin/alpha', '.local/bin/alpha/child'):
            with self.subTest(relative=relative):
                source = self.repo / 'packages/second/install' / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('fixture')
                with self.assertRaisesRegex(engine.Refusal, 'overlapping batch destinations'):
                    self.prepare(False)
                self.assertEqual(self.state(), {})
                source.unlink()

    def test_invalid_mapping_or_exclusion_policy_refuses_with_zero_writes(self):
        policy = self.repo / 'manifests/ignore-all-install.txt'
        policy.parent.mkdir()
        policy.symlink_to(self.base / 'absent')
        before = self.state()
        with self.assertRaises(engine.Refusal):
            self.prepare()
        policy.unlink()
        policy.write_text('../escape\n')
        with self.assertRaises(engine.Refusal):
            self.prepare()
        policy.unlink()
        link = self.repo / 'stow/third'
        link.unlink()
        link.symlink_to('../packages/second/install')
        with self.assertRaises(engine.Refusal):
            self.prepare()
        self.assertEqual(self.state(), before)

    def test_empty_selection_refuses(self):
        (self.repo / 'manifests').mkdir()
        (self.repo / 'manifests/ignore-all-install.txt').write_text('demo\nsecond\nthird\n')
        with self.assertRaisesRegex(engine.Refusal, 'no user packages selected'):
            self.prepare()

    def test_explicit_roots_retain_per_package_validation(self):
        shutil.rmtree(self.old / 'packages/third')
        before = self.state()
        with contextlib.redirect_stderr(io.StringIO()):
            selection, prepared, failures = self.prepare()
        self.assertEqual(list(failures), ['third'])
        self.assertEqual(list(prepared), ['demo', 'second'])
        self.assertEqual(self.state(), before)

    def test_discovery_can_bind_different_roots_for_different_packages(self):
        other = self.base / 'another source'
        shutil.copytree(self.old, other, symlinks=True)
        path = self.target / '.local/bin/second'
        path.unlink()
        path.symlink_to(other / 'stow/second/.local/bin/second')
        selection, prepared, failures = self.prepare(False)
        self.assertEqual(prepared['demo'][0], [self.old])
        self.assertEqual(prepared['second'][0], [other])
        self.apply((selection, prepared, failures))
        self.assert_current('second', ['.local/bin/second'])

    def test_bare_yes_never_authorizes_discovery(self):
        before = self.state()
        result = self.command('install', '--rebind', '--yes', 'all-user')
        self.assertEqual(result.returncode, 1)
        self.assertIn('--yes requires explicit --from-repo', result.stderr)
        for name in ('demo', 'second', 'third'):
            self.assertIn(f'Package result: {name}: not-started; retained link changes: 0', result.stdout)
        self.assertEqual(self.state(), before)

    def interactive(self, reply):
        argv = ['rebind', '--target', str(self.target), '--package', 'all-user']
        with mock.patch.object(engine, '__file__', str(self.repo / 'scripts/rebind-user-package')), \
             mock.patch.object(sys, 'argv', argv), mock.patch.object(sys.stdin, 'isatty', return_value=True), \
             mock.patch('builtins.input', side_effect=reply) as prompt, contextlib.redirect_stdout(io.StringIO()):
            result = engine.main()
        self.assertEqual(prompt.call_count, 1)
        return result

    def test_one_confirmation_covers_the_exact_complete_batch(self):
        before = self.state()
        def reply(prompt):
            self.assertEqual(self.state(), before)
            self.assertIn('all-user', prompt)
            return 'REBIND'
        self.assertEqual(self.interactive(reply), 0)
        self.assertEqual(self.progress()['state'], 'completed')

    def test_cancelled_batch_has_zero_writes(self):
        before = self.state()
        with self.assertRaises(engine.Refusal):
            self.interactive(lambda prompt: 'no')
        self.assertEqual(self.state(), before)

    def test_last_source_change_during_confirmation_blocks_only_that_package(self):
        before = self.state()
        def reply(prompt):
            (self.repo / 'packages/third/install/.local/bin/third').write_text('changed after preview')
            return 'REBIND'
        with self.assertRaises(engine.Refusal):
            self.interactive(reply)
        self.assert_current('demo', self.files)
        self.assert_current('second', ['.local/bin/second'])
        self.assertEqual(os.readlink(self.target / '.local/bin/third'), before['.local/bin/third'])
        self.assertEqual(self.progress()['packages']['third']['outcome']['status'], 'not-started')

    def test_selection_change_after_approval_refuses_every_write(self):
        prepared = self.prepare()
        before = self.state()
        (self.repo / 'manifests').mkdir()
        (self.repo / 'manifests/ignore-all-install.txt').write_text('second\n')
        with self.assertRaisesRegex(engine.Refusal, 'selection changed'):
            self.apply(prepared)
        self.assertEqual(self.state(), before)

    def test_parent_replacement_after_approval_is_refused(self):
        prepared = self.prepare()
        original = self.target / '.local/bin'
        original.rename(original.with_name('saved'))
        original.mkdir()
        with self.assertRaises(engine.Refusal):
            self.apply(prepared)
        self.assertFalse(list(original.iterdir()))

    def test_shared_missing_parents_are_created_once_and_owned_by_batch(self):
        self.add_package('shared-a', ['.config/shared/a'], linked=False)
        self.add_package('shared-b', ['.config/shared/b'], linked=False)
        self.apply()
        self.assert_current('shared-a', ['.config/shared/a'])
        self.assert_current('shared-b', ['.config/shared/b'])
        self.assertEqual(self.progress()['state'], 'completed')

    def test_batch_combines_current_missing_legacy_and_validated_rename(self):
        current = self.target / self.files[0]
        current.unlink()
        current.symlink_to(self.repo / 'stow/demo' / self.files[0])
        before = engine.identity(current)
        oldrel, newrel = '.local/bin/second', '.local/bin/second-new'
        (self.repo / 'packages/second/install' / oldrel).rename(
            self.repo / 'packages/second/install' / newrel)
        (self.repo / 'packages/second/rebind-paths.manifest').write_text(oldrel + ' ' + newrel + '\n')
        local_json = self.repo / 'packages/third/install/.config/example/local.json'
        local_json.parent.mkdir(parents=True)
        local_json.write_bytes(b'{"local": "uncommitted owner settings"}\n')
        payload = local_json.read_bytes()
        self.apply()
        self.assertEqual(engine.identity(current), before)
        self.assertFalse((self.target / oldrel).is_symlink())
        self.assert_current('second', [newrel])
        self.assert_current('third', ['.local/bin/third', '.config/example/local.json'])
        self.assertEqual(local_json.read_bytes(), payload)

    def test_batch_journal_binds_original_links_and_source_digests(self):
        before = self.state()
        self.apply()
        progress = self.progress()
        plans = progress['plans']
        self.assertEqual(plans['demo']['roots'], [str(self.old)])
        for row in plans['demo']['snapshot']['rows']:
            self.assertEqual(row['old'], before[row['path']])
        self.assertEqual(len(plans['third']['snapshot']['files']['.local/bin/third'][1]), 64)

    def test_parent_replacement_during_staging_refuses_publication(self):
        before = self.state()
        original = engine.os.symlink
        moved = self.target / '.local/saved-bin'
        def raced(*args, **kwargs):
            result = original(*args, **kwargs)
            if 'dir_fd' in kwargs and not moved.exists():
                (self.target / '.local/bin').rename(moved)
                (self.target / '.local/bin').mkdir()
            return result
        with mock.patch.object(engine.os, 'symlink', side_effect=raced), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertFalse(list((self.target / '.local/bin').iterdir()))
        self.assertEqual(os.readlink(moved / 'alpha'), before['.local/bin/alpha'])
        self.assertFalse(list(moved.glob('.runner-rebind-*')))

    def test_selection_change_between_packages_stops_before_next_transaction(self):
        original = engine.apply_locked
        def changed(repo, target, package, *args):
            result = original(repo, target, package, *args)
            if package == 'demo':
                (repo / 'manifests').mkdir()
                (repo / 'manifests/ignore-all-install.txt').write_text('third\n')
            return result
        with mock.patch.object(engine, 'apply_locked', side_effect=changed), self.assertRaises(engine.Refusal):
            self.apply()
        self.assert_current('demo', self.files)
        self.assertEqual(self.progress()['packages']['third']['state'], 'unattempted')

    def test_signal_at_completed_publication_keeps_durably_recorded_package(self):
        original = engine.write_progress
        sent = False
        def interrupted(path, progress):
            nonlocal sent
            result = original(path, progress)
            if progress['packages']['demo']['state'] == 'completed' and not sent:
                sent = True
                os.kill(os.getpid(), signal.SIGTERM)
            return result
        def handler(signum, frame):
            raise engine.Interrupted('injected boundary signal')
        previous = signal.signal(signal.SIGTERM, handler)
        try:
            with mock.patch.object(engine, 'write_progress', side_effect=interrupted), self.assertRaises(engine.Refusal):
                self.apply()
        finally:
            signal.signal(signal.SIGTERM, previous)
        self.assert_current('demo', self.files)
        progress = self.progress()
        self.assertEqual(progress['packages']['demo']['state'], 'completed')
        self.assertEqual(progress['packages']['second']['state'], 'unattempted')

    def test_lock_contention_blocks_batch_without_journal_or_writes(self):
        prepared = self.prepare()
        before = self.state()
        with engine.target_lock(self.target), self.assertRaises(BlockingIOError):
            self.apply(prepared)
        self.assertEqual(self.state(), before)
        self.assertFalse(list(self.base.glob('runner-rebind-batch-*')))

    def test_mid_batch_failure_rolls_back_only_failed_package_and_reports_rest(self):
        original = engine.verify_result
        before = self.state()
        def fail(target, repo, package, snapshot):
            if package == 'second':
                raise engine.Refusal('injected final verification failure')
            return original(target, repo, package, snapshot)
        with mock.patch.object(engine, 'verify_result', side_effect=fail), self.assertRaises(engine.Refusal):
            self.apply()
        self.assert_current('demo', self.files)
        self.assertEqual(os.readlink(self.target / '.local/bin/second'), before['.local/bin/second'])
        self.assert_current('third', ['.local/bin/third'])
        progress = self.progress()
        self.assertEqual({name: result['state'] for name, result in progress['packages'].items()},
                         {'demo': 'completed', 'second': 'failed', 'third': 'completed'})
        self.assertTrue(Path(progress['packages']['second']['journal']).is_file())
        self.assertFalse(list(self.target.rglob('.runner-rebind-*')))
        # Resumption is a new full preflight, preserving completed current links.
        self.apply()
        self.assert_current('third', ['.local/bin/third'])

    def test_between_package_race_keeps_concurrent_data_and_completed_package(self):
        original = engine.apply_locked
        def raced(repo, target, package, *args):
            result = original(repo, target, package, *args)
            if package == 'demo':
                path = target / '.local/bin/second'
                path.unlink()
                path.write_text('concurrent data')
            return result
        with mock.patch.object(engine, 'apply_locked', side_effect=raced), self.assertRaises(engine.Refusal):
            self.apply()
        self.assert_current('demo', self.files)
        self.assertEqual((self.target / '.local/bin/second').read_text(), 'concurrent data')
        self.assert_current('third', ['.local/bin/third'])

    def test_handled_signal_in_second_package_restores_its_original_link(self):
        original = engine.os.replace
        before = self.state()
        def interrupted(src, dst, *args, **kwargs):
            result = original(src, dst, *args, **kwargs)
            if dst == 'second' and 'dst_dir_fd' in kwargs:
                os.kill(os.getpid(), signal.SIGTERM)
            return result
        def handler(signum, frame):
            raise engine.Interrupted('injected signal')
        previous = signal.signal(signal.SIGTERM, handler)
        try:
            with mock.patch.object(engine.os, 'replace', side_effect=interrupted), self.assertRaises(engine.Refusal):
                self.apply()
        finally:
            signal.signal(signal.SIGTERM, previous)
        self.assert_current('demo', self.files)
        self.assertEqual(os.readlink(self.target / '.local/bin/second'), before['.local/bin/second'])
        self.assertEqual(self.progress()['packages']['third']['state'], 'unattempted')

    def test_progress_write_failure_does_not_claim_rolled_back_package_completed(self):
        original = engine.write_progress
        before = self.state()
        def fail(path, progress):
            if progress['packages']['second']['state'] == 'completed':
                raise OSError('injected journal write failure')
            return original(path, progress)
        with mock.patch.object(engine, 'write_progress', side_effect=fail), self.assertRaises(engine.Refusal):
            self.apply()
        self.assert_current('demo', self.files)
        self.assertEqual(os.readlink(self.target / '.local/bin/second'), before['.local/bin/second'])
        self.assertEqual(self.progress()['packages']['second']['state'], 'failed')
        self.assert_current('third', ['.local/bin/third'])

    def test_final_batch_verification_failure_preserves_completed_transactions(self):
        original = engine.verify_result
        calls = 0
        def fail(*args):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise engine.Refusal('injected final batch failure')
            return original(*args)
        with mock.patch.object(engine, 'verify_result', side_effect=fail), self.assertRaises(engine.Refusal):
            self.apply()
        progress = self.progress()
        self.assertEqual(progress['state'], 'failed')
        self.assertEqual(progress['stage'], 'complete')
        self.assertTrue(all(result['state'] == 'completed' for result in progress['packages'].values()))

    def test_batch_reports_unchanged_rollback_and_later_success_separately(self):
        for rel in self.files:
            (self.target / rel).unlink()
            self.link(rel, self.repo)
        original = engine.verify_result
        def fail(target, repo, package, snapshot):
            if package == 'second':
                raise engine.Refusal('injected')
            return original(target, repo, package, snapshot)
        selection, plans, failures = self.prepare()
        with mock.patch.object(engine, 'verify_result', side_effect=fail), \
                contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(engine.Refusal):
            engine.apply_batch(self.repo, self.target, selection, plans, failures)
        for name, status in (('demo', 'unchanged'), ('second', 'rolled-back')):
            self.assertIn(f'Package result: {name}: {status}; retained link changes: 0', output.getvalue())
        self.assertIn('Package result: third: rebound; retained link changes: 1', output.getvalue())
        outcomes = self.progress()['packages']
        self.assertEqual(outcomes['demo']['outcome']['verification'], 'current')
        self.assertEqual(outcomes['second']['outcome']['verification'], 'original')

    def test_batch_reports_incomplete_package_rollback_without_claiming_zero_changes(self):
        original = engine.verify_result
        def race(target, repo, package, snapshot):
            if package == 'second':
                path = target / '.local/bin/second'
                path.unlink()
                path.write_text('concurrent data')
                raise engine.Refusal('injected')
            return original(target, repo, package, snapshot)
        selection, plans, failures = self.prepare()
        with mock.patch.object(engine, 'verify_result', side_effect=race), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(engine.Refusal):
            engine.apply_batch(self.repo, self.target, selection, plans, failures)
        self.assertIn('Package result: demo: rebound; retained link changes: 2', output.getvalue())
        self.assertIn('Package result: second: manual-recovery; retained link changes: unknown', output.getvalue())
        self.assertIn('Manual recovery check: .local/bin/second', output.getvalue())
        self.assertIn('Package result: third: rebound; retained link changes: 1', output.getvalue())
        outcome = self.progress()['packages']['second']['outcome']
        self.assertEqual(outcome['recovery_paths'], ['.local/bin/second'])
        self.assertIsNone(outcome['retained_changes'])

    def test_failure_rechecks_completed_packages_under_the_same_target_lock(self):
        original = engine.verify_result
        failed = False
        lock_checks = []
        def fail(target, repo, package, snapshot):
            nonlocal failed
            if package == 'second':
                failed = True
                path = target / self.files[0]
                path.unlink()
                path.write_text('concurrent data')
                raise engine.Refusal('injected')
            if failed:
                with self.assertRaises(BlockingIOError), engine.target_lock(target):
                    pass
                lock_checks.append(package)
            return original(target, repo, package, snapshot)
        selection, plans, failures = self.prepare()
        with mock.patch.object(engine, 'verify_result', side_effect=fail), \
                contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(engine.Refusal):
            engine.apply_batch(self.repo, self.target, selection, plans, failures)
        self.assertIn('demo', lock_checks)
        self.assertIn('Package result: demo: final-state-unverified; retained link changes: unknown', output.getvalue())
        self.assertEqual(self.progress()['packages']['demo']['outcome']['status'], 'final-state-unverified')
        self.assertEqual((self.target / self.files[0]).read_text(), 'concurrent data')

    def test_early_apply_refusal_reports_every_package_with_zero_retained_changes(self):
        selection, plans, failures = self.prepare()
        with engine.target_lock(self.target), contextlib.redirect_stdout(io.StringIO()) as output, \
                self.assertRaises(BlockingIOError):
            engine.apply_batch(self.repo, self.target, selection, plans, failures)
        for name in selection['selected']:
            self.assertIn(f'Package result: {name}: unattempted; retained link changes: 0', output.getvalue())
        self.assertIn('Batch status: failed; stage: before-writes', output.getvalue())
        self.assertFalse(list(self.base.glob('runner-rebind-batch-*')))

    def test_failed_package_removes_its_shared_new_directory_before_next_package(self):
        for root in (self.repo, self.old):
            source = root / 'packages/second/install/.config/shared/second'
            source.parent.mkdir(parents=True)
            source.write_text('fixture')
            source = root / 'packages/third/install/.config/shared/third'
            source.parent.mkdir(parents=True)
            source.write_text('fixture')
        original = engine.verify_result
        def fail(target, repo, package, snapshot):
            if package == 'second':
                raise engine.Refusal('injected')
            return original(target, repo, package, snapshot)
        with mock.patch.object(engine, 'verify_result', side_effect=fail), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertFalse((self.target / '.config/shared/second').exists())
        self.assert_current('third', ['.config/shared/third', '.local/bin/third'])
        self.assertEqual(self.progress()['packages']['second']['outcome']['status'], 'rolled-back')

    def test_multiple_package_failures_are_recorded_and_later_package_still_succeeds(self):
        original = engine.verify_result
        before = self.state()
        def fail(target, repo, package, snapshot):
            if package in ('demo', 'second'):
                raise engine.Refusal('injected ' + package)
            return original(target, repo, package, snapshot)
        with mock.patch.object(engine, 'verify_result', side_effect=fail), self.assertRaises(engine.Refusal):
            self.apply()
        for path in self.files + ['.local/bin/second']:
            self.assertEqual(os.readlink(self.target / path), before[path])
        self.assert_current('third', ['.local/bin/third'])
        progress = self.progress()
        self.assertEqual(progress['stage'], 'complete')
        for name in ('demo', 'second'):
            self.assertEqual(progress['packages'][name]['outcome']['status'], 'rolled-back')
            self.assertEqual(progress['packages'][name]['error'], 'injected ' + name)

    def test_persistent_batch_journal_error_stops_before_next_package(self):
        original = engine.write_progress
        def fail(path, progress):
            if progress['packages']['second']['state'] in ('running', 'failed'):
                raise OSError('persistent journal failure')
            return original(path, progress)
        before = self.state()
        with mock.patch.object(engine, 'write_progress', side_effect=fail), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(OSError):
            self.apply()
        self.assert_current('demo', self.files)
        for rel in ('.local/bin/second', '.local/bin/third'):
            self.assertEqual(os.readlink(self.target / rel), before[rel])

    def test_failed_batch_dry_run_reports_blocked_package_and_changes_nothing(self):
        path = self.target / '.local/bin/second'
        path.unlink()
        path.write_text('owner data')
        before = self.state()
        result = self.command('install', '--rebind', '--from-repo', str(self.old), '--dry-run', 'all-user')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Package result: second: blocked; retained link changes: 0', result.stdout)
        for name in ('demo', 'third'):
            self.assertIn(f'Package result: {name}: preview-only; retained link changes: 0', result.stdout)
        self.assertEqual(self.state(), before)
        self.assertEqual(path.read_text(), 'owner data')


if __name__ == '__main__':
    unittest.main()
