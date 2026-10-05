"""Durability ordering and injected storage failures on disposable roots."""
import contextlib
import json
import os
from pathlib import Path
import stat
import shutil
import signal
import unittest
from unittest import mock

import test_runner_rebind as user
import test_runner_rebind_batch as batch
import test_runner_system_rebind as system


def fd_path(fd):
    return Path(os.readlink(f'/proc/self/fd/{fd}'))


class SystemDurabilityTests(unittest.TestCase):
    setUp = system.SystemRebindTests.setUp
    source = system.SystemRebindTests.source
    write_manifest = system.SystemRebindTests.write_manifest
    plan = system.SystemRebindTests.plan
    apply = system.SystemRebindTests.apply
    state = system.SystemRebindTests.state
    result = system.SystemRebindTests.result

    def trace(self):
        engine = system.engine
        events = []
        original_sync, original_move = os.fsync, engine.move
        original_save, original_write = engine.save, engine.write_at
        original_unlink = os.unlink
        def sync(fd):
            events.append(('sync', fd_path(fd)))
            return original_sync(fd)
        def move(fd, source, destination):
            events.append(('move', fd_path(fd), source, destination))
            return original_move(fd, source, destination)
        def save(journal, record):
            events.append(('save', record['status'], json.loads(json.dumps(record['changes']))))
            return original_save(journal, record)
        def write(fd, name, *args):
            result = original_write(fd, name, *args)
            events.append(('write', fd_path(fd), name))
            return result
        def unlink(name, *, dir_fd=None):
            events.append(('unlink', fd_path(dir_fd) if dir_fd is not None else None, name))
            return original_unlink(name, dir_fd=dir_fd)
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(engine.os, 'fsync', side_effect=sync))
        stack.enter_context(mock.patch.object(engine, 'move', side_effect=move))
        stack.enter_context(mock.patch.object(engine, 'save', side_effect=save))
        stack.enter_context(mock.patch.object(engine, 'write_at', side_effect=write))
        stack.enter_context(mock.patch.object(engine.os, 'unlink', side_effect=unlink))
        return stack, events

    def test_forward_namespace_is_durable_before_progress_and_commit(self):
        stack, events = self.trace()
        with stack:
            self.apply()
        parent = (self.target / self.paths[0]).parent
        first_move = next(index for index, event in enumerate(events) if event[0] == 'move')
        self.assertIn(('sync', self.journals), events[:first_move])
        for index, event in enumerate(events):
            if event[0] == 'move':
                self.assertEqual(events[index + 1], ('sync', parent))
            if event[0] == 'write' and event[2].endswith('.new'):
                self.assertEqual(events[index + 1], ('sync', parent))
            if event[0] == 'write' and event[2].endswith('.before'):
                next_move = next(position for position in range(index + 1, len(events))
                                 if events[position][0] == 'move')
                self.assertIn(('sync', event[1]), events[index + 1:next_move])

    def test_journal_parent_sync_failure_prevents_all_target_writes(self):
        before = self.state()
        original = os.fsync
        def fail(fd):
            if fd_path(fd) == self.journals:
                raise OSError('fixture journal parent sync failure')
            return original(fd)
        with mock.patch.object(system.engine.os, 'fsync', side_effect=fail), \
                mock.patch.object(system.engine, 'move') as move, self.assertRaises(OSError):
            self.apply()
        move.assert_not_called()
        self.assertEqual(self.state(), before)

    def test_restore_and_stage_cleanup_are_synced_before_terminal_record(self):
        before = self.state()
        original = system.engine.move
        def fail_publication(fd, source, destination):
            if source.endswith('.new') and destination == 'b':
                raise OSError('fixture fail after quarantine')
            return original(fd, source, destination)
        with mock.patch.object(system.engine, 'move', side_effect=fail_publication):
            stack, events = self.trace()
            with stack, self.assertRaises(OSError):
                self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')
        terminal = next(index for index, event in enumerate(events)
                        if event[:2] == ('save', 'rolled-back'))
        for index, event in enumerate(events[:terminal]):
            if event[0] == 'move' and event[2].endswith('.old'):
                next_record = next(position for position in range(index + 1, len(events))
                                   if events[position][0] == 'save')
                self.assertIn(('sync', event[1]), events[index + 1:next_record])
            if event[0] == 'unlink' and str(event[2]).startswith('.runner-system-'):
                self.assertEqual(events[index + 1], ('sync', event[1]))

    def test_restore_sync_failure_never_reports_rolled_back(self):
        original_move, original_sync = system.engine.move, os.fsync
        restored = False
        def move(fd, source, destination):
            nonlocal restored
            if source.endswith('.new') and destination == 'a':
                raise OSError('fixture publication failure')
            result = original_move(fd, source, destination)
            if source.endswith('.old'):
                restored = True
            return result
        def sync(fd):
            if restored and fd_path(fd) == (self.target / self.paths[0]).parent:
                raise OSError('fixture restore sync failure')
            return original_sync(fd)
        with mock.patch.object(system.engine, 'move', side_effect=move), \
                mock.patch.object(system.engine.os, 'fsync', side_effect=sync), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.result()[1]['status'], 'recovery-required')

    def test_rollback_progress_failure_still_restores_owned_files(self):
        before = self.state()
        original_move, original_save = system.engine.move, system.engine.save
        def move(fd, source, destination):
            if source.endswith('.new') and destination == 'b':
                raise OSError('fixture publication failure')
            return original_move(fd, source, destination)
        def save(journal, record):
            if record['status'] == 'rolling-back':
                raise OSError('fixture rolling-back progress failure')
            return original_save(journal, record)
        with mock.patch.object(system.engine, 'move', side_effect=move), \
                mock.patch.object(system.engine, 'save', side_effect=save), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'recovery-required')

    def test_vanished_quarantine_and_untouched_writer_cannot_prove_rollback(self):
        for loss in ('quarantine', 'untouched'):
            with self.subTest(loss=loss):
                original = system.engine.move
                def writer(fd, source, destination):
                    result = original(fd, source, destination)
                    if source.endswith('.new') and destination == 'a':
                        if loss == 'quarantine':
                            for path in self.target.rglob('*.old'):
                                path.unlink()
                        else:
                            (self.target / self.paths[1]).write_text('retained writer')
                        raise OSError('fixture failure after concurrent write')
                    return result
                with mock.patch.object(system.engine, 'move', side_effect=writer), self.assertRaises(OSError):
                    self.apply()
                self.assertEqual(self.result()[1]['status'], 'recovery-required')
                # Reset only synthetic data and journals for the second case.
                for relative in self.paths:
                    (self.target / relative).write_bytes(self.source(self.old, relative).read_bytes())
                    (self.target / relative).chmod(0o640)
                for journal in self.journals.iterdir():
                    shutil.rmtree(journal)
                for path in self.target.rglob('.runner-system-*'):
                    path.unlink()

    def test_publication_sync_error_rolls_back_without_committed_record(self):
        before = self.state()
        original_move, original_sync = system.engine.move, os.fsync
        fail_next = False
        def move(fd, source, destination):
            nonlocal fail_next
            result = original_move(fd, source, destination)
            if source.endswith('.new') and destination == 'a':
                fail_next = True
            return result
        def sync(fd):
            nonlocal fail_next
            if fail_next and fd_path(fd) == (self.target / self.paths[0]).parent:
                fail_next = False
                raise OSError('fixture publication sync failure')
            return original_sync(fd)
        with mock.patch.object(system.engine, 'move', side_effect=move), \
                mock.patch.object(system.engine.os, 'fsync', side_effect=sync), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')

    def test_backup_or_stage_sync_failure_never_quarantines_target(self):
        for boundary in ('backup', 'stage'):
            with self.subTest(boundary=boundary):
                before = self.state()
                original = os.fsync
                failed = False
                def sync(fd):
                    nonlocal failed
                    path = fd_path(fd)
                    match = (path.name.endswith('.before') if boundary == 'backup'
                             else path == (self.target / self.paths[0]).parent)
                    if not failed and match:
                        failed = True
                        raise OSError('fixture backup/stage sync failure')
                    return original(fd)
                with mock.patch.object(system.engine.os, 'fsync', side_effect=sync), \
                        mock.patch.object(system.engine, 'move') as move, self.assertRaises(OSError):
                    self.apply()
                self.assertTrue(failed)
                move.assert_not_called()
                self.assertEqual(self.state(), before)
                for journal in self.journals.iterdir():
                    shutil.rmtree(journal)

    def test_second_signal_during_rollback_is_delivered_after_terminal_record(self):
        before = self.state()
        original_move, original_save = system.engine.move, system.engine.save
        delivered = False
        def move(fd, source, destination):
            if source.endswith('.new') and destination == 'b':
                raise OSError('fixture publication failure')
            return original_move(fd, source, destination)
        def save(journal, record):
            nonlocal delivered
            if record['status'] == 'rolling-back':
                delivered = True
                os.kill(os.getpid(), signal.SIGTERM)
            return original_save(journal, record)
        previous = signal.signal(signal.SIGTERM, system.engine.interrupted)
        try:
            with mock.patch.object(system.engine, 'move', side_effect=move), \
                    mock.patch.object(system.engine, 'save', side_effect=save), \
                    self.assertRaises(system.engine.Refusal):
                self.apply()
        finally:
            signal.signal(signal.SIGTERM, previous)
        self.assertTrue(delivered)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.result()[1]['status'], 'rolled-back')


