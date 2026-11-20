"""Spark Media tests. Plain unittest:

    python -m unittest discover -s files/spark-media/tests -v

Logic tests run anywhere. Player tests need GStreamer's Python bindings (they skip without
them). UI tests need a display (on CI: xvfb-run) and open real windows for a few seconds.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-media-{var.lower()}-'))

from PIL import Image  # noqa: E402

from sparkmedia import core  # noqa: E402
from sparkmedia import player as gst  # noqa: E402


def touch(path: str, data: bytes = b'') -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-media-test-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_kind_of(self):
        self.assertEqual(core.kind_of('a/B.JPG'), 'photo')
        self.assertEqual(core.kind_of('movie.mkv'), 'video')
        self.assertEqual(core.kind_of('song.flac'), 'music')
        self.assertIsNone(core.kind_of('notes.txt'))
        self.assertIsNone(core.kind_of('noext'))

    def test_natural_order(self):
        names = ['Track 10.mp3', 'track 2.mp3', 'Track 1.mp3']
        self.assertEqual(sorted(names, key=core.natural_key),
                         ['Track 1.mp3', 'track 2.mp3', 'Track 10.mp3'])

    def test_folder_items_and_siblings(self):
        for name in ('b.jpg', 'a10.png', 'a2.png', 'clip.mp4', 'song.mp3', '.hidden.jpg',
                     'readme.txt'):
            touch(os.path.join(self.dir, name))
        os.mkdir(os.path.join(self.dir, 'Sub'))
        dirs, files = core.folder_items(self.dir, 'photo')
        self.assertEqual([os.path.basename(d) for d in dirs], ['Sub'])
        self.assertEqual([os.path.basename(f) for f in files], ['a2.png', 'a10.png', 'b.jpg'])
        _dirs, everything = core.folder_items(self.dir)
        self.assertEqual(len(everything), 5)
        sibs = core.siblings(os.path.join(self.dir, 'b.jpg'))
        self.assertEqual([os.path.basename(f) for f in sibs], ['a2.png', 'a10.png', 'b.jpg'])

    def test_subtitle_and_cover(self):
        video = touch(os.path.join(self.dir, 'Movie.mkv'))
        self.assertIsNone(core.subtitle_for(video))
        touch(os.path.join(self.dir, 'Movie.en.srt'))
        self.assertEqual(os.path.basename(core.subtitle_for(video)), 'Movie.en.srt')
        song = touch(os.path.join(self.dir, 'song.mp3'))
        self.assertIsNone(core.folder_cover(song))
        touch(os.path.join(self.dir, 'Cover.JPG'))
        self.assertEqual(os.path.basename(core.folder_cover(song)), 'Cover.JPG')

    def test_clock(self):
        self.assertEqual(core.clock(0), '0:00')
        self.assertEqual(core.clock(75.9), '1:15')
        self.assertEqual(core.clock(3725), '1:02:05')
        self.assertEqual(core.clock(None), '--:--')

    def test_path_from_arg(self):
        if os.name != 'nt':
            self.assertEqual(core.path_from_arg('file:///home/a%20b/c.jpg'), '/home/a b/c.jpg')

    def test_fit_and_regions(self):
        self.assertAlmostEqual(core.fit_scale((4000, 2000), (1000, 1000)), 0.25)
        self.assertEqual(core.fit_scale((200, 100), (1000, 1000)), 1.0)       # no upscaling
        # small image: centred whatever the requested centre
        self.assertEqual(core.clamp_center((200, 100), (1000, 800), 1.0, (0, 0)), (100, 50))
        # big image at 100%: the centre stays far enough from the edges
        self.assertEqual(core.clamp_center((4000, 3000), (1000, 800), 1.0, (0, 0)), (500, 400))
        box, offset = core.visible_region((4000, 3000), (1000, 800), 1.0, (500, 400))
        self.assertEqual(box[:2], (0, 0))
        self.assertEqual(offset, (0, 0))
        self.assertLessEqual(box[2] - box[0], 1002)
        # zoomed in 4x: only a quarter of the view's size in image pixels is cropped
        box, _ = core.visible_region((4000, 3000), (1000, 800), 4.0, (2000, 1500))
        self.assertLessEqual(box[2] - box[0], 252)

    def test_photo_orientation_and_animation(self):
        path = os.path.join(self.dir, 'turned.jpg')
        image = Image.new('RGB', (300, 200), 'red')
        exif = image.getexif()
        exif[0x0112] = 6                     # rotate 90° clockwise to show
        image.save(path, exif=exif.tobytes())
        self.assertEqual(core.Photo(path).size, (200, 300))
        gif = os.path.join(self.dir, 'loop.gif')
        frames = [Image.new('RGB', (40, 40), c) for c in ('red', 'green', 'blue')]
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=50, loop=0)
        photo = core.Photo(gif)
        self.assertTrue(photo.animated)
        self.assertEqual(len(photo.frames), 3)
        deep = os.path.join(self.dir, 'deep.png')
        Image.new('I;16', (20, 20), 40000).save(deep)
        self.assertIn(core.Photo(deep).image.mode, ('RGB', 'RGBA'))

    def test_broken_photo(self):
        path = touch(os.path.join(self.dir, 'broken.jpg'), b'not a jpeg')
        with self.assertRaises(core.PhotoError):
            core.Photo(path)
        self.assertIsNone(core.photo_thumbnail(path))

    def test_thumbnail_cache(self):
        path = os.path.join(self.dir, 'big.png')
        Image.new('RGB', (1200, 800), 'blue').save(path)
        thumb = core.photo_thumbnail(path)
        self.assertEqual(max(thumb.size), 256)
        cached = core.thumbnail_path(path)
        self.assertTrue(os.path.isfile(cached))
        with Image.open(cached) as stored:
            self.assertEqual(stored.info.get('Thumb::URI'), core.file_uri(path))
        self.assertIsNotNone(core.cached_thumbnail(path))
        # a changed file invalidates it
        os.utime(path, (time.time() + 100, time.time() + 100))
        self.assertIsNone(core.cached_thumbnail(path))


@unittest.skipUnless(gst.available(), "GStreamer's Python bindings are not installed")
class PlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='spark-media-gst-')
        cls.song = os.path.join(cls.dir, 'tone.ogg')
        pipeline = gst.Gst.parse_launch(
            f'audiotestsrc num-buffers=86 ! audioconvert ! vorbisenc ! oggmux ! '
            f'filesink location={cls.song}')
        pipeline.set_state(gst.Gst.State.PLAYING)
        pipeline.get_bus().timed_pop_filtered(30 * gst.SECOND, gst.Gst.MessageType.EOS)
        pipeline.set_state(gst.Gst.State.NULL)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _run(self, p, until, limit=15.0):
        end = time.time() + limit
        while time.time() < end and not until():
            p.poll()
            time.sleep(0.03)

    def test_plays_to_the_end(self):
        events = []
        p = gst.Player(lambda w, _d: events.append(w), audio_sink='fakesink',
                       video_sink='fakesink')
        p.load(self.song, video=False)
        self._run(p, lambda: 'eos' in events)
        self.assertIn('eos', events)
        self.assertAlmostEqual(p.duration, 2.0, delta=0.3)
        self.assertTrue(p.ended)
        p.close()

    def test_seek_pause_volume(self):
        events = []
        p = gst.Player(lambda w, _d: events.append(w), audio_sink='fakesink',
                       video_sink='fakesink')
        p.load(self.song, video=False, play=False)
        self._run(p, lambda: 'ready' in events)
        p.seek(1.0)
        self._run(p, lambda: (p.position() or 0) >= 0.9, limit=3)
        self.assertGreaterEqual(p.position(), 0.9)
        p.volume = 0.5
        self.assertAlmostEqual(p.playbin.get_property('volume'), 0.125)
        p.muted = True
        self.assertTrue(p.playbin.get_property('mute'))
        p.close()

    def test_missing_file_reports_error(self):
        events = []
        p = gst.Player(lambda w, _d: events.append(w), audio_sink='fakesink',
                       video_sink='fakesink')
        p.load(os.path.join(self.dir, 'gone.ogg'), video=False)
        self._run(p, lambda: 'error' in events)
        self.assertIn('error', events)
        self.assertTrue(p.error)
        p.close()


def have_display() -> bool:
    if os.name == 'nt':
        return True
    return bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class UITests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-media-ui-')
        for i, colour in enumerate(('red', 'green', 'blue')):
            Image.new('RGB', (1600, 900), colour).save(os.path.join(self.dir, f'p{i}.png'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def pump(self, app, seconds=0.4):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def test_library_viewer_round_trip(self):
        from sparkmedia.app import App
        from sparkmedia.library import HomeView
        from sparkmedia.viewer import PhotoView
        app = App([self.dir], 'photo')
        try:
            self.pump(app, 1.0)
            self.assertIsInstance(app.view, HomeView)
            self.assertEqual(len(app.view.files), 3)
            app.view.activate(0)
            self.pump(app)
            view = app.view
            self.assertIsInstance(view, PhotoView)
            self.assertEqual(view.index, 0)
            view.next()
            view.next()
            view.next()                    # wraps round
            self.assertEqual(view.index, 0)
            view.zoom_to(1.0)
            self.pump(app)
            self.assertAlmostEqual(view.scale, 1.0)
            view.fit()
            self.assertTrue(view.fitted)
            view.rotate()
            self.assertEqual(view.rotation, 90)
            app.toggle_fullscreen()
            self.pump(app)
            self.assertFalse(view.bar.winfo_ismapped())
            app.toggle_fullscreen()
            self.pump(app)
            app.go_back()
            self.pump(app)
            self.assertIsInstance(app.view, HomeView)
        finally:
            app._on_close()

    def test_opens_file_from_command_line(self):
        from sparkmedia.app import App
        from sparkmedia.viewer import PhotoView
        app = App([os.path.join(self.dir, 'p1.png')])
        try:
            self.pump(app)
            self.assertIsInstance(app.view, PhotoView)
            self.assertEqual(app.view.index, 1)
            self.assertEqual(len(app.view.files), 3)
        finally:
            app._on_close()

    @unittest.skipUnless(gst.available(), "needs GStreamer")
    def test_music_view_plays(self):
        from sparkmedia.app import App
        from sparkmedia.playview import PlayerView
        song = os.path.join(self.dir, 'tone.ogg')
        pipeline = gst.Gst.parse_launch(
            f'audiotestsrc num-buffers=86 ! audioconvert ! vorbisenc ! oggmux ! '
            f'filesink location={song}')
        pipeline.set_state(gst.Gst.State.PLAYING)
        pipeline.get_bus().timed_pop_filtered(30 * gst.SECOND, gst.Gst.MessageType.EOS)
        pipeline.set_state(gst.Gst.State.NULL)
        app = App([song])
        try:
            self.pump(app, 1.5)
            self.assertIsInstance(app.view, PlayerView)
            self.assertIsNotNone(app.view.player)
            # audio output may not exist on CI; it either plays or reports a clear error
            self.assertTrue(app.view.player.duration or app.view.player.error)
        finally:
            app._on_close()


if __name__ == '__main__':
    unittest.main()
