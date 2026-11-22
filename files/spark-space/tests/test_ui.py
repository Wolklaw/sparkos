"""The window, under a display (Xvfb in CI): scan a temporary folder, the treemap and lists,
drill in and back, the largest files and types, and moving a temporary file to a temporary
trash with the confirm answered by the test. Nothing outside the temporary folders is written;
opening and "show in folder" are recorded, not run."""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-space-{var.lower()}-'))
os.environ['SPARK_SPACE_REDUCED_MOTION'] = '1'


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def write(path: str, size: int) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'\1' * size)
    return path


@unittest.skipUnless(have_display(), "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='spark-space-ui-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = os.path.join(self.tmp, 'data')        # the trash goes here
        self.old_data = os.environ.get('XDG_DATA_HOME')
        os.environ['XDG_DATA_HOME'] = self.data
        self.addCleanup(self._restore)
        self.tree = os.path.join(self.tmp, 'scanme')
        write(os.path.join(self.tree, 'videos', 'big film.mkv'), 3_000_000)
        write(os.path.join(self.tree, 'videos', 'clip.mp4'), 500_000)
        write(os.path.join(self.tree, 'models', 'llm.gguf'), 2_000_000)
        write(os.path.join(self.tree, 'docs', 'notes.txt'), 4000)
        for i in range(30):
            write(os.path.join(self.tree, 'many', f'f{i}.bin'), 1000 * (i + 1))
        self.opened = []
        self.answers = []
        from sparkspace.app import App
        self.warnings = []
        self.app = App(opener=lambda argv: self.opened.append(argv) or True,
                       ask=self._ask, tell=lambda *a, **k: None,
                       warn=lambda *a, **k: self.warnings.append(a),
                       error=lambda *a, **k: self.fail(f"error dialog: {a}"))
        self.addCleanup(self.app.close)
        self.app.root.geometry('1180x760')
        self.pump()

    def _restore(self):
        if self.old_data is None:
            os.environ.pop('XDG_DATA_HOME', None)
        else:
            os.environ['XDG_DATA_HOME'] = self.old_data

    def _ask(self, title, message, **kw):
        self.answers.append((title, message))
        return self.answer

    def pump(self, seconds: float = 0.3, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.root.update()
            if until is not None and until():
                return
            time.sleep(0.01)

    def scan(self):
        app = self.app
        app.scan(self.tree)
        self.pump(10, until=lambda: app.screen is app.results)
        self.assertIs(app.screen, app.results)
        self.pump(0.3)
        return app.results

    def node_named(self, r, name):
        for iid, node in r.rows['folder'].items():
            if node.name == name:
                return iid, node
        self.fail(f"{name} not in the list")

    def test_start_screen_lists_drives(self):
        # a container may have no disks worth a card; whatever is there gets measured
        hs = self.app.home_screen
        from sparkspace.text import t
        self.pump(5, until=lambda: all(c['numbers'].cget('text') != t('drive.measuring')
                                       for c in hs.cards.values()))
        for card in hs.cards.values():
            self.assertNotEqual(card['numbers'].cget('text'), t('drive.measuring'))
        self.assertIs(self.app.screen, hs)

    def test_scan_view_drill_and_back(self):
        r = self.scan()
        self.assertEqual(r.current.path(), self.tree)
        names = [n.name for n in r.rows['folder'].values()]
        self.assertEqual(names[0], 'videos')                      # biggest first
        self.assertGreater(len(r.map_items), 4)                    # the treemap drew
        self.assertFalse(r.up_button.enabled)
        iid, videos = self.node_named(r, 'videos')
        r.folder_tree.selection_set(iid)
        self.pump(0.1)
        self.assertIs(r.selected, videos)
        r._row_double('folder')
        self.pump(0.2)
        self.assertIs(r.current, videos)
        crumbs = [w.cget('text') for w in r.crumbs.winfo_children()]
        self.assertIn('videos', crumbs)
        self.assertTrue(r.up_button.enabled)
        r.go_up()
        self.pump(0.2)
        self.assertEqual(r.current.path(), self.tree)
        self.assertIs(r.selected, videos)                          # came back with it selected
        # double-click on a block in the treemap
        tag = next(t for t, n in r.map_items.items() if n is videos)
        x0, y0, x1, y1 = r.canvas.coords(r.canvas.find_withtag(tag)[0])
        r.canvas.event_generate('<Motion>', x=int(x0 + 5), y=int(y0 + 5))
        self.pump(0.1)
        self.assertEqual(r.hover_tag, tag)

    def test_largest_and_types(self):
        r = self.scan()
        r.set_tab('largest')
        self.pump(5, until=lambda: r.summary is not None)
        first = r.largest_tree.get_children()[0]
        self.assertEqual(r.largest_tree.item(first, 'text'), 'big film.mkv')
        r.set_tab('types')
        self.pump(0.2)
        self.assertIn('video', r.types_tree.get_children())
        r.types_tree.selection_set('models')
        self.pump(5, until=lambda: r.summary is not None and r.summary.kind == 'models')
        self.assertEqual(r.tab, 'largest')
        rows = [r.largest_tree.item(i, 'text') for i in r.largest_tree.get_children()]
        self.assertEqual(rows, ['llm.gguf'])

    def test_open_and_show_are_handed_off(self):
        r = self.scan()
        _iid, videos = self.node_named(r, 'videos')
        r.select(videos)
        r.open_selected()
        r.show_selected()
        self.assertEqual(self.opened[0], ['xdg-open', videos.path()])
        if shutil.which('spark-files'):
            self.assertEqual(self.opened[1][1:], ['--select', videos.path()])
        else:                                   # the desktop's file manager, on the parent
            self.assertEqual(self.opened[1], ['xdg-open', self.tree])

    def test_move_to_trash_with_confirm(self):
        r = self.scan()
        _iid, videos = self.node_named(r, 'videos')
        r.go(videos)
        film_path = os.path.join(self.tree, 'videos', 'big film.mkv')
        film = next(n for n in r.rows['folder'].values() if n.name == 'big film.mkv')
        r.select(film)
        self.assertTrue(r.b_trash.enabled)
        before = r.root_node.size
        self.answer = False                                       # "no" keeps it
        r.trash_selected()
        self.assertTrue(os.path.exists(film_path))
        self.answer = True
        r.trash_selected()
        self.pump(0.2)
        self.assertEqual(len(self.answers), 2)
        self.assertFalse(os.path.exists(film_path))
        self.assertTrue(os.path.exists(os.path.join(self.data, 'Trash', 'files',
                                                    'big film.mkv')))
        self.assertEqual(r.root_node.size, before - film.size)
        self.assertNotIn('big film.mkv', [n.name for n in r.rows['folder'].values()])

    def test_never_drive_is_look_only(self):
        from sparkspace import safety
        saved = safety.NEVER_DRIVE_PATHS
        safety.NEVER_DRIVE_PATHS = saved + (os.path.join(self.tree, 'models'),)
        self.addCleanup(setattr, safety, 'NEVER_DRIVE_PATHS', saved)
        r = self.scan()
        _iid, models = self.node_named(r, 'models')
        r.select(models)
        self.assertFalse(r.b_trash.enabled)
        self.answer = True
        r.trash_selected()                                        # the key still refuses
        self.pump(0.1)
        self.assertEqual(self.answers, [])                        # never even asked
        self.assertEqual(len(self.warnings), 1)
        self.assertTrue(os.path.exists(os.path.join(self.tree, 'models', 'llm.gguf')))

    def test_cancel_shows_partial(self):
        app = self.app
        app.scan(self.tree)
        app.cancel_scan()
        self.pump(10, until=lambda: app.screen is app.results)
        self.assertIs(app.screen, app.results)


if __name__ == '__main__':
    unittest.main()
