"""The window, on libvirt's test driver (a fake hypervisor), in English and in French. Needs a
display (run under xvfb-run); skipped without one. Checks the pages work and that no label or
button is cut off in either language. SPARK_SHOT_DIR=/some/folder saves screenshots."""

import os
import sys
import tempfile
import time
import unittest
import warnings

os.environ['SPARK_BOXES_URI'] = 'test:///default'
os.environ.setdefault('GDK_DEBUG', 'no-portals')
warnings.filterwarnings('ignore', category=DeprecationWarning)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk, GLib, Gtk
    HAVE_GTK = Gtk.init_check()[0] if isinstance(Gtk.init_check(), tuple) else bool(Gtk.init_check())
except (ImportError, ValueError):
    HAVE_GTK = False

try:
    import libvirt  # noqa: F401
    HAVE_LIBVIRT = True
except ImportError:
    HAVE_LIBVIRT = False

from sparkboxes import core, isoinfo, text, xmlgen  # noqa: E402


_APP = None


def wait(condition, timeout=6.0) -> bool:
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if condition():
            return True
        time.sleep(0.01)
    return bool(condition())


def settle(ms=200):
    end = time.monotonic() + ms / 1000
    ctx = GLib.MainContext.default()
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.005)


def walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from walk(child)


def shot(window, name):
    folder = os.environ.get('SPARK_SHOT_DIR')
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    settle(300)
    gdk = window.get_window()
    pix = Gdk.pixbuf_get_from_window(gdk, 0, 0, gdk.get_width(), gdk.get_height())
    if pix:
        pix.savev(os.path.join(folder, name), 'png', [], [])


