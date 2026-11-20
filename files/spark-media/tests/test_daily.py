"""Tests for one Spark Media per person, MPRIS (media keys, Plasma's media controls) and
HEIC/AVIF photos.

MPRIS tests need a session bus: CI runs them under `dbus-run-session` and calls Spark Media
from outside with `gdbus`, like Plasma does. Lines starting with "heif:" and "mpris:" go to the
CI summary."""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-media-{var.lower()}-'))
os.environ.setdefault('SPARK_MEDIA_AUDIO_SINK', 'fakesink')

from PIL import Image  # noqa: E402

import fixtures  # noqa: E402
from sparkmedia import core, edits, heif, instance, mpris, text  # noqa: E402
from sparkmedia import player as gst  # noqa: E402

text.set_language('en')
FIXTURES = os.path.join(HERE, 'fixtures')
UNIX = os.name != 'nt'
BUS = bool(os.environ.get('DBUS_SESSION_BUS_ADDRESS')) and bool(shutil.which('gdbus'))


class FakeTk:
    """Stands in for Tk's file handlers, so the socket and D-Bus parts run without a display:
    the test calls pump() where Tk's loop would call the handler."""

    def __init__(self):
        self.handlers = {}
        self.tk = self

    def createfilehandler(self, fd, _mask, callback):
        self.handlers[fd] = callback

    def deletefilehandler(self, fd):
        self.handlers.pop(fd, None)

    def pump(self, seconds=0.0):
        import select
        end = time.time() + seconds
        while True:
            fds = list(self.handlers)
            if fds:
                ready, _w, _x = select.select(fds, [], [], 0.05)
                for fd in ready:
                    if fd in self.handlers:
                        self.handlers[fd](fd, 0)
            if time.time() >= end:
                return


# ─── One Spark Media ──────────────────────────────────────────

@unittest.skipUnless(UNIX, "Unix sockets and Tk file handlers: Linux only")
class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.runtime = tempfile.mkdtemp(prefix='spark-media-run-')
        self.saved = os.environ.get('XDG_RUNTIME_DIR')
        os.environ['XDG_RUNTIME_DIR'] = self.runtime
        os.environ.pop('SPARK_MEDIA_NEW_INSTANCE', None)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop('XDG_RUNTIME_DIR', None)
        else:
            os.environ['XDG_RUNTIME_DIR'] = self.saved
        shutil.rmtree(self.runtime, ignore_errors=True)

    def test_nobody_listening(self):
        self.assertFalse(instance.hand_off(['/tmp/a.jpg']))
        self.assertTrue(instance.socket_path().startswith(self.runtime))
        self.assertEqual(os.stat(os.path.dirname(instance.socket_path())).st_mode & 0o777, 0o700)

    def test_hand_off_and_stale_socket(self):
        path = instance.socket_path()
        dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)     # a crash leaves this
        dead.bind(path)
        dead.close()
        self.assertTrue(os.path.exists(path))
        self.assertFalse(instance.hand_off(['/x.jpg']))               # dead: not taken
        got = []
        root = FakeTk()
        listener = instance.Listener(root, lambda paths, kind: got.append((paths, kind)))
        self.assertTrue(listener.start())                             # the stale one is replaced
        # a second listener doesn't steal a live socket
        self.assertFalse(instance.Listener(FakeTk(), lambda *a: None).start())
        result = []
        sender = threading.Thread(target=lambda: result.append(
            instance.hand_off(['/music/é song.flac', '/b.flac'], 'music')))
        sender.start()
        deadline = time.time() + 5
        while sender.is_alive() and time.time() < deadline:
            root.pump(0.05)
        sender.join(1)
        self.assertEqual(result, [True])
        self.assertEqual(got, [(['/music/é song.flac', '/b.flac'], 'music')])
        listener.stop()
        self.assertFalse(os.path.exists(path))

    def test_junk_is_ignored(self):
        got = []
        root = FakeTk()
        listener = instance.Listener(root, lambda *a: got.append(a))
        self.assertTrue(listener.start())
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(instance.socket_path())
        client.sendall(b'not json\n')
        root.pump(0.3)
        client.close()
        self.assertEqual(got, [])
        listener.stop()


# ─── MPRIS ────────────────────────────────────────────────────

