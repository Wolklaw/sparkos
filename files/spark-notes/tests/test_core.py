"""Notes, clipboard history, settings, the CLI and the watcher's capture step. No display needed:
the clipboard is a fake wl-paste and wl-copy (tests/fakes) that keep their state in a folder, so
every case from "text" to "a password manager copied this" runs the real capture code."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sparknotes import capture, cli, core, text  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
# A stand-in for wl-paste and wl-copy. State lives in $FAKE_CLIP: <type> files plus a "types" list.
import os, sys
state = os.environ['FAKE_CLIP']
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
types_path = os.path.join(state, 'types')

def types():
    try:
        return [t for t in open(types_path).read().split('\n') if t]
    except OSError:
        return []

def opt(flag):
    return args[args.index(flag) + 1] if flag in args else None

if name == 'wl-copy':
    mime = opt('--type') or 'text/plain'
    open(os.path.join(state, 'data'), 'wb').write(sys.stdin.buffer.read())
    open(types_path, 'w').write(mime + '\n')
    open(os.path.join(state, 'copied'), 'a').write(mime + '\n')
elif '--list-types' in args:
    if not types():
        sys.exit(1)
    print('\n'.join(types()))
else:
    want = opt('--type')
    if not types() or (want and want not in types()):
        sys.exit(1)
    sys.stdout.buffer.write(open(os.path.join(state, 'data'), 'rb').read())
'''

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\xa5'
       b'\xd8\x87\xf0\x00\x00\x00\x00IEND\xaeB`\x82')


class Home(unittest.TestCase):
    """A temporary XDG home and a fake clipboard on PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.saved = dict(os.environ)
        for var, sub in (('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'),
                         ('XDG_DATA_HOME', 'data')):
            os.environ[var] = os.path.join(self.root, sub)
        self.clip = os.path.join(self.root, 'clip')
        bindir = os.path.join(self.root, 'bin')
        os.makedirs(self.clip)
        os.makedirs(bindir)
        for name in ('wl-paste', 'wl-copy'):
            path = os.path.join(bindir, name)
            with open(path, 'w') as f:
                f.write(FAKE.replace('#!/usr/bin/env python3', '#!' + sys.executable))
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        os.environ['FAKE_CLIP'] = self.clip
        os.environ['PATH'] = bindir + os.pathsep + os.environ['PATH']
        self.history = core.History()
        self.store = core.NoteStore()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def copy(self, data: bytes, *types: str):
        with open(os.path.join(self.clip, 'data'), 'wb') as f:
            f.write(data)
        with open(os.path.join(self.clip, 'types'), 'w') as f:
            f.write('\n'.join(types) + '\n')

    def empty(self):
        try:
            os.unlink(os.path.join(self.clip, 'types'))
        except FileNotFoundError:
            pass

    def texts(self):
        return [i.text for i in self.history.items()]


