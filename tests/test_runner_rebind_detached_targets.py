"""Grouped forced-target follow-up, with final rollback-aware observations."""
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import test_runner_rebind_force as force

engine = force.engine


class DetachedTargetTests(unittest.TestCase):
    setUp = force.ForceLinkTests.setUp
    command = force.ForceLinkTests.command
    link = force.ForceLinkTests.link
    state = force.ForceLinkTests.state
    force_leaf = force.ForceLinkTests.force_leaf
    clean_journals = force.ForceLinkTests.clean_journals
    cli = force.ForceLinkTests.cli
    snapshot = force.ForceLinkTests.snapshot

    def apply_report(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = engine.apply(self.repo, self.target, 'demo', [self.old], self.snapshot())
        return result['outcome'], output.getvalue()

    def test_success_groups_existing_targets_and_records_the_same_checks(self):
        result = self.cli('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        footer = result.stdout.split('Detached forced targets to inspect', 1)[1]
        self.assertIn('Directory: ' + json.dumps(str(self.foreign.parent)), footer)
        self.assertIn('Target: ' + json.dumps(str(self.foreign)) + ' [exists]', footer)
        self.assertIn('demo: ' + json.dumps(str(self.target / self.files[0])), footer)
        journal = Path(next(line.split(': ', 1)[1] for line in result.stdout.splitlines()
                            if line.startswith('Rollback journal: ')))
        checks = json.loads(journal.with_name('result.json').read_text())['detached_targets']
        self.assertEqual(checks, [{'old_target': str(self.foreign),
                                  'installed_path': str(self.target / self.files[0]),
                                  'target_state': 'exists', 'link_state': 'replaced'}])

    def test_confirmed_missing_target_is_omitted(self):
        self.foreign.unlink()
        outcome, output = self.apply_report()
        self.assertEqual(outcome['detached_targets'], [])
        self.assertEqual(outcome['omitted_missing_targets'], 1)
        footer = output.split('Detached forced targets to inspect', 1)[1]
        self.assertNotIn(str(self.foreign), footer)

    def test_same_target_is_deduplicated_but_all_detached_links_remain_visible(self):
        self.force_leaf(self.files[-1])
        outcome, output = self.apply_report()
        self.assertEqual(len(outcome['detached_targets']), 2)
        self.assertEqual(output.count('Target: ' + json.dumps(str(self.foreign))), 1)
        for rel in self.files:
            self.assertIn('demo: ' + json.dumps(str(self.target / rel)), output)

    def test_directory_target_is_reported_without_enumerating_it(self):
        directory = self.base / 'foreign directory'
        directory.mkdir()
        (directory / 'private-fixture').write_text('owner data')
        self.force_leaf(self.files[0], directory)
        with mock.patch.object(engine.os, 'walk', wraps=engine.os.walk) as walks:
            outcome, _ = self.apply_report()
        self.assertTrue(all(Path(call.args[0]) != directory for call in walks.call_args_list))
        self.assertEqual(outcome['detached_targets'][0]['old_target'], str(directory))

    def test_relative_reference_is_normalized_through_known_installed_parents(self):
        path = self.target / self.files[0]
        self.force_leaf(self.files[0], os.path.relpath(self.foreign, path.parent))
        outcome, _ = self.apply_report()
        self.assertEqual(outcome['detached_targets'][0]['old_target'], str(self.foreign))

    def test_noncanonical_reference_is_not_collapsed_through_a_foreign_symlink(self):
        child = self.base / 'other' / 'child'
        child.mkdir(parents=True)
        (child.parent / 'payload').write_text('owner data')
        alias = self.base / 'alias'
        alias.symlink_to(child)
        reference = str(alias) + '/../payload'
        self.force_leaf(self.files[0], reference)
        outcome, _ = self.apply_report()
        self.assertEqual(outcome['detached_targets'][0]['old_target'], reference)
        self.assertEqual(outcome['detached_targets'][0]['target_state'], 'exists')
        self.assertFalse((self.base / 'payload').exists())

    def test_trailing_slash_on_file_remains_missing_instead_of_becoming_a_file_reference(self):
        self.force_leaf(self.files[0], str(self.foreign) + '/')
        outcome, _ = self.apply_report()
        self.assertEqual(outcome['detached_targets'], [])
        self.assertEqual(outcome['omitted_missing_targets'], 1)

    def test_loop_is_unknown_and_requires_a_check(self):
        self.foreign.unlink()
        self.foreign.symlink_to(self.foreign)
        outcome, output = self.apply_report()
        self.assertEqual(outcome['detached_targets'][0]['target_state'], 'unknown')
        self.assertIn('Target: ' + json.dumps(str(self.foreign)) + ' [unknown]', output)

    def test_permission_error_is_not_treated_as_absence(self):
        original = engine.os.stat
        def denied(path, *args, **kwargs):
            if str(path) == str(self.foreign):
                raise PermissionError('fixture inaccessible target')
            return original(path, *args, **kwargs)
        with mock.patch.object(engine.os, 'stat', side_effect=denied):
            outcome, _ = self.apply_report()
        self.assertEqual(outcome['detached_targets'][0]['target_state'], 'unknown')

    def test_verified_rollback_has_no_detached_target_checks(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(engine, 'verify_result', side_effect=engine.Refusal('fixture failure')):
                with self.assertRaises(engine.Refusal):
                    engine.apply(self.repo, self.target, 'demo', [self.old], self.snapshot())
        journal = next(self.base.glob('runner-rebind-journal-*/result.json'))
        outcome = json.loads(journal.read_text())
        self.assertEqual(outcome['status'], 'rolled-back')
        self.assertEqual(outcome['detached_targets'], [])

    def test_incomplete_rollback_keeps_existing_target_with_unverified_link_state(self):
        path = self.target / self.files[0]
        def concurrent_failure(*args):
            path.unlink()
            path.write_text('concurrent owner data')
            raise engine.Refusal('fixture failure')
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(engine, 'verify_result', side_effect=concurrent_failure):
                with self.assertRaises(engine.Refusal):
                    engine.apply(self.repo, self.target, 'demo', [self.old], self.snapshot())
        outcome = json.loads(next(self.base.glob('runner-rebind-journal-*/result.json')).read_text())
        self.assertEqual(outcome['status'], 'manual-recovery')
        self.assertEqual(outcome['detached_targets'][0]['link_state'], 'unverified')
        self.assertEqual(outcome['detached_targets'][0]['target_state'], 'exists')

    def test_dry_run_does_not_probe_or_claim_actual_detachment(self):
        with mock.patch.object(engine, 'probe_detached_target', side_effect=AssertionError('premature probe')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.snapshot()
        result = self.cli('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Detached forced targets to inspect', result.stdout)


class DetachedBatchTests(unittest.TestCase):
    setUp = force.ForceBatchTests.setUp
    command = force.ForceBatchTests.command
    link = force.ForceBatchTests.link
    state = force.ForceBatchTests.state
    add_package = force.ForceBatchTests.add_package
    assert_current = force.ForceBatchTests.assert_current
    progress = force.ForceBatchTests.progress
    clean_journals = force.ForceBatchTests.clean_journals
    prepare = force.ForceBatchTests.prepare

    def existing_targets(self):
        for rel in (self.files[0], '.local/bin/second', '.local/bin/third'):
            Path(os.readlink(self.target / rel)).write_text('owner data')

    def test_batch_groups_once_across_packages_and_omits_restored_second_package(self):
        self.existing_targets()
        shared = os.readlink(self.target / self.files[0])
        third = self.target / '.local/bin/third'
        third.unlink()
        third.symlink_to(shared)
        selection, plans, failures = self.prepare()
        original = engine.verify_result
        def second_fails(target, repo, package, snapshot):
            if package == 'second':
                raise engine.Refusal('fixture failure')
            return original(target, repo, package, snapshot)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with mock.patch.object(engine, 'verify_result', side_effect=second_fails):
                with self.assertRaises(engine.Refusal):
                    engine.apply_batch(self.repo, self.target, selection, plans, failures)
        footer = output.getvalue().split('Detached forced targets to inspect', 1)[1]
        self.assertEqual(footer.count('Target: ' + json.dumps(shared)), 1)
        self.assertIn('demo:', footer)
        self.assertIn('third:', footer)
        self.assertNotIn('second:', footer)
        results = self.progress()['packages']
        self.assertEqual(results['second']['outcome']['detached_targets'], [])
        self.assertEqual(results['demo']['outcome']['detached_targets'][0]['old_target'], shared)

    def test_final_state_uncertainty_preserves_detached_target_evidence(self):
        self.existing_targets()
        selection, plans, failures = self.prepare()
        original = engine.verify_result
        calls = 0
        def late_failure(target, repo, package, snapshot):
            nonlocal calls
            if package == 'demo':
                calls += 1
                if calls >= 2:
                    raise engine.Refusal('fixture late failure')
            return original(target, repo, package, snapshot)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with mock.patch.object(engine, 'verify_result', side_effect=late_failure):
                with self.assertRaises(engine.Refusal):
                    engine.apply_batch(self.repo, self.target, selection, plans, failures)
        outcome = self.progress()['packages']['demo']['outcome']
        self.assertEqual(outcome['status'], 'final-state-unverified')
        self.assertEqual(len(outcome['detached_targets']), 1)
        footer = output.getvalue().split('Detached forced targets to inspect', 1)[1]
        self.assertIn('demo:', footer)
        self.assertIn('final-state-unverified', footer)

    def test_end_of_batch_refresh_omits_target_removed_after_its_package_completed(self):
        self.existing_targets()
        old = Path(os.readlink(self.target / self.files[0]))
        selection, plans, failures = self.prepare()
        original = engine.verify_result
        def remove_later(target, repo, package, snapshot):
            if package == 'third' and old.exists():
                old.unlink()
            return original(target, repo, package, snapshot)
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(engine, 'verify_result', side_effect=remove_later):
                engine.apply_batch(self.repo, self.target, selection, plans, failures)
        outcome = self.progress()['packages']['demo']['outcome']
        self.assertEqual(outcome['detached_targets'], [])
        self.assertEqual(outcome['omitted_missing_targets'], 1)
