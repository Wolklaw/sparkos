"""The window, under a display (Xvfb in CI): the clip list, play, rename, trim, copy, delete to
the trash, the settings, and the save button against a real service on a test pattern. HOME and
the XDG folders are temporary, the dialogs are answered by the test, and opening a file is
recorded, not run."""

import os
import shutil
import time
import unittest

import testenv
from sparkclips import clipfile, core, games, library, pipeline
from sparkclips.text import t

HAVE_GST = clipfile.init() is None and pipeline.pick_encoder('h264') is not None \
    and not pipeline.missing_elements()
STATUS = {'ok': True, 'state': 'recording', 'game': 'Test Game', 'source': 'wine', 'held': 12.0,
          'seconds': 30, 'keep': True, 'only_in_game': True, 'bytes': 1_000_000,
          'encoder': 'H.264', 'audio': 'AAC', 'tracks': 1, 'problem': None, 'detail': ''}


def make_clip(name='Test Game 2026-11-24 20.00.00', game='Test Game', seconds=4):
    """A real, small MP4 made with GStreamer, so thumbnails, probe and trim have a file."""
    folder = os.path.join(core.clips_dir(), game)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + '.mp4')
    for encoder in ('x264enc key-int-max=30 tune=zerolatency', 'openh264enc gop-size=30'):
        os.system(f'gst-launch-1.0 -q -e videotestsrc num-buffers={seconds * 30} pattern=ball ! '
                  f'video/x-raw,width=320,height=180,framerate=30/1 ! videoconvert ! '
                  f'{encoder} ! h264parse ! mp4mux ! filesink location="{path}" >/dev/null 2>&1')
        if os.path.isfile(path) and os.path.getsize(path) > 1000:
            return path
    raise unittest.SkipTest("no x264enc or openh264enc to make a test clip with")