def gdbus(*args, timeout=10):
    out = subprocess.run(['gdbus', 'call', '--session', '--dest', mpris.BUS_NAME,
                          '--object-path', mpris.PATH] + list(args),
                         capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return out.stdout.strip()


def prop(name, iface=mpris.PLAYER_IFACE):
    return gdbus('--method', 'org.freedesktop.DBus.Properties.Get', iface, name)


@unittest.skipUnless(UNIX and BUS and mpris.available() is None,
                     "needs a session bus (dbus-run-session), gdbus and Gio")
class MprisTests(unittest.TestCase):
    """The D-Bus side on its own, with commands recorded instead of played."""

    def setUp(self):
        self.root = FakeTk()
        self.calls = []
        self.server = mpris.Mpris(self.root, lambda m, *a: self.calls.append((m,) + a),
                                  lambda: 12.5)
        self.assertTrue(self.server.start(), self.server.error)

    def tearDown(self):
        self.server.stop()

    def test_methods_properties_and_signals(self):
        print(f"mpris: owns {self.server.name} on the session bus")
        self.assertEqual(self.server.name, mpris.BUS_NAME)
        self.assertIn("'Spark Media'", prop('Identity', mpris.ROOT_IFACE))
        self.assertIn("'dev.wolklaw.SparkMedia'", prop('DesktopEntry', mpris.ROOT_IFACE))
        self.assertIn("'Stopped'", prop('PlaybackStatus'))
        monitor = subprocess.Popen(['gdbus', 'monitor', '--session', '--dest', mpris.BUS_NAME],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(0.5)
        self.server.update({'PlaybackStatus': 'Playing', 'CanGoNext': True, 'CanSeek': True,
                            'Metadata': {'mpris:trackid': '/dev/wolklaw/SparkMedia/track/3',
                                         'mpris:length': 200_000_000, 'xesam:title': 'Été',
                                         'xesam:artist': ['Signal'], 'xesam:album': 'Tones',
                                         'mpris:artUrl': 'file:///tmp/cover.jpg'}})
        self.server.seeked(42.0)
        self.assertIn("'Playing'", prop('PlaybackStatus'))
        meta = prop('Metadata')
        for piece in ("'xesam:title': <'Été'>", "'xesam:artist': <['Signal']>",
                      "'mpris:length': <int64 200000000>", "'mpris:artUrl': <'file:///tmp/cover.jpg'>",
                      "objectpath '/dev/wolklaw/SparkMedia/track/3'"):
            self.assertIn(piece, meta)
        self.assertIn('12500000', prop('Position'))
        for method, args in (('PlayPause', []), ('Next', []), ('Previous', []), ('Pause', []),
                             ('Play', []), ('Stop', []), ('Seek', ['5000000']),
                             ('SetPosition', ['/dev/wolklaw/SparkMedia/track/3', '30000000']),
                             ('SetPosition', ['/dev/wolklaw/SparkMedia/track/9', '1'])):
            gdbus('--method', f'{mpris.PLAYER_IFACE}.{method}', *args)
        gdbus('--method', 'org.freedesktop.DBus.Properties.Set', mpris.PLAYER_IFACE, 'Volume',
              '<0.25>')
        gdbus('--method', f'{mpris.ROOT_IFACE}.Raise')
        self.root.pump(0.5)
        self.assertEqual(self.calls, [('PlayPause',), ('Next',), ('Previous',), ('Pause',),
                                      ('Play',), ('Stop',), ('Seek', 5000000),
                                      ('SetPosition', '/dev/wolklaw/SparkMedia/track/3', 30000000),
                                      ('SetVolume', 0.25), ('Raise',)])     # the stale id ignored
        time.sleep(0.3)
        monitor.terminate()
        seen = monitor.communicate(timeout=5)[0]
        self.assertIn('PropertiesChanged', seen)
        self.assertIn("'PlaybackStatus': <'Playing'>", seen)
        self.assertIn('Seeked', seen)
        self.assertIn('42000000', seen)
        print("mpris: Play, Pause, PlayPause, Next, Previous, Stop, Seek, SetPosition, Volume, "
              "Raise, Metadata, PropertiesChanged and Seeked checked with gdbus")

    def test_second_player_gets_its_own_name(self):
        other = mpris.Mpris(FakeTk(), lambda *a: None, lambda: 0)
        try:
            self.assertTrue(other.start())
            self.assertEqual(other.name, f'{mpris.BUS_NAME}.instance{os.getpid()}')
        finally:
            other.stop()


# ─── HEIC and AVIF ────────────────────────────────────────────

def quarters_ok(test, image):
    """Red top left, green top right, blue bottom left, white bottom right."""
    w, h = image.size
    corners = [image.getpixel(p)[:3] for p in ((4, 4), (w - 5, 4), (4, h - 5), (w - 5, h - 5))]
    for got, want in zip(corners, ((220, 30, 40), (30, 200, 60), (40, 60, 220), (245, 245, 245))):
        test.assertTrue(all(abs(a - b) < 40 for a, b in zip(got, want)), (corners, image.size))


class HeifTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-media-heif-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_report(self):
        found = heif.decoders()
        print(f"heif: libheif {heif.version() or 'not found'}; HEIC (HEVC) decoder "
              f"{'yes' if found['heic'] else 'NO'}; AVIF (AV1) decoder "
              f"{'yes' if found['avif'] else 'NO'}")
        for name, kind in (('quarters.heic', 'heic'), ('quarters.avif', 'avif')):
            with open(os.path.join(FIXTURES, name), 'rb') as f:
                self.assertEqual(heif.brand(f.read(64)), kind)
        self.assertEqual(core.kind_of('IMG_0001.HEIC'), 'photo')
        self.assertEqual(core.kind_of('x.hif'), 'photo')

    def test_heic(self):
        path = os.path.join(FIXTURES, 'quarters.heic')
        if not heif.decoders()['heic']:
            with self.assertRaises(core.PhotoError) as caught:
                core.Photo(path)
            print(f"heif: HEIC can't be decoded here; the viewer says: {caught.exception}")
            self.assertTrue('libheif' in str(caught.exception))
            return
        for name in ('quarters.heic', 'turned.heic'):
            photo = core.Photo(os.path.join(FIXTURES, name))
            self.assertEqual(photo.size, (96, 64), name)       # turned.heic: libheif turns it
            quarters_ok(self, photo.image)
            self.assertEqual(photo.format, 'HEIC')
            self.assertEqual(photo.taken, '2025-06-21 14:05')
            self.assertEqual(photo.camera, 'Spark Phone')
        thumb = core.photo_thumbnail(path)
        self.assertEqual(thumb.size, (96, 64))
        # an edit is a JPEG copy with the date and camera; the HEIC itself is never rewritten
        copy = os.path.join(self.dir, 'IMG_1.heic')
        shutil.copy(path, copy)
        photo = core.Photo(copy)
        self.assertFalse(edits.can_replace(photo.format, copy))
        e = edits.Edits()
        e.rotate(photo.size)
        saved = edits.save(edits.apply(photo.image, e), copy, photo.format, photo.exif)
        self.assertEqual(os.path.basename(saved), 'IMG_1 (edited).jpg')
        with Image.open(saved) as out:
            self.assertEqual(out.size, (64, 96))
            self.assertEqual(out.getexif().get_ifd(0x8769).get(0x9003), '2025:06:21 14:05:00')
            self.assertEqual(out.getexif().get(0x0112), 1)
        print("heif: HEIC opens upright, with its date and camera, and saves edits as JPEG")

    def test_avif(self):
        made = []
        if shutil.which('heif-enc'):
            png = os.path.join(self.dir, 'q.png')
            from make_heif_fixtures import quarters
            quarters().save(png)
            out = os.path.join(self.dir, 'made.avif')
            result = subprocess.run(['heif-enc', '--avif', '-q', '90', '-o', out, png],
                                    capture_output=True, text=True)
            if result.returncode == 0 and os.path.isfile(out):
                made.append(out)
                print("heif: made an AVIF here with heif-enc")
        found = heif.decoders()['avif']
        for path in [os.path.join(FIXTURES, 'quarters.avif')] + made:
            try:
                photo = core.Photo(path)
            except core.PhotoError as exc:
                self.assertFalse(found, f"libheif has AV1 but {path} failed: {exc}")
                print(f"heif: AVIF can't be decoded here: {exc}")
                continue
            self.assertEqual(photo.size, (96, 64))
            quarters_ok(self, photo.image)
        print(f"heif: AVIF fixtures checked ({1 + len(made)} file(s); libheif AV1 decoder: "
              f"{'yes' if found else 'no'})")

    def test_damaged(self):
        path = os.path.join(self.dir, 'bad.heic')
        with open(path, 'wb') as f:
            f.write(b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic' + b'\x00' * 50)
        with self.assertRaises(core.PhotoError):
            core.Photo(path)
        self.assertIsNone(core.photo_thumbnail(path))


# ─── The whole window ─────────────────────────────────────────

def have_display() -> bool:
    return UNIX and bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class WindowTests(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix='spark-media-daily-'))
        self.saved = {k: os.environ.get(k) for k in ('HOME', 'XDG_RUNTIME_DIR',
                                                     'SPARK_MEDIA_NO_MPRIS')}
        os.environ['HOME'] = os.path.join(self.dir, 'home')
        os.makedirs(os.path.join(os.environ['HOME'], 'Music'))
        os.environ['XDG_RUNTIME_DIR'] = os.path.join(self.dir, 'run')
        os.makedirs(os.environ['XDG_RUNTIME_DIR'], mode=0o700)
        os.environ.pop('SPARK_MEDIA_NEW_INSTANCE', None)
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app._on_close()
            except Exception:      # noqa: BLE001
                pass
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.dir, ignore_errors=True)

    def pump(self, seconds=0.4, until=None):
        end = time.time() + seconds
        while time.time() < end:
            self.app.root.update()
            if until is not None and until():
                return True
            time.sleep(0.02)
        return until() if until else True

    def second_start(self, *args):
        """`spark-media ARGS` as Dolphin would start it, while this window keeps running."""
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'spark_media.py')] + list(args),
                                env=dict(os.environ), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        self.assertTrue(self.pump(20, until=lambda: proc.poll() is not None), "it didn't exit")
        return proc.returncode, proc.stdout.read()

    def songs(self, n=3):
        made = []
        for i in range(n):
            path = os.path.join(self.dir, 'home', 'Music', f'{i + 1:02d} Tone {i + 1}.flac')
            if not gst.available() or not fixtures.encode(gst, path, 4.0):
                raise unittest.SkipTest("needs GStreamer with a FLAC encoder")
            fixtures.flac_tags(path, {'TITLE': f'Tone {i + 1}', 'ARTIST': 'Signal',
                                      'ALBUM': 'Tones', 'TRACKNUMBER': str(i + 1)},
                               picture=fixtures.cover_jpeg('#22d8ff') if i == 0 else None)
            made.append(path)
        return made

    def test_second_start_hands_over(self):
        from sparkmedia.app import App
        from sparkmedia.playview import MusicPlayerView
        from sparkmedia.viewer import PhotoView
        songs = self.songs()
        photo = os.path.join(self.dir, 'pic.jpg')
        Image.new('RGB', (300, 200), 'red').save(photo)
        os.environ['SPARK_MEDIA_NO_MPRIS'] = '1'
        self.app = App([songs[0]])
        self.pump(1.0)
        self.assertIsInstance(self.app.view, MusicPlayerView)
        self.assertEqual(self.app.music.current, songs[0])
        t0 = time.time()
        code, output = self.second_start(songs[2])
        print(f"mpris: a second start handed its song over and exited in {time.time() - t0:.2f} s")
        self.assertEqual(code, 0, output)
        self.pump(0.5)
        self.assertEqual(self.app.music.current, songs[2])            # plays now
        self.assertEqual(self.app.music.queue.items, [songs[0], songs[2]])
        self.assertTrue(self.app.music.playing)
        code, output = self.second_start(photo)
        self.assertEqual(code, 0, output)
        self.pump(0.5)
        self.assertIsInstance(self.app.view, PhotoView)               # same window
        self.assertEqual(self.app.view.files[self.app.view.index], photo)
        self.assertEqual(self.app.music.current, songs[2])            # the music went on
        # after this window closes, the next start opens its own
        self.app._on_close()
        self.app = None
        self.assertFalse(instance.hand_off([photo]))

    @unittest.skipUnless(BUS and mpris.available() is None, "needs a session bus and gdbus")
    def test_media_keys_drive_the_music(self):
        from sparkmedia.app import App
        songs = self.songs()
        self.app = App([songs[0]])
        self.pump(1.0, until=lambda: self.app.mpris is not None)
        self.assertIsNotNone(self.app.mpris, "MPRIS didn't start")

        def call(method, *args):
            box = []
            worker = threading.Thread(target=lambda: box.append(
                gdbus('--method', f'{mpris.PLAYER_IFACE}.{method}', *args)))
            worker.start()
            self.pump(5, until=lambda: not worker.is_alive())
            self.pump(0.4)

        def get(name):
            box = []
            worker = threading.Thread(target=lambda: box.append(prop(name)))
            worker.start()
            self.pump(5, until=lambda: not worker.is_alive())
            return box[0]

        self.pump(1.0)
        self.assertIn("'Playing'", get('PlaybackStatus'))
        meta = get('Metadata')
        self.assertIn("'xesam:title': <'Tone 1'>", meta)
        self.assertIn("'xesam:artist': <['Signal']>", meta)
        self.assertIn("'mpris:artUrl': <'file://", meta)
        self.assertIn("'mpris:length': <int64 4", meta)               # about 4 s
        call('PlayPause')
        self.assertFalse(self.app.music.playing)
        self.assertIn("'Paused'", get('PlaybackStatus'))
        call('Play')
        self.assertTrue(self.app.music.playing)
        call('Next')
        self.assertEqual(self.app.music.current, songs[1])
        self.assertIn("'Tone 2'", get('Metadata'))
        call('SetPosition', '/dev/wolklaw/SparkMedia/track/1', '2000000')
        self.pump(0.5)
        self.assertGreater(self.app.music.player.position() or 0, 1.5)
        call('Previous')                       # past 3 s? no: 2 s in, so the song before
        self.assertEqual(self.app.music.current, songs[0])
        call('Stop')
        self.assertIn("'Stopped'", get('PlaybackStatus'))
        call('Play')
        self.assertTrue(self.app.music.playing)
        print("mpris: media keys play, pause, skip, seek and stop the music in the window")
