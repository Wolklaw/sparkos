"""The machine's screen: a window with spice-gtk's display widget. libvirt hands over a file
descriptor on the machine's SPICE channel (openGraphicsFD), so there is no port, no socket file
and no password to manage. Keyboard, mouse (grabbed with a click, released with Ctrl+Alt) and
sound come with the widget; the clipboard is shared when the guest runs spice-vdagent."""

import logging

import gi

from . import APP_SLUG, GTK_VERSION
from .text import t

gi.require_version('Gtk', GTK_VERSION)
gi.require_version('Gdk', GTK_VERSION)
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

log = logging.getLogger(APP_SLUG)

try:
    gi.require_version('SpiceClientGLib', '2.0')
    gi.require_version('SpiceClientGtk', '3.0')
    from gi.repository import SpiceClientGLib, SpiceClientGtk
    HAVE_SPICE = True
except (ImportError, ValueError):
    HAVE_SPICE = False

CTRL_ALT_DEL = [29, 56, 111]          # Linux input codes: left Ctrl, left Alt, Delete


class ConsoleWindow(Gtk.Window):
    """One window per running machine."""

    def __init__(self, app, manager, name: str, send_keys, glitch=None):
        super().__init__(title=t('con.title', name=name), application=app)
        self.manager = manager
        self.vm_name = name
        self.session = None
        self.display = None
        self.glitch = glitch
        self.set_default_size(1024, 768)
        self.get_style_context().add_class('spark-boxes')

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(box)
        bar = Gtk.Box(spacing=8)
        bar.get_style_context().add_class('consolebar')
        self.status = Gtk.Label(label=t('con.connecting'), xalign=0)
        self.status.get_style_context().add_class('status')
        bar.pack_start(self.status, True, True, 0)
        for label, handler in ((t('act.cad'), lambda *_: send_keys(name, CTRL_ALT_DEL)),
                               (t('con.fullscreen'), self._toggle_fullscreen)):
            button = Gtk.Button(label=label)
            button.connect('clicked', handler)
            bar.pack_end(button, False, False, 0)
        hint = Gtk.Label(label=t('con.release'))
        hint.get_style_context().add_class('meta')
        bar.pack_end(hint, False, False, 8)
        box.pack_start(bar, False, False, 0)
        self.holder = Gtk.Box()
        box.pack_start(self.holder, True, True, 0)
        self.connect('destroy', self._on_destroy)
        self.show_all()
        self._open()

    def _open(self) -> None:
        if not HAVE_SPICE:
            self.status.set_text(t('con.unavailable', why="spice-gtk isn't installed"))
            return
        try:
            fd = self.manager.graphics_fd(self.vm_name)
        except Exception as exc:        # BoxesError: the machine is off, or libvirt refused
            self.status.set_text(t('con.unavailable', why=str(exc)))
            log.warning("screen of %s: %s", self.vm_name, exc)
            return
        self.session = SpiceClientGLib.Session()
        self.session.connect('channel-new', self._channel_new)
        SpiceClientGtk.GtkSession.get(self.session).set_property('auto-clipboard', True)
        if not self.session.open_fd(fd):
            self.status.set_text(t('con.unavailable', why="the display didn't open"))

    def _channel_new(self, session, channel) -> None:
        if isinstance(channel, SpiceClientGLib.MainChannel):
            channel.connect('channel-event', self._main_event)
        elif isinstance(channel, SpiceClientGLib.DisplayChannel) and self.display is None:
            self.display = SpiceClientGtk.Display.new(session, channel.get_property('channel-id'))
            self.display.set_property('scaling', True)
            self.display.set_property('resize-guest', False)
            self.holder.pack_start(self.display, True, True, 0)
            self.display.show()
            self.status.set_text(self.vm_name)
            GLib.idle_add(self.display.grab_focus)
        elif isinstance(channel, SpiceClientGLib.PlaybackChannel):
            SpiceClientGLib.Audio.get(session, None)

    def _main_event(self, _channel, event) -> None:
        closing = (SpiceClientGLib.ChannelEvent.CLOSED, SpiceClientGLib.ChannelEvent.ERROR_CONNECT,
                   SpiceClientGLib.ChannelEvent.ERROR_IO)
        if event in closing:
            self.status.set_text(t('con.lost'))
            if self.glitch:
                self.glitch.now(self.status)

    def _toggle_fullscreen(self, *_args) -> None:
        state = self.get_window().get_state() if self.get_window() else 0
        if state & Gdk.WindowState.FULLSCREEN:
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_destroy(self, *_args) -> None:
        if self.session is not None:
            try:
                self.session.disconnect()
            except Exception:           # already closed
                pass
            self.session = None
