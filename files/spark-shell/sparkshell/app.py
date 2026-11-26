"""The shell as one Gtk.Application: owns dev.wolklaw.SparkShell on the session bus, builds the
windows for every monitor and wires the services together."""

import atexit
import os
import logging

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, apps, config, theme  # noqa: E402
from .dbusutil import DBusFail, export  # noqa: E402
from .launcherui import Launcher  # noqa: E402
from .lockctl import LockControl  # noqa: E402
from .notifyd import NotificationServer  # noqa: E402
from .notifyui import NotificationsUI  # noqa: E402
from .osd import OSD_SERVICE_XML, Controls, Osd, osd_service_call  # noqa: E402
from .panel import Panel  # noqa: E402
from .screensaver import ScreenSaverService  # noqa: E402
from .tray import TrayHost  # noqa: E402
from .wallpaper import Wallpaper  # noqa: E402
from .windows import WindowTracker  # noqa: E402

log = logging.getLogger('spark-shell')

SHELL_XML = """
<node>
  <interface name="dev.wolklaw.SparkShell">
    <method name="Windows"><arg type="s" name="json" direction="in"/></method>
    <method name="Key"><arg type="s" name="name" direction="in"/></method>
    <method name="ToggleLauncher"/>
    <method name="HideLauncher"><arg type="b" name="was_open" direction="out"/></method>
    <method name="State"><arg type="s" name="json" direction="out"/></method>
    <method name="Screenshot">
      <arg type="s" name="dir" direction="in"/><arg type="s" name="json" direction="out"/>
    </method>
    <method name="Quit"/>
  </interface>
</node>
"""
PLASMASHELL_XML = """
<node>
  <interface name="org.kde.PlasmaShell">
    <method name="activateLauncherMenu"/>
    <method name="toggleDashboard"/>
  </interface>
</node>
"""


