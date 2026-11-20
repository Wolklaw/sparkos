"""What the service does on the desktop: open links, show notifications, read and set the
clipboard, play a sound, and open the window when the user is needed. Over D-Bus through
GObject's Gio (in SparkOS) when it's there; otherwise the gdbus, wl-clipboard and xdg-open
commands. FakeDesktop records the same calls in a file instead, for the tests."""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

from . import APP_ID, APP_NAME, APP_SLUG

log = logging.getLogger(APP_SLUG)

ENTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'spark_link.py')
SOUNDS = ('/usr/share/sounds/ocean/stereo/phone-incoming-call.oga',
          '/usr/share/sounds/freedesktop/stereo/phone-incoming-call.oga',
          '/usr/share/sounds/freedesktop/stereo/complete.oga')


def markup_escape(text: str) -> str:
    """Plasma reads a little HTML in a notification's body: show phone text as text."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def downloads_dir() -> str:
    home = os.path.expanduser('~')
    path = ''
    cfg = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
    try:
        with open(os.path.join(cfg, 'user-dirs.dirs'), encoding='utf-8') as f:
            for line in f:
                if line.startswith('XDG_DOWNLOAD_DIR='):
                    value = line.split('=', 1)[1].strip().strip('"')
                    path = value.replace('$HOME', home)
    except OSError:
        pass
    if not path or not os.path.isabs(path) or os.path.realpath(path) == os.path.realpath(home):
        path = os.path.join(home, 'Downloads')
    os.makedirs(path, exist_ok=True)
    return path


def _spawn(cmd: List[str], stdin: Optional[bytes] = None) -> bool:
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin is not None else
                                subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        if stdin is not None:
            proc.stdin.write(stdin)
            proc.stdin.close()
        return True
    except OSError as exc:
        log.warning("couldn't run %s: %s", cmd[0], exc)
        return False


class Bus:
    """The session bus through Gio, with a GLib main loop in a thread for signals."""

    def __init__(self, system: bool = False):
        from gi.repository import Gio, GLib          # raises ImportError without GObject
        self.Gio, self.GLib = Gio, GLib
        kind = Gio.BusType.SYSTEM if system else Gio.BusType.SESSION
        self.conn = Gio.bus_get_sync(kind, None)    # raises GLib.Error without a bus
        self._loop = None

    def call(self, dest: str, path: str, iface: str, method: str, args=None, reply=None,
             timeout_ms: int = 3000):
        GLib = self.GLib
        params = GLib.Variant(args[0], tuple(args[1:])) if args else None
        rtype = GLib.VariantType.new(reply) if reply else None
        result = self.conn.call_sync(dest, path, iface, method, params, rtype,
                                     self.Gio.DBusCallFlags.NONE, timeout_ms, None)
        return result.unpack() if result is not None else None

    def subscribe(self, sender: str, iface: str, member: str, path: str,
                  callback: Callable[[], None]) -> int:
        self._ensure_loop()
        return self.conn.signal_subscribe(sender, iface, member, path, None,
                                          self.Gio.DBusSignalFlags.NONE,
                                          lambda *_a: callback())

    def unsubscribe(self, handle: int) -> None:
        self.conn.signal_unsubscribe(handle)

    def _ensure_loop(self) -> None:
        if self._loop is None:
            self._loop = self.GLib.MainLoop()
            threading.Thread(target=self._loop.run, name='glib', daemon=True).start()


def session_bus() -> Optional[Bus]:
    try:
        return Bus()
    except Exception as exc:                     # ImportError, GLib.Error
        log.info("no session bus through Gio (%s); using commands", exc)
        return None


class Desktop:
    def __init__(self):
        self.bus = session_bus()
        self.notes: Dict[str, int] = {}          # notification key -> id
        self._clip_sub: Optional[int] = None
        self._clip_poll: Optional[threading.Event] = None

    # ── links ──
    def open_url(self, url: str) -> bool:
        for cmd in ('soot', 'xdg-open'):
            exe = shutil.which(cmd)
            if exe:
                return _spawn([exe, url])
        log.warning("no soot or xdg-open to open a link")
        return False

    # ── notifications ──
    def notify(self, summary: str, body: str = '', key: Optional[str] = None,
               urgency: int = 1, app: str = APP_NAME) -> Optional[int]:
        replaces = self.notes.get(key, 0) if key else 0
        body = markup_escape(body)
        nid = None
        if self.bus:
            GLib = self.bus.GLib
            hints = {'desktop-entry': GLib.Variant('s', APP_ID),
                     'urgency': GLib.Variant('y', urgency)}
            try:
                (nid,) = self.bus.call('org.freedesktop.Notifications',
                                       '/org/freedesktop/Notifications',
                                       'org.freedesktop.Notifications', 'Notify',
                                       ('(susssasa{sv}i)', app, replaces, APP_ID, summary, body,
                                        [], hints, -1), '(u)')
            except Exception as exc:
                log.warning("notification not shown: %s", exc)
        elif shutil.which('gdbus'):
            done = subprocess.run(
                ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.Notifications',
                 '--object-path', '/org/freedesktop/Notifications', '--method',
                 'org.freedesktop.Notifications.Notify', app, str(replaces), APP_ID, summary,
                 body, '[]', "{'desktop-entry': <'%s'>}" % APP_ID, '-1'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
            text = done.stdout.decode('ascii', 'replace')
            digits = ''.join(c for c in text.split(',')[0] if c.isdigit())
            nid = int(digits) if digits else None
        if key and nid:
            self.notes[key] = nid
        return nid

    def close_notification(self, key: str) -> None:
        nid = self.notes.pop(key, None)
        if not nid:
            return
        if self.bus:
            try:
                self.bus.call('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                              'org.freedesktop.Notifications', 'CloseNotification',
                              ('(u)', nid))
            except Exception as exc:
                log.info("couldn't close a notification: %s", exc)
        elif shutil.which('gdbus'):
            subprocess.run(['gdbus', 'call', '--session', '--dest',
                            'org.freedesktop.Notifications', '--object-path',
                            '/org/freedesktop/Notifications', '--method',
                            'org.freedesktop.Notifications.CloseNotification', str(nid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)

    # ── clipboard: Plasma's Klipper over D-Bus, else wl-clipboard ──
    def _klipper(self, method: str, args=None, reply=None):
        return self.bus.call('org.kde.klipper', '/klipper', 'org.kde.klipper.klipper', method,
                             args, reply)

    def get_clipboard(self) -> Optional[str]:
        if self.bus:
            try:
                (text,) = self._klipper('getClipboardContents', reply='(s)')
                return text
            except Exception:
                pass
        if shutil.which('wl-paste') and os.environ.get('WAYLAND_DISPLAY'):
            try:
                done = subprocess.run(['wl-paste', '--no-newline', '--type', 'text'],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      timeout=3)
                if done.returncode == 0:
                    return done.stdout.decode('utf-8', 'replace')
            except (OSError, subprocess.TimeoutExpired):
                pass
        return None

    def set_clipboard(self, text: str) -> bool:
        if self.bus:
            try:
                self._klipper('setClipboardContents', ('(s)', text))
                return True
            except Exception:
                pass
        if shutil.which('wl-copy') and os.environ.get('WAYLAND_DISPLAY'):
            return _spawn(['wl-copy', '--type', 'text/plain;charset=utf-8'],
                          text.encode('utf-8'))
        log.warning("no way to set the clipboard (no Klipper, no wl-copy)")
        return False

    def watch_clipboard(self, callback: Callable[[str], None]) -> bool:
        """Call back with the new text each time the PC's clipboard changes, until
        unwatch_clipboard. Klipper's signal when it's there (no polling); else every 2 s."""
        self.unwatch_clipboard()
        if self.bus:
            try:
                self._klipper('getClipboardContents', reply='(s)')
                self._clip_sub = self.bus.subscribe(
                    'org.kde.klipper', 'org.kde.klipper.klipper', 'clipboardHistoryUpdated',
                    '/klipper', lambda: self._clip_changed(callback))
                return True
            except Exception as exc:
                log.info("Klipper not reachable (%s)", exc)
        if self.get_clipboard() is None:
            return False
        stop = threading.Event()
        self._clip_poll = stop

        def poll():
            last = self.get_clipboard()
            while not stop.wait(2.0):
                now = self.get_clipboard()
                if now is not None and now != last:
                    last = now
                    callback(now)

        threading.Thread(target=poll, name='clipboard', daemon=True).start()
        return True

    def _clip_changed(self, callback: Callable[[str], None]) -> None:
        text = self.get_clipboard()
        if text is not None:
            callback(text)

    def unwatch_clipboard(self) -> None:
        if self._clip_sub is not None and self.bus:
            self.bus.unsubscribe(self._clip_sub)
        self._clip_sub = None
        if self._clip_poll is not None:
            self._clip_poll.set()
        self._clip_poll = None

    def clipboard_backend(self) -> str:
        if self.bus:
            try:
                self._klipper('getClipboardContents', reply='(s)')
                return 'Klipper (D-Bus)'
            except Exception:
                pass
        if shutil.which('wl-paste') and shutil.which('wl-copy'):
            return 'wl-clipboard'
        return ''

    # ── sound, window ──
    def ring(self) -> None:
        for player in ('pw-play', 'paplay', 'canberra-gtk-play'):
            exe = shutil.which(player)
            sound = next((s for s in SOUNDS if os.path.isfile(s)), None)
            if exe and sound:
                _spawn([exe, '-f', sound] if player == 'canberra-gtk-play' else [exe, sound])
                return

    def show_window(self) -> None:
        exe = shutil.which(APP_SLUG)
        _spawn([exe, '--show'] if exe else [sys.executable, ENTRY, '--show'])

    def downloads(self) -> str:
        return downloads_dir()


class FakeDesktop(Desktop):
    """Records every call as a JSON line in a file (SPARK_LINK_FAKE_DESKTOP) instead of
    touching the desktop, so tests can check what a phone made the PC do."""

    def __init__(self, path: str, downloads: Optional[str] = None):
        self.path = path
        self.folder = downloads or os.environ.get('SPARK_LINK_DOWNLOADS') or None
        self.bus = None
        self.notes = {}
        self.clipboard = ''
        self._watch: Optional[Callable[[str], None]] = None
        self._count = 0
        self._lock = threading.Lock()

    def _log(self, action: str, **kw) -> None:
        with self._lock:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(dict(kw, action=action, t=time.time())) + '\n')

    def open_url(self, url):
        self._log('open_url', url=url)
        return True

    def notify(self, summary, body='', key=None, urgency=1, app=APP_NAME):
        self._count += 1
        nid = self.notes.get(key) or self._count
        if key:
            self.notes[key] = nid
        self._log('notify', summary=summary, body=markup_escape(body), key=key, id=nid)
        return nid

    def close_notification(self, key):
        nid = self.notes.pop(key, None)
        if nid:
            self._log('close_notification', key=key, id=nid)

    def get_clipboard(self):
        return self.clipboard

    def set_clipboard(self, text):
        self.clipboard = text
        self._log('set_clipboard', text=text)
        return True

    def watch_clipboard(self, callback):
        self._watch = callback
        self._log('watch_clipboard')
        return True

    def unwatch_clipboard(self):
        if self._watch:
            self._log('unwatch_clipboard')
        self._watch = None

    def local_copy(self, text: str) -> None:
        """Tests: the user copied text on the PC."""
        self.clipboard = text
        if self._watch:
            self._watch(text)

    def clipboard_backend(self):
        return 'fake'

    def ring(self):
        self._log('ring')

    def show_window(self):
        self._log('show_window')

    def downloads(self):
        if self.folder:
            os.makedirs(self.folder, exist_ok=True)
            return self.folder
        return downloads_dir()
