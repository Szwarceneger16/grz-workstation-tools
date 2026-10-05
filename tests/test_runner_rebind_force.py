"""Explicit leaf-link replacement in disposable repositories and targets."""
import argparse
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


class ForceLinkTests(unittest.TestCase):
    command = single.RebindTests.command
    link = single.RebindTests.link
    state = single.RebindTests.state

    def setUp(self):
        single.RebindTests.setUp(self)
        self.foreign = self.base / 'foreign payload'
        self.foreign.write_text('owner data\n')
        self.force_leaf(self.files[0])

    def force_leaf(self, rel, destination=None):
        path = self.target / rel
        path.unlink()
        path.symlink_to(destination or self.foreign)
        return path

    def clean_journals(self, result):
        for line in result.stdout.splitlines():
            if line.startswith(('Rollback journal: ', 'Batch recovery journal: ')):
                path = Path(line.split(': ', 1)[1])
                self.assertTrue(path.parent.name.startswith('runner-rebind-'))
                self.addCleanup(shutil.rmtree, path.parent, True)

    def cli(self, *args):
        result = self.command('install', '--rebind', '--force-links', '--from-repo',
                              str(self.old), *args, 'demo')
        self.clean_journals(result)
        return result

    def snapshot(self, recover=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.prepare(self.repo, self.target, 'demo', [self.old], recover, True)[1]

    def apply(self, snapshot):
        with contextlib.redirect_stdout(io.StringIO()):
            engine.apply(self.repo, self.target, 'demo', [self.old], snapshot)

    def test_dry_run_discloses_unproven_old_text_and_new_link(self):
        before = self.state()
        result = self.cli('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('force-link: ' + self.files[0], result.stdout)
        self.assertIn('targets and payload are not inspected', result.stdout)
        self.assertIn(json.dumps(str(self.foreign)), result.stdout)
        self.assertIn('replace link text:', result.stdout)
        self.assertEqual(self.state(), before)

    def test_healthy_foreign_leaf_replaced_without_changing_foreign_payload(self):
        before = (self.foreign.read_bytes(), engine.identity(self.foreign))
        result = self.cli('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / self.files[0]).resolve(),
                         self.repo / 'packages/demo/install' / self.files[0])
        self.assertEqual(before, (self.foreign.read_bytes(), engine.identity(self.foreign)))
        journal = Path(next(line.split(': ', 1)[1] for line in result.stdout.splitlines()
                            if line.startswith('Rollback journal: ')))
        saved = json.loads(journal.read_text())['snapshot']
        self.assertTrue(saved['force_links'])
        self.assertEqual(saved['rows'][0]['old'], str(self.foreign))

    def test_dangling_and_directory_target_leaves_replace_only_the_link(self):
        for destination in (self.base / 'absent', self.old / 'packages/demo/install'):
            self.force_leaf(self.files[0], destination)
            result = self.cli('--yes')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((self.old / 'packages/demo/install').is_dir())

    def test_indirect_foreign_chain_is_not_resolved_or_read(self):
        indirect = self.base / 'indirect'
        indirect.symlink_to(self.foreign)
        for rel in self.files:
            self.force_leaf(rel, indirect)
        original = Path.read_bytes
        def read_known(path):
            self.assertNotIn(path, (indirect, self.foreign))
            return original(path)
        with mock.patch.object(engine.Path, 'resolve', side_effect=AssertionError('foreign resolution')):
            with mock.patch.object(engine.Path, 'read_bytes', new=read_known):
                snapshot = engine.plan(self.repo, self.target, 'demo', [self.old], force_links=True)
        self.assertTrue(all(row['state'] == 'force-link' for row in snapshot['rows']))
        self.apply(snapshot)
        self.assertEqual(self.foreign.read_text(), 'owner data\n')
        self.assertEqual(os.readlink(indirect), str(self.foreign))

    def test_without_force_existing_refusal_and_ordinary_commands_are_preserved(self):
        before = self.state()
        for args in (('install', '--rebind', '--from-repo', str(self.old), '--yes', 'demo'),
                     ('install', '--force-links', 'demo'), ('verify', '--force-links', 'demo'),
                     ('install', '--rebind', '--force', '--from-repo', str(self.old), 'demo')):
            self.assertNotEqual(self.command(*args).returncode, 0)
        self.assertEqual(self.state(), before)

    def test_explicit_root_and_approval_are_mandatory_even_when_forcing(self):
        before = self.state()
        result = self.command('install', '--rebind', '--force-links', '--yes', 'demo')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--force-links requires explicit --from-repo', result.stderr)
        self.assertNotEqual(self.cli().returncode, 0)
        self.assertEqual(self.state(), before)

    def test_interactive_approval_requires_the_distinct_force_phrase(self):
        args = argparse.Namespace(yes=False, package='demo', force_links=True)
        with mock.patch.object(engine.sys.stdin, 'isatty', return_value=True):
            with mock.patch('builtins.input', return_value='REBIND'):
                with self.assertRaises(engine.Refusal):
                    engine.approve(args, [self.old])
            with mock.patch('builtins.input', return_value='FORCE REBIND') as prompt:
                engine.approve(args, [self.old])
                self.assertIn('FORCE REBIND', prompt.call_args.args[0])

    def test_regular_file_directory_and_fifo_remain_conflicts(self):
        path = self.target / self.files[-1]
        for kind in ('file', 'directory', 'fifo'):
            path.unlink()
            if kind == 'file':
                path.write_text('private fixture data')
            elif kind == 'directory':
                path.mkdir()
            else:
                os.mkfifo(path)
            before = self.state()
            self.assertNotEqual(self.cli('--yes').returncode, 0)
            self.assertEqual(self.state(), before)
            self.assertEqual(self.foreign.read_text(), 'owner data\n')
            if kind == 'file':
                self.assertEqual(path.read_text(), 'private fixture data')
            path.rmdir() if kind == 'directory' else path.unlink()
            self.link(self.files[-1])

    def test_control_characters_in_link_text_are_refused(self):
        self.force_leaf(self.files[0], str(self.foreign) + '\nunsafe')
        before = self.state()
        result = self.cli('--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unsafe link text', result.stderr)
        self.assertEqual(self.state(), before)

    def test_symlinked_parent_and_invalid_package_inventory_are_not_bypassed(self):
        before = self.state()
        payload = self.repo / 'packages/demo/install' / self.files[-1]
        payload.unlink()
        payload.symlink_to(self.foreign)
        self.assertNotEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(self.state(), before)
        payload.unlink()
        payload.write_text('fixture\n')
        shutil.rmtree(self.target / '.local/bin')
        (self.target / '.local/bin').symlink_to(self.old / 'packages/demo/install/.local/bin')
        before = self.state()
        self.assertNotEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(self.state(), before)

    def test_force_does_not_delete_rename_or_unmapped_legacy_residue(self):
        rel = '.local/bin/old-alpha'
        self.link(rel)
        (self.repo / 'packages/demo/rebind-paths.manifest').write_text(rel + ' ' + self.files[0] + '\n')
        before = self.state()
        self.assertNotEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(self.state(), before)

    def test_missing_root_requires_recovery_and_combined_modes_retain_both_flags(self):
        shutil.rmtree(self.old)
        before = self.state()
        self.assertNotEqual(self.cli('--dry-run').returncode, 0)
        self.assertEqual(self.state(), before)
        result = self.command('verify', '--rebind', '--recover-dangling', '--force-links',
                              '--from-repo', str(self.old), 'demo')
        self.assertEqual(result.returncode, 3, result.stderr)
        hint = next(line for line in result.stdout.splitlines() if line.startswith('Review explicit dry-run: '))
        self.assertIn('--force-links', hint)
        self.assertIn('--recover-dangling', hint)
        self.assertEqual(self.state(), before)
        result = self.cli('--recover-dangling', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_force_inspection_is_read_only_and_current_links_remain_idempotent(self):
        before = self.state()
        result = self.command('verify', '--rebind', '--force-links', '--from-repo', str(self.old), 'demo')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('--force-links', result.stdout)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.cli('--yes').returncode, 0)
        ids = [engine.identity(self.target / rel) for rel in self.files]
        self.assertEqual(self.cli('--yes').returncode, 0)
        self.assertEqual(ids, [engine.identity(self.target / rel) for rel in self.files])

    def test_rollback_restores_old_foreign_text_and_leaves_its_payload_untouched(self):
        snapshot = self.snapshot()
        before = self.state()
        with mock.patch.object(engine, 'verify_result', side_effect=engine.Refusal('fixture failure')):
            with self.assertRaises(engine.Refusal):
                self.apply(snapshot)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.foreign.read_text(), 'owner data\n')
        outcome = json.loads(next(self.base.glob('runner-rebind-journal-*/result.json')).read_text())
        self.assertEqual(outcome['status'], 'rolled-back')
        self.assertEqual(outcome['retained_changes'], 0)

    def test_changed_leaf_after_approval_is_not_overwritten(self):
        snapshot = self.snapshot()
        self.force_leaf(self.files[0], self.base / 'new writer')
        before = self.state()
        with self.assertRaises(engine.Refusal):
            self.apply(snapshot)
        self.assertEqual(self.state(), before)

    def test_concurrent_writer_during_rollback_is_preserved_and_reported(self):
        snapshot = self.snapshot()
        path = self.target / self.files[0]
        def concurrent_failure(*args):
            path.unlink()
            path.write_text('concurrent owner data')
            raise engine.Refusal('fixture failure')
        with mock.patch.object(engine, 'verify_result', side_effect=concurrent_failure):
            with self.assertRaises(engine.Refusal):
                self.apply(snapshot)
        self.assertEqual(path.read_text(), 'concurrent owner data')
        outcome = json.loads(next(self.base.glob('runner-rebind-journal-*/result.json')).read_text())
        self.assertEqual(outcome['status'], 'manual-recovery')
        self.assertIn(self.files[0], outcome['recovery_paths'])

    def test_force_never_runs_hooks_or_system_helpers(self):
        marker = self.base / 'unexpected'
        for name in ('packages/demo/install.hook.sh', 'packages/demo/verify.hook.sh',
                     'scripts/stow-select', 'scripts/system-copy-select'):
            path = self.repo / name
            path.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            path.chmod(0o755)
        self.assertEqual(self.cli('--yes').returncode, 0)
        self.assertFalse(marker.exists())


class ForceBatchTests(unittest.TestCase):
    command = single.RebindTests.command
    link = single.RebindTests.link
    state = single.RebindTests.state
    add_package = batch.RebindBatchTests.add_package
    assert_current = batch.RebindBatchTests.assert_current
    progress = batch.RebindBatchTests.progress
    clean_journals = ForceLinkTests.clean_journals

    def setUp(self):
        batch.RebindBatchTests.setUp(self)
        for rel in (self.files[0], '.local/bin/second', '.local/bin/third'):
            path = self.target / rel
            path.unlink()
            path.symlink_to(self.base / ('foreign-' + path.name))

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.prepare_batch(self.repo, self.target, [self.old], force_links=True)

    def test_second_package_rolls_back_and_successful_first_and_third_remain(self):
        selection, plans, failures = self.prepare()
        second_before = os.readlink(self.target / '.local/bin/second')
        original = engine.verify_result
        def fail_second(target, repo, package, snapshot):
            if package == 'second':
                raise engine.Refusal('fixture second failure')
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
        self.assertEqual(results['third']['outcome']['status'], 'rebound')

    def test_incomplete_second_rollback_preserves_writer_and_continues_third(self):
        selection, plans, failures = self.prepare()
        path = self.target / '.local/bin/second'
        original = engine.verify_result
        def concurrent_failure(target, repo, package, snapshot):
            if package == 'second':
                path.unlink()
                path.write_text('concurrent owner data')
                raise engine.Refusal('fixture second failure')
            return original(target, repo, package, snapshot)
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(engine, 'verify_result', side_effect=concurrent_failure):
                with self.assertRaises(engine.Refusal):
                    engine.apply_batch(self.repo, self.target, selection, plans, failures)
        self.assert_current('demo', self.files)
        self.assert_current('third', ['.local/bin/third'])
        self.assertEqual(path.read_text(), 'concurrent owner data')
        second = self.progress()['packages']['second']['outcome']
        self.assertEqual(second['status'], 'manual-recovery')
        self.assertIn('.local/bin/second', second['recovery_paths'])

    def test_preflight_regular_file_conflict_blocks_only_its_package(self):
        path = self.target / '.local/bin/second'
        path.unlink()
        path.write_text('owner data')
        result = self.command('install', '--rebind', '--force-links', '--from-repo',
                              str(self.old), '--yes', 'all-user')
        self.clean_journals(result)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('second: blocked; retained link changes: 0', result.stdout)
        self.assert_current('demo', self.files)
        self.assert_current('third', ['.local/bin/third'])
        self.assertEqual(path.read_text(), 'owner data')

    def test_exclusions_dry_run_inspection_and_system_refusals(self):
        (self.repo / 'manifests').mkdir()
        (self.repo / 'manifests/ignore-all-install.txt').write_text('second\n')
        before = self.state()
        result = self.command('install', '--rebind', '--force-links', '--from-repo',
                              str(self.old), '--dry-run', 'all-user')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('second: excluded;', result.stdout)
        self.assertEqual(self.state(), before)
        for selector in ('all', 'all-system'):
            result = self.command('install', '--rebind', '--force-links', '--from-repo',
                                  str(self.old), '--yes', selector)
            self.assertNotEqual(result.returncode, 0)
        result = self.command('install', '--rebind', '--force-links', '--from-repo',
                              str(self.old), '--yes', 'all-user')
        self.clean_journals(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.target / '.local/bin/second'), before['.local/bin/second'])
        result = self.command('verify', '--rebind', '--force-links', '--from-repo',
                              str(self.old), 'all-user')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('3 packages, 1 need migration, 0 failed', result.stdout)
