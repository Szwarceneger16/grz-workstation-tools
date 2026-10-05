"""Missing-checkout recovery: disposable targets, no live workstation actions."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

import test_runner_rebind as single
import test_runner_rebind_batch as batch

engine = single.engine


class RecoveryTests(unittest.TestCase):
    command = single.RebindTests.command
    link = single.RebindTests.link
    state = single.RebindTests.state

    def setUp(self):
        single.RebindTests.setUp(self)
        shutil.rmtree(self.old)

    def cli(self, *args):
        result = self.command('install', '--rebind', '--recover-dangling',
                              '--from-repo', str(self.old), *args, 'demo')
        self.clean_journals(result)
        return result

    def clean_journals(self, result):
        for line in result.stdout.splitlines():
            if line.startswith(('Rollback journal: ', 'Batch recovery journal: ')):
                path = Path(line.split(': ', 1)[1])
                self.assertTrue(path.parent.name.startswith('runner-rebind-'))
                self.addCleanup(shutil.rmtree, path.parent, True)

    def snapshot(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.prepare(self.repo, self.target, 'demo', [self.old], True)[1]

    def apply(self, snapshot):
        with contextlib.redirect_stdout(io.StringIO()):
            engine.apply(self.repo, self.target, 'demo', [self.old], snapshot)

    def test_dry_run_discloses_weaker_evidence_and_changes_nothing(self):
        before = self.state()
        result = self.cli('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('old payload and ownership cannot be verified', result.stdout)
        self.assertIn('recover-dangling: .local/bin/alpha', result.stdout)
        self.assertEqual(self.state(), before)

    def test_named_recovery_and_repeat_preserve_current_link_identity(self):
        result = self.cli('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        for rel in self.files:
            self.assertEqual((self.target / rel).resolve(), self.repo / 'packages/demo/install' / rel)
        before = [engine.identity(self.target / rel) for rel in self.files]
        result = self.cli('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('demo: unchanged;', result.stdout)
        self.assertEqual(before, [engine.identity(self.target / rel) for rel in self.files])

    def test_inspection_is_read_only_and_repair_hint_retains_recovery_flag(self):
        before = self.state()
        result = self.command('verify', '--rebind', '--recover-dangling',
                              '--from-repo', str(self.old), 'demo')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('--recover-dangling', result.stdout)
        self.assertEqual(self.state(), before)

    def test_recovery_is_opt_in_with_explicit_source_and_approval(self):
        before = self.state()
        for args in (
            ('install', '--rebind', '--from-repo', str(self.old), '--yes', 'demo'),
            ('install', '--rebind', '--recover-dangling', '--yes', 'demo'),
            ('install', '--recover-dangling', 'demo'),
            ('verify', '--recover-dangling', 'demo'),
        ):
            self.assertNotEqual(self.command(*args).returncode, 0)
        self.assertNotEqual(self.cli().returncode, 0)
        self.assertEqual(self.state(), before)

    def test_present_source_and_symlink_source_are_refused(self):
        for symlink in (False, True):
            if symlink:
                self.old.symlink_to(self.repo)
            else:
                self.old.mkdir()
            before = self.state()
            self.assertNotEqual(self.cli('--yes').returncode, 0)
            self.assertEqual(self.state(), before)
            self.old.unlink() if symlink else self.old.rmdir()

    def test_absolute_package_install_link_is_recovered(self):
        path = self.target / self.files[0]
        path.unlink()
        path.symlink_to(self.old / 'packages/demo/install' / self.files[0])
        self.assertEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(path.resolve(), self.repo / 'packages/demo/install' / self.files[0])

    def test_regular_foreign_wrong_package_and_wrong_path_are_not_overwritten(self):
        path = self.target / self.files[-1]
        for destination in (None, self.base / 'unrelated',
                            self.old / 'stow/other' / self.files[-1],
                            self.old / 'stow/demo/.local/bin/other'):
            path.unlink()
            path.write_text('owner data') if destination is None else path.symlink_to(destination)
            before = self.state()
            self.assertNotEqual(self.cli('--yes').returncode, 0)
            self.assertEqual(self.state(), before)
            if destination is None:
                self.assertEqual(path.read_text(), 'owner data')

    def test_indirect_link_and_noncanonical_text_are_refused_without_resolution(self):
        path = self.target / self.files[-1]
        indirect = self.base / 'indirect'
        indirect.symlink_to(self.old / 'stow/demo' / self.files[-1])
        for destination in (str(indirect), str(self.old) + '/extra/../stow/demo/' + self.files[-1]):
            path.unlink()
            path.symlink_to(destination)
            before = self.state()
            with mock.patch.object(engine.Path, 'resolve', side_effect=AssertionError('foreign resolve')):
                snapshot = engine.plan(self.repo, self.target, 'demo', [self.old], True)
            self.assertIn(self.files[-1], snapshot['conflicts'])
            self.assertEqual(self.state(), before)

    def test_rename_residue_is_refused_and_undeclared_links_are_not_scanned(self):
        old_path = '.local/bin/old-alpha'
        (self.repo / 'packages/demo/rebind-paths.manifest').write_text(old_path + ' ' + self.files[0] + '\n')
        extra = self.link(old_path)
        before = self.state()
        self.assertNotEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(self.state(), before)
        extra.unlink()
        extra = self.link('.local/bin/undeclared')
        raw = os.readlink(extra)
        self.assertEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(os.readlink(extra), raw)

    def test_linked_target_parent_blocks_all_changes(self):
        shutil.rmtree(self.target / '.local/bin')
        (self.target / '.local/bin').symlink_to(self.repo / 'packages/demo/install/.local/bin')
        before = self.state()
        self.assertNotEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(self.state(), before)

    def test_root_reappearing_after_approval_blocks_without_writes(self):
        snapshot = self.snapshot()
        before = self.state()
        self.old.mkdir()
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)

    def test_duplicate_relative_current_and_target_nested_roots_are_refused(self):
        before = self.state()
        for roots in ([str(self.old), str(self.old)], ['relative-checkout'],
                      [str(self.repo)], [str(self.target / 'lost')], ['/']):
            args = [value for root in roots for value in ('--from-repo', root)]
            result = self.command('install', '--rebind', '--recover-dangling',
                                  *args, '--yes', 'demo')
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state(), before)

    def test_two_explicit_missing_roots_recover_only_the_selected_leaves(self):
        other = self.base / 'other lost checkout'
        path = self.target / self.files[-1]
        path.unlink()
        path.symlink_to(other / 'packages/demo/install' / self.files[-1])
        before = self.state()
        self.assertNotEqual(self.cli('--dry-run').returncode, 0)
        self.assertEqual(self.state(), before)
        result = self.cli('--from-repo', str(other), '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        for rel in self.files:
            self.assertEqual((self.target / rel).resolve(), self.repo / 'packages/demo/install' / rel)

    def test_live_link_changed_after_approval_blocks_without_overwriting_writer(self):
        snapshot = self.snapshot()
        path = self.target / self.files[-1]
        path.unlink()
        path.symlink_to(self.base / 'another writer')
        before = self.state()
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)

    def test_current_payload_changed_after_approval_blocks_before_writes(self):
        snapshot = self.snapshot()
        before = self.state()
        (self.repo / 'packages/demo/install' / self.files[-1]).write_text('changed payload\n')
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)

    def test_missing_ancestor_replaced_by_symlink_blocks_without_writes(self):
        new_root = self.base / 'missing' / 'checkout'
        for rel in self.files:
            path = self.target / rel
            path.unlink()
            path.symlink_to(new_root / 'stow/demo' / rel)
        snapshot = engine.plan(self.repo, self.target, 'demo', [new_root], True)
        before = self.state()
        new_root.parent.symlink_to(self.repo)
        with self.assertRaises(engine.Refusal):
            engine.apply(self.repo, self.target, 'demo', [new_root], snapshot)
        self.assertEqual(self.state(), before)

    def test_failure_restores_exact_dangling_text_and_records_recovery_evidence(self):
        snapshot = self.snapshot()
        before = self.state()
        with mock.patch.object(engine, 'verify_result', side_effect=engine.Refusal('fixture final failure')):
            with self.assertRaises(engine.Refusal):
                self.apply(snapshot)
        self.assertEqual(self.state(), before)
        journal = next(self.base.glob('runner-rebind-journal-*/before.json'))
        self.assertTrue(json.loads(journal.read_text())['snapshot']['recover_dangling'])
        outcome = json.loads(journal.with_name('result.json').read_text())
        self.assertEqual(outcome['status'], 'rolled-back')
        self.assertEqual(outcome['retained_changes'], 0)

    def test_root_return_during_transaction_rolls_back(self):
        snapshot = self.snapshot()
        before = self.state()
        original = engine.os.replace
        def root_returns(src, dst, *args, **kwargs):
            result = original(src, dst, *args, **kwargs)
            if dst == 'alpha':
                self.old.mkdir()
            return result
        with mock.patch.object(engine.os, 'replace', side_effect=root_returns):
            with self.assertRaises(engine.Refusal):
                self.apply(snapshot)
        self.assertEqual(self.state(), before)

    def test_recovery_keeps_system_hooks_and_external_verification_out_of_scope(self):
        marker = self.base / 'unexpected'
        for name in ('packages/demo/install.hook.sh', 'packages/demo/verify.hook.sh',
                     'scripts/system-copy-select', 'scripts/stow-select'):
            path = self.repo / name
            path.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            path.chmod(0o755)
        self.assertEqual(self.cli('--yes').returncode, 0)
        self.assertFalse(marker.exists())


class RecoveryBatchTests(unittest.TestCase):
    command = single.RebindTests.command
    link = single.RebindTests.link
    state = single.RebindTests.state
    add_package = batch.RebindBatchTests.add_package
    assert_current = batch.RebindBatchTests.assert_current
    progress = batch.RebindBatchTests.progress
    clean_journals = RecoveryTests.clean_journals

    def setUp(self):
        batch.RebindBatchTests.setUp(self)
        shutil.rmtree(self.old)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.prepare_batch(self.repo, self.target, [self.old], True)

    def test_batch_rollback_only_failed_second_package_and_continue_third(self):
        selection, plans, failures = self.prepare()
        second_before = os.readlink(self.target / '.local/bin/second')
        original = engine.verify_result
        def fail_second(target, repo, package, snapshot):
            if package == 'second':
                raise engine.Refusal('fixture second-package failure')
            return original(target, repo, package, snapshot)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with mock.patch.object(engine, 'verify_result', side_effect=fail_second):
                with self.assertRaises(engine.Refusal):
                    engine.apply_batch(self.repo, self.target, selection, plans, failures)
        self.assert_current('demo', self.files)
        self.assert_current('third', ['.local/bin/third'])
        self.assertEqual(os.readlink(self.target / '.local/bin/second'), second_before)
        self.assertIn('second: rolled-back; retained link changes: 0', output.getvalue())
        results = self.progress()['packages']
        self.assertEqual(results['demo']['outcome']['status'], 'rebound')
        self.assertEqual(results['second']['outcome']['status'], 'rolled-back')
        self.assertEqual(results['third']['outcome']['status'], 'rebound')

    def test_cli_conflict_is_reported_while_other_packages_recover(self):
        path = self.target / '.local/bin/second'
        path.unlink()
        path.write_text('owner data')
        result = self.command('install', '--rebind', '--recover-dangling', '--from-repo',
                              str(self.old), '--yes', 'all-user')
        self.clean_journals(result)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('second: blocked; retained link changes: 0', result.stdout)
        self.assert_current('demo', self.files)
        self.assert_current('third', ['.local/bin/third'])
        self.assertEqual(path.read_text(), 'owner data')

    def test_batch_excludes_mutation_but_inspection_includes_excluded_package(self):
        (self.repo / 'manifests').mkdir()
        (self.repo / 'manifests/ignore-all-install.txt').write_text('second\n')
        second_before = os.readlink(self.target / '.local/bin/second')
        result = self.command('install', '--rebind', '--recover-dangling', '--from-repo',
                              str(self.old), '--yes', 'all-user')
        self.clean_journals(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('second: excluded;', result.stdout)
        self.assertEqual(os.readlink(self.target / '.local/bin/second'), second_before)
        result = self.command('verify', '--rebind', '--recover-dangling', '--from-repo',
                              str(self.old), 'all-user')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('3 packages, 1 need migration, 0 failed', result.stdout)

    def test_batch_dry_run_and_system_selectors_preserve_all_links(self):
        before = self.state()
        result = self.command('install', '--rebind', '--recover-dangling', '--from-repo',
                              str(self.old), '--dry-run', 'all-user')
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('demo', 'second', 'third'):
            self.assertIn(name + ': preview-only;', result.stdout)
        for selector in ('all', 'all-system'):
            result = self.command('install', '--rebind', '--recover-dangling', '--from-repo',
                                  str(self.old), '--yes', selector)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state(), before)