class NotesTest(Home):

    def test_write_read_title(self):
        nid = self.store.new_id()
        self.assertTrue(self.store.save(nid, "# Shopping\nmilk\neggs\n"))
        note = self.store.load(nid)
        self.assertEqual(note.title, 'Shopping')
        self.assertEqual(note.snippet(), 'milk')
        self.assertEqual(note.body, "# Shopping\nmilk\neggs\n")

    def test_note_is_a_plain_file(self):
        nid = self.store.new_id()
        self.store.save(nid, "hello")
        path = os.path.join(self.store.notes_dir, nid + '.md')
        with open(path, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'hello')
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_empty_note_is_not_kept(self):
        nid = self.store.new_id()
        self.store.save(nid, "x")
        self.store.save(nid, "  \n")
        self.assertEqual(self.store.list(), [])

    def test_search_ignores_case_and_accents(self):
        a, b = self.store.new_id(), self.store.new_id()
        self.store.save(a, "Café du matin")
        self.store.save(b, "something else")
        self.assertEqual([n.id for n in self.store.list('CAFE')], [a])
        self.assertEqual([n.id for n in self.store.list('matin cafe')], [a])
        self.assertEqual(self.store.list('zzz'), [])

    def test_pinned_first(self):
        a, b = self.store.new_id(), self.store.new_id()
        self.store.save(a, "older")
        os.utime(os.path.join(self.store.notes_dir, a + '.md'), (1, 1))
        self.store.save(b, "newer")
        self.assertEqual([n.id for n in self.store.list()], [b, a])
        self.store.set_pinned(a, True)
        self.assertEqual([n.id for n in self.store.list()], [a, b])
        self.assertTrue(self.store.load(a).pinned)
        self.store.set_pinned(a, False)
        self.assertEqual([n.id for n in self.store.list()], [b, a])

    def test_delete_goes_to_trash_and_comes_back(self):
        nid = self.store.new_id()
        self.store.save(nid, "keep me")
        self.assertTrue(self.store.delete(nid))
        self.assertEqual(self.store.list(), [])
        self.assertTrue(os.path.exists(os.path.join(self.store.trash_dir, nid + '.md')))
        self.assertTrue(self.store.restore(nid))
        self.assertEqual(self.store.load(nid).body, "keep me")

    def test_bad_id_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.save('../evil', 'x')
        self.assertIsNone(self.store.load('nothere'))

    def test_data_folder_is_private(self):
        self.assertEqual(stat.S_IMODE(os.stat(core.data_dir()).st_mode), 0o700)


class HistoryTest(Home):

    def test_newest_first_and_repeat_moves_up(self):
        for s in ('one', 'two', 'one'):
            self.history.add_text(s)
        self.assertEqual(self.texts(), ['one', 'two'])

    def test_empty_and_blank_copies_are_ignored(self):
        self.assertIsNone(self.history.add_text('   \n'))
        self.assertEqual(self.history.items(), [])

    def test_limit_trims_oldest_but_not_pinned(self):
        first = self.history.add_text('first', limit=5)
        self.history.set_pinned(first.id, True)
        for n in range(8):
            self.history.add_text(f'copy {n}', limit=5)
        texts = self.texts()
        self.assertEqual(texts[0], 'first')
        self.assertEqual(len(texts), 6)           # the pin, plus five
        self.assertNotIn('copy 0', texts)
        self.assertIn('copy 7', texts)

    def test_too_big_text_is_not_kept(self):
        self.assertIsNone(self.history.add_text('x' * (core.MAX_TEXT_BYTES + 1)))

    def test_images(self):
        item = self.history.add_image(PNG, 'image/png')
        self.assertEqual(item.kind, 'image')
        self.assertEqual(self.history.image_bytes(item), PNG)
        self.assertIsNone(self.history.add_image(b'x', 'image/tiff'))
        self.assertIsNone(self.history.add_image(b'', 'image/png'))

    def test_image_file_goes_with_the_item(self):
        item = self.history.add_image(PNG, 'image/png')
        path = self.history.image_path(item)
        self.assertTrue(os.path.exists(path))
        self.history.delete(item.id)
        self.assertFalse(os.path.exists(path))

    def test_images_are_capped(self):
        for n in range(core.MAX_IMAGES + 4):
            self.history.add_image(PNG + bytes([n]), 'image/png')
        self.assertEqual(len(self.history.items()), core.MAX_IMAGES)
        self.assertEqual(len(os.listdir(self.history.images)), core.MAX_IMAGES)

    def test_clear_keeps_pins(self):
        a = self.history.add_text('pinned')
        self.history.add_text('loose')
        self.history.set_pinned(a.id, True)
        self.assertEqual(self.history.clear(keep_pinned=True), 1)
        self.assertEqual(self.texts(), ['pinned'])
        self.assertEqual(self.history.clear(keep_pinned=False), 1)
        self.assertEqual(self.history.items(), [])

    def test_search(self):
        self.history.add_text('Dîner à Québec')
        self.history.add_text('other')
        self.history.add_image(PNG, 'image/png')
        self.assertEqual([i.text for i in self.history.search('quebec diner')], ['Dîner à Québec'])
        self.assertEqual(len(self.history.search('')), 3)

    def test_survives_a_damaged_file(self):
        self.history.add_text('x')
        with open(self.history.path, 'w') as f:
            f.write('{not json')
        self.assertEqual(self.history.items(), [])
        self.history.add_text('y')
        self.assertEqual(self.texts(), ['y'])

    def test_history_file_is_private(self):
        self.history.add_text('x')
        self.assertEqual(stat.S_IMODE(os.stat(self.history.path).st_mode), 0o600)


