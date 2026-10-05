"""Offline root trust and relocation regression probes on disposable trees."""
import contextlib
import io
import os
from pathlib import Path
import stat
import types
import unittest
from unittest import mock

import test_runner_rebind as user
import test_runner_system_rebind as system
from test_runner_system_rebind_boundaries import fd_path


def foreign(info):
    result = types.SimpleNamespace(**{name: getattr(info, name) for name in dir(info)
                                     if name.startswith('st_')})
    result.st_uid = os.geteuid() + 50000
    return result


class SystemTargetAncestryTests(unittest.TestCase):
    setUp = system.SystemRebindTests.setUp
    source = system.SystemRebindTests.source
    write_manifest = system.SystemRebindTests.write_manifest
    plan = system.SystemRebindTests.plan
    apply = system.SystemRebindTests.apply
    state = system.SystemRebindTests.state
    result = system.SystemRebindTests.result

    def nested_target(self):
        shared = self.base / 'shared'
        nested = shared / 'nested'
        nested.mkdir(parents=True)
        shared.chmod(0o755)
        nested.chmod(0o755)
        self.target = self.target.rename(nested / 'root')
        return shared, nested

    def test_writable_ancestors_above_offline_root_refuse_before_journal_or_move(self):
        for level in ('shared', 'nested'):
            for mode in (0o770, 0o777):
                with self.subTest(level=level, mode=oct(mode)):
                    self.setUp()
                    shared, nested = self.nested_target()
                    ancestor = shared if level == 'shared' else nested
                    ancestor.chmod(mode)
                    before = self.state()
                    with mock.patch.object(system.engine, 'move', wraps=system.engine.move) as move, \
                         self.assertRaisesRegex(system.engine.Refusal, 'system target ancestry'):
                        self.apply()
                    move.assert_not_called()
                    self.assertEqual(self.state(), before)
                    self.assertEqual(list(self.journals.iterdir()), [])

    def test_foreign_owned_ancestors_refuse_even_when_private_or_sticky(self):
        shared, nested = self.nested_target()
        original = system.engine.os.fstat
        for ancestor in (shared, nested):
            for mode in (0o700, 0o1777):
                with self.subTest(ancestor=ancestor, mode=oct(mode)):
                    ancestor.chmod(mode)
                    def untrusted(fd):
                        info = original(fd)
                        return foreign(info) if fd_path(fd) == ancestor else info
                    with mock.patch.object(system.engine.os, 'fstat', side_effect=untrusted), \
                         self.assertRaisesRegex(system.engine.Refusal, 'system target ancestry'):
                        self.plan()
                    ancestor.chmod(0o755)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_trusted_sticky_ancestor_supports_migration_but_target_itself_must_be_private(self):
        shared, _ = self.nested_target()
        shared.chmod(0o1777)
        self.apply()
        self.assertEqual(self.result()[1]['status'], 'committed')
        self.target.chmod(0o1777)
        with self.assertRaisesRegex(system.engine.Refusal, 'system target ancestry'):
            self.plan()

    def test_ancestry_permissions_changed_after_approval_stop_before_publication(self):
        shared, _ = self.nested_target()
        approved = self.plan()
        before = self.state()
        shared.chmod(0o777)
        with mock.patch.object(system.engine, 'move', wraps=system.engine.move) as move, \
             self.assertRaisesRegex(system.engine.Refusal, 'system target ancestry'):
            self.apply(approved)
        move.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_untrusted_ancestor_blocks_retained_fd_root_relocation_attack(self):
        shared, _ = self.nested_target()
        shared.chmod(0o777)
        original = system.engine.write_at
        moved = shared / 'relocated-root'
        def relocate(fd, name, *args):
            if fd_path(fd).is_relative_to(self.target) and not moved.exists():
                self.target.rename(moved)
            return original(fd, name, *args)
        before = self.state()
        with mock.patch.object(system.engine, 'write_at', side_effect=relocate) as write, \
             self.assertRaisesRegex(system.engine.Refusal, 'system target ancestry'):
            self.apply()
        write.assert_not_called()
        self.assertFalse(moved.exists())
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])