class UserDurabilityTests(unittest.TestCase):
    setUp = user.RebindTests.setUp
    link = user.RebindTests.link
    snapshot = user.RebindTests.snapshot
    apply = user.RebindTests.apply
    state = user.RebindTests.state

    def test_record_file_sync_precedes_replace_and_directory_sync(self):
        events = []
        original_sync, original_replace = os.fsync, os.replace
        path = self.base / 'outcome.json'
        def sync(fd):
            events.append(('sync', stat.S_ISDIR(os.fstat(fd).st_mode)))
            return original_sync(fd)
        def replace(source, destination):
            events.append(('replace',))
            return original_replace(source, destination)
        with mock.patch.object(user.engine.os, 'fsync', side_effect=sync), \
                mock.patch.object(user.engine.os, 'replace', side_effect=replace):
            user.engine.write_record(path, {'state': 'fixture'})
        self.assertEqual(events, [('sync', False), ('replace',), ('sync', True)])

    def test_record_sync_failure_does_not_publish_new_outcome(self):
        path = self.base / 'outcome.json'
        path.write_text('{"state":"old"}')
        with mock.patch.object(user.engine.os, 'fsync', side_effect=OSError('fixture sync failure')), \
                self.assertRaises(OSError):
            user.engine.write_record(path, {'state': 'new'})
        self.assertEqual(json.loads(path.read_text()), {'state': 'old'})
        self.assertFalse(list(self.base.glob('.progress-*')))

    def test_package_journal_parent_sync_failure_prevents_link_writes(self):
        before = self.state()
        original = os.fsync
        def sync(fd):
            if fd_path(fd) == self.base:
                raise OSError('fixture journal parent sync failure')
            return original(fd)
        with mock.patch.object(user.engine.os, 'fsync', side_effect=sync), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.state(), before)

    def test_link_sync_failure_is_rolled_back_before_result(self):
        before = self.state()
        original = os.fsync
        failed = False
        def sync(fd):
            nonlocal failed
            if not failed and fd_path(fd) == self.target / '.local/bin':
                failed = True
                raise OSError('fixture installed link sync failure')
            return original(fd)
        with mock.patch.object(user.engine.os, 'fsync', side_effect=sync), self.assertRaises(OSError):
            self.apply()
        self.assertTrue(failed)
        self.assertEqual(self.state(), before)
        result = next(self.base.glob('runner-rebind-journal-*/result.json'))
        self.assertEqual(json.loads(result.read_text())['status'], 'rolled-back')

    def test_persistent_link_sync_error_reports_manual_recovery(self):
        original = os.fsync
        def sync(fd):
            if fd_path(fd) == self.target / '.local/bin':
                raise OSError('fixture persistent installed-directory sync failure')
            return original(fd)
        with mock.patch.object(user.engine.os, 'fsync', side_effect=sync), self.assertRaises(OSError):
            self.apply()
        result = next(self.base.glob('runner-rebind-journal-*/result.json'))
        self.assertEqual(json.loads(result.read_text())['status'], 'manual-recovery')

    def test_owned_directory_removal_sync_error_is_not_ignored(self):
        snapshot = self.snapshot()
        created = self.target / 'created-only-by-transaction'
        created.mkdir()
        identity = user.engine.identity(created)
        original = os.fsync
        def sync(fd):
            if fd_path(fd) == self.target:
                raise OSError('fixture removed directory sync failure')
            return original(fd)
        with mock.patch.object(user.engine.os, 'fsync', side_effect=sync):
            outcome = user.engine.rollback_package(self.target, snapshot, [], [(created, identity)], None)
        self.assertFalse(created.exists())
        self.assertEqual(outcome['status'], 'manual-recovery')
        self.assertIn(created.name, outcome['recovery_paths'])


class BatchDurabilityTests(unittest.TestCase):
    setUp = batch.RebindBatchTests.setUp
    add_package = batch.RebindBatchTests.add_package
    command = batch.RebindBatchTests.command
    link = batch.RebindBatchTests.link
    state = batch.RebindBatchTests.state
    prepare = batch.RebindBatchTests.prepare
    apply = batch.RebindBatchTests.apply

    def test_batch_journal_sync_failure_prevents_all_package_writes(self):
        before = self.state()
        original = os.fsync
        def sync(fd):
            if fd_path(fd) == self.base:
                raise OSError('fixture batch journal parent sync failure')
            return original(fd)
        with mock.patch.object(user.engine.os, 'fsync', side_effect=sync), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.state(), before)


if __name__ == '__main__':
    unittest.main()
