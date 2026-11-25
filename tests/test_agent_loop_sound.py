"""Run completion sounds against fake audio/notification tools, never live audio."""
import contextlib
import fcntl
import json
import importlib.util
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'packages/ai-agents-hooks/install/.local/bin/agent-loop-sound'
HELPER = SCRIPT.parent.parent / 'lib/agent-loop-sounds/ducking.py'
SPEC = importlib.util.spec_from_file_location('sound_ducking', HELPER)
DUCK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DUCK)

MOCK = r'''#!/usr/bin/python3
import contextlib, fcntl, json, os, re, signal, subprocess, sys, time, wave
from pathlib import Path
base = Path(os.environ['AUDIO_FIXTURE'])
@contextlib.contextmanager
def state():
    with (base / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads((base / 'state.json').read_text())
        yield data
        (base / 'state.json').write_text(json.dumps(data))
tool = Path(sys.argv[0]).name
if tool == 'pw-play':
    with wave.open(sys.argv[-1]) as wav:
        duration = wav.getnframes() / wav.getframerate()
    with state() as data:
        index = data['next_index']; data['next_index'] += 1
        tag = re.search(r'agent.loop-sound.id = "([^"]+)"', sys.argv[sys.argv.index('--properties') + 1]).group(1)
        data['streams'][str(index)] = {'pid': '' if os.environ.get('OMIT_PLAYER_PID') else str(os.getpid()),
                                     'app': 'agent-loop-sound', 'raw': 0, 'tag': tag}
        data['started'].append({'index': index, 'args': sys.argv[1:]})
    def stop(*args): raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    try: time.sleep(duration)
    finally:
        with state() as data: data['streams'].pop(str(index), None)
elif tool == 'pactl':
    args = sys.argv[1:]
    with state() as data:
        if args == ['--format=json', 'list', 'sink-inputs']:
            print(json.dumps([{'index': int(index), 'properties': {'application.process.id': stream['pid'],
                  'application.name': stream['app'], 'agent.loop-sound.id': stream.get('tag', '')}}
                  for index, stream in data['streams'].items()]))
        elif args == ['list', 'sink-inputs']:
            for index, stream in data['streams'].items():
                print('Sink Input #' + index + '\n Volume: front-left: ' + str(stream['raw']) + ' / 100% / 0.00 dB')
                print(' application.process.id = "' + stream['pid'] + '"')
        elif args[:1] == ['set-sink-input-volume']:
            index, value = args[1:3]
            stream = data['streams'][index]
            raw = int(float(value[:-1]) * 65536 / 100) if value.endswith('%') else int(value)
            data['writes'].append({'index': int(index), 'app': stream['app'], 'raw': raw})
            stream['raw'] = raw
        else: raise SystemExit(90)
elif tool == 'pw-dump':
    with state() as data:
        print(json.dumps([{'id': 0, 'info': dict.fromkeys(['cookie'], 123)}] + [
            {'id': int(index), 'info': {'props': {'object.serial': stream.get('serial', int(index)),
             'application.name': stream['app'], 'media.class': 'Stream/Output/Audio'},
             'params': {'Props': [{'channelVolumes': [(stream['raw'] / 65536)**3],
             'softVolumes': stream.get('soft', [1.0]), 'mute': False,
             'softMute': stream.get('soft_mute', False)}]}}}
            for index, stream in data['streams'].items()]))
elif tool == 'pw-cli':
    status = 0
    with state() as data:
        args = sys.argv[1:]
        if args[:1] != ['set-param'] or args[2] != 'Props': raise SystemExit(92)
        stream = data['streams'][args[1]]
        props = json.loads(args[3])
        if props['softVolumes'] == [1.0] and data.get('failed_restores', 0):
            data['failed_restores'] -= 1
            status = 1
        else:
            stream['soft'] = props['softVolumes']; stream['soft_mute'] = props['softMute']
            data['mixing'].append({'index': int(args[1]), 'app': stream['app'], 'props': props})
    raise SystemExit(status)
elif tool == 'systemd-run':
    args = sys.argv[1:]
    if args[:1] == ['supervise']:
        try:
            for _ in range(3):
                watcher = subprocess.Popen(args[1:])
                with state() as data:
                    data['watchers'].append(watcher.pid)
                try:
                    if watcher.wait(timeout=8) == 0:
                        break
                except subprocess.TimeoutExpired:
                    watcher.kill()
                    watcher.wait()
                    break
        finally:
            with state() as data:
                data['managers'].remove(os.getpid())
    elif os.environ.get('FIXTURE_MANAGER_UNAVAILABLE') == '1':
        raise SystemExit(1)
    else:
        flags, command = args[:args.index('--')], args[args.index('--') + 1:]
        if not {'--user', '--property=Type=exec', '--property=Restart=on-failure'} <= set(flags):
            raise SystemExit(93)
        if '--watch' not in command:
            raise SystemExit(94)
        with state() as data:
            manager = subprocess.Popen(
                [sys.argv[0], 'supervise', *command], start_new_session=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            data['managers'].append(manager.pid)
elif tool == 'notify-send':
    if '--help' in sys.argv: print('--action --wait')
    elif os.environ.get('FIXTURE_STOP') == '1':
        time.sleep(.15); print('stop')
    else: time.sleep(1.2)
else: raise SystemExit(91)
'''


class AgentSoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        for tool in ('pw-play', 'pactl', 'notify-send', 'pw-dump', 'pw-cli', 'systemd-run'):
            path = self.bin / tool
            path.write_text(MOCK)
            path.chmod(0o755)
        self.sound = self.base / 'sample.wav'
        with wave.open(str(self.sound), 'wb') as wav:
            wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * 400)
        (self.base / 'state.json').write_text(json.dumps({
            'streams': {'10': {'pid': '42', 'app': 'Firefox', 'raw': 65536}},
            'next_index': 1000, 'started': [], 'writes': [], 'mixing': [],
            'managers': [], 'watchers': []}))
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        XDG_CACHE_HOME=str(self.base / 'cache'),
                        XDG_RUNTIME_DIR=str(self.base / 'runtime'), AUDIO_FIXTURE=str(self.base),
                        AGENT_SOUND_DURATION_SECONDS='1.2', AGENT_DUCK_PERCENT='80',
                        AGENT_SOUND_VOLUME_PERCENT='100')
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate(timeout=2)
        self.await_recovery()
        self.temp.cleanup()

    @contextlib.contextmanager
    def state(self):
        with (self.base / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads((self.base / 'state.json').read_text())
            yield data
            (self.base / 'state.json').write_text(json.dumps(data))

    def start(self, **overrides):
        process = subprocess.Popen(['bash', str(SCRIPT), 'Codex', str(self.sound), '15'],
                                   env=dict(self.env, **overrides), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def await_players(self, count):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.state() as data:
                if len(data['started']) >= count:
                    return
            time.sleep(.02)
        self.fail('fake players did not start')

    def finish(self, process):
        output, errors = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, (output, errors))
        self.assertEqual(errors, '')

    def await_recovery(self):
        deadline = time.monotonic() + 9
        while time.monotonic() < deadline:
            with self.state() as data:
                if not data['managers']:
                    return
            time.sleep(.025)
        self.fail('supervised recovery did not finish')

    def await_duck(self, index='10'):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            with self.state() as data:
                if abs(data['streams'][index].get('soft', [1])[0] - .512) < 1e-5:
                    return
            time.sleep(.02)
        self.fail('temporary attenuation did not appear')

    def assert_only_signal_writes(self):
        with self.state() as data:
            self.assertTrue(data['writes'])
            self.assertTrue(all(write['app'] == 'agent-loop-sound' for write in data['writes']), data['writes'])
            self.assertTrue(all('--media-role' in player['args'] and 'Notification' in player['args']
                                for player in data['started']))

    def test_signal_preserves_other_application_volume(self):
        process = self.start()
        self.finish(process)
        self.await_recovery()
        self.assert_only_signal_writes()
        with self.state() as data:
            self.assertEqual(data['streams']['10']['raw'], 65536)
            self.assertAlmostEqual(data['streams']['10']['soft'][0], 1.0)
            self.assertTrue(any(abs(write['props']['softVolumes'][0] - .512) < 1e-5
                                for write in data['mixing']))
        self.assertEqual(list((self.base / 'runtime/agent-loop-sounds').glob('*.duck.*')), [])

    def test_ten_second_loop_repeats_complete_stereo_frames(self):
        # Non-silent, distinct left/right samples detect silence, truncation and
        # reversing samples instead of whole interleaved audio frames.
        frames = struct.pack('<hhhhhh', 100, -100, 200, -200, 300, -300)
        with wave.open(str(self.sound), 'wb') as wav:
            wav.setparams((2, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(frames)
        process = self.start(AGENT_SOUND_DURATION_SECONDS='10', FIXTURE_STOP='1')
        self.finish(process)
        with self.state() as data:
            loop = data['started'][0]['args'][-1]
        with wave.open(loop, 'rb') as wav:
            self.assertEqual(wav.getnframes(), 80000)
            self.assertEqual(wav.getframerate(), 8000)
            self.assertEqual(wav.getnchannels(), 2)
            payload = wav.readframes(wav.getnframes())
        reversed_frames = frames[8:12] + frames[4:8] + frames[:4]
        pattern = frames + reversed_frames
        expected = (pattern * ((len(payload) + len(pattern) - 1) // len(pattern)))[:len(payload)]
        self.assertEqual(payload, expected)

    def test_overlapping_signals_and_song_change_preserve_new_stream(self):
        first, second = self.start(), self.start(AGENT_SOUND_DURATION_SECONDS='2')
        self.await_players(2)
        self.await_duck()
        with self.state() as data:
            data['streams'].pop('10')
            data['streams']['11'] = {'pid': '42', 'app': 'Firefox', 'raw': 65536}
        self.finish(first); self.finish(second)
        self.await_recovery()
        self.assert_only_signal_writes()
        with self.state() as data:
            self.assertEqual(data['streams']['11']['raw'], 65536)
            self.assertAlmostEqual(data['streams']['11']['soft'][0], 1.0)
            self.assertTrue(all(abs(write['props']['softVolumes'][0] - .512) < 1e-5
                                or abs(write['props']['softVolumes'][0] - 1) < 1e-5
                                for write in data['mixing']))

    def test_manual_slider_change_survives_cleanup(self):
        process = self.start()
        self.await_players(1)
        self.await_duck()
        with self.state() as data:
            data['streams']['10']['raw'] = 26214
        self.finish(process)
        self.await_recovery()
        self.assert_only_signal_writes()
        with self.state() as data:
            self.assertEqual(data['streams']['10']['raw'], 26214)
            self.assertAlmostEqual(data['streams']['10']['soft'][0], (26214 / 65536)**3)

    def test_stop_action_preserves_other_application_volume(self):
        process = self.start(FIXTURE_STOP='1')
        self.finish(process)
        with self.state() as data:
            self.assertEqual(data['streams']['10']['raw'], 65536)
            self.assertFalse(any(stream['app'] == 'agent-loop-sound' for stream in data['streams'].values()))
        self.assertEqual(list((self.base / 'runtime/agent-loop-sounds').glob('*.stop.*')), [])

    def test_signal_volume_override_applies_only_to_signal(self):
        process = self.start(AGENT_SOUND_VOLUME_PERCENT='55')
        self.finish(process)
        self.assert_only_signal_writes()
        with self.state() as data:
            self.assertTrue(all(write['raw'] == int(65536 * .55) for write in data['writes']))
            self.assertEqual(data['streams']['10']['raw'], 65536)

    def test_native_stream_without_pid_gets_its_own_volume(self):
        process = self.start(OMIT_PLAYER_PID='1', AGENT_SOUND_VOLUME_PERCENT='55')
        self.finish(process)
        self.assert_only_signal_writes()
        with self.state() as data:
            self.assertTrue(all(write['raw'] == int(65536 * .55) for write in data['writes']))

    def test_terminated_hook_restores_mixing(self):
        process = self.start(AGENT_SOUND_DURATION_SECONDS='3')
        self.await_duck()
        process.terminate()
        self.finish(process)
        self.await_recovery()
        with self.state() as data:
            self.assertEqual(data['streams']['10']['raw'], 65536)
            self.assertAlmostEqual(data['streams']['10']['soft'][0], 1.0)

    def test_killed_parent_is_detected_and_restored(self):
        process = self.start(AGENT_SOUND_DURATION_SECONDS='2')
        self.await_duck()
        process.kill()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with self.state() as data:
                if abs(data['streams']['10'].get('soft', [0])[0] - 1) < 1e-5:
                    return
            time.sleep(.02)
        self.fail('orphaned ducking was not released')

    def test_killed_notification_and_watcher_restore_without_a_second_sound(self):
        process = self.start(AGENT_SOUND_DURATION_SECONDS='2')
        self.await_duck()
        with self.state() as data:
            watcher = data['watchers'][0]
        os.kill(watcher, signal.SIGKILL)
        process.kill()
        process.communicate(timeout=4)
        self.await_recovery()
        with self.state() as data:
            self.assertEqual(len(data['started']), 1)
            self.assertEqual(len(data['watchers']), 2)
            self.assertAlmostEqual(data['streams']['10']['soft'][0], 1.0)
            self.assertEqual(data['streams']['10']['raw'], 65536)

    def test_recovery_retries_audio_write_after_notification_ends(self):
        process = self.start(AGENT_SOUND_DURATION_SECONDS='2')
        self.await_duck()
        with self.state() as data:
            data['failed_restores'] = 6
        process.kill()
        process.communicate(timeout=4)
        self.await_recovery()
        with self.state() as data:
            self.assertEqual(data['failed_restores'], 0)
            self.assertAlmostEqual(data['streams']['10']['soft'][0], 1.0)

    def test_unavailable_recovery_service_keeps_existing_mix(self):
        self.finish(self.start(FIXTURE_MANAGER_UNAVAILABLE='1'))
        with self.state() as data:
            self.assertEqual(len(data['started']), 1)
            self.assertFalse(data['mixing'])


class FakeAudio:
    def __init__(self):
        self.generation = 123
        self.nodes = {'100': {'id': 10, 'serial': 100, 'channels': [1., .125],
                             'soft': [1., 1.], 'mute': False, 'soft_mute': False,
                             'signal': False}}
        self.writes = []
        self.fail = False
        self.unconfirmed = False

    def snapshot(self):
        return self.generation, json.loads(json.dumps(self.nodes))

    def set_soft(self, generation, node, volumes, mute):
        if self.fail:
            return False
        self.writes.append((node['serial'], volumes, mute))
        self.nodes[str(node['serial'])]['soft'] = volumes
        self.nodes[str(node['serial'])]['soft_mute'] = mute
        return not self.unconfirmed


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.audio = FakeAudio()
        self.coordinator = DUCK.Coordinator(self.temp.name, self.audio,
                                             alive=lambda owner: owner.get('alive', True))

    def tearDown(self):
        self.temp.cleanup()

    def test_overlap_uses_one_factor_until_last_release(self):
        self.coordinator.step('a', {'percent': 80})
        self.coordinator.step('b', {'percent': 80})
        self.assertEqual(len(self.audio.writes), 1)
        self.coordinator.step('a')
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.512, .064]))
        self.coordinator.step('b')
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [1., .125]))

    def test_different_requests_use_strongest_without_multiplication(self):
        self.coordinator.step('a', {'percent': 80})
        self.coordinator.step('b', {'percent': 50})
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.125, .015625]))
        self.coordinator.step('b')
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.512, .064]))
        self.coordinator.step('a')

    def test_new_song_starts_from_unchanged_saved_volume(self):
        self.coordinator.step('a', {'percent': 80})
        original = self.audio.nodes.pop('100')
        self.audio.nodes['101'] = dict(original, serial=101, id=11, soft=[1., 1.])
        self.coordinator.step('a', {'percent': 80})
        self.assertTrue(DUCK.same(self.audio.nodes['101']['soft'], [.512, .064]))
        self.coordinator.step('a')
        self.assertEqual(self.audio.nodes['101']['channels'], [1., .125])

    def test_zero_then_restored_volume_is_not_saved_as_baseline(self):
        self.audio.nodes['100']['channels'] = [0., 0.]
        self.coordinator.step('a', {'percent': 80})
        self.audio.nodes['100']['channels'] = [1., .125]
        self.coordinator.step('a', {'percent': 80})
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.512, .064]))
        self.coordinator.step('a')
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [1., .125]))

    def test_manual_slider_and_mute_changes_survive(self):
        self.coordinator.step('a', {'percent': 80})
        self.audio.nodes['100'].update(channels=[.064, .008], mute=True)
        self.coordinator.step('a', {'percent': 80})
        self.assertTrue(self.audio.nodes['100']['soft_mute'])
        self.coordinator.step('a')
        self.assertEqual(self.audio.nodes['100']['channels'], [.064, .008])
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.064, .008]))
        self.assertTrue(self.audio.nodes['100']['soft_mute'])

    def test_slider_change_between_sessions_keeps_ducking_available(self):
        self.coordinator.step('a', {'percent': 80})
        self.assertEqual(self.coordinator.step('a'), (False, False))
        # PipeWire leaves the old soft values in Props while selecting the new
        # channel volume path when a user changes the slider.
        self.audio.nodes['100']['channels'] = [.064, .008]
        self.coordinator.step('b', {'percent': 80})
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.032768, .004096]))
        self.assertEqual(self.coordinator.step('b'), (False, False))
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.064, .008]))

    def test_no_stream_at_end_leaves_no_saved_volume_damage(self):
        self.coordinator.step('a', {'percent': 80})
        self.audio.nodes.clear()
        self.assertEqual(self.coordinator.step('a'), (False, False))

    def test_dead_owner_is_recovered_by_next_hook(self):
        self.coordinator.step('a', {'percent': 80, 'alive': False})
        self.assertFalse(self.audio.writes)
        self.coordinator.step('a', {'percent': 80})
        path = Path(self.temp.name) / 'coordination.json'
        state = json.loads(path.read_text()); state['owners']['a']['alive'] = False
        path.write_text(json.dumps(state))
        self.coordinator.step('b', {'percent': 80})
        self.assertEqual(len(self.audio.writes), 1)
        self.coordinator.step('b')
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [1., .125]))

    def test_expired_notification_is_released_with_both_processes_alive(self):
        owner = {'parent': 100, 'parent_birth': 'same', 'player': 101, 'player_birth': 'same',
                 'percent': 80, 'deadline': 5.0}
        coordinator = DUCK.Coordinator(self.temp.name, self.audio)
        with patch.object(DUCK, 'birth', return_value='same'), patch.object(DUCK.time, 'monotonic') as clock:
            clock.return_value = 4.0
            self.assertTrue(coordinator.step('a', owner)[0])
            clock.return_value = 6.0
            self.assertEqual(coordinator.step('a', owner), (False, False))
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [1., .125]))

    def test_server_restart_and_reused_node_id_do_not_restore_old_volume(self):
        self.coordinator.step('a', {'percent': 80})
        self.audio.generation += 1
        self.audio.nodes['100'].update(channels=[.027, .027], soft=[1., 1.])
        self.coordinator.step('a')
        self.assertEqual(len(self.audio.writes), 1)

    def test_failed_restore_is_retained_and_retried(self):
        self.coordinator.step('a', {'percent': 80})
        self.audio.fail = True
        self.assertEqual(self.coordinator.step('a'), (False, True))
        self.audio.fail = False
        self.assertEqual(self.coordinator.step('a'), (False, False))
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [1., .125]))

    def test_lost_write_reply_does_not_lose_recovery_after_restart(self):
        self.audio.unconfirmed = True
        self.coordinator.step('a', {'percent': 80})
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [.512, .064]))
        self.audio.unconfirmed = False
        restarted = DUCK.Coordinator(self.temp.name, self.audio, alive=lambda owner: False)
        self.assertEqual(restarted.step('a'), (False, False))
        self.assertTrue(DUCK.same(self.audio.nodes['100']['soft'], [1., .125]))

    def test_stream_with_temporarily_missing_props_keeps_pending_restore(self):
        self.coordinator.step('a', {'percent': 80})
        node = self.audio.nodes['100']
        self.audio.nodes['100'] = None
        self.assertEqual(self.coordinator.step('a'), (False, True))
        self.audio.nodes['100'] = node
        self.assertEqual(self.coordinator.step('a'), (False, False))
        self.assertTrue(DUCK.same(node['soft'], [1., .125]))

    def test_other_mixer_is_not_overwritten(self):
        self.coordinator.step('a', {'percent': 80})
        self.audio.nodes['100']['soft'] = [.25, .25]
        self.coordinator.step('a', {'percent': 80})
        self.coordinator.step('a')
        self.assertEqual(self.audio.nodes['100']['soft'], [.25, .25])

    def test_existing_nondefault_software_mixer_is_skipped(self):
        self.audio.nodes['100']['soft'] = [.25, .25]
        self.coordinator.step('a', {'percent': 80})
        self.coordinator.step('a')
        self.assertFalse(self.audio.writes)

    def test_runtime_lock_cannot_be_a_symlink(self):
        target = Path(self.temp.name) / 'elsewhere'; target.write_text('unchanged')
        (Path(self.temp.name) / 'coordination.lock').symlink_to(target)
        with self.assertRaises(OSError):
            self.coordinator.step('a', {'percent': 80})
        self.assertEqual(target.read_text(), 'unchanged')

    def test_dump_updates_keep_identity_and_replace_parameters(self):
        snapshot = [{'id': 0, 'info': dict.fromkeys(['cookie'], 123)}, {'id': 10, 'info': {
            'props': {'media.class': 'Stream/Output/Audio', 'object.serial': 100},
            'params': {'Props': [{'channelVolumes': [1.], 'softVolumes': [1.]}]}}}]
        update = [{'id': 10, 'info': {'params': {'Props': [
            {'channelVolumes': [.125], 'softVolumes': [.064]}]}}}]
        generation, nodes = DUCK.nodes_from_dump(json.dumps(snapshot) + json.dumps(update))
        self.assertEqual(generation, 123)
        self.assertEqual(nodes['100']['channels'], [.125])
        self.assertEqual(nodes['100']['soft'], [.064])
        incomplete = [{'id': 10, 'info': {'params': {'Props': []}}}]
        _, nodes = DUCK.nodes_from_dump(json.dumps(snapshot) + json.dumps(incomplete))
        self.assertIn('100', nodes)
        self.assertIsNone(nodes['100'])
        _, nodes = DUCK.nodes_from_dump(json.dumps(snapshot) + json.dumps([{'id': 10, 'info': None}]))
        self.assertFalse(nodes)


