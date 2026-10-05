"""Raw authorization, canonical roots and journal trust on disposable fixtures."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import types
import unittest
from unittest import mock

import test_runner_rebind as user
import test_runner_system_rebind as system

engine = system.engine


def fd_path(fd):
    return Path(os.readlink(f'/proc/self/fd/{fd}'))


class SystemBoundaryTests(unittest.TestCase):
    setUp = system.SystemRebindTests.setUp
    source = system.SystemRebindTests.source
    write_manifest = system.SystemRebindTests.write_manifest
    plan = system.SystemRebindTests.plan
    apply = system.SystemRebindTests.apply
    state = system.SystemRebindTests.state
    result = system.SystemRebindTests.result

    def test_setid_approval_whitespace_never_becomes_exact_authorization(self):
        self.write_manifest(self.repo, '4640')
        policy = self.repo / 'manifests/allow-setid-system-paths.txt'
        before = self.state()
        for padding in (' ', '\t', '\r', '\v', '\f', '\u0085', '\u2028', '\u2029'):
            for prefix in (True, False):
                with self.subTest(padding=repr(padding), prefix=prefix):
                    first = padding + self.paths[0] if prefix else self.paths[0] + padding
                    policy.write_text(first + '\n' + self.paths[1] + '\n')
                    with self.assertRaises(engine.Refusal):
                        self.apply()
                    self.assertEqual(self.state(), before)
                    self.assertEqual(list(self.journals.iterdir()), [])

    def test_raw_policy_format_refuses_indented_comments_and_whitespace_only_rows(self):
        for name in ('allow-setid-system-paths.txt', 'protected-system-paths.txt'):
            path = self.repo / 'manifests' / name
            for text in (' # indented comment\n', '\t# indented comment\n', ' \n', '\r\n'):
                with self.subTest(name=name, text=repr(text)):
                    path.write_text(text)
                    with self.assertRaises(engine.Refusal):
                        self.plan()
            path.unlink()

    def test_exact_policy_entries_and_column_zero_comments_remain_supported(self):
        self.write_manifest(self.repo, '4640')
        (self.repo / 'manifests/allow-setid-system-paths.txt').write_text(
            '# Exact privilege approvals\n\n' + '\n'.join(self.paths))
        self.apply()
        self.assertTrue(all(stat.S_IMODE((self.target / path).stat().st_mode) == 0o4640
                            for path in self.paths))

    @unittest.skipUnless(shutil.which('zsh'), 'Zsh is required for validator comparison')
    def test_setid_approval_agrees_with_authoritative_check_repo(self):
        self.write_manifest(self.repo, '4640')
        scripts = self.repo / 'scripts'
        scripts.mkdir()
        for name in ('check-repo', 'system-copy-select'):
            shutil.copy2(system.ROOT / 'scripts' / name, scripts / name)
        shutil.copy2(system.ROOT / 'run.sh', self.repo / 'run.sh')
        path = self.repo / 'manifests/allow-setid-system-paths.txt'
        for padding in ('', ' ', '\t', '\r'):
            with self.subTest(padding=repr(padding)):
                path.write_text(''.join(relative + padding + '\n' for relative in self.paths))
                checked = subprocess.run(['zsh', str(scripts / 'check-repo'), 'demo'],
                                         text=True, capture_output=True, timeout=20)
                if padding:
                    self.assertNotEqual(checked.returncode, 0)
                    self.assertIn('requires an entry', checked.stderr)
                    with self.assertRaises(engine.Refusal):
                        self.plan()
                else:
                    self.assertEqual(checked.returncode, 0, checked.stderr)
                    self.assertEqual([row['class'] for row in self.plan()['rows']], ['REBINDABLE'] * 2)

    def test_non_lf_manifest_separators_are_refused_before_payload_read(self):
        for name in ('system-install.manifest', 'system-config.manifest'):
            path = self.repo / 'packages/demo' / name
            original = path.read_bytes() if path.exists() else None
            for separator in ('\r\n', '\v', '\f', '\u0085', '\u2028', '\u2029', '\u00a0'):
                with self.subTest(name=name, separator=repr(separator)):
                    path.write_text(separator.join(f'{relative} 0640 {self.ids}' for relative in self.paths))
                    with self.assertRaises(engine.Refusal):
                        self.plan()
            path.unlink() if original is None else path.write_bytes(original)

    def test_double_slash_roots_are_refused_before_any_lookup(self):
        for path in ('//', '///', '/' + str(self.repo), '/' + str(self.old), '/' + str(self.target)):
            with self.subTest(path=path), mock.patch.object(engine.os, 'open') as opened:
                with self.assertRaises(engine.Refusal):
                    engine.absolute(path)
                opened.assert_not_called()

    def test_direct_prepare_cannot_bypass_overlap_with_a_double_slash_alias(self):
        before = self.state()
        for repo, target, roots in ((self.repo, Path('/' + str(self.repo)), [self.old]),
                                   (Path('/' + str(self.repo)), self.target, [self.old]),
                                   (self.repo, self.target, [Path('/' + str(self.old))])):
            with self.subTest(repo=repo, target=target, roots=roots), self.assertRaises(engine.Refusal):
                engine.prepare(repo, target, 'demo', roots)
        self.assertEqual(self.state(), before)

    def test_cli_rejects_alias_for_each_root_option_without_writes(self):
        options = {'--repo': self.repo, '--system-root': self.target,
                   '--from-repo': self.old, '--journal-dir': self.journals}
        before = self.state()
        for changed in options:
            args = [item for option, path in options.items()
                    for item in (option, '/' + str(path) if option == changed else str(path))]
            result = subprocess.run(['python3', '-I', str(system.ROOT / 'scripts/rebind-system-package'),
                                     *args, '--package', 'demo', '--yes'],
                                    capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0, changed)
            self.assertIn('normalized absolute path', result.stderr)
            self.assertEqual(self.state(), before)
            self.assertEqual(list(self.journals.iterdir()), [])

    def test_physical_root_alias_cannot_bypass_lexical_overlap_checks(self):
        original = engine.os.fstat
        for aliased in (self.repo, self.old):
            alias = aliased.stat()
            def bound(fd):
                info = original(fd)
                if fd_path(fd) == self.target:
                    return types.SimpleNamespace(st_dev=alias.st_dev, st_ino=alias.st_ino,
                        st_mode=info.st_mode, st_uid=info.st_uid, st_gid=info.st_gid)
                return info
            with self.subTest(aliased=aliased), mock.patch.object(engine.os, 'fstat', side_effect=bound), \
                    self.assertRaises(engine.Refusal):
                self.plan()

    def test_destination_inode_alias_of_any_source_is_a_conflict(self):
        original = engine.read
        source_state, _ = original(self.source(self.old, self.paths[1]))
        def bound(path, **kwargs):
            state, data = original(path, **kwargs)
            if path == self.target / self.paths[0]:
                state['identity'][:2] = source_state['identity'][:2]
            return state, data
        before = self.state()
        with mock.patch.object(engine, 'read', side_effect=bound):
            plan = self.plan()
        self.assertEqual(plan['rows'][0]['class'], 'FOREIGN')
        with self.assertRaises(engine.Refusal):
            self.apply(plan)
        self.assertEqual(self.state(), before)

    def test_writable_journal_parent_and_ancestor_fail_before_creation(self):
        before = self.state()
        for path in (self.journals, self.base):
            original = stat.S_IMODE(path.stat().st_mode)
            path.chmod(0o777)
            try:
                with mock.patch.object(engine, 'move', wraps=engine.move) as move, self.assertRaises(engine.Refusal):
                    self.apply()
                move.assert_not_called()
                self.assertEqual(self.state(), before)
                self.assertEqual(list(self.journals.iterdir()), [])
            finally:
                path.chmod(original)

    def test_foreign_owned_journal_ancestry_is_refused_even_with_sticky_bit(self):
        before = self.state()
        original = engine.os.fstat
        for path in (self.journals, self.base):
            for sticky in (False, True):
                def foreign(fd):
                    info = original(fd)
                    if fd_path(fd) == path:
                        return types.SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino,
                            st_mode=stat.S_IFDIR | (0o1777 if sticky else 0o700),
                            st_uid=os.geteuid() + 50000, st_gid=info.st_gid)
                    return info
                with self.subTest(path=path, sticky=sticky), \
                        mock.patch.object(engine.os, 'fstat', side_effect=foreign), \
                        self.assertRaises(engine.Refusal):
                    self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_trusted_sticky_shared_journal_parent_remains_supported(self):
        self.journals.chmod(0o1777)
        self.apply()
        self.assertEqual(self.result()[1]['status'], 'committed')

    def test_journal_creation_uses_the_anchored_parent_descriptor(self):
        original = engine.os.mkdir
        observed = []
        def mkdir(name, mode=0o777, *, dir_fd=None):
            if Path(name).name.startswith('runner-system-rebind-'):
                self.assertIsNotNone(dir_fd)
                self.assertEqual(fd_path(dir_fd), self.journals)
                self.assertEqual(str(name), Path(name).name)
                observed.append(name)
            return original(name, mode, dir_fd=dir_fd)
        with mock.patch.object(engine.os, 'mkdir', side_effect=mkdir):
            self.apply()
        self.assertEqual(len(observed), 1)

    def test_parent_replacement_cannot_redirect_journal_creation(self):
        before = self.state()
        original = engine.os.mkdir
        retained = self.base / 'original journal parent'
        moved = False
        def mkdir(name, mode=0o777, *, dir_fd=None):
            nonlocal moved
            if Path(name).name.startswith('runner-system-rebind-') and not moved:
                moved = True
                self.journals.rename(retained)
                original(self.journals, 0o700)
            return original(name, mode, dir_fd=dir_fd)
        with mock.patch.object(engine.os, 'mkdir', side_effect=mkdir), \
                mock.patch.object(engine, 'move', wraps=engine.move) as move, self.assertRaises(engine.Refusal):
            self.apply()
        self.assertTrue(moved)
        move.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.journals.iterdir()), [])
        self.assertEqual(len(list(retained.glob('runner-system-rebind-*'))), 1)

    def test_replaced_journal_never_receives_backup_data(self):
        before = self.state()
        original = engine.write_at
        retained = self.journals / 'retained original'
        replacement = None
        def write(fd, name, *args):
            nonlocal replacement
            if name == '0.before':
                replacement = fd_path(fd)
                replacement.rename(retained)
                replacement.mkdir(mode=0o700)
            return original(fd, name, *args)
        with mock.patch.object(engine, 'write_at', side_effect=write), \
                mock.patch.object(engine, 'move', wraps=engine.move) as move, self.assertRaises(engine.Refusal):
            self.apply()
        move.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(replacement.iterdir()), [])
        self.assertEqual((retained / '0.before').read_bytes(), before[self.paths[0]][0])

    def test_journal_move_after_publication_stops_forward_work_and_restores_targets(self):
        before = self.state()
        original = engine.move
        retained = self.journals / 'retained original'
        replacement = None
        def move(fd, source, destination):
            nonlocal replacement
            result = original(fd, source, destination)
            if source.endswith('.new') and destination == 'a':
                replacement = next(self.journals.glob('runner-system-rebind-*'))
                replacement.rename(retained)
                replacement.mkdir(mode=0o700)
            return result
        with mock.patch.object(engine, 'move', side_effect=move), self.assertRaises(engine.Refusal):
            self.apply()
        self.assertEqual(self.state(), before)
        self.assertEqual(list(replacement.iterdir()), [])
        self.assertTrue((retained / 'progress.json').exists())
        self.assertTrue((retained / '0.before').exists())

    def test_journal_permissions_change_stops_before_target_mutation(self):
        before = self.state()
        original = engine.write_at
        def write(fd, name, *args):
            result = original(fd, name, *args)
            if name == '0.before':
                fd_path(fd).chmod(0o755)
            return result
        with mock.patch.object(engine, 'write_at', side_effect=write), \
                mock.patch.object(engine, 'move', wraps=engine.move) as move, self.assertRaises(engine.Refusal):
            self.apply()
        move.assert_not_called()
        self.assertEqual(self.state(), before)


class UserRootBoundaryTests(unittest.TestCase):
    def test_user_helper_refuses_double_slash_before_traversal(self):
        for path in ('//', '//tmp/example', '///tmp/example'):
            with self.subTest(path=path), mock.patch.object(user.engine, 'directories') as traversed:
                with self.assertRaises(user.engine.Refusal):
                    user.engine.absolute(path)
                traversed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
