"""The shell as one Gtk.Application: owns dev.wolklaw.SparkShell on the session bus, builds the
windows for every monitor and wires the services together."""

import atexit
import sys
import os
import logging

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, apps, config, ordering, theme  # noqa: E402
from .compositor import CompositorLink  # noqa: E402
from .connectstatus import ConnectStatus, host_connector  # noqa: E402
from .dbusutil import DBusFail, export  # noqa: E402
from .launcherui import Launcher  # noqa: E402
from .lockctl import LockControl  # noqa: E402
from .notifyd import NotificationServer  # noqa: E402
from .notifyui import NotificationsUI  # noqa: E402
from .osd import Controls, Osd  # noqa: E402
from .panel import Panel  # noqa: E402
from .screensaver import ScreenSaverService  # noqa: E402
from .tray import TrayHost  # noqa: E402
from .wallpaper import Wallpaper, screen_sizes  # noqa: E402
from .windows import WindowTracker  # noqa: E402

log = logging.getLogger('spark-shell')

SHELL_XML = """
<node>
  <interface name="dev.wolklaw.SparkShell">
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
class Shell(Gtk.Application):
    def __init__(self):
        # REPLACE: a shell left over from a signed-out session must not keep the name (the new
        # one would only pass it "activate" and exit, and the new session stays black).
        # ALLOW_REPLACEMENT: when a newer shell takes the name, this one quits (name-lost).
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.REPLACE | Gio.ApplicationFlags.ALLOW_REPLACEMENT)
        self.config = config.clean({})
        self.panels = []
        self.wallpapers = []
        self.loose_order = []     # keys of unpinned apps, as dragged this session
        self.compositor = CompositorLink()
        self.connect_status = ConnectStatus()
        self.started = False

    # lifecycle ---------------------------------------------------------------------------
    def do_activate(self):
        if self.started:
            return
        display = Gdk.Display.get_default()
        if display is None:
            # Started after the compositor is gone (a logout): nothing to draw on, so leave
            # instead of hanging on with no windows
            print('spark-shell: no display, exiting', file=sys.stderr)
            self.quit()
            return
        self.started = True
        self.hold()
        provider = Gtk.CssProvider()
        provider.load_from_string(theme.CSS)
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        conn = self.get_dbus_connection() or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.conn = conn

        self.config = config.load()
        self.catalog = apps.Catalog()
        self.tracker = WindowTracker()
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
        # The compositor binds the keys itself: Super runs spark-shell --toggle, and the
        # volume and brightness keys call Key on /Shell.
        Gio.bus_own_name_on_connection(conn, 'org.freedesktop.Notifications',
                                       Gio.BusNameOwnerFlags.REPLACE |
                                       Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
                                       lambda c, n: self.notifyd.start(),
                                       lambda c, n: log.warning('lost %s', n))
        self.tray.start()
        self.tracker.start()
        self.lockctl = LockControl()
        self.lockctl.start()
        self.screensaver = ScreenSaverService(conn)
        self.screensaver.start()
        atexit.register(self.screensaver.stop)

        self._watch_config()
        self.compositor.on_change = self._workspaces_changed
        self.compositor.start()
        self.connect_status.on_change = self.refresh_connect
        self.connect_status.set_enabled(self.config['connect_widget']['enabled'])
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
        screens = screen_sizes([monitors.get_item(i) for i in range(monitors.get_n_items())])
        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            self.wallpapers.append(Wallpaper(monitor, self.config, screens))
            self.panels.append(Panel(self, monitor, with_tray=(i == 0)))
        for w in self.wallpapers + self.panels:
            w.present()
        self._workspaces_changed()
        self.refresh_connect()

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
        self.connect_status.set_enabled(new['connect_widget']['enabled'])
        if position:
            self.rebuild()
        else:
            for w in self.wallpapers:
                w.apply(new)
            for p in self.panels:
                p.tasks.refresh()
                if p.tray is not None:
                    p.tray.set_order(new['tray_order'])
            self.refresh_connect()

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

    def move_task(self, keys, src, dst, after, pinnable):
        """A task button was dropped (see ordering.reorder_tasks): save a changed pinned list,
        keep the unpinned order for this session and redraw every panel."""
        pinned, loose = ordering.reorder_tasks(keys, self.config['pinned'], src, dst, after,
                                               pinnable)
        self.loose_order = loose
        if pinned != self.config['pinned']:
            self.config['pinned'] = pinned
            try:
                config.save_pinned(pinned)
            except OSError as e:
                log.warning('could not save pinned apps: %s', e)
        # not inside the drop handler: the dragged button is still being used
        GLib.idle_add(lambda: ([p.tasks.refresh(force=True) for p in self.panels], False)[1])

    def set_tray_order(self, order):
        self.config['tray_order'] = list(order)
        try:
            config.save_tray_order(order)
        except OSError as e:
            log.warning('could not save the tray order: %s', e)
        for p in self.panels:
            if p.tray is not None:
                p.tray.set_order(order)

    # workspaces and the Spark Connect widget ---------------------------------------------
    def _workspaces_changed(self):
        for p in self.panels:
            p.workspaces.update()

    def connect_host(self) -> str:
        """The connector of the panel that shows the Spark Connect widget."""
        connectors = [p.connector for p in self.panels]
        return host_connector(self.config['connect_widget']['monitor'], connectors,
                              connectors[0] if connectors else '')

    def refresh_connect(self):
        for p in self.panels:
            p.connect_button.update()

    def _save_connect(self, **kw):
        try:
            self.config['connect_widget'] = config.save_connect_widget(**kw)
        except OSError as e:
            log.warning('could not save the Spark Connect widget setting: %s', e)
            return
        self.connect_status.set_enabled(self.config['connect_widget']['enabled'])
        self.refresh_connect()

    def set_connect_enabled(self, on):
        self._save_connect(enabled=on)

    def set_connect_monitor(self, connector):
        self._save_connect(monitor=connector)

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

    def _shell_call(self, interface, method, args, sender):
        if method == 'Key':
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
            'workspaces': {'connected': self.compositor.connected, 'count': self.compositor.count,
                           'current': self.compositor.current,
                           'shown': [p.connector for p in self.panels
                                     if p.workspaces.get_visible()]},
            'connect_widget': {'enabled': self.connect_status.enabled,
                               'installed': self.connect_status.installed,
                               'host': self.connect_host(),
                               'shown': [p.connector for p in self.panels
                                         if p.connect_button.get_visible()]},
            'osd': self.osd.last,
        })