@unittest.skipUnless(HAVE_GTK and HAVE_LIBVIRT, 'needs a display and python3-libvirt')
class WindowTests(unittest.TestCase):
    lang = 'en'

    @classmethod
    def setUpClass(cls):
        from sparkboxes import style
        cls.style = style
        style.install()
        global _APP
        if _APP is None:
            _APP = Gtk.Application()
            _APP.register(None)
        cls.shared_app = _APP

    def setUp(self):
        os.environ['SPARK_LANG'] = self.lang
        self.tmp = tempfile.mkdtemp()
        os.environ['XDG_STATE_HOME'] = self.tmp
        os.environ['XDG_CACHE_HOME'] = self.tmp
        self.addCleanup(__import__('shutil').rmtree, self.tmp)
        from sparkboxes.window import BoxesWindow
        self.manager = core.Manager('test:///default', glib_events=True)
        self.app = self.shared_app
        self.consoles = []
        self.picked = []
        self.win = BoxesWindow(self.app, self.manager, self.style.Glitch(False),
                               self.consoles.append, iso_picker=lambda _w: self.picked.pop(0))
        self.win.resize(1100, 700)
        self.manager.import_iso = lambda path, progress=None: path    # the test driver can't upload
        self.names = []
        self.addCleanup(self.cleanup)
        self.assertTrue(wait(lambda: self.manager.conn is not None))
        settle()

    def cleanup(self):
        self.win.destroy()
        m = core.Manager('test:///default', glib_events=True)
        m.connect()
        for dom in m.conn.listAllDomains():
            if dom.name().startswith('ui-'):
                if dom.isActive():
                    dom.destroy()
                dom.undefine()
        m.close()

    def add(self, name, preset='linux'):
        self.manager.create_vm(xmlgen.VmSpec(name=name, preset=preset, cpus=2, memory_mb=2048,
                                             kvm=False), 10)
        self.win.refresh()
        self.assertTrue(wait(lambda: name in self.win.rows))

    def click(self, button):
        self.assertTrue(button.get_sensitive(), "the button is off")
        button.clicked()

    def page(self):
        return self.win.stack.get_visible_child_name()

    def test_empty_then_listed(self):
        self.assertTrue(wait(lambda: self.page() in ('empty', 'detail')))
        self.add('ui-one')
        self.win.list.select_row(self.win.rows['ui-one'])
        self.assertTrue(wait(lambda: self.win.d_name.get_text() == 'ui-one' and self.page() == 'detail'))

    def test_start_pause_and_stop(self):
        self.add('ui-power')
        self.win.list.select_row(self.win.rows['ui-power'])
        self.assertTrue(wait(lambda: self.win.selected == 'ui-power' and self.win.b_start.get_sensitive()))
        self.assertFalse(self.win.b_open.get_sensitive())
        self.click(self.win.b_start)
        self.assertTrue(wait(lambda: self.win.d_state.get_text() == text.t('state.running')))
        self.assertTrue(self.win.b_open.get_sensitive())
        self.assertFalse(self.win.s_apply.get_sensitive(), "settings need the machine off")
        self.click(self.win.b_pause)
        self.assertTrue(wait(lambda: self.win.d_state.get_text() == text.t('state.paused')))
        self.click(self.win.b_pause)
        self.assertTrue(wait(lambda: self.win.d_state.get_text() == text.t('state.running')))
        self.click(self.win.b_open)
        self.assertEqual(self.consoles, ['ui-power'])
        self.click(self.win.b_force)
        self.assertTrue(wait(lambda: self.win.d_state.get_text() == text.t('state.off')))

    def test_apply_settings(self):
        self.add('ui-set')
        self.win.list.select_row(self.win.rows['ui-set'])
        self.assertTrue(wait(lambda: self.win.loaded == 'ui-set'))
        self.win.s_cpus.set_value(3)
        self.win.s_mem.set_value(1536)
        self.click(self.win.s_apply)
        self.assertTrue(wait(lambda: self.win.status.get_text() == text.t('set.applied')))
        self.assertTrue(wait(lambda: next(v for v in self.win.vms if v.name == 'ui-set').cpus == 3))

    def test_snapshot_page(self):
        self.add('ui-snap')
        self.win.list.select_row(self.win.rows['ui-snap'])
        self.assertTrue(wait(lambda: self.win.loaded == 'ui-snap'))
        self.win.n_label.set_text('first')
        self.click(self.win.n_take)
        self.assertTrue(wait(lambda: any(getattr(r, 'snap_name', '').startswith('first')
                                         for r in self.win.n_list.get_children())))
        self.win.n_list.select_row([r for r in self.win.n_list.get_children()
                                    if getattr(r, 'snap_name', None)][0])
        self.assertTrue(self.win.n_forget.get_sensitive())
        self.click(self.win.n_forget)
        self.assertTrue(wait(lambda: not any(getattr(r, 'snap_name', None)
                                             for r in self.win.n_list.get_children())))

    def test_new_machine_page(self):
        self.win.show_new()
        self.assertEqual(self.page(), 'new')
        self.assertFalse(self.win.f_create.get_sensitive(), "no name yet")
        self.win.f_name.set_text('bad name!')
        self.assertFalse(self.win.f_create.get_sensitive())
        iso = os.path.join(self.tmp, 'Fedora-KDE-Live.iso')
        with open(iso, 'wb') as f:
            f.write(b'\0' * isoinfo.PVD_OFFSET + b'\x01CD001\x01\0')
            f.seek(isoinfo.LABEL_AT)
            f.write(b'Fedora-KDE-Live'.ljust(32))
        self.picked.append(iso)
        self.click(self.win.f_iso_pick)
        self.assertEqual(self.win.selected_preset(), 'linux')
        self.assertEqual(self.win.f_mem.get_value_as_int(), min(4096, self.win.f_mem.get_value_as_int()))
        self.win.f_name.set_text('ui-made')
        self.assertTrue(self.win.f_create.get_sensitive())
        self.click(self.win.f_create)
        self.assertTrue(wait(lambda: 'ui-made' in self.win.rows and self.page() == 'detail'))
        self.assertEqual(self.win.status.get_text(), text.t('new.made', name='ui-made'))

    def test_a_taken_name_is_refused(self):
        self.add('ui-taken')
        self.win.show_new()
        self.win.f_name.set_text('ui-taken')
        self.assertFalse(self.win.f_create.get_sensitive())

    def test_preset_buttons_act_like_one_choice(self):
        self.win.show_new()
        self.win.f_presets['linux'].set_active(True)
        self.assertEqual(self.win.selected_preset(), 'linux')
        self.assertFalse(self.win.f_presets['win11'].get_active())
        self.assertEqual(self.win.f_disk.get_value_as_int(), xmlgen.default_disk_gb('linux'))

    def test_usb_page_shows_the_refusals(self):
        from sparkboxes import usbdev
        self.add('ui-usb')
        self.win.list.select_row(self.win.rows['ui-usb'])
        self.assertTrue(wait(lambda: self.win.loaded == 'ui-usb'))
        self.win._show_usb([usbdev.UsbDevice(1, 2, 'aaaa', 'bbbb', 'Mouse'),
                            usbdev.UsbDevice(1, 3, 'cccc', 'dddd', 'Disk D', refused='d')])
        rows = [r for r in self.win.u_list.get_children() if getattr(r, 'usb', None)]
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0].give.get_sensitive(), "the machine is off")
        self.assertFalse(rows[1].give.get_sensitive())

    def test_unavailable_page(self):
        from sparkboxes.window import BoxesWindow
        win = BoxesWindow(self.app, core.Manager('qemu+unix:///nonexistent-socket', glib_events=True), self.style.Glitch(False),
                          lambda n: None)
        self.addCleanup(win.destroy)
        self.assertTrue(wait(lambda: win.stack.get_visible_child_name() == 'unavailable', 15))
        self.assertFalse(win.new_button.get_sensitive())

    def test_nothing_is_cut_off(self):
        """Every label and button gets as much room as it asks for, on every page, in this
        language. Wrapped labels grow downward; the ones that don't wrap must fit sideways."""
        self.add('ui-fit', 'win11')
        self.win.list.select_row(self.win.rows['ui-fit'])
        self.assertTrue(wait(lambda: self.win.loaded == 'ui-fit'))
        pages = []
        for tab in range(4):
            pages.append(('detail', tab))
        pages.append(('new', 0))
        pages.append(('unavailable', 0))
        for name, tab in pages:
            if name == 'unavailable':
                self.win.un_title.set_text(text.t('un.group'))
                self.win.un_body.set_text(text.t('un.group_body'))
            if name == 'new':
                self.win.show_new()
            elif name == 'detail':
                self.win.hide_new() if self.page() == 'new' else None
                self.win.stack.set_visible_child_name('detail')
                self.win.notebook.set_current_page(tab)
            else:
                self.win.stack.set_visible_child_name(name)
            settle(250)
            shot(self.win, f"{self.lang}-{name}{tab}.png")
            minimum, _natural = self.win.get_preferred_width()
            self.assertLessEqual(minimum, 1100, f"{name}/{tab}: the window needs {minimum}px")
            bad = []
            page = self.win.stack.get_visible_child()
            for widget in walk(page):
                if not widget.get_mapped():
                    continue
                if isinstance(widget, Gtk.Label) and not widget.get_line_wrap() \
                        and widget.get_ellipsize() == 0:
                    need = widget.get_preferred_width()[0]
                    if widget.get_allocated_width() < need:
                        bad.append((widget.get_text(), widget.get_allocated_width(), need))
                if isinstance(widget, Gtk.Button):
                    need = widget.get_preferred_width()[0]
                    if widget.get_allocated_width() < need:
                        bad.append((widget.get_label(), widget.get_allocated_width(), need))
            self.assertEqual(bad, [], f"cut off on {name}/{tab} in {self.lang}")
        self.win.hide_new() if self.page() == 'new' else None

    def test_buttons_fit_in_the_sidebar_and_top_row(self):
        self.add('ui-top')
        self.win.list.select_row(self.win.rows['ui-top'])
        self.assertTrue(wait(lambda: self.win.loaded == 'ui-top'))
        for button in (self.win.b_start, self.win.b_open, self.win.b_pause, self.win.b_shutdown,
                       self.win.b_force, self.win.b_delete, self.win.new_button):
            settle(50)
            self.assertGreaterEqual(button.get_allocated_width(), button.get_preferred_width()[0],
                                    button.get_label())
        self.assertLessEqual(self.win.get_preferred_width()[0], 1100)


class WindowTestsFrench(WindowTests):
    lang = 'fr'


class StyleTests(unittest.TestCase):

    @unittest.skipUnless(HAVE_GTK, 'needs a display')
    def test_the_css_parses(self):
        from sparkboxes import style
        style.install()
        provider = Gtk.CssProvider()
        provider.load_from_data(style.CSS.encode())

    @unittest.skipUnless(HAVE_GTK, 'needs a display')
    def test_corners_are_3px_and_channels_are_the_house_pair(self):
        from sparkboxes import style
        self.assertIn('border-radius: 3px', style.CSS)
        self.assertNotIn('border-radius: 6px', style.CSS)
        self.assertIn('#ff2e88', style.CSS)
        self.assertIn('#22d8ff', style.CSS)


if __name__ == '__main__':
    unittest.main()
