"""Cross-command regression probes in disposable repos and targets only."""
import shutil
import unittest
from pathlib import Path

import test_runner_rebind as single


class MigrationBoundaryTests(unittest.TestCase):
    command = single.RebindTests.command
    cli = single.RebindTests.cli
    link = single.RebindTests.link
    state = single.RebindTests.state

    def setUp(self):
        single.RebindTests.setUp(self)

    def retain_cli_journals(self, result):
        for line in result.stdout.splitlines():
            if line.startswith('Rollback journal: '):
                path = Path(line.split(': ', 1)[1])
                self.assertTrue(path.parent.name.startswith('runner-rebind-journal-'))
                self.addCleanup(shutil.rmtree, path.parent, True)

    def test_existing_package_cleanup_refuses_and_rebind_transfers_its_links(self):
        before = self.state()
        result = self.command('uninstall', '--orphaned', '--yes', 'demo')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('still has a source tree', result.stderr)
        self.assertEqual(self.state(), before)
        result = self.cli('--yes')
        self.retain_cli_journals(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        for relative in self.files:
            self.assertEqual((self.target / relative).resolve(),
                             self.repo / 'packages/demo/install' / relative)

    def test_missing_source_rebind_refuses_and_cleanup_keeps_foreign_checkout_links(self):
        shutil.rmtree(self.old)
        before = self.state()
        result = self.cli('--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state(), before)
        shutil.rmtree(self.repo / 'packages/demo')
        (self.repo / 'stow/demo').unlink()
        own = self.target / '.local/bin/own-orphan'
        own.symlink_to(self.repo / 'stow/demo/.local/bin/own-orphan')
        result = self.command('uninstall', '--orphaned', '--yes', 'demo')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(own.is_symlink())
        self.assertEqual(self.state(), before)

    def test_ordinary_verification_and_migration_inspection_keep_their_distinct_results(self):
        before = self.state()
        result = self.command('verify', 'demo')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('installed symlink points elsewhere', result.stderr)
        result = self.command('verify', '--rebind', '--from-repo', str(self.old), 'demo')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.state(), before)
        result = self.cli('--yes')
        self.retain_cli_journals(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.command('verify', 'demo')
        self.assertEqual(result.returncode, 0, result.stderr)