class UserTargetAncestryTests(unittest.TestCase):
    setUp = user.RebindTests.setUp
    link = user.RebindTests.link
    state = user.RebindTests.state

    def nested_target(self):
        shared = self.base / 'shared'
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        self.target = self.target.rename(shared / 'root')
        for rel in self.files:
            (self.target / rel).unlink()
            self.link(rel)
        return shared

    def test_user_normal_force_recovery_and_batch_reject_writable_ancestor(self):
        shared = self.nested_target()
        shared.chmod(0o777)
        before = self.state()
        for modes in ({}, {'force_links': True}, {'recover_dangling': True}):
            roots = [self.base / 'missing-root'] if modes.get('recover_dangling') else [self.old]
            with self.subTest(modes=modes), \
                 self.assertRaisesRegex(user.engine.Refusal, 'user target ancestry'):
                user.engine.plan(self.repo, self.target, 'demo', roots, **modes)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                _, prepared, failures = user.engine.prepare_batch(self.repo, self.target, roots, **modes)
            self.assertEqual(prepared, {})
            self.assertIn('user target ancestry', failures['demo'])
        self.assertEqual(self.state(), before)

    def test_user_foreign_owned_ancestor_is_refused_even_with_sticky_bit(self):
        shared = self.nested_target()
        original = Path.lstat
        for mode in (0o700, 0o1777):
            with self.subTest(mode=oct(mode)):
                shared.chmod(mode)
                def untrusted(path):
                    info = original(path)
                    return foreign(info) if path == shared else info
                with mock.patch.object(Path, 'lstat', untrusted), \
                     self.assertRaisesRegex(user.engine.Refusal, 'user target ancestry'):
                    user.engine.plan(self.repo, self.target, 'demo', [self.old])

    def test_user_sticky_shared_ancestor_supported_but_writable_destination_parent_refused(self):
        shared = self.nested_target()
        shared.chmod(0o1777)
        snapshot = user.engine.plan(self.repo, self.target, 'demo', [self.old])
        self.assertFalse(snapshot['conflicts'])
        (self.target / '.local/bin').chmod(0o1777)
        with self.assertRaisesRegex(user.engine.Refusal, 'user target ancestry'):
            user.engine.plan(self.repo, self.target, 'demo', [self.old])

    def test_new_user_destination_parents_remain_private_with_permissive_umask(self):
        rel = '.config/new/private/tool'
        source = self.repo / 'packages/demo/install' / rel
        source.parent.mkdir(parents=True)
        source.write_text('new fixture')
        snapshot = user.engine.plan(self.repo, self.target, 'demo', [self.old])
        previous = os.umask(0)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                user.engine.apply(self.repo, self.target, 'demo', [self.old], snapshot)
        finally:
            os.umask(previous)
        for parent in (self.target / '.config', self.target / '.config/new',
                       self.target / '.config/new/private'):
            self.assertFalse(stat.S_IMODE(parent.stat().st_mode) & 0o022)
        self.assertEqual((self.target / rel).resolve(), source)

    def test_user_ancestry_change_after_approval_stops_before_journal(self):
        shared = self.nested_target()
        snapshot = user.engine.plan(self.repo, self.target, 'demo', [self.old])
        before = self.state()
        shared.chmod(0o777)
        with mock.patch.object(user.engine, 'new_journal', wraps=user.engine.new_journal) as journal, \
             self.assertRaisesRegex(user.engine.Refusal, 'user target ancestry'):
            user.engine.apply(self.repo, self.target, 'demo', [self.old], snapshot)
        journal.assert_not_called()
        self.assertEqual(self.state(), before)


if __name__ == '__main__':
    unittest.main()
