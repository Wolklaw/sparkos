"""MPRIS2 on the session bus, so the keyboard's media keys, the shell's media widget and the lock
screen control the music: org.mpris.MediaPlayer2.SparkMedia.

D-Bus runs on GLib's Gio, through PyGObject (already there for GStreamer), in a thread with its
own GLib main loop; the window's Tk loop is never polled. A call from outside (Play, Next, ...)
is answered at once in that thread and handed to Tk through a pipe Tk watches, so it acts in
the window's thread like a click. The window tells D-Bus what changed (PropertiesChanged)."""

import hashlib
import os
import queue
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from . import APP_ID, APP_NAME
from .core import cache_dir, file_uri, log

BUS_NAME = 'org.mpris.MediaPlayer2.SparkMedia'
PATH = '/org/mpris/MediaPlayer2'
ROOT_IFACE = 'org.mpris.MediaPlayer2'
PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player'
NO_TRACK = '/org/mpris/MediaPlayer2/TrackList/NoTrack'

XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek"><arg direction="in" name="Offset" type="x"/></method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri"><arg direction="in" name="Uri" type="s"/></method>
    <signal name="Seeked"><arg name="Position" type="x"/></signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""

AUDIO_MIME = ['audio/mpeg', 'audio/flac', 'audio/x-flac', 'audio/ogg', 'audio/x-vorbis+ogg',
              'audio/opus', 'audio/x-opus+ogg', 'audio/mp4', 'audio/x-m4a', 'audio/aac',
              'audio/wav', 'audio/x-wav', 'audio/x-ms-wma', 'audio/x-aiff', 'audio/x-wavpack',
              'audio/x-ape', 'audio/x-musepack', 'audio/x-mpegurl']

# what each property is, as D-Bus types: everything the window reports goes through here
PLAYER_TYPES = {'PlaybackStatus': 's', 'LoopStatus': 's', 'Rate': 'd', 'Shuffle': 'b',
                'Metadata': 'a{sv}', 'Volume': 'd', 'MinimumRate': 'd', 'MaximumRate': 'd',
                'CanGoNext': 'b', 'CanGoPrevious': 'b', 'CanPlay': 'b', 'CanPause': 'b',
                'CanSeek': 'b', 'CanControl': 'b'}


def available() -> Optional[str]:
    """None when Gio's D-Bus can be used, otherwise why not."""
    if os.name == 'nt':
        return "no session bus on Windows"
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib  # noqa: F401
    except (ImportError, ValueError) as exc:
        return f"no Gio: {exc}"
    return None


def metadata_variant(meta: Dict[str, Any]):
    from gi.repository import GLib
    out = {}
    for key, value in meta.items():
        if value in (None, '', []):
            continue
        if key == 'mpris:trackid':
            out[key] = GLib.Variant('o', value)
        elif key == 'mpris:length':
            out[key] = GLib.Variant('x', int(value))
        elif key in ('xesam:artist', 'xesam:albumArtist'):
            out[key] = GLib.Variant('as', list(value))
        elif key == 'xesam:trackNumber':
            out[key] = GLib.Variant('i', int(value))
        else:
            out[key] = GLib.Variant('s', str(value))
    return GLib.Variant('a{sv}', out)


