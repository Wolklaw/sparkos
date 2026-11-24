"""Spark Camera without a window: the helpers, the formats, and the real pipelines fed by a test
pattern and a test tone (SPARK_CAMERA_FAKE=1), so no camera or microphone is needed. Everything
is written to temporary folders, and HOME points at one, so nothing of yours is touched."""

import atexit
import contextlib
import io
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP_HOME = tempfile.mkdtemp(prefix='spark-camera-home-')
os.environ['HOME'] = TMP_HOME
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.pop(var, None)
os.environ['SPARK_CAMERA_FAKE'] = '1'
os.environ['SPARK_CAMERA_REDUCED_MOTION'] = '1'

from sparkcamera import core, media  # noqa: E402


atexit.register(shutil.rmtree, TMP_HOME, True)


class Helpers(unittest.TestCase):
    def test_duration_text(self):
        self.assertEqual(core.duration_text(0), '0:00')
        self.assertEqual(core.duration_text(72.4), '1:12')
        self.assertEqual(core.duration_text(3725), '1:02:05')
        self.assertEqual(core.duration_text(-5), '0:00')

    def test_folders_are_under_home(self):
        self.assertTrue(core.home().startswith(tempfile.gettempdir()), "HOME is not a temp folder")
        self.assertEqual(core.photos_dir(), os.path.join(core.home(), 'Pictures', 'Camera'))
        self.assertEqual(core.videos_dir(), os.path.join(core.home(), 'Videos', 'Camera'))
        self.assertEqual(core.recordings_dir(), os.path.join(core.home(), 'Music', 'Recordings'))
        self.assertEqual(core.home_short(core.photos_dir()), '~/Pictures/Camera')

    def test_stamp_has_no_colons(self):
        self.assertNotIn(':', core.stamp())

    def test_unique_path_never_overwrites(self):
        folder = tempfile.mkdtemp(prefix='spark-camera-unique-')
        self.addCleanup(shutil.rmtree, folder, True)
        first = core.unique_path(folder, 'Photo', '.jpg')
        open(first, 'w').close()
        second = core.unique_path(folder, 'Photo', '.jpg')
        self.assertNotEqual(first, second)
        self.assertTrue(second.endswith('Photo 2.jpg'))

    def test_settings_round_trip_and_bad_file(self):
        values = dict(core.DEFAULTS, countdown=5, mirror=False)
        core.save_settings(values)
        loaded = core.load_settings()
        self.assertEqual(loaded['countdown'], 5)
        self.assertFalse(loaded['mirror'])
        with open(core.settings_path(), 'w') as f:
            f.write('{ not json')
        self.assertEqual(core.load_settings(), core.DEFAULTS)

    def test_level_fraction(self):
        self.assertEqual(media.level_fraction(-90), 0.0)
        self.assertEqual(media.level_fraction(0), 1.0)
        self.assertAlmostEqual(media.level_fraction(-30), 0.5)

    def test_clean_name(self):
        from sparkcamera.app import clean_name
        self.assertEqual(clean_name('  ../../etc/passwd  '), 'etc passwd')
        self.assertEqual(clean_name('.hidden'), 'hidden')
        self.assertEqual(clean_name('a\x00b\nc'), 'a b c')
        self.assertEqual(clean_name('   '), '')
        self.assertLessEqual(len(clean_name('x' * 500)), 120)


