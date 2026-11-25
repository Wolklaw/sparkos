"""The tray controller: one process, one StatusNotifierItem per applet. It shows an item when it
is turned on, its service is there and (for power and printers) there is something to show;
it hides it when any of that stops being true. A config change from `spark-tray --item`
takes effect at once, with no restart."""

import os
import signal
from typing import Callable, Dict, List, Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk   # noqa: E402

from . import BUS_NAME, core, ui                    # noqa: E402
from .core import ITEMS, load_config, log           # noqa: E402
from .dbusutil import Bus                           # noqa: E402
from .items import ALL_ITEMS, Context, TrayItem     # noqa: E402
from .sni import Appearance, StatusNotifierItem     # noqa: E402

RECHECK_SECONDS = 8


def private_session_connection() -> Gio.DBusConnection:
    """A connection of its own for one tray item. Every item answers at /StatusNotifierItem
    (that is the path trays assume when they are given only a bus name), so two items can't
    share a connection."""
    address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
    return Gio.DBusConnection.new_for_address_sync(
        address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)


def _safe(fn: Callable, default):
    def wrapped(*args):
        try:
            return fn(*args)
        except Exception:                      # noqa: BLE001 - the tray must always answer
            log.exception("%s failed", getattr(fn, '__name__', 'callback'))
            return default
    return wrapped


class Tray:
    def __init__(self, system_bus: Optional[Bus] = None, session_bus: Optional[Bus] = None,
                 fake_dir: str = '', on_quit: Optional[Callable[[], None]] = None):
        self.system = system_bus or Bus.system()
        self.session = session_bus or Bus.session()
        self.on_quit = on_quit or Gtk.main_quit
        self.config = load_config()
        self.prompter = ui.Prompter()
        self.ctx = Context(self.system, self.prompter, self.config, self.item_changed,
                           self.disable, self.quit, fake_dir)
        self.items: Dict[str, TrayItem] = {}
        self.snis: Dict[str, StatusNotifierItem] = {}
        for cls in ALL_ITEMS:
            item = cls(self.ctx)
            self.items[item.name] = item
            self.ctx.items[item.name] = item
            self.snis[item.name] = StatusNotifierItem(private_session_connection(),
                                                      self._look(item))
        self._pending: set = set()
        self._flush_id = 0
        self._timer = 0
        self._monitor: Optional[Gio.FileMonitor] = None
        self._name_id = 0
        self.has_name = False

    def _look(self, item: TrayItem) -> Appearance:
        return Appearance(
            id_=f"spark-tray-{item.name}", category='Hardware',
            title=_safe(item.title, item.name), icon=_safe(item.icon, 'dialog-question'),
            tooltip=_safe(item.tooltip, ''), menu=_safe(item.menu, []),
            activate=_safe(item.activate, None), secondary=_safe(item.secondary, None),
            scroll=_safe(item.scroll, None))

    # — lifecycle —
    def start(self, own_name: bool = True) -> None:
        if own_name:
            self._name_id = Gio.bus_own_name_on_connection(
                self.session.conn, BUS_NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                self._got_name, self._lost_name)
        else:
            self.has_name = True
        self.sync_all()
        self._timer = GLib.timeout_add_seconds(RECHECK_SECONDS, self._recheck)
        self._watch_config()

    def _got_name(self, *_args) -> None:
        self.has_name = True

    def _lost_name(self, *_args) -> None:
        if not self.has_name:
            log.info("Spark Tray is already running in this session; leaving")
            self.quit()

    def stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        if self._flush_id:
            GLib.source_remove(self._flush_id)
            self._flush_id = 0
        if self._monitor:
            self._monitor.cancel()
            self._monitor = None
        for name, item in self.items.items():
            self.snis[name].hide()
            if item.popup:
                item.popup.destroy()
                item.popup = None
            item.stop()
        for win in list(self.prompter.open):
            win.close_quietly()
        for sni in self.snis.values():
            try:
                sni.conn.close_sync(None)
            except GLib.Error:
                pass
        if self._name_id:
            Gio.bus_unown_name(self._name_id)
            self._name_id = 0

    def quit(self) -> None:
        self.stop()
        self.on_quit()

    # — what is on the tray —
    def enabled(self, name: str) -> bool:
        return bool(self.config['items'].get(name, True))

    def shown(self) -> List[str]:
        return [n for n, s in self.snis.items() if s.shown]

    def sync(self, item: TrayItem) -> None:
        name = item.name
        if self.enabled(name):
            if not item.started:
                item.started = item.start()
        elif item.started:
            item.stop()
        want = self.enabled(name) and item.started and _safe(item.visible, False)()
        sni = self.snis[name]
        if want and not sni.shown:
            sni.show()
        elif not want and sni.shown:
            sni.hide()
            if item.popup:
                item.popup.hide()
        if want:
            sni.refresh()
            _safe(item.update, None)()

    def sync_all(self) -> None:
        for item in self.items.values():
            self.sync(item)

    def item_changed(self, item: TrayItem) -> None:
        """A backend reported a change. Bursts of signals become one redraw."""
        self._pending.add(item.name)
        if not self._flush_id:
            self._flush_id = GLib.timeout_add(120, self._flush)

    def _flush(self) -> bool:
        self._flush_id = 0
        names, self._pending = self._pending, set()
        for name in names:
            self.sync(self.items[name])
        return False

    def _recheck(self) -> bool:
        for item in self.items.values():
            if self.enabled(item.name):
                _safe(item.recheck, None)()
                self.sync(item)
        return True

    # — turning items on and off —
    def disable(self, name: str) -> None:
        core.set_item_enabled(name, False)
        self._reload_config()

    def _reload_config(self) -> None:
        new = load_config()
        self.config.clear()
        self.config.update(new)
        self.sync_all()

    def _watch_config(self) -> None:
        path = os.path.join(core.config_dir(), 'config.json')
        try:
            self._monitor = Gio.File.new_for_path(path).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect('changed', lambda *_a: GLib.idle_add(self._config_changed))
        except GLib.Error as exc:
            log.warning("not watching config.json: %s", exc.message)

    def _config_changed(self) -> bool:
        self._reload_config()
        return False


def run(fake_dir: str = '') -> int:
    core.setup_logging()
    tray = Tray(fake_dir=fake_dir)
    for sig in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (tray.quit(), False)[1])
    tray.start()
    Gtk.main()
    return 0
