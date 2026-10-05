"""Grouped forced-target follow-up, with final rollback-aware observations."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
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

    def test_probe_runs_with_unmasked_signals_after_durable_success_record(self):
        original = engine.probe_detached_target
        def checked(reference):
            self.assertFalse(signal.pthread_sigmask(signal.SIG_BLOCK, set()) &
                             {signal.SIGINT, signal.SIGTERM})
            outcome = json.loads(next(self.base.glob('runner-rebind-journal-*/result.json')).read_text())
            self.assertEqual(outcome['status'], 'rebound')
            self.assertEqual(outcome['detached_targets'][0]['target_state'], 'unknown')
            return original(reference)
        with mock.patch.object(engine, 'probe_detached_target', side_effect=checked) as probes:
            outcome, _ = self.apply_report()
        self.assertEqual(probes.call_count, 1)
        self.assertEqual(outcome['detached_targets'][0]['target_state'], 'exists')

    def test_signal_during_success_probe_keeps_committed_links_and_durable_unknown_report(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig):
                self.force_leaf(self.files[0])
                def interrupted(signum, frame):
                    raise engine.Interrupted('fixture report signal')
                def probe(reference):
                    self.assertNotIn(sig, signal.pthread_sigmask(signal.SIG_BLOCK, set()))
                    os.kill(os.getpid(), sig)
                    self.fail('probe continued after interruption')
                previous = signal.signal(sig, interrupted)
                try:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        with mock.patch.object(engine, 'probe_detached_target', side_effect=probe) as probes:
                            with self.assertRaises(engine.Interrupted):
                                engine.apply(self.repo, self.target, 'demo', [self.old], self.snapshot())
                finally:
                    signal.signal(sig, previous)
                self.assertEqual(probes.call_count, 1)
                self.assertIn('[unknown]', output.getvalue())
                self.assertEqual((self.target / self.files[0]).resolve(),
                                 self.repo / 'packages/demo/install' / self.files[0])
                outcomes = [json.loads(path.read_text())
                            for path in self.base.glob('runner-rebind-journal-*/result.json')]
                self.assertTrue(all(outcome['status'] == 'rebound' and
                                    outcome['detached_targets'][0]['target_state'] == 'unknown'
                                    for outcome in outcomes))
                with engine.target_lock(self.target):
                    pass

    def test_second_signal_during_failed_package_probe_preserves_rollback_record(self):
        path = self.target / self.files[0]
        def concurrent_failure(*args):
            path.unlink()
            path.write_text('concurrent owner data')
            raise engine.Refusal('fixture transaction failure')
        def interrupted(signum, frame):
            raise engine.Interrupted('fixture second signal')
        def probe(reference):
            self.assertNotIn(signal.SIGTERM, signal.pthread_sigmask(signal.SIG_BLOCK, set()))
            outcome = json.loads(next(self.base.glob('runner-rebind-journal-*/result.json')).read_text())
            self.assertEqual(outcome['status'], 'manual-recovery')
            self.assertEqual(outcome['detached_targets'][0]['target_state'], 'unknown')
            os.kill(os.getpid(), signal.SIGTERM)
        previous = signal.signal(signal.SIGTERM, interrupted)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(engine, 'verify_result', side_effect=concurrent_failure), \
                        mock.patch.object(engine, 'probe_detached_target', side_effect=probe):
                    with self.assertRaises(engine.Interrupted):
                        engine.apply(self.repo, self.target, 'demo', [self.old], self.snapshot())
        finally:
            signal.signal(signal.SIGTERM, previous)
        self.assertEqual(path.read_text(), 'concurrent owner data')
        with engine.target_lock(self.target):
            pass


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

    def test_failed_batch_refresh_probes_with_signals_unmasked_and_failure_record_saved(self):
        self.existing_targets()
        selection, plans, failures = self.prepare()
        original_verify = engine.verify_result
        original_probe = engine.probe_detached_target
        failure_probes = []
        def second_fails(target, repo, package, snapshot):
            if package == 'second':
                raise engine.Refusal('fixture second-package failure')
            return original_verify(target, repo, package, snapshot)
        def checked(reference):
            self.assertFalse(signal.pthread_sigmask(signal.SIG_BLOCK, set()) &
                             {signal.SIGINT, signal.SIGTERM})
            progress = self.progress()
            if progress['state'] == 'failed':
                failure_probes.append(reference)
                self.assertEqual(progress['packages']['second']['outcome']['status'], 'rolled-back')
            return original_probe(reference)
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(engine, 'verify_result', side_effect=second_fails), \
                    mock.patch.object(engine, 'probe_detached_target', side_effect=checked):
                with self.assertRaises(engine.Refusal):
                    engine.apply_batch(self.repo, self.target, selection, plans, failures)
        self.assertTrue(failure_probes)

    def test_signal_during_first_package_probe_stops_batch_without_retry_or_rollback(self):
        self.existing_targets()
        selection, plans, failures = self.prepare()
        def interrupted(signum, frame):
            raise engine.Interrupted('fixture batch report signal')
        def probe(reference):
            self.assertNotIn(signal.SIGTERM, signal.pthread_sigmask(signal.SIG_BLOCK, set()))
            self.assertEqual(self.progress()['packages']['demo']['state'], 'completed')
            os.kill(os.getpid(), signal.SIGTERM)
        previous = signal.signal(signal.SIGTERM, interrupted)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(engine, 'probe_detached_target', side_effect=probe) as probes:
                    with self.assertRaises(engine.Interrupted):
                        engine.apply_batch(self.repo, self.target, selection, plans, failures)
        finally:
            signal.signal(signal.SIGTERM, previous)
        self.assertEqual(probes.call_count, 1)
        progress = self.progress()
        self.assertEqual(progress['packages']['demo']['state'], 'completed')
        self.assertEqual(progress['packages']['second']['state'], 'unattempted')
        self.assertEqual(progress['packages']['third']['state'], 'unattempted')
        self.assertEqual(progress['packages']['demo']['outcome']['detached_targets'][0]['target_state'], 'unknown')
        self.assert_current('demo', self.files)
        with engine.target_lock(self.target):
            pass

    def test_keyboard_interrupt_during_final_refresh_keeps_all_completed_packages(self):
        self.existing_targets()
        selection, plans, failures = self.prepare()
        original = engine.probe_detached_target
        calls = 0
        def probe(reference):
            nonlocal calls
            calls += 1
            self.assertNotIn(signal.SIGINT, signal.pthread_sigmask(signal.SIG_BLOCK, set()))
            if calls == 4:
                raise KeyboardInterrupt('fixture final report interruption')
            return original(reference)
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(engine, 'probe_detached_target', side_effect=probe):
                with self.assertRaises(KeyboardInterrupt):
                    engine.apply_batch(self.repo, self.target, selection, plans, failures)
        self.assertEqual(calls, 4)
        progress = self.progress()
        self.assertTrue(all(result['state'] == 'completed' for result in progress['packages'].values()))
        self.assertTrue(all(result['outcome']['detached_targets'][0]['target_state'] == 'unknown'
                            for result in progress['packages'].values()))
        with engine.target_lock(self.target):
            pass
