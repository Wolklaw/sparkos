"""The portal backend: what an app asks for (filters, folders, names), the answers, the D-Bus
side (a session bus, no display: dbus-run-session) and the chooser window (a display).

    dbus-run-session -- python -m unittest discover -s files/spark-files/tests -p 'test_portal*'
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-files-{var.lower()}-'))
os.environ['SPARK_FILES_REDUCED_MOTION'] = '1'

from sparkfiles import portal  # noqa: E402
from sparkfiles.portal import (CANCELLED, ENDED, OK, AppChooserAnswer, Ask, Filter,  # noqa: E402
                               app_results, file_results, file_uri, path_from_bytes,
                               save_targets, uri_path)

IMAGES = ('Images', [(0, '*.png'), (0, '*.JPG'), (1, 'image/webp')])
TEXT = ('Text', [(1, 'text/*')])


def have_bus() -> bool:
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS') or portal.Gio is None:
        return False
    try:
        portal.Gio.bus_get_sync(portal.Gio.BusType.SESSION, None)
        return True
    except Exception:     # noqa: BLE001
        return False


def have_display() -> bool:
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:     # noqa: BLE001
        return False


BUS = have_bus()
DISPLAY = have_display()


class Filters(unittest.TestCase):
    def test_globs_ignore_case_and_mime_wildcards(self):
        f = Filter(*IMAGES)
        self.assertTrue(f.matches('photo.PNG'))
        self.assertTrue(f.matches('photo.jpg'))
        self.assertFalse(f.matches('notes.txt', 'text/plain'))
        self.assertTrue(f.matches('x.webp', 'image/webp'))
        self.assertTrue(f.uses_mime)
        t = Filter(*TEXT)
        self.assertTrue(t.matches('readme', 'text/plain'))
        self.assertFalse(t.matches('readme', 'application/pdf'))
        self.assertFalse(t.matches('readme'))            # no type known: no match

    def test_raw_round_trip(self):
        self.assertEqual(Filter(*IMAGES).raw(), IMAGES)


class Asking(unittest.TestCase):
    def test_open_with_filters(self):
        a = Ask('OpenFile', 'Pick', {'filters': [IMAGES, TEXT], 'multiple': True,
                                     'accept_label': '_Import'})
        self.assertEqual(a.current_filter, Filter(*IMAGES))
        self.assertTrue(a.multiple)
        self.assertFalse(a.directory)
        self.assertFalse(a.saving)
        self.assertTrue(a.shows('sub', True))            # folders always
        self.assertTrue(a.shows('a.png', False))
        self.assertFalse(a.shows('a.txt', False, 'text/plain'))
        self.assertTrue(a.shows('a.txt', False, 'text/plain', Filter(*TEXT)))

    def test_current_filter_not_in_the_list_is_added_first(self):
        a = Ask('OpenFile', '', {'filters': [TEXT], 'current_filter': IMAGES})
        self.assertEqual([f.name for f in a.filters], ['Images', 'Text'])
        self.assertEqual(a.current_filter.name, 'Images')

    def test_directory_shows_no_files(self):
        a = Ask('OpenFile', '', {'directory': True})
        self.assertTrue(a.directory)
        self.assertFalse(a.shows('a.png', False))
        self.assertTrue(a.shows('sub', True))

    def test_save_takes_name_and_folder_from_bytes(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        a = Ask('SaveFile', '', {'current_file': os.fsencode(os.path.join(tmp, 'é.odt')) + b'\0'})
        self.assertEqual(a.current_name, 'é.odt')
        self.assertEqual(a.start_folder('/fallback'), tmp)
        b = Ask('SaveFile', '', {'current_name': 'new.txt',
                                 'current_folder': os.fsencode(tmp) + b'\0'})
        self.assertEqual(b.current_name, 'new.txt')
        self.assertEqual(b.start_folder('/fallback'), tmp)
        self.assertEqual(Ask('SaveFile', '', {'current_folder': b'/nope\0'}
                             ).start_folder('/fallback'), '/fallback')

    def test_save_files_picks_a_folder(self):
        a = Ask('SaveFiles', '', {'files': [b'a.txt\0', b'/x/b.txt\0']})
        self.assertTrue(a.directory)
        self.assertEqual(a.files, ['a.txt', 'b.txt'])
        self.assertEqual(save_targets('/home/me', a.files), ['/home/me/a.txt', '/home/me/b.txt'])

    def test_choices(self):
        a = Ask('OpenFile', '', {'choices': [('enc', 'Encoding', [('utf8', 'UTF-8'),
                                                                   ('l1', 'Latin-1')], 'l1'),
                                             ('ro', 'Read only', [], 'true'),
                                             ('bad', 'Bad', [('x', 'X')], 'missing')]})
        enc, ro, bad = a.choices
        self.assertEqual((enc.value, enc.is_check), ('l1', False))
        self.assertEqual((ro.value, ro.is_check), ('true', True))
        self.assertEqual(bad.value, 'x')

    def test_paths(self):
        self.assertEqual(path_from_bytes(b'/a b\0junk'), '/a b')
        self.assertEqual(path_from_bytes(None), '')
        uri = file_uri('/tmp/a b/ç#.txt')
        self.assertEqual(uri, 'file:///tmp/a%20b/%C3%A7%23.txt')
        self.assertEqual(uri_path(uri), '/tmp/a b/ç#.txt')


class Answers(unittest.TestCase):
    def test_open(self):
        a = Ask('OpenFile', '', {'filters': [IMAGES, TEXT],
                                 'choices': [('ro', 'Read only', [], 'false')]})
        response, results = file_results(a, ['/tmp/x.png'], Filter(*TEXT))
        self.assertEqual(response, OK)
        self.assertEqual(results['uris'], ('as', ['file:///tmp/x.png']))
        self.assertEqual(results['current_filter'], ('(sa(us))', TEXT))
        self.assertEqual(results['choices'], ('a(ss)', [('ro', 'false')]))
        self.assertEqual(results['writable'], ('b', True))

    def test_save_has_no_writable_and_no_filter_without_filters(self):
        response, results = file_results(Ask('SaveFile', '', {}), ['/tmp/x'])
        self.assertEqual(response, OK)
        self.assertEqual(set(results), {'uris'})

    def test_nothing_picked_is_a_cancel(self):
        self.assertEqual(file_results(Ask('OpenFile', '', {}), []), (CANCELLED, {}))

    def test_app(self):
        self.assertEqual(app_results('org.kde.okular.desktop'),
                         (OK, {'choice': ('s', 'org.kde.okular')}))
        self.assertEqual(app_results(None), (CANCELLED, {}))
        ans = AppChooserAnswer(['a', 'b', 'c'], 'b.desktop')
        self.assertEqual(ans.first_index(['a.desktop', 'b.desktop']), 1)
        self.assertEqual(AppChooserAnswer(['a']).first_index(['a.desktop']), 0)

    @unittest.skipIf(portal.GLib is None, "needs PyGObject")
    def test_variant(self):
        v = portal.to_variant(*file_results(Ask('OpenFile', '', {}), ['/tmp/x']))
        self.assertEqual(v.get_type_string(), '(ua{sv})')
        self.assertEqual(v.unpack()[1]['uris'], ['file:///tmp/x'])


class FakeBridge:
    """gloop.Bridge's two hops, with a GLib loop in a thread and 'Tk' in another."""

    def __init__(self):
        from gi.repository import GLib
        self.context = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(self.context, False)
        self._exported = []
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.context.push_thread_default()
        self.ready.set()
        self.loop.run()

    def post(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def in_glib(self, fn):
        def once():
            fn()
            return False
        self.context.invoke_full(0, once)


@unittest.skipUnless(BUS, "needs a session bus (dbus-run-session)")
class OnTheBus(unittest.TestCase):
    """The real D-Bus calls xdg-desktop-portal makes: OpenFile answered, and Close on the
    request object ending a dialog that's still open."""

    def setUp(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bridge = FakeBridge()
        self.bridge.thread.start()
        self.bridge.ready.wait(3)
        self.asked = []
        self.closed = threading.Event()
        self.mode = 'answer'

        def on_file(ask, parent, reply):
            self.asked.append((ask, parent))
            if self.mode == 'answer':
                reply(*file_results(ask, ['/tmp/picked file.txt']))
                return None
            return self.closed.set

        def on_app(handle, choices, options, parent, reply):
            reply(*app_results(choices[-1]))

        self.service = portal.Service(self.bridge, on_file, on_app)
        ids = []
        self.bridge.in_glib(lambda: ids.append(self.service.start()))
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        deadline = time.monotonic() + 5
        while not (self.service.owns and len(self.bridge._exported) == 2) and \
                time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.service.owns)
        self.assertEqual(len(self.bridge._exported), 2)
        self.addCleanup(self._stop, ids)

    def _stop(self, ids):
        # Every test shares one session bus connection: wait until the object is gone, or the
        # next test's register_object finds the path taken and this cleanup then removes it.
        done = threading.Event()

        def stop():
            for i in ids:
                self.Gio.bus_unown_name(i)
            for c, r in self.bridge._exported:
                c.unregister_object(r)
            self.bridge.loop.quit()
            done.set()
        self.bridge.in_glib(stop)
        done.wait(5)
        self.bridge.thread.join(5)

    def call(self, iface, method, args, sig, timeout=5000):
        return self.bus.call_sync(portal.PORTAL_NAME, portal.PORTAL_PATH, iface, method,
                                  self.GLib.Variant(sig, args), None,
                                  self.Gio.DBusCallFlags.NONE, timeout, None).unpack()

    def test_open_file(self):
        opts = {'filters': self.GLib.Variant('a(sa(us))', [IMAGES]),
                'multiple': self.GLib.Variant('b', False)}
        response, results = self.call(portal.FC_IFACE, 'OpenFile',
                                      ('/org/freedesktop/portal/desktop/request/1_1/t1',
                                       'org.example.App', 'x11:1234', 'Pick one', opts),
                                      '(osssa{sv})')
        self.assertEqual(response, OK)
        self.assertEqual(results['uris'], ['file:///tmp/picked%20file.txt'])
        self.assertEqual(results['current_filter'], IMAGES)
        ask, parent = self.asked[0]
        self.assertEqual((ask.title, ask.app_id, parent), ('Pick one', 'org.example.App',
                                                           'x11:1234'))

    def test_version_property(self):
        v = self.bus.call_sync(portal.PORTAL_NAME, portal.PORTAL_PATH,
                               'org.freedesktop.DBus.Properties', 'Get',
                               self.GLib.Variant('(ss)', (portal.FC_IFACE, 'version')), None,
                               self.Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        self.assertEqual(v, 4)

    def test_close_ends_the_request(self):
        self.mode = 'wait'
        handle = '/org/freedesktop/portal/desktop/request/1_1/t2'
        got = []

        def ask():
            got.append(self.call(portal.FC_IFACE, 'SaveFile',
                                 (handle, 'org.example.App', '', 'Save', {}), '(osssa{sv})'))
        caller = threading.Thread(target=ask)
        caller.start()
        deadline = time.monotonic() + 5
        while not self.asked and time.monotonic() < deadline:
            time.sleep(0.05)
        self.bus.call_sync(portal.PORTAL_NAME, handle, portal.REQUEST_IFACE, 'Close', None,
                           None, self.Gio.DBusCallFlags.NONE, 3000, None)
        caller.join(5)
        self.assertEqual(got, [(ENDED, {})])
        self.assertTrue(self.closed.wait(3))

    def test_choose_application(self):
        response, results = self.call(portal.AC_IFACE, 'ChooseApplication',
                                      ('/org/freedesktop/portal/desktop/request/1_1/t3',
                                       'org.example.App', '', ['a', 'org.kde.kate'], {}),
                                      '(ossasa{sv})')
        self.assertEqual((response, results), (OK, {'choice': 'org.kde.kate'}))


@unittest.skipUnless(DISPLAY, "needs a display")
class ChooserWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['SPARK_FILES_NO_PORTAL'] = '1'
        from sparkfiles.app import App
        cls.app = App()
        cls.app.quit = lambda: None

    @classmethod
    def tearDownClass(cls):
        for w in list(cls.app.windows):
            w.destroy()
        cls.app.shutdown()

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-files-chooser-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        for n in ('a.png', 'b.txt', 'c.PNG'):
            open(os.path.join(self.dir, n), 'w').close()
        os.mkdir(os.path.join(self.dir, 'sub'))
        self.replies = []

    def open(self, method, options):
        options.setdefault('current_folder', os.fsencode(self.dir) + b'\0')
        a = Ask(method, '', options)
        close = self.app.portal_file(a, '', lambda *r: self.replies.append(r))
        w = self.app.windows[-1]
        self.app.root.update()
        return w, close

    def names(self, w):
        return [e.name for e in w.active.view.entries]

    def test_open_filters_and_picks(self):
        w, _close = self.open('OpenFile', {'filters': [IMAGES, TEXT]})
        self.assertIsNone(self.app.focus_window())          # a chooser isn't a file manager
        self.assertEqual(self.names(w), ['sub', 'a.png', 'c.PNG'])
        w.set_filter(Filter(*TEXT))
        self.assertEqual(self.names(w), ['sub', 'b.txt'])
        w.active.open_entries([e for e in w.active.view.entries if e.name == 'b.txt'])
        self.assertEqual(self.replies[0][0], OK)
        self.assertEqual(self.replies[0][1]['current_filter'], ('(sa(us))', TEXT))
        self.assertFalse(w.winfo_exists())

    def test_closing_cancels(self):
        w, close = self.open('OpenFile', {})
        close()
        self.assertEqual(self.replies, [(CANCELLED, {})])
        close()                                             # once only
        self.assertEqual(len(self.replies), 1)

    def test_save_typed_name(self):
        w, _close = self.open('SaveFile', {'current_name': 'new.txt'})
        self.assertEqual(w.name_entry.get(), 'new.txt')
        w.accept()
        self.assertEqual(self.replies[0][1]['uris'][1],
                         [file_uri(os.path.join(self.dir, 'new.txt'))])

    def test_directory(self):
        w, _close = self.open('OpenFile', {'directory': True})
        self.assertEqual(self.names(w), ['sub'])
        w.accept()
        self.assertEqual(self.replies[0][1]['uris'][1], [file_uri(self.dir)])


if __name__ == '__main__':
    unittest.main()