class SettingsTest(Home):

    def test_defaults_and_round_trip(self):
        self.assertEqual(core.load_settings(), core.DEFAULTS)
        s = core.load_settings()
        s['paused'] = True
        self.assertTrue(core.save_settings(s))
        self.assertTrue(core.load_settings()['paused'])

    def test_bad_values_are_cleaned(self):
        clean = core.clean_settings({'max_items': 10 ** 9, 'paused': 'yes', 'images': 0})
        self.assertEqual(clean['max_items'], core.MAX_ITEMS_RANGE[1])
        self.assertEqual(clean['paused'], core.DEFAULTS['paused'])
        self.assertEqual(clean['images'], core.DEFAULTS['images'])
        self.assertEqual(core.clean_settings('nonsense'), core.DEFAULTS)


class CaptureTest(Home):

    def test_text(self):
        self.copy('héllo wörld'.encode(), 'text/plain;charset=utf-8', 'text/plain')
        self.assertEqual(capture.capture(), 'text')
        self.assertEqual(self.texts(), ['héllo wörld'])

    def test_plain_text_only(self):
        self.copy(b'plain', 'text/plain')
        self.assertEqual(capture.capture(), 'text')
        self.assertEqual(self.texts(), ['plain'])

    def test_image(self):
        self.copy(PNG, 'image/png')
        self.assertEqual(capture.capture(), 'image')
        self.assertEqual(self.history.items()[0].kind, 'image')

    def test_images_can_be_turned_off(self):
        core.save_settings(dict(core.load_settings(), images=False))
        self.copy(PNG, 'image/png')
        self.assertEqual(capture.capture(), 'skipped')
        self.assertEqual(self.history.items(), [])

    def test_password_manager_copy_is_skipped(self):
        self.copy(b'hunter2', 'text/plain', core.PASSWORD_HINT)
        self.assertEqual(capture.capture(), 'password')
        self.assertEqual(self.history.items(), [])

    def test_paused_keeps_nothing(self):
        core.save_settings(dict(core.load_settings(), paused=True))
        self.copy(b'secret plans', 'text/plain')
        self.assertEqual(capture.capture(), 'paused')
        self.assertEqual(self.history.items(), [])

    def test_blank_copy_is_skipped(self):
        self.copy(b'  \n', 'text/plain')
        self.assertEqual(capture.capture(), 'skipped')

    def test_unknown_type_is_skipped(self):
        self.copy(b'<x/>', 'application/x-thing')
        self.assertEqual(capture.capture(), 'skipped')

    def test_empty_clipboard_restores_the_newest(self):
        self.history.add_text('older')
        self.history.add_text('newest')
        self.empty()
        self.assertEqual(capture.capture(), 'restored')
        out = subprocess.run(['wl-paste', '--no-newline'], capture_output=True)
        self.assertEqual(out.stdout, b'newest')

    def test_empty_clipboard_is_left_alone_when_keep_alive_is_off(self):
        core.save_settings(dict(core.load_settings(), keep_alive=False))
        self.history.add_text('newest')
        self.empty()
        self.assertEqual(capture.capture(), 'empty')

    def test_empty_clipboard_and_empty_history(self):
        self.empty()
        self.assertEqual(capture.capture(), 'empty')

    def test_copy_item_puts_text_and_image_back(self):
        t_item = self.history.add_text('again')
        self.assertTrue(capture.copy_item(t_item))
        out = subprocess.run(['wl-paste', '--no-newline'], capture_output=True)
        self.assertEqual(out.stdout, b'again')
        i_item = self.history.add_image(PNG, 'image/png')
        self.assertTrue(capture.copy_item(i_item))
        out = subprocess.run(['wl-paste', '--no-newline', '--type', 'image/png'],
                             capture_output=True)
        self.assertEqual(out.stdout, PNG)

    def test_capture_main_never_raises(self):
        self.copy(b'ok', 'text/plain')
        self.assertEqual(capture.capture_main(), 0)
        self.assertEqual(self.texts(), ['ok'])

    def test_watch_command_uses_wl_paste_watch(self):
        cmd = capture.watch_command()
        self.assertEqual(cmd[:2], ['wl-paste', '--watch'])
        self.assertTrue(cmd[-2].endswith('spark_notes.py'))
        self.assertEqual(cmd[-1], '--capture')


