"""GIO's side of Spark Files, in one background thread running GLib's main loop: folder
watching, the D-Bus names (one Spark Files per session, and FileManager1 for "Show in
folder"), and drives being plugged in or out.

Everything that happens there reaches Tk's thread through Bridge.post(): a queue, and one
byte on a pipe that Tk watches (createfilehandler), so nothing polls and an idle window costs
no CPU."""

import os
import queue
import threading
from typing import Callable, Dict, List, Optional

from . import BUS_NAME, BUS_PATH, FM1_NAME, FM1_PATH
from .core import log

try:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = GLib = None

APP_XML = f"""
<node>
  <interface name="{BUS_NAME}">
    <method name="Open">
      <arg type="as" name="uris" direction="in"/>
      <arg type="s" name="mode" direction="in"/>
    </method>
  </interface>
</node>"""

FM1_XML = f"""
<node>
  <interface name="{FM1_NAME}">
    <method name="ShowFolders">
      <arg type="as" name="URIs" direction="in"/>
      <arg type="s" name="StartupId" direction="in"/>
    </method>
    <method name="ShowItems">
      <arg type="as" name="URIs" direction="in"/>
      <arg type="s" name="StartupId" direction="in"/>
    </method>
    <method name="ShowItemProperties">
      <arg type="as" name="URIs" direction="in"/>
      <arg type="s" name="StartupId" direction="in"/>
    </method>
  </interface>
</node>"""


def available() -> bool:
    return Gio is not None


def hand_over(uris: List[str], mode: str, timeout_ms: int = 3000) -> bool:
    """Give the request to the Spark Files already running in this session; False when there
    isn't one (or no session bus), and this process should open the window itself."""
    if Gio is None:
        return False
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(BUS_NAME, BUS_PATH, BUS_NAME, 'Open',
                      GLib.Variant('(ass)', (uris, mode)), None,
                      Gio.DBusCallFlags.NO_AUTO_START, timeout_ms, None)
        return True
    except Exception as exc:            # noqa: BLE001 - GLib.Error: nobody owns the name
        log.debug("no running Spark Files to hand over to: %s", exc)
        return False