class Shell(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config = config.clean({})
        self.panels = []
        self.wallpapers = []
        self.started = False

    # lifecycle ---------------------------------------------------------------------------
    def do_activate(self):
        if self.started:
            return
        self.started = True
        self.hold()
        display = Gdk.Display.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_string(theme.CSS)
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        conn = self.get_dbus_connection() or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.conn = conn

        self.config = config.load()
        self.catalog = apps.Catalog()
        self.tracker = WindowTracker(conn)
        self.tracker.on_changed = self._windows_changed
        self._window_ids = set()
        self.notifyd = NotificationServer(conn)
        atexit.register(self.notifyd.flush)
        self.notifications_ui = NotificationsUI(self.notifyd, self.tracker)
        self.tray = TrayHost(conn)
        self.osd = Osd()
        self.controls = Controls(self.osd, conn)
        self.launcher = Launcher(self)

        export(conn, '/Shell', SHELL_XML, self._shell_call)
        # In the Spark compositor session nothing from KDE runs: the compositor binds the
        # Super key itself (spark-shell --toggle), so the plasmashell, KDE OSD and
        # kglobalaccel stand-ins are only for the KWin session.
        sparkwl = 'sparkwl' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
        if not sparkwl:
            export(conn, '/PlasmaShell', PLASMASHELL_XML, self._plasma_call)
            export(conn, '/org/kde/osdService', OSD_SERVICE_XML,
                   lambda _i, method, args, _s: osd_service_call(self.osd, method, args))
            Gio.bus_own_name_on_connection(conn, 'org.kde.plasmashell',
                                           Gio.BusNameOwnerFlags.DO_NOT_QUEUE, None, None)
        Gio.bus_own_name_on_connection(conn, 'org.freedesktop.Notifications',
                                       Gio.BusNameOwnerFlags.REPLACE |
                                       Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
                                       lambda c, n: self.notifyd.start(),
                                       lambda c, n: log.warning('lost %s', n))
        if not sparkwl:
            self._grab_launcher_shortcut(conn)
        self.tray.start()
        self.tracker.start()
        if sparkwl:     # Plasma's session has KScreenLocker and its own ScreenSaver service
            self.lockctl = LockControl()
            self.lockctl.start()
            self.screensaver = ScreenSaverService(conn)
            self.screensaver.start()
            atexit.register(self.screensaver.stop)

        self._watch_config()
        display.get_monitors().connect('items-changed', lambda *_: self.rebuild())
        self.rebuild()
        self.catalog_monitor = Gio.AppInfoMonitor.get()
        self.catalog_monitor.connect('changed', lambda *_: self.catalog.reload())
        log.info('spark shell %s is up', APP_ID)

    def rebuild(self):
        """Windows for the current monitors."""
        for w in self.panels + self.wallpapers:
            w.destroy()
        self.panels, self.wallpapers = [], []
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            self.wallpapers.append(Wallpaper(monitor, self.config))
            self.panels.append(Panel(self, monitor, with_tray=(i == 0)))
        for w in self.wallpapers + self.panels:
            w.present()

    # config ------------------------------------------------------------------------------
    def _watch_config(self):
        path = config.config_path()
        try:
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            pass
        self._config_monitor = Gio.File.new_for_path(path).monitor_file(
            Gio.FileMonitorFlags.NONE, None)
        self._config_monitor.connect('changed', self._config_changed)

    def _config_changed(self, *_):
        new = config.load()
        if new == self.config:
            return
        position = new['panel_position'] != self.config['panel_position']
        self.config = new
        if position:
            self.rebuild()
        else:
            for w in self.wallpapers:
                w.apply(new)
            for p in self.panels:
                p.tasks.refresh()

    def set_pinned(self, ident, on):
        pinned = [p for p in self.config['pinned'] if p != ident]
        if on:
            pinned.append(ident)
        self.config['pinned'] = pinned
        try:
            config.save_pinned(pinned)
        except OSError as e:
            log.warning('could not save pinned apps: %s', e)
        for p in self.panels:
            p.tasks.refresh()

    # actions -----------------------------------------------------------------------------
    def _windows_changed(self, windows):
        for p in self.panels:
            p.tasks.refresh()
        # A window that opens while the menu is up (Win+Shift+S, a notification's app) closes
        # the menu: it is a see-through full-screen layer above every window, so left open it
        # would take the first click and keep the keyboard from the new window.
        ids = set(self.tracker.all_ids) or {w['id'] for w in windows}
        if ids - self._window_ids and self.launcher.get_visible():
            self.launcher.hide_launcher()
        self._window_ids = ids

    def toggle_launcher(self):
        self.launcher.toggle()

    # Plasma 6 binds the Meta key (and Alt+F1) as plasmashell's kglobalaccel shortcut
    # "activate application launcher"; kglobalaccel only sends it to a client that registered
    # that shortcut as present, which plasmashell does through KGlobalAccel. The shell does the
    # same over D-Bus, keeping the keys saved in kglobalshortcutsrc.
    LAUNCHER_ACTION = ['plasmashell', 'activate application launcher', 'plasmashell',
                       'Activate Application Launcher']

    def _grab_launcher_shortcut(self, conn):
        def done(c, res, what):
            try:
                c.call_finish(res)
            except GLib.Error as e:
                log.warning('kglobalaccel %s: %s', what, e.message)

        def call(method, args, what):
            conn.call('org.kde.kglobalaccel', '/kglobalaccel', 'org.kde.KGlobalAccel', method,
                      args, None, Gio.DBusCallFlags.NONE, 3000, None, done, what)
        call('doRegister', GLib.Variant('(as)', (self.LAUNCHER_ACTION,)), 'register')
        # flags 2 = SetPresent; the keys are loaded from the saved config (autoloading)
        call('setShortcutKeys', GLib.Variant('(asa(ai)u)', (self.LAUNCHER_ACTION, [], 2)),
             'set present')

        def pressed(_c, _sender, _path, _iface, _signal, params):
            if params.unpack()[1] == self.LAUNCHER_ACTION[1]:
                self.toggle_launcher()
        conn.signal_subscribe('org.kde.kglobalaccel', 'org.kde.kglobalaccel.Component',
                              'globalShortcutPressed', '/component/plasmashell', None,
                              Gio.DBusSignalFlags.NONE, pressed)

    def _shell_call(self, interface, method, args, sender):
        if method == 'Windows':
            self.tracker.update(args[0])
        elif method == 'Key':
            self.controls.key(args[0])
        elif method == 'ToggleLauncher':
            self.toggle_launcher()
        elif method == 'HideLauncher':
            # Spark Snip asks before its screenshot, so the menu is not in the picture
            was_open = self.launcher.get_visible()
            if was_open:
                self.launcher.hide_launcher()
            return (was_open,)
        elif method == 'State':
            return (self.state_json(),)
        elif method == 'Screenshot':
            return (self.screenshot(args[0]),)
        elif method == 'Quit':
            self.quit()
        else:
            raise DBusFail('unknown method ' + method,
                           'org.freedesktop.DBus.Error.UnknownMethod')

    def screenshot(self, directory):
        """Render each of the shell's own windows to a PNG (works with no screen to capture)."""
        import json
        import os
        os.makedirs(directory, exist_ok=True)
        named = [('panel-%s' % p.connector, p) for p in self.panels]
        named += [('wallpaper-%d' % i, w) for i, w in enumerate(self.wallpapers)]
        named += [('notifications', self.notifications_ui.toasts), ('launcher', self.launcher),
                  ('osd', self.osd)]
        written = []
        for name, window in named:
            width, height = window.get_width(), window.get_height()
            renderer = window.get_native().get_renderer() if window.get_native() else None
            if not window.get_visible() or renderer is None or width <= 0 or height <= 0:
                log.info('screenshot: skipped %s (visible %s, %sx%s, renderer %s)', name,
                         window.get_visible(), width, height, renderer is not None)
                continue
            snapshot = Gtk.Snapshot()
            Gtk.WidgetPaintable.new(window).snapshot(snapshot, width, height)
            node = snapshot.to_node()
            if node is None and window.get_child() is not None:     # the window's own box
                snapshot = Gtk.Snapshot()
                child = window.get_child()
                Gtk.WidgetPaintable.new(child).snapshot(snapshot, child.get_width(),
                                                        child.get_height())
                node = snapshot.to_node()
                width, height = child.get_width(), child.get_height()
            if node is None:
                log.info('screenshot: %s drew nothing (%sx%s)', name, width, height)
                continue
            texture = renderer.render_texture(node, None)
            path = os.path.join(directory, name + '.png')
            ok = texture.save_to_png(path)
            log.info('screenshot: %s %sx%s saved=%s', name, width, height, ok)
            if ok:
                written.append(path)
        return json.dumps(written)

    def state_json(self):
        """What the shell is showing, for tests and bug reports."""
        import json
        from . import layer
        return json.dumps({
            'layer_shell': layer.is_available(),
            'panels': [p.connector for p in self.panels],
            'wallpapers': len(self.wallpapers),
            'windows': self.tracker.windows,
            'tracker_loaded': self.tracker.loaded,
            'tray': [i.id for i in self.tray.visible_items()],
            'tray_owns_watcher': self.tray.owns_watcher,
            'notifications': {'active': len(self.notifyd.active),
                              'history': len(self.notifyd.history),
                              'dnd': self.notifyd.dnd},
            'launcher_open': self.launcher.get_visible(),
            'osd': self.osd.last,
        })

    def _plasma_call(self, interface, method, args, sender):
        # KWin's Meta key calls this on plasmashell; the Spark shell answers it
        if method in ('activateLauncherMenu', 'toggleDashboard'):
            GLib.idle_add(lambda: self.toggle_launcher() and False)
        return None
