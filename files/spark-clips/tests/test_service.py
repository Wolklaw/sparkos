"""The service on a test pattern and a test tone (SPARK_CLIPS_FAKE=1): it records into the
buffer, keeps the buffer's memory flat, saves clips (checked by reading the file back), trims
them, and answers the control socket the way --save and --status use it. Needs GStreamer and a
video encoder; skipped without them. No display, no GPU, no game."""

import contextlib
import io
import os
import time
import unittest

import testenv
from sparkclips import buffer, cli, clipfile, core, games, ipc, library, pipeline
from sparkclips.daemon import Service
from sparkclips.text import t

HAVE = clipfile.init() is None and pipeline.pick_encoder('h264') is not None \
    and not pipeline.missing_elements()
GAME = games.Game('Test Game', 'wine', 1)


def wait(service, state, seconds=25.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        service.tick()
        if service.state == state:
            return True
        time.sleep(0.25)
    return False


@unittest.skipUnless(HAVE, "needs GStreamer and a video encoder")
class Recording(unittest.TestCase):
    def setUp(self):
        testenv.reset()
        core.save_settings(dict(core.DEFAULTS, seconds=15, fps='30'))
        self.game = GAME
        self.service = Service(notifier=None, probe=lambda: self.game)
        self.addCleanup(self.service.shutdown)

    def test_waits_for_a_game_then_records_then_stops(self):
        self.game = None
        for _ in range(3):
            self.service.tick()
        self.assertEqual(self.service.state, 'waiting')
        self.assertIsNone(self.service.proc)
        self.assertEqual(buffer.list_pieces(core.buffer_dir()), [])
        self.assertEqual(self.service.save()['problem'], 'not_recording')
        self.game = GAME
        self.service.last_probe = 0.0
        self.assertTrue(wait(self.service, 'recording'))
        self.assertEqual(self.service.status()['game'], 'Test Game')
        # the game ends: after the grace period the buffer stops and the memory is freed
        self.game = None
        self.service.gone_since = time.monotonic() - 3600
        self.service.last_probe = 0.0
        self.assertTrue(wait(self.service, 'waiting', 10))
        self.assertEqual(buffer.list_pieces(core.buffer_dir()), [])

    def test_saves_a_playable_clip_with_sound_in_the_games_folder(self):
        self.assertTrue(wait(self.service, 'recording'))
        time.sleep(7)
        self.service.tick()
        reply = self.service.save()
        self.assertTrue(reply['ok'], reply)
        path = reply['path']
        self.assertEqual(os.path.dirname(path), os.path.join(core.clips_dir(), 'Test Game'))
        self.assertTrue(path.endswith('.mp4'))
        info = clipfile.probe(path)
        self.assertTrue(info['video'])
        self.assertEqual(info['audio'], 1)                          # sound on, microphone off
        self.assertEqual(info['codec'], 'h264')
        self.assertGreaterEqual(info['duration'], 4)
        self.assertLessEqual(info['duration'], 9)
        self.assertEqual(self.service.status()['last_clip']['path'], path)
        self.assertEqual([c.path for c in library.list_clips()], [path])
        # nothing but the clip is left in its folder
        self.assertEqual(os.listdir(os.path.dirname(path)), [os.path.basename(path)])

        # a thumbnail from the file
        thumb = os.path.join(core.cache_dir(), 'thumb.jpg')
        self.assertTrue(clipfile.thumbnail(path, thumb, 160))
        from PIL import Image
        with Image.open(thumb) as image:
            self.assertEqual(image.size[0], 160)
            self.assertEqual(image.size[1], 90)             # the shape of the 640x360 picture

        # a lossless cut: about the length asked, and it starts on a keyframe (a second at most
        # before the start)
        cut = library.trimmed_name(os.path.dirname(path), os.path.splitext(
            os.path.basename(path))[0])
        clipfile.trim_clip(path, cut, 1.5, 3.5)
        length = clipfile.probe(cut)['duration']
        self.assertGreaterEqual(length, 1.9)
        self.assertLessEqual(length, 3.6)
        self.assertEqual(clipfile.probe(cut)['audio'], 1)

    def test_the_microphone_adds_a_second_track(self):
        core.save_settings(dict(core.DEFAULTS, seconds=15, fps='30', mic=True))
        self.service.reload()
        self.assertTrue(wait(self.service, 'recording'))
        time.sleep(5)
        reply = self.service.save()
        self.assertTrue(reply['ok'], reply)
        self.assertEqual(clipfile.probe(reply['path'])['audio'], 2)

    def test_the_buffer_does_not_grow_past_its_length(self):
        self.assertTrue(wait(self.service, 'recording'))
        end = time.monotonic() + 26
        most = 0
        while time.monotonic() < end:
            self.service.tick()
            most = max(most, len(buffer.list_pieces(core.buffer_dir())))
            time.sleep(0.5)
        held = buffer.list_pieces(core.buffer_dir())
        self.assertGreater(len(held), 10)
        self.assertLessEqual(most, 15 + buffer.MARGIN + 3)
        self.assertGreater(held[0].number, 3, "the first pieces should be gone")
        self.assertLess(buffer.used_bytes(held), 15_000_000)

    def test_a_changed_setting_restarts_the_recording(self):
        self.assertTrue(wait(self.service, 'recording'))
        first = self.service.proc.pid
        core.save_settings(dict(core.DEFAULTS, seconds=15, fps='60', sound=False))
        self.service.reload()
        self.assertTrue(wait(self.service, 'recording'))
        self.assertNotEqual(self.service.proc.pid, first)
        time.sleep(4)
        self.service.tick()
        reply = self.service.save()
        self.assertTrue(reply['ok'], reply)
        self.assertEqual(clipfile.probe(reply['path'])['audio'], 0)

    def test_turning_the_replay_off_stops_it(self):
        self.assertTrue(wait(self.service, 'recording'))
        core.save_settings(dict(core.DEFAULTS, seconds=15, keep=False))
        self.service.reload()
        self.assertTrue(wait(self.service, 'off', 10))
        self.assertIsNone(self.service.proc)

    def test_a_missing_encoder_is_reported_not_retried_forever(self):
        os.environ['SPARK_CLIPS_ENCODER'] = 'no-such-encoder'
        self.addCleanup(os.environ.pop, 'SPARK_CLIPS_ENCODER', None)
        self.service.tick()
        self.assertEqual(self.service.state, 'error')
        self.assertEqual(self.service.problem, 'no_encoder')

    def test_the_command_line_talks_to_the_service(self):
        self.service.start_background()
        self.assertTrue(wait(self.service, 'recording'))
        time.sleep(5)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--status']), cli.EXIT_OK)
        self.assertIn('Test Game', out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--save']), cli.EXIT_OK)
        path = out.getvalue().strip()
        self.assertTrue(os.path.isfile(path), path)
        status = ipc.ask('status')
        self.assertEqual(status['state'], 'recording')
        self.assertEqual(status['last_clip']['path'], path)


class Without(unittest.TestCase):
    """No service running: the command line says so and exits with its own code."""

    def test_status_and_save_without_a_service(self):
        testenv.reset()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(['--status']), cli.EXIT_NO_SERVICE)
            self.assertEqual(cli.main(['--save']), cli.EXIT_NO_SERVICE)
        said = t('cli.service_off').split('.')[0]
        self.assertIn(said, out.getvalue())
        self.assertIn(said, err.getvalue())

    def test_status_json(self):
        testenv.reset()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--status', '--json']), cli.EXIT_NO_SERVICE)
        self.assertEqual(out.getvalue().strip(), '{"ok": false, "state": "service_off"}')


@unittest.skipUnless(HAVE, "needs GStreamer and a video encoder")
class SelfTest(unittest.TestCase):
    def test_self_test_passes_and_cleans_up(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['--self-test'])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn('self-test passed', out.getvalue())


if __name__ == '__main__':
    unittest.main()