@unittest.skipIf(media.init(), "GStreamer is not available")
class Engine(unittest.TestCase):
    def test_fake_devices(self):
        cams, mics = media.list_cameras(), media.list_mics()
        self.assertEqual(len(cams), 1)
        self.assertEqual(len(mics), 1)
        self.assertTrue(cams[0].modes)
        self.assertIsNotNone(media.pick_mode(cams[0].modes, '640x480'))

    def test_formats_come_from_installed_elements(self):
        voice = media.voice_formats()
        self.assertTrue(voice, "no voice encoder at all")
        for fmt in media.video_formats() + voice:
            self.assertTrue(fmt.label and fmt.ext.startswith('.'))
        self.assertIs(media.pick_by_key(voice, 'nope'), voice[0])
        self.assertIsNone(media.pick_by_key([], 'x'))

    def test_self_test_passes_and_cleans_up(self):
        from sparkcamera import cli
        before = {n for n in os.listdir(tempfile.gettempdir())
                  if n.startswith('spark-camera-selftest-')}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.self_test()
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn('self-test passed', out.getvalue())
        after = {n for n in os.listdir(tempfile.gettempdir())
                 if n.startswith('spark-camera-selftest-')}
        self.assertEqual(after, before, "the self-test left its folder behind")

    def test_recording_starts_at_zero_and_has_sound(self):
        cam, mic = media.list_cameras()[0], media.list_mics()[0]
        fmt = media.video_formats()[0]
        tmp = tempfile.mkdtemp(prefix='spark-camera-rec-')
        self.addCleanup(shutil.rmtree, tmp, True)
        session = media.CameraSession(cam, media.pick_mode(cam.modes, '640x480') or cam.modes[0])
        self.addCleanup(session.stop)
        session.start()
        end = time.monotonic() + 5
        while session.new_preview() is None and time.monotonic() < end:
            time.sleep(0.05)
        path = os.path.join(tmp, 'clip' + fmt.ext)
        session.start_recording(path, fmt, mic)
        time.sleep(1.5)
        session.stop_recording()
        events, end = [], time.monotonic() + 8
        while not events and time.monotonic() < end:
            time.sleep(0.05)
            events += session.poll()
        self.assertTrue(events, "no 'recorded' event")
        self.assertGreater(os.path.getsize(path), 1024)
        self.assertTrue(0.8 <= media.file_duration(path) <= 3.0)

    def test_stop_right_after_start_still_finishes(self):
        cam, mic = media.list_cameras()[0], media.list_mics()[0]
        fmt = media.video_formats()[0]
        tmp = tempfile.mkdtemp(prefix='spark-camera-quick-')
        self.addCleanup(shutil.rmtree, tmp, True)
        session = media.CameraSession(cam, media.pick_mode(cam.modes, '640x480') or cam.modes[0])
        self.addCleanup(session.stop)
        session.start()
        end = time.monotonic() + 5
        while session.new_preview() is None and time.monotonic() < end:
            time.sleep(0.05)
        time.sleep(0.5)
        path = os.path.join(tmp, 'clip' + fmt.ext)
        session.start_recording(path, fmt, mic)
        session.stop_recording()                       # a double click
        events, end = [], time.monotonic() + 3
        while not events and time.monotonic() < end:
            time.sleep(0.05)
            events += session.poll()
        self.assertTrue(events, "the recording never finished")
        self.assertGreater(os.path.getsize(path), 1024)

    def test_voice_pause_is_not_recorded(self):
        mic, fmt = media.list_mics()[0], media.voice_formats()[0]
        tmp = tempfile.mkdtemp(prefix='spark-camera-voice-')
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, 'v' + fmt.ext)
        rec = media.VoiceSession(mic, fmt, path)
        rec.start()
        time.sleep(0.8)
        rec.pause()
        self.assertTrue(rec.paused)
        time.sleep(2.0)
        rec.resume()
        time.sleep(0.8)
        rec.finish()
        events, end = [], time.monotonic() + 8
        while not events and time.monotonic() < end:
            time.sleep(0.05)
            events += rec.poll()
        length = media.file_duration(path)
        self.assertTrue(1.0 <= length <= 2.8, f"{length} s: the pause was recorded")


class Files(unittest.TestCase):
    def test_gallery_and_recordings_listing(self):
        from sparkcamera.app import gallery_items, recording_files
        for folder, name in ((core.photos_dir(), 'a.jpg'), (core.videos_dir(), 'b.webm'),
                             (core.videos_dir(), 'notes.txt'), (core.recordings_dir(), 'c.opus'),
                             (core.recordings_dir(), 'd.flac'), (core.recordings_dir(), 'e.png')):
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, name), 'wb') as f:
                f.write(b'x' * 10)
        kinds = {os.path.basename(p): k for p, k, _m in gallery_items()}
        self.assertEqual(kinds, {'a.jpg': 'photo', 'b.webm': 'video'})
        self.assertEqual(sorted(os.path.basename(p) for p, _m, _s in recording_files()),
                         ['c.opus', 'd.flac'])


if __name__ == '__main__':
    unittest.main()