@unittest.skipUnless(testenv.have_display(), "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        testenv.reset()
        self.opened, self.errors, self.asked, self.answer = [], [], [], True
        self.new_name = None
        from sparkclips.app import App
        self.app = App(opener=lambda argv: self.opened.append(argv) or True, ask=self._ask,
                       tell=lambda *a, **k: None, warn=lambda *a, **k: None,
                       error=lambda *a, **k: self.errors.append(a),
                       name=lambda *a, **k: self.new_name, poll=False)
        self.addCleanup(self.app.close)
        self.app.root.geometry('1120x760')
        self.pump(0.5)

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

    def with_clip(self, **kw):
        path = make_clip(**kw)
        self.app.refresh_library(force=True)
        self.pump(0.2)
        self.app.select(path)
        return path

    def test_an_empty_library_says_so_and_the_tools_are_off(self):
        self.assertEqual(self.app.clips, [])
        self.assertTrue(self.app.empty.winfo_ismapped())
        self.assertFalse(self.app.tools['play'].enabled)

    def test_service_off_disables_saving_and_offers_to_start_it(self):
        self.app.apply_status(None)
        self.pump(0.3)
        self.assertFalse(self.app.save_button.enabled)
        self.assertTrue(self.app.service_button.winfo_ismapped())
        self.assertIn('SERVICE', self.app.state_label.cget('text').upper())

    def test_states_show_what_to_do(self):
        app = self.app
        app.apply_status(dict(STATUS))
        self.pump(0.2)
        self.assertTrue(app.save_button.enabled)
        self.assertFalse(app.service_button.winfo_ismapped())
        self.assertFalse(app.setup_button.winfo_ismapped())
        app.apply_status(dict(STATUS, state='needs_setup'))
        self.pump(0.2)
        self.assertFalse(app.save_button.enabled)
        self.assertTrue(app.setup_button.winfo_ismapped())
        app.apply_status(dict(STATUS, state='error', problem='no_encoder'))
        self.pump(0.2)
        self.assertIn(t('problem.no_encoder'), app.problem_label.cget('text'))
        app.apply_status(dict(STATUS, state='waiting', game=None))
        self.pump(0.2)
        self.assertFalse(app.save_button.enabled)

    def test_the_list_shows_clips_with_thumbnails_and_lengths(self):
        path = self.with_clip()
        self.pump(40, until=lambda: path in self.app.images and path in self.app.infos)
        self.assertEqual([c.path for c in self.app.clips], [path])
        self.assertIn(path, self.app.images)
        self.assertAlmostEqual(self.app.infos[path]['duration'], 4, delta=1)
        self.assertIn('0:0', self.app.cards[path].meta.cget('text'))
        self.assertTrue(self.app.tools['play'].enabled)

    def test_play_and_folder_open_through_the_opener(self):
        path = self.with_clip()
        self.app.play()
        self.assertEqual(self.opened[-1][-1], path)
        self.app.open_folder()
        self.assertEqual(self.opened[-1][-1], os.path.dirname(path))

    def test_rename_keeps_the_type_and_refuses_clashes_and_paths(self):
        path = self.with_clip()
        self.new_name = '../../Boss fight'
        self.app.rename()
        new = os.path.join(os.path.dirname(path), 'Boss fight.mp4')
        self.assertTrue(os.path.isfile(new))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.app.selected, new)
        other = make_clip(name='Other')
        self.app.refresh_library(force=True)
        self.app.select(other)
        self.new_name = 'Boss fight'
        self.app.rename()
        self.assertEqual(len(self.errors), 1)
        self.assertTrue(os.path.isfile(other))

    def test_delete_asks_then_uses_the_trash(self):
        path = self.with_clip()
        self.answer = False
        self.app.delete()
        self.assertTrue(os.path.isfile(path))
        self.answer = True
        self.app.delete()
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.errors, [])
        trashed = os.path.join(core.data_home(), 'Trash', 'files')
        self.assertEqual(os.listdir(trashed), [os.path.basename(path)])
        self.assertEqual(self.app.clips, [])

    def test_copy_puts_the_file_on_the_clipboard(self):
        path = self.with_clip()
        self.app.copy_file()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.app.root.clipboard_get(type='text/uri-list').strip(),
                         library.path_to_uri(path))
        self.assertIn(library.path_to_uri(path),
                      self.app.root.clipboard_get(type='x-special/gnome-copied-files'))

    def test_trim_makes_a_new_shorter_file_and_keeps_the_original(self):
        path = self.with_clip(seconds=6)
        clip = self.app.current()
        self.app.do_trim(clip, 1.0, 4.0)
        self.pump(20, until=lambda: any('trimmed' in c.name for c in self.app.clips))
        names = sorted(os.listdir(os.path.dirname(path)))
        self.assertEqual(len(names), 2, names)
        self.assertTrue(os.path.isfile(path))
        cut = [n for n in names if 'trimmed' in n][0]
        length = clipfile.probe(os.path.join(os.path.dirname(path), cut))['duration']
        self.assertGreaterEqual(length, 2.5)
        self.assertLessEqual(length, 4.2)
        self.assertEqual(self.errors, [])

    def test_the_trim_window_opens_with_the_whole_clip(self):
        self.with_clip(seconds=5)
        self.app.trim()
        self.pump(0.3)
        self.assertIsNotNone(self.app.trim_window)
        self.assertTrue(self.app.trim_window.winfo_exists())
        self.assertAlmostEqual(self.app.trim_end.get(), 5.0, delta=1.0)
        self.app.trim_window.destroy()

    def test_settings_are_saved_and_the_estimate_follows(self):
        app = self.app
        before = app.memory.cget('text')
        app.change(seconds=300)
        self.assertEqual(core.load_settings()['seconds'], 300)
        self.assertNotEqual(app.memory.cget('text'), before)
        app.change(mic=True, codec='hevc', fps='120', bitrate=20, size='1080', only_in_game=False,
                   sound=False)
        saved = core.load_settings()
        self.assertEqual((saved['mic'], saved['codec'], saved['fps'], saved['bitrate'],
                          saved['size'], saved['only_in_game'], saved['sound']),
                         (True, 'hevc', '120', 20, '1080', False, False))

    def test_a_buffer_too_big_for_the_memory_is_flagged(self):
        from sparkclips import buffer
        real = buffer.free_bytes
        buffer.free_bytes = lambda _folder: 1_000_000_000
        self.addCleanup(setattr, buffer, 'free_bytes', real)
        self.app.change(seconds=300, bitrate=60)
        self.assertEqual(self.app.memory.cget('fg'), '#f4c95d')

    def test_the_shortcut_is_shown(self):
        self.app.show_shortcut()
        self.assertIn('Meta+Alt+G', self.app.shortcut_label.cget('text'))


@unittest.skipUnless(testenv.have_display() and HAVE_GST, "needs a display, GStreamer and an encoder")
class WithTheService(unittest.TestCase):
    """The window and a real service (a test pattern) talking over the control socket."""

    def test_save_button_makes_a_clip_that_shows_up(self):
        testenv.reset()
        from sparkclips.app import App
        from sparkclips.daemon import Service
        core.save_settings(dict(core.DEFAULTS, seconds=15, fps='30'))
        service = Service(notifier=None, probe=lambda: games.Game('Test Game', 'wine', 1))
        self.addCleanup(service.shutdown)
        service.start_background()
        errors = []
        app = App(opener=lambda argv: True, ask=lambda *a, **k: True, tell=lambda *a, **k: None,
                  warn=lambda *a, **k: None, error=lambda *a, **k: errors.append(a),
                  name=lambda *a, **k: None)
        self.addCleanup(app.close)

        def pump(seconds, until=None):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                app.root.update()
                if until is not None and until():
                    return True
                time.sleep(0.02)
            return False
        self.assertTrue(pump(30, until=lambda: app.service is not None
                             and app.service['state'] == 'recording'))
        self.assertTrue(app.save_button.enabled)
        pump(6)
        app.save_clip()
        self.assertTrue(pump(30, until=lambda: len(app.clips) == 1))
        self.assertEqual(errors, [])
        self.assertEqual(app.selected, app.clips[0].path)
        self.assertTrue(os.path.isfile(app.clips[0].path))
        self.assertEqual(app.clips[0].game, 'Test Game')


if __name__ == '__main__':
    unittest.main()