class Bridge:
    def __init__(self, root, on_request: Callable[[str, List[str]], None],
                 on_mounts_changed: Callable[[], None]):
        """on_request(mode, uris) runs in Tk's thread; mode is 'open', 'window', 'tab',
        'show-items', 'show-folders' or 'properties'."""
        self.root = root
        self.on_request, self.on_mounts_changed = on_request, on_mounts_changed
        self._queue: 'queue.Queue[Callable[[], None]]' = queue.Queue()
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)
        os.set_blocking(self._w, False)
        import tkinter
        root.tk.createfilehandler(self._r, tkinter.READABLE, self._drain)
        self.loop = None
        self.context = None
        self.owns_app_name = False
        self.owns_fm1 = False
        self._names: List[int] = []
        self._exported: List[tuple] = []         # (connection, registration id)
        self._monitors: Dict[int, object] = {}
        self._next_id = 1
        self._volume_monitor = None
        self.volumes: List[dict] = []         # drives plugged in but not mounted yet
        self._ready = threading.Event()
        if Gio is not None:
            self.thread = threading.Thread(target=self._run, name='glib', daemon=True)
            self.thread.start()
            self._ready.wait(3)

    # Tk side

    def post(self, fn: Callable[[], None]) -> None:
        """Run fn in Tk's thread soon. Safe from any thread."""
        self._queue.put(fn)
        try:
            os.write(self._w, b'x')
        except (BlockingIOError, OSError):
            pass                                        # the pipe is full: it'll drain anyway

    def _drain(self, _fd, _mask) -> None:
        try:
            while os.read(self._r, 4096):
                pass
        except (BlockingIOError, OSError):
            pass
        while True:
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:                           # noqa: BLE001
                log.exception("bridge callback")

    def in_glib(self, fn: Callable[[], None]) -> None:
        """Run fn in the GLib thread."""
        if self.context is None:
            return

        def once():
            try:
                fn()
            except Exception:                           # noqa: BLE001
                log.exception("glib call")
            return False
        self.context.invoke_full(GLib.PRIORITY_DEFAULT, once)

    def close(self) -> None:
        try:
            self.root.tk.deletefilehandler(self._r)
        except Exception:                               # noqa: BLE001
            pass
        if self.loop is not None:
            def stop():
                for conn, rid in self._exported:
                    try:
                        conn.unregister_object(rid)
                    except Exception:               # noqa: BLE001
                        pass
                self._exported.clear()
                for oid in self._names:
                    Gio.bus_unown_name(oid)
                for mon in self._monitors.values():
                    mon.cancel()
                self._monitors.clear()
                self.loop.quit()
            self.in_glib(stop)
        for fd in (self._r, self._w):
            try:
                os.close(fd)
            except OSError:
                pass

    # watching folders

    def watch(self, path: str, on_change: Callable[[str, str, Optional[str]], None]) -> int:
        """Call on_change(event, path, other) in Tk's thread when something in the folder
        changes. Returns an id for unwatch()."""
        if Gio is None:
            return 0
        wid = self._next_id
        self._next_id += 1

        def start():
            try:
                mon = Gio.File.new_for_path(path).monitor_directory(
                    Gio.FileMonitorFlags.WATCH_MOVES, None)
            except Exception as exc:                    # noqa: BLE001
                log.debug("can't watch %s: %s", path, exc)
                return
            mon.set_rate_limit(300)

            def changed(_m, f, other, event):
                name = event.value_nick
                p = f.get_path() if f else None
                o = other.get_path() if other else None
                self.post(lambda: on_change(name, p, o))
            mon.connect('changed', changed)
            self._monitors[wid] = mon
        self.in_glib(start)
        return wid

    def unwatch(self, wid: int) -> None:
        if not wid:
            return

        def stop():
            mon = self._monitors.pop(wid, None)
            if mon is not None:
                mon.cancel()
        self.in_glib(stop)

    # the GLib thread

    def _run(self) -> None:
        self.context = GLib.MainContext.new()
        self.context.push_thread_default()
        self.loop = GLib.MainLoop.new(self.context, False)
        try:
            self._own(BUS_NAME, APP_XML, BUS_PATH, 'app')
            self._own(FM1_NAME, FM1_XML, FM1_PATH, 'fm1')
            try:
                self._volume_monitor = Gio.VolumeMonitor.get()
                for sig in ('mount-added', 'mount-removed', 'volume-added', 'volume-removed',
                            'mount-changed', 'volume-changed'):
                    self._volume_monitor.connect(sig, lambda *_a: self._volumes_changed())
                self._snapshot()
            except Exception as exc:                    # noqa: BLE001
                log.debug("no volume monitor: %s", exc)
        finally:
            self._ready.set()
        self.loop.run()

    def _volume_id(self, volume) -> str:
        return (volume.get_identifier('uuid') or volume.get_identifier('unix-device') or
                volume.get_name() or '')

    def _snapshot(self) -> None:
        out = []
        for volume in self._volume_monitor.get_volumes():
            try:
                mount = volume.get_mount()
                drive = volume.get_drive()
                removable = bool(drive and (drive.is_removable() or drive.is_media_removable()))
                if not removable and not volume.can_eject():
                    continue                    # internal disks: Windows drives come by path
                root = mount.get_root().get_path() if mount is not None else ''
                out.append({'id': self._volume_id(volume), 'name': volume.get_name() or '?',
                            'mounted': mount is not None, 'path': root or '',
                            'can_mount': volume.can_mount(),
                            'device': volume.get_identifier('unix-device') or ''})
            except Exception as exc:            # noqa: BLE001
                log.debug("volume: %s", exc)
        self.volumes = out

    def _volumes_changed(self) -> None:
        self._snapshot()
        self.post(self.on_mounts_changed)

    def mount(self, volume_id: str, done: Callable[[Optional[str], Optional[str]], None]
              ) -> None:
        """Mount a plugged-in drive (udisks asks for a password if it must); done(path, why)
        runs in Tk's thread."""
        def start():
            volume = next((v for v in self._volume_monitor.get_volumes()
                           if self._volume_id(v) == volume_id), None)
            if volume is None:
                self.post(lambda: done(None, 'gone'))
                return

            def finished(vol, result):
                try:
                    vol.mount_finish(result)
                    mount = vol.get_mount()
                    path = mount.get_root().get_path() if mount else None
                    self.post(lambda: done(path, None if path else '?'))
                except Exception as exc:        # noqa: BLE001
                    why = getattr(exc, 'message', str(exc))
                    self.post(lambda: done(None, why))
            volume.mount(Gio.MountMountFlags.NONE, Gio.MountOperation(), None, finished)
        if self._volume_monitor is None:
            done(None, 'no volume monitor')
            return
        self.in_glib(start)

    def _own(self, name: str, xml: str, path: str, which: str) -> None:
        node = Gio.DBusNodeInfo.new_for_xml(xml)

        def call(_conn, _sender, _path, _iface, method, params, invocation):
            uris = list(params.unpack()[0])
            mode = {'ShowFolders': 'show-folders', 'ShowItems': 'show-items',
                    'ShowItemProperties': 'properties'}.get(method)
            if method == 'Open':
                mode = params.unpack()[1] or 'open'
            invocation.return_value(None)
            if mode:
                self.post(lambda: self.on_request(mode, uris))

        def bus_acquired(conn, _name):
            try:
                rid = conn.register_object(path, node.interfaces[0], call, None, None)
                self._exported.append((conn, rid))
            except Exception as exc:                    # noqa: BLE001
                log.warning("could not register %s: %s", path, exc)

        def acquired(_conn, _name):
            setattr(self, 'owns_app_name' if which == 'app' else 'owns_fm1', True)
            log.info("own %s", name)

        def lost(_conn, _name):
            setattr(self, 'owns_app_name' if which == 'app' else 'owns_fm1', False)
            log.info("don't own %s (another program has it)", name)

        flags = Gio.BusNameOwnerFlags.NONE
        if which == 'fm1':
            # take "Show in folder" over from another file manager's daemon if it's running, and give it
            # back if someone else asks the same way
            flags = Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT | Gio.BusNameOwnerFlags.REPLACE
        self._names.append(Gio.bus_own_name(Gio.BusType.SESSION, name, flags, bus_acquired,
                                            acquired, lost))