class AudioWriteTests(unittest.TestCase):
    def setUp(self):
        self.node = FakeAudio().nodes['100']
        self.audio = DUCK.Audio()

    def test_reused_id_does_not_accept_old_serial(self):
        self.audio.snapshot = lambda: (123, {'101': dict(self.node, serial=101)})
        with patch.object(DUCK.subprocess, 'run') as command:
            self.assertFalse(self.audio.set_soft(123, self.node, [.512, .064], False))
            command.assert_not_called()

    def test_slider_change_between_snapshots_prevents_stale_write(self):
        self.audio.snapshot = lambda: (123, {'100': dict(self.node, channels=[.125, .125])})
        with patch.object(DUCK.subprocess, 'run') as command:
            self.assertFalse(self.audio.set_soft(123, self.node, [.512, .064], False))
            command.assert_not_called()

    def test_command_success_without_effect_is_not_committed(self):
        self.audio.snapshot = lambda: (123, {'100': self.node})
        with patch.object(DUCK.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            self.assertFalse(self.audio.set_soft(123, self.node, [.512, .064], False))

    def test_only_temporary_properties_are_written(self):
        after = dict(self.node, soft=[.512, .064])
        snapshots = iter([(123, {'100': self.node}), (123, {'100': after})])
        self.audio.snapshot = lambda: next(snapshots)
        with patch.object(DUCK.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as command:
            self.assertTrue(self.audio.set_soft(123, self.node, [.512, .064], False))
            self.assertEqual(json.loads(command.call_args.args[0][-1]),
                             {'softVolumes': [.512, .064], 'softMute': False})


if __name__ == '__main__':
    unittest.main()