class CliTest(Home):

    def run_cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, 'spark_notes.py'), *args],
                              capture_output=True, text=True, env=os.environ, timeout=60)

    def test_capture_loads_only_capture_and_core(self):
        """wl-paste starts --capture on every copy: it must not import the window code."""
        code = ("import runpy, sys; sys.argv = ['spark_notes.py', '--capture'];"
                "sys.path.insert(0, %r);"
                "\ntry: runpy.run_path(%r, run_name='__main__')"
                "\nexcept SystemExit: pass"
                "\nprint(sorted(m for m in ('sparknotes.app', 'sparknotes.cli', 'argparse', 'gi', "
                "'tkinter') if m in sys.modules))" % (ROOT, os.path.join(ROOT, 'spark_notes.py')))
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                           env=os.environ, timeout=60)
        self.assertEqual(r.stdout.strip().splitlines()[-1], '[]', r.stderr)

    def test_version(self):
        r = self.run_cli('--version')
        self.assertEqual(r.returncode, 0)
        self.assertIn('Spark Notes', r.stdout)

    def test_list_empty_and_full(self):
        r = self.run_cli('--list')
        self.assertEqual(r.returncode, 1)
        self.history.add_text('find me')
        r = self.run_cli('--list', 'find')
        self.assertEqual(r.returncode, 0)
        self.assertIn('find me', r.stdout)

    def test_pause_and_resume(self):
        self.assertEqual(self.run_cli('--pause').returncode, 0)
        self.assertTrue(core.load_settings()['paused'])
        self.assertEqual(self.run_cli('--resume').returncode, 0)
        self.assertFalse(core.load_settings()['paused'])

    def test_self_test_passes_without_touching_real_files(self):
        r = self.run_cli('--self-test')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('self-test passed', r.stdout)
        self.assertEqual(self.history.items(), [])

    def test_capture_option_is_hidden_from_help(self):
        self.assertNotIn('--capture', cli.parser().format_help())


class TextTest(unittest.TestCase):

    def test_both_languages_cover_every_key(self):
        self.assertEqual(set(text.EN), set(text.FR))
        for table in (text.EN, text.FR):
            for key, value in table.items():
                self.assertTrue(value.strip(), key)

    def test_placeholders_match(self):
        import string
        for key in text.EN:
            names = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
            self.assertEqual(names(text.EN[key]), names(text.FR[key]), key)

    def test_french_is_picked(self):
        saved = dict(os.environ)
        try:
            for var in ('LC_ALL', 'LC_MESSAGES', 'LANGUAGE'):
                os.environ.pop(var, None)
            os.environ['LANG'] = 'fr_CA.UTF-8'
            self.assertEqual(text.t('clip.clear'), text.FR['clip.clear'])
            os.environ['LANG'] = 'en_US.UTF-8'
            self.assertEqual(text.t('clip.clear'), text.EN['clip.clear'])
        finally:
            os.environ.clear()
            os.environ.update(saved)


class HelpersTest(unittest.TestCase):

    def test_ago_and_size(self):
        self.assertEqual(core.ago(100, now=100, language='en'), 'now')
        self.assertEqual(core.ago(0, now=300, language='en'), '5 min')
        self.assertEqual(core.ago(0, now=7200, language='fr'), '2 h')
        self.assertTrue(core.human_size(2048, language='en').startswith('2'))

    def test_settings_file_is_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 's.json')
            self.assertTrue(core.save_settings(dict(core.DEFAULTS), path))
            with open(path) as f:
                self.assertEqual(json.load(f), core.DEFAULTS)


if __name__ == '__main__':
    unittest.main()