# ─── Apps: open, open with, defaults (GIO's view of the desktop entries and mimeapps.list) ─

def content_type(path: str, is_dir: bool = False, sniff: bool = False) -> str:
    """The MIME type: from the name (fast) or, with sniff, from the content too."""
    if is_dir:
        return 'inode/directory'
    if Gio is None:
        import mimetypes
        return mimetypes.guess_type(path)[0] or 'application/octet-stream'
    if sniff:
        try:
            info = Gio.File.new_for_path(path).query_info(
                'standard::content-type', Gio.FileQueryInfoFlags.NONE, None)
            ct = info.get_content_type()
            if ct:
                return Gio.content_type_get_mime_type(ct) or ct
        except Exception:                             # noqa: BLE001
            pass
    ct, _uncertain = Gio.content_type_guess(path, None)
    return Gio.content_type_get_mime_type(ct) or ct or 'application/octet-stream'


def type_description(mime: str) -> str:
    if Gio is None:
        return mime
    try:
        return Gio.content_type_get_description(mime) or mime
    except Exception:                                 # noqa: BLE001
        return mime


class App:
    """A desktop app that can open files."""

    __slots__ = ('id', 'name', 'icon', 'info')

    def __init__(self, info):
        self.info = info
        self.id = info.get_id() or ''
        self.name = info.get_display_name() or info.get_name() or self.id
        icon = info.get_icon()
        self.icon = icon.to_string() if icon is not None else ''

    def __repr__(self) -> str:
        return f"App({self.id!r})"


def default_app(mime: str) -> Optional[App]:
    if Gio is None:
        return None
    info = Gio.AppInfo.get_default_for_type(mime, False)
    return App(info) if info is not None else None


def apps_for(mime: str) -> List[App]:
    if Gio is None:
        return []
    seen, out = set(), []
    for info in Gio.AppInfo.get_recommended_for_type(mime) + Gio.AppInfo.get_all_for_type(mime):
        if info.get_id() in seen or not info.should_show():
            continue
        seen.add(info.get_id())
        out.append(App(info))
    return out


def all_apps() -> List[App]:
    if Gio is None:
        return []
    out = [App(i) for i in Gio.AppInfo.get_all() if i.should_show()]
    out.sort(key=lambda a: a.name.casefold())
    return out


def set_default(app: App, mime: str) -> None:
    app.info.set_as_default_for_type(mime)


def launch(app: Optional[App], paths: List[str]) -> Optional[str]:
    """Open paths with app (or each with its default app). None on success, else why."""
    if Gio is None or app is None:
        import subprocess
        for p in paths:
            try:
                subprocess.Popen(['xdg-open', p], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            except OSError as exc:
                return str(exc)
        return None
    try:
        files = [Gio.File.new_for_path(p) for p in paths]
        if app.info.supports_files() or app.info.supports_uris():
            app.info.launch(files, None)
        else:
            for f in files:
                app.info.launch([f], None)
        return None
    except Exception as exc:                          # noqa: BLE001 - GLib.Error
        return getattr(exc, 'message', None) or str(exc)
