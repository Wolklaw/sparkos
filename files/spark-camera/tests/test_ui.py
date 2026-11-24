"""The window, under a display (Xvfb in CI), on a test pattern and a test tone: a photo, a video,
a voice recording, rename and delete-to-trash. HOME and the XDG folders are temporary, the
dialogs are answered by the test, and opening a file is recorded, not run. Nothing outside the
temporary folders is written."""

import atexit
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP_HOME = tempfile.mkdtemp(prefix='spark-camera-uihome-')
os.environ['HOME'] = TMP_HOME
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.pop(var, None)
os.environ['SPARK_CAMERA_FAKE'] = '1'
os.environ['SPARK_CAMERA_REDUCED_MOTION'] = '1'

from sparkcamera import core, media  # noqa: E402


atexit.register(shutil.rmtree, TMP_HOME, True)


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
@unittest.skipIf(media.init(), "GStreamer is not available")
class Window(unittest.TestCase):
    def setUp(self):
        for sub in ('Pictures', 'Videos', 'Music', '.config', '.local'):
            shutil.rmtree(os.path.join(core.home(), sub), ignore_errors=True)
        self.opened, self.errors, self.asked, self.answer = [], [], [], True
        self.new_name = None
        from sparkcamera.app import App
        self.app = App(opener=lambda argv: self.opened.append(argv) or True,
                       ask=self._ask, tell=lambda *a, **k: None, warn=lambda *a, **k: None,
                       error=lambda *a, **k: self.errors.append(a),
                       name=lambda *a, **k: self.new_name)
        self.addCleanup(self.app.close)
        self.app.root.geometry('1120x780')
        self.pump(1.2)

    def _ask(self, title, message, **kw):
        self.asked.append((title, message))
        return self.answer

    def pump(self, seconds=0.3, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.root.update()
            if until is not None and until():
                return
            time.sleep(0.01)

    def test_opens_on_the_camera_with_a_picture(self):
        self.assertEqual(self.app.tab, 'camera')
        self.pump(3, until=lambda: self.app.cam.session is not None
                  and self.app.cam.session.running)
        self.assertTrue(self.app.cam.session.running)
        self.assertEqual(self.errors, [])

    def test_photo_is_a_jpeg_in_pictures_camera(self):
        cam = self.app.cam
        self.pump(3, until=lambda: cam.session is not None and cam.session.running)
        path = None
        for _ in range(20):
            path = cam.take_photo()
            if path:
                break
            self.pump(0.3)
        self.assertIsNotNone(path)
        self.assertEqual(os.path.dirname(path), core.photos_dir())
        from PIL import Image
        with Image.open(path) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertGreaterEqual(image.size[0], 320)
        self.pump(0.5)
        self.assertEqual(self.errors, [])

    def test_countdown_waits_then_takes_the_photo(self):
        cam = self.app.cam
        self.pump(3, until=lambda: cam.session is not None and cam.session.running)
        self.pump(0.8)
        self.app.settings['countdown'] = 3
        cam.shutter()
        self.assertEqual(cam.state, 'counting')
        self.pump(1.5)
        self.assertFalse(os.path.isdir(core.photos_dir()) and os.listdir(core.photos_dir()),
                         "photo taken before the countdown ended")
        cam.shutter()                                   # a second press cancels
        self.assertEqual(cam.state, 'idle')
        self.pump(2.5)
        self.assertFalse(os.path.isdir(core.photos_dir()) and os.listdir(core.photos_dir()))

    def test_video_records_and_lands_in_the_gallery(self):
        cam = self.app.cam
        self.pump(3, until=lambda: cam.session is not None and cam.session.running)
        self.pump(0.8)
        cam.set_kind('video')
        cam.shutter()
        self.assertEqual(cam.state, 'recording')
        self.pump(1.5)
        cam.shutter()
        self.pump(10, until=lambda: cam.state == 'idle')
        self.assertEqual(cam.state, 'idle')
        files = os.listdir(core.videos_dir())
        self.assertEqual(len(files), 1, files)
        self.assertGreater(os.path.getsize(os.path.join(core.videos_dir(), files[0])), 1024)
        self.assertEqual(self.errors, [])

    def test_voice_record_pause_stop_rename_delete(self):
        app = self.app
        app.pick_tab('voice')
        self.pump(1.0)
        v = app.voice
        v.record()
        self.assertIsNotNone(v.rec)
        self.pump(1.0)
        v.pause()
        self.assertTrue(v.rec.paused)
        v.pause()
        self.pump(0.5)
        self.assertFalse(app.cam.busy())
        v.finish()
        self.pump(10, until=lambda: v.rec is None)
        self.assertIsNone(v.rec)
        self.assertEqual(len(v.rows), 1)
        path = next(iter(v.rows))
        self.assertEqual(os.path.dirname(path), core.recordings_dir())
        # rename keeps the extension and refuses names that climb out of the folder
        v.tree.selection_set(v.rows[path])
        self.new_name = '../../Interview'
        v.rename()
        renamed = [n for n in os.listdir(core.recordings_dir())]
        self.assertEqual(len(renamed), 1)
        self.assertTrue(renamed[0].startswith('Interview'), renamed)
        self.assertTrue(renamed[0].endswith(os.path.splitext(path)[1]))
        # delete asks, then goes to the trash and never deletes for good
        path = os.path.join(core.recordings_dir(), renamed[0])
        v.tree.selection_set(v.rows[path])
        self.answer = False
        v.delete()
        self.assertTrue(os.path.exists(path), "deleted although the answer was no")
        self.answer = True
        v.tree.selection_set(v.rows[path])
        v.delete()
        self.assertFalse(os.path.exists(path))
        trashed = os.listdir(os.path.join(core.data_home(), 'Trash', 'files'))
        self.assertEqual(trashed, renamed)
        self.assertEqual(self.errors, [])

    def test_cannot_switch_tab_while_recording(self):
        cam = self.app.cam
        self.pump(3, until=lambda: cam.session is not None and cam.session.running)
        self.pump(0.8)
        cam.set_kind('video')
        cam.shutter()
        self.app.pick_tab('voice')
        self.assertEqual(self.app.tab, 'camera')
        cam.shutter()
        self.pump(10, until=lambda: cam.state == 'idle')
        self.app.pick_tab('voice')
        self.assertEqual(self.app.tab, 'voice')


if __name__ == '__main__':
    unittest.main()