class Mpris:
    """Start with start(); the app calls update() when the music changes and seeked() after a
    seek. Commands from D-Bus reach run(name, *args) in Tk's thread."""

    def __init__(self, root, run: Callable[..., None], position: Callable[[], Optional[float]]):
        self.root = root
        self.run = run                     # run('PlayPause') etc., in Tk's thread
        self.position = position           # seconds; called from the D-Bus thread
        self.state: Dict[str, Any] = {
            'PlaybackStatus': 'Stopped', 'LoopStatus': 'None', 'Rate': 1.0, 'Shuffle': False,
            'Metadata': {'mpris:trackid': NO_TRACK}, 'Volume': 1.0, 'MinimumRate': 1.0,
            'MaximumRate': 1.0, 'CanGoNext': False, 'CanGoPrevious': False, 'CanPlay': False,
            'CanPause': False, 'CanSeek': False, 'CanControl': True}
        self.lock = threading.Lock()
        self.connection = None             # set once the name is ours
        self._conn = None
        self.name: Optional[str] = None
        self.error: Optional[str] = None
        self._ready = threading.Event()
        self._loop = None
        self._thread: Optional[threading.Thread] = None
        self._commands: "queue.Queue[Tuple[str, tuple]]" = queue.Queue()
        self._pipe: Optional[Tuple[int, int]] = None

    # ── starting and stopping ──
    def start(self, timeout: float = 5.0) -> bool:
        problem = available()
        if problem:
            self.error = problem
            log.info("MPRIS off: %s", problem)
            return False
        import tkinter
        self._pipe = os.pipe()
        os.set_blocking(self._pipe[0], False)
        self.root.tk.createfilehandler(self._pipe[0], tkinter.READABLE, self._wake)
        self._thread = threading.Thread(target=self._serve, daemon=True, name='mpris')
        self._thread.start()
        self._ready.wait(timeout)
        if self.connection is None:
            log.info("MPRIS off: %s", self.error)
            self.stop()
            return False
        return True

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.quit()
        if self._thread is not None:
            self._thread.join(2)
        if self._conn is not None:
            try:
                self._conn.close_sync(None)           # gives up the name and the objects
            except Exception:      # noqa: BLE001
                pass
            self._conn = None
        if self._pipe is not None:
            try:
                self.root.tk.deletefilehandler(self._pipe[0])
            except Exception:      # noqa: BLE001
                pass
            for fd in self._pipe:
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._pipe = None
        self.connection = None

    def _serve(self) -> None:
        from gi.repository import Gio, GLib
        context = GLib.MainContext.new()
        context.push_thread_default()
        try:
            try:
                # a connection of our own (not the shared one), closed again in stop()
                address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
                connection = Gio.DBusConnection.new_for_address_sync(
                    address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
                    | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
            except GLib.Error as exc:
                self.error = f"no session bus ({exc.message})"
                self._ready.set()
                return
            self._conn = connection
            info = Gio.DBusNodeInfo.new_for_xml(XML)
            for iface in info.interfaces:
                connection.register_object(PATH, iface, self._call, self._get, self._set)
            self._loop = GLib.MainLoop.new(context, False)
            self.name = None
            names = [BUS_NAME, f'{BUS_NAME}.instance{os.getpid()}']

            def own(i: int) -> None:
                Gio.bus_own_name_on_connection(
                    connection, names[i], Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                    lambda _c, name: self._acquired(connection, name),
                    lambda _c, name: own(i + 1) if i + 1 < len(names) else self._lost(name))

            own(0)
            self._loop.run()
        finally:
            context.pop_thread_default()

    def _acquired(self, connection, name: str) -> None:
        self.name = name
        self.connection = connection
        log.info("MPRIS: %s", name)
        self._ready.set()

    def _lost(self, name: str) -> None:
        self.error = f"could not own {name}"
        self._ready.set()

    # ── D-Bus side (its own thread) ──
    def _call(self, _conn, _sender, _path, iface, method, params, invocation) -> None:
        args = tuple(params.unpack()) if params is not None else ()
        if iface == PLAYER_IFACE and method == 'SetPosition':
            with self.lock:
                current = self.state['Metadata'].get('mpris:trackid')
            if args[0] != current:              # the spec: ignore a stale track id
                invocation.return_value(None)
                return
        self._commands.put((method, args))
        if self._pipe is not None:
            try:
                os.write(self._pipe[1], b'x')
            except OSError:
                pass
        invocation.return_value(None)

    def _get(self, _conn, _sender, _path, iface, prop):
        from gi.repository import GLib
        if iface == ROOT_IFACE:
            fixed = {'CanQuit': ('b', True), 'CanRaise': ('b', True),
                     'HasTrackList': ('b', False), 'Identity': ('s', APP_NAME),
                     'DesktopEntry': ('s', APP_ID), 'SupportedUriSchemes': ('as', ['file']),
                     'SupportedMimeTypes': ('as', AUDIO_MIME)}
            kind, value = fixed[prop]
            return GLib.Variant(kind, value)
        if prop == 'Position':
            seconds = self.position() or 0.0
            return GLib.Variant('x', int(seconds * 1_000_000))
        with self.lock:
            value = self.state[prop]
        if prop == 'Metadata':
            return metadata_variant(value)
        return GLib.Variant(PLAYER_TYPES[prop], value)

    def _set(self, _conn, _sender, _path, iface, prop, value) -> bool:
        if iface != PLAYER_IFACE or prop not in ('LoopStatus', 'Shuffle', 'Volume', 'Rate'):
            return False
        self._commands.put(('Set' + prop, (value.unpack(),)))
        if self._pipe is not None:
            os.write(self._pipe[1], b'x')
        return True

    # ── Tk side ──
    def _wake(self, _fd, _mask) -> None:
        try:
            os.read(self._pipe[0], 4096)
        except (OSError, TypeError):
            pass
        while True:
            try:
                method, args = self._commands.get_nowait()
            except queue.Empty:
                break
            try:
                self.run(method, *args)
            except Exception:      # noqa: BLE001 - a bad call must not break the window
                log.exception("MPRIS %s failed", method)

    def update(self, changes: Dict[str, Any]) -> None:
        """New values from the window; tells D-Bus about the ones that changed."""
        changed = {}
        with self.lock:
            for key, value in changes.items():
                if self.state.get(key) != value:
                    self.state[key] = value
                    changed[key] = value
        if changed and self.connection is not None:
            from gi.repository import GLib
            props = {k: (metadata_variant(v) if k == 'Metadata'
                         else GLib.Variant(PLAYER_TYPES[k], v)) for k, v in changed.items()}
            self._emit('org.freedesktop.DBus.Properties', 'PropertiesChanged',
                       GLib.Variant('(sa{sv}as)', (PLAYER_IFACE, props, [])))

    def seeked(self, seconds: float) -> None:
        if self.connection is not None:
            from gi.repository import GLib
            self._emit(PLAYER_IFACE, 'Seeked', GLib.Variant('(x)', (int(seconds * 1_000_000),)))

    def _emit(self, iface: str, signal: str, params) -> None:
        try:
            self.connection.emit_signal(None, PATH, iface, signal, params)
        except Exception as exc:      # noqa: BLE001 - the bus went away
            log.warning("MPRIS signal %s failed: %s", signal, exc)


# ─── What the window reports ──────────────────────────────────

def art_url(cover_image, cover_file: Optional[str], key: str) -> Optional[str]:
    """A file:// URL for the cover: the cached album cover or the folder's image when there is
    one, else the song's embedded picture written to the cache once."""
    if cover_file and os.path.isfile(cover_file):
        return file_uri(cover_file)
    if cover_image is None:
        return None
    folder = os.path.join(cache_dir(), 'mpris')
    path = os.path.join(folder, hashlib.md5(key.encode('utf-8')).hexdigest() + '.jpg')
    if not os.path.isfile(path):
        try:
            os.makedirs(folder, exist_ok=True)
            old = sorted((os.path.join(folder, n) for n in os.listdir(folder)),
                         key=os.path.getmtime)
            for stale in old[:-40]:              # one file per song: keep the folder small
                os.remove(stale)
            image = cover_image.convert('RGB')
            image.thumbnail((512, 512))
            image.save(path, 'JPEG', quality=88)
        except OSError as exc:
            log.debug("no cover file for MPRIS: %s", exc)
            return None
    return file_uri(path)

