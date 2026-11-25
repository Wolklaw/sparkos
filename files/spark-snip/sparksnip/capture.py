"""Reading the screen without a helper program.

KDE Plasma: KWin's org.kde.KWin.ScreenShot2 D-Bus interface. Spark Snip passes it one end of
a pipe; KWin answers with the image's size and pixel format, then writes the raw pixels into
the pipe from a worker thread. Plasma 6.8 lets any program on the session bus call it.
Earlier Plasma versions only allowed programs whose desktop entry lists the interface in
X-KDE-DBUS-Restricted-Interfaces, so Spark Snip's entry declares it.

Anywhere else, or when KWin refuses: the XDG Desktop Portal's Screenshot call, which answers
with a PNG file. Both go through PyGObject's Gio, which the recorder already needs.
"""

import logging
import os
import secrets
import select
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from PIL import Image

from . import APP_SLUG

log = logging.getLogger(APP_SLUG)

KWIN_BUS = 'org.kde.KWin.ScreenShot2'
KWIN_PATH = '/org/kde/KWin/ScreenShot2'
KWIN_IFACE = 'org.kde.KWin.ScreenShot2'

PORTAL_BUS = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
PORTAL_SCREENSHOT = 'org.freedesktop.portal.Screenshot'

CALL_TIMEOUT = 15            # seconds for KWin's reply, and again for the pixels
PORTAL_TIMEOUT = 60          # the portal may ask the user first

# QImage::Format -> (Pillow mode, Pillow raw mode). Qt's 32-bit "ARGB32" formats are stored
# as one native-endian integer, so on x86 and ARM the bytes run B, G, R, A. The 8888 formats
# are stored byte by byte. Lower-case "a" in a raw mode means premultiplied alpha.
QIMAGE_FORMATS: Dict[int, Tuple[str, str]] = {
    4: ('RGB', 'BGRX'),      # Format_RGB32
    5: ('RGBA', 'BGRA'),     # Format_ARGB32
    6: ('RGBA', 'BGRa'),     # Format_ARGB32_Premultiplied
    13: ('RGB', 'RGB'),      # Format_RGB888
    16: ('RGB', 'RGBX'),     # Format_RGBX8888: KWin's screen, area and workspace captures
    17: ('RGBA', 'RGBA'),    # Format_RGBA8888
    18: ('RGBA', 'RGBa'),    # Format_RGBA8888_Premultiplied: KWin's window captures
    29: ('RGB', 'BGR'),      # Format_BGR888
}


class ScreenReadError(Exception):
    """One way of reading the screen failed. The message says which and why."""


def image_from_raw(data: bytes, width: int, height: int, stride: int, fmt: int) -> Image.Image:
    """KWin's raw pixels -> a Pillow image. Rows may be padded past width * bytes per pixel."""
    if fmt not in QIMAGE_FORMATS:
        raise ScreenReadError(f"KWin sent pixel format {fmt}, which Spark Snip does not read")
    if width <= 0 or height <= 0:
        raise ScreenReadError(f"KWin sent an empty image ({width} x {height})")
    if len(data) < stride * height:
        raise ScreenReadError(f"KWin sent {len(data)} bytes, {stride * height} expected")
    mode, raw = QIMAGE_FORMATS[fmt]
    # frombytes, not frombuffer: frombuffer maps some raw modes straight onto the buffer
    # and keeps their mode (RGBX), and the bytes must not be shared anyway
    return Image.frombytes(mode, (width, height), data, 'raw', raw, stride, 1)


def _gio():
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as exc:
        raise ScreenReadError("needs PyGObject (Fedora: python3-gobject-base)") from exc
    return Gio, GLib


def session_bus():
    """A private connection to the session bus, so each capture starts clean and uses the
    current DBUS_SESSION_BUS_ADDRESS (the tests point it at their own bus)."""
    Gio, _GLib = _gio()
    try:
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        return Gio.DBusConnection.new_for_address_sync(
            address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
    except Exception as exc:                        # noqa: BLE001 - GLib.Error
        raise ScreenReadError(f"no session bus: {_dbus_message(exc)}") from exc


def _dbus_message(exc: Exception) -> str:
    """'GDBus.Error:org.x.Error.Foo: text' -> 'text (org.x.Error.Foo)'."""
    text = str(getattr(exc, 'message', '') or exc)
    if text.startswith('GDBus.Error:'):
        name, _, rest = text[len('GDBus.Error:'):].partition(': ')
        return f"{rest} ({name})" if rest else name
    return text


def _close_quietly(fd: int):
    try:
        os.close(fd)
    except OSError:
        pass


class _PipeReader(threading.Thread):
    """Reads one end of a pipe to EOF. KWin writes after it has replied, but older versions
    may write first; reading from the start means a full pipe can never stall either side."""

    def __init__(self, fd: int, deadline: float):
        super().__init__(daemon=True, name='kwin-pipe')
        self.fd, self.deadline = fd, deadline
        self.chunks = []
        self.error: Optional[str] = None

    def run(self):
        try:
            while True:
                left = self.deadline - time.monotonic()
                if left <= 0:
                    self.error = f"no pixels from KWin after {CALL_TIMEOUT * 2}s"
                    return
                ready, _, _ = select.select([self.fd], [], [], min(left, 0.5))
                if not ready:
                    continue
                chunk = os.read(self.fd, 1 << 20)
                if not chunk:
                    return
                self.chunks.append(chunk)
        except OSError as exc:
            self.error = f"reading KWin's pipe: {exc}"
        finally:
            _close_quietly(self.fd)


class KWinScreenShot:
    """org.kde.KWin.ScreenShot2. Every capture blocks until the image is in; KWin takes a few
    milliseconds, so the Tk thread may call it directly."""

    def __init__(self, bus=None):
        self.Gio, self.GLib = _gio()
        self.own_bus = bus is None
        self.bus = bus or session_bus()

    def close(self):
        if self.own_bus and self.bus is not None:
            try:
                self.bus.close_sync(None)
            except Exception:                       # noqa: BLE001 - already closed
                pass
            self.bus = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def version(self) -> int:
        GLib = self.GLib
        try:
            reply = self.bus.call_sync(KWIN_BUS, KWIN_PATH, 'org.freedesktop.DBus.Properties',
                                       'Get', GLib.Variant('(ss)', (KWIN_IFACE, 'Version')),
                                       GLib.VariantType('(v)'), self.Gio.DBusCallFlags.NONE,
                                       CALL_TIMEOUT * 1000, None)
            return int(reply.unpack()[0])
        except Exception as exc:                    # noqa: BLE001 - GLib.Error
            raise ScreenReadError(f"KWin: {_dbus_message(exc)}") from exc

    @staticmethod
    def options(cursor: bool = False, native: bool = True, **extra: bool) -> Dict[str, bool]:
        """native-resolution: full detail on scaled (HiDPI) screens, like a photo of the
        panel rather than of the logical desktop."""
        opts = {'include-cursor': cursor, 'native-resolution': native}
        opts.update({key.replace('_', '-'): value for key, value in extra.items()})
        return opts

    def _capture(self, method: str, signature: str, args: tuple,
                 options: Dict[str, bool]) -> Image.Image:
        Gio, GLib = self.Gio, self.GLib
        read_end, write_end = os.pipe()
        reader = _PipeReader(read_end, time.monotonic() + CALL_TIMEOUT * 2)
        reader.start()
        fds = Gio.UnixFDList.new()
        try:
            index = fds.append(write_end)            # the list keeps its own copy
        finally:
            _close_quietly(write_end)
        opts = {key: GLib.Variant('b', bool(value)) for key, value in options.items()}
        try:
            reply, _out = self.bus.call_with_unix_fd_list_sync(
                KWIN_BUS, KWIN_PATH, KWIN_IFACE, method,
                GLib.Variant(f'({signature}a{{sv}}h)', (*args, opts, index)),
                GLib.VariantType('(a{sv})'), Gio.DBusCallFlags.NONE, CALL_TIMEOUT * 1000,
                fds, None)
        except Exception as exc:                    # noqa: BLE001 - GLib.Error
            raise ScreenReadError(f"KWin {method}: {_dbus_message(exc)}") from exc
        finally:
            # our copy of the write end must close, or the reader never sees EOF
            for fd in fds.steal_fds():
                _close_quietly(fd)
        results: Dict[str, Any] = reply.unpack()[0]
        reader.join(CALL_TIMEOUT * 2 + 1)
        if reader.is_alive():
            raise ScreenReadError(f"KWin {method}: the pixels never arrived")
        if reader.error:
            raise ScreenReadError(f"KWin {method}: {reader.error}")
        kind = results.get('type', 'raw')
        if kind != 'raw':
            raise ScreenReadError(f"KWin {method}: unknown image type {kind!r}")
        image = image_from_raw(b''.join(reader.chunks), int(results['width']),
                               int(results['height']), int(results['stride']),
                               int(results['format']))
        log.info("KWin %s: %sx%s format=%s scale=%s", method, image.width, image.height,
                 results.get('format'), results.get('scale'))
        return image

    # what ScreenShot2 offers; Spark Snip itself uses workspace()
    def workspace(self, **opts) -> Image.Image:
        """Every monitor, as one image laid out like the desktop."""
        return self._capture('CaptureWorkspace', '', (), self.options(**opts))

    def screen(self, name: str, **opts) -> Image.Image:
        """One monitor, by connector name (DP-1, HDMI-A-1)."""
        return self._capture('CaptureScreen', 's', (name,), self.options(**opts))

    def active_screen(self, **opts) -> Image.Image:
        return self._capture('CaptureActiveScreen', '', (), self.options(**opts))

    def active_window(self, decoration: bool = True, shadow: bool = False,
                      **opts) -> Image.Image:
        return self._capture('CaptureActiveWindow', '', (), self.options(
            include_decoration=decoration, include_shadow=shadow, **opts))

    def area(self, x: int, y: int, width: int, height: int, **opts) -> Image.Image:
        """A rectangle in logical desktop coordinates."""
        return self._capture('CaptureArea', 'iiuu', (x, y, width, height), self.options(**opts))


def _temporary(path: str) -> bool:
    """Only delete the portal's file when it is clearly a scratch copy."""
    real = os.path.realpath(path)
    roots = {os.path.realpath(tempfile.gettempdir())}
    if os.environ.get('XDG_RUNTIME_DIR'):
        roots.add(os.path.realpath(os.environ['XDG_RUNTIME_DIR']))
    return any(real.startswith(root + os.sep) for root in roots)


def portal_screenshot(bus=None, timeout: float = PORTAL_TIMEOUT,
                      cancelled: Callable[[], bool] = lambda: False) -> Image.Image:
    """org.freedesktop.portal.Screenshot, without its dialog. Blocks until the portal answers."""
    Gio, GLib = _gio()
    own = bus is None
    bus = bus or session_bus()
    sender = bus.get_unique_name()[1:].replace('.', '_')
    token = 'sparksnip_' + secrets.token_hex(6)
    request = f'{PORTAL_PATH}/request/{sender}/{token}'
    context = GLib.MainContext.new()
    context.push_thread_default()
    box: Dict[str, Any] = {}

    def on_response(_conn, _sender, _path, _iface, _signal, params, *_):
        box['response'] = params.unpack()

    try:
        sub = bus.signal_subscribe(PORTAL_BUS, 'org.freedesktop.portal.Request', 'Response',
                                   request, None, Gio.DBusSignalFlags.NONE, on_response)
        try:
            bus.call_sync(PORTAL_BUS, PORTAL_PATH, PORTAL_SCREENSHOT, 'Screenshot',
                          GLib.Variant('(sa{sv})', ('', {
                              'handle_token': GLib.Variant('s', token),
                              'interactive': GLib.Variant('b', False),
                              'modal': GLib.Variant('b', False)})),
                          GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE,
                          CALL_TIMEOUT * 1000, None)
            deadline = time.monotonic() + timeout
            while 'response' not in box:
                if cancelled():
                    raise ScreenReadError("portal: cancelled")
                if time.monotonic() > deadline:
                    raise ScreenReadError(f"portal: no answer after {int(timeout)}s")
                if not context.iteration(False):
                    time.sleep(0.02)
        finally:
            bus.signal_unsubscribe(sub)
    except ScreenReadError:
        raise
    except Exception as exc:                        # noqa: BLE001 - GLib.Error
        raise ScreenReadError(f"portal: {_dbus_message(exc)}") from exc
    finally:
        context.pop_thread_default()
        if own:
            try:
                bus.close_sync(None)
            except Exception:                       # noqa: BLE001
                pass
    code, results = box['response']
    if code == 1:
        raise ScreenReadError("portal: the screenshot was declined")
    if code != 0 or 'uri' not in results:
        raise ScreenReadError("portal: the screenshot failed")
    uri = urlparse(str(results['uri']))
    if uri.scheme != 'file':
        raise ScreenReadError(f"portal: unexpected answer {results['uri']!r}")
    path = unquote(uri.path)
    try:
        with Image.open(path) as img:
            img.load()
            image = img.convert('RGB')
    except OSError as exc:
        raise ScreenReadError(f"portal: could not open {path}: {exc}") from exc
    if _temporary(path):
        _remove_quietly(path)
    log.info("portal screenshot %sx%s from %s", image.width, image.height, path)
    return image


def _remove_quietly(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


def kwin_screenshot_offered(bus=None) -> bool:
    """Is org.kde.KWin.ScreenShot2 on the session bus (running) or startable from a service
    file? That is true in a Plasma session and in a session that runs KWin alone."""
    Gio, GLib = _gio()
    own = bus is None
    bus = bus or session_bus()
    try:
        def ask(method: str, args, reply: str):
            return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                 'org.freedesktop.DBus', method, args, GLib.VariantType(reply),
                                 Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        try:
            if ask('NameHasOwner', GLib.Variant('(s)', (KWIN_BUS,)), '(b)'):
                return True
            return KWIN_BUS in ask('ListActivatableNames', None, '(as)')
        except GLib.Error as exc:
            log.info("asking the bus about KWin failed: %s", _dbus_message(exc))
            return False
    finally:
        if own:
            _close_quietly_bus(bus)


def _close_quietly_bus(bus):
    try:
        bus.close_sync(None)
    except Exception:                               # noqa: BLE001
        pass


def gio_ready() -> Tuple[bool, str]:
    """For --self-test: can this Python talk D-Bus and pass file descriptors?"""
    try:
        Gio, _GLib = _gio()
        Gio.UnixFDList.new()
        return True, "PyGObject Gio with Unix fd passing"
    except Exception as exc:                        # noqa: BLE001
        return False, str(exc)


# ─── Checks ───────────────────────────────────────────────────

DESKTOP_FILE = 'dev.wolklaw.SparkSnip.desktop'
RESTRICTED_KEY = 'X-KDE-DBUS-Restricted-Interfaces'
DESKTOPS = {      # what capture_order() sees on each kind of desktop
    'plasma': {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
               'XDG_CURRENT_DESKTOP': 'KDE'},
    'gnome': {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
              'XDG_CURRENT_DESKTOP': 'GNOME'},
    'wlroots': {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
                'XDG_CURRENT_DESKTOP': 'sway'},
    'x11': {'XDG_SESSION_TYPE': 'x11', 'DISPLAY': ':0', 'XDG_CURRENT_DESKTOP': 'KDE'},
    # KWin alone, no plasmashell, and not called KDE: the order depends on the bus
    'spark': {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
              'XDG_CURRENT_DESKTOP': 'Spark', 'SPARK_SNIP_KWIN': '1'},
}


def orders_by_desktop() -> Dict[str, list]:
    from .core import capture_order
    keys = {'XDG_SESSION_TYPE', 'WAYLAND_DISPLAY', 'DISPLAY', 'XDG_CURRENT_DESKTOP',
            'SPARK_SNIP_CAPTURE', 'SPARK_SNIP_KWIN'}
    saved = {key: os.environ.get(key) for key in keys}
    orders = {}
    try:
        for name, env in DESKTOPS.items():
            for key in keys:
                os.environ.pop(key, None)
            os.environ.update(env)
            orders[name] = capture_order()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return orders


def desktop_entry_paths() -> list:
    data_dirs = [os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')]
    data_dirs += (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':')
    paths = []
    for base in data_dirs:
        for sub in ('applications', 'kglobalaccel'):
            path = os.path.join(base, sub, DESKTOP_FILE)
            if os.path.isfile(path) and path not in paths:
                paths.append(path)
    source = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          DESKTOP_FILE)
    if os.path.isfile(source):
        paths.append(source)
    return paths


def check_desktop_entry(path: str) -> Dict[str, Any]:
    """Declares the KWin interface, owns the four keys, and never mentions Spectacle."""
    with open(path, encoding='utf-8') as f:
        text = f.read()
    keys = []
    restricted = []
    for line in text.splitlines():
        if line.startswith('X-KDE-Shortcuts='):
            keys += [k for k in line.split('=', 1)[1].split(',') if k]
        if line.startswith(RESTRICTED_KEY + '='):
            restricted += line.split('=', 1)[1].split(',')
    report = {'path': path, 'shortcuts': keys, 'restricted_interfaces': restricted,
              'mentions_spectacle': 'spectacle' in text.lower()}
    report['passed'] = (KWIN_IFACE in restricted and not report['mentions_spectacle']
                        and {'Print', 'Meta+Shift+S', 'Meta+Shift+T', 'Meta+Shift+R'} <= set(keys))
    return report


def self_check() -> Dict[str, Any]:
    """For --self-test (no display or desktop needed): Spark Snip can read the screen on
    Plasma without Spectacle. The live KWin and portal calls need a real session; see
    capture_check()."""
    import shutil
    report: Dict[str, Any] = {}
    ok, detail = gio_ready()
    report['dbus'] = detail
    try:       # Pillow decodes the formats KWin sends: RGBX and premultiplied RGBA
        rgbx = image_from_raw(bytes([10, 20, 30, 255, 40, 50, 60, 255, 0, 0, 0, 0]) * 2,
                              2, 2, 12, 16)
        rgba = image_from_raw(bytes([50, 25, 0, 128]), 1, 1, 4, 18)
        red, green = rgba.getpixel((0, 0))[:2]           # 50 and 25 at half opacity
        report['raw_decode'] = (rgbx.getpixel((1, 1)) == (40, 50, 60)
                                and abs(red - 100) <= 1 and abs(green - 50) <= 1)
    except Exception as exc:                        # noqa: BLE001
        report['raw_decode'] = f"failed: {exc}"
    orders = orders_by_desktop()
    report['capture_order'] = orders
    # Spectacle may be tried after a built-in method, but never in place of one
    report['spectacle_required'] = any(
        'spectacle' in order and not set(order[:order.index('spectacle')]) & {'kwin', 'portal'}
        for order in orders.values())
    report['plasma_uses_kwin'] = orders['plasma'][:1] == ['kwin']
    # a session with KWin and no plasmashell, named something else, still reads through KWin
    report['spark_uses_kwin'] = orders['spark'][:1] == ['kwin']
    report['spectacle_installed'] = bool(shutil.which('spectacle'))     # just for the record
    entries = [check_desktop_entry(path) for path in desktop_entry_paths()]
    report['desktop_entries'] = entries
    report['passed'] = (ok and report['raw_decode'] is True and not report['spectacle_required']
                        and report['plasma_uses_kwin'] and report['spark_uses_kwin']
                        and all(e['passed'] for e in entries))
    return report


def capture_test(path: str) -> Dict[str, Any]:
    """spark-snip --capture-test FILE: one full-screen screenshot through KWin only (no
    portal, no Spectacle), saved as PNG. For the boot test, run in the user's Plasma session.
    Fails when KWin refuses, sends nothing usable, or sends a picture of a single colour
    (what a broken capture usually looks like; a real desktop never is one)."""
    report: Dict[str, Any] = {'method': 'kwin CaptureWorkspace', 'file': path}
    started = time.monotonic()
    try:
        with KWinScreenShot() as kwin:
            try:
                report['kwin_version'] = kwin.version()
            except ScreenReadError as exc:
                report['kwin_version'] = str(exc)
            image = kwin.workspace().convert('RGB')
    except ScreenReadError as exc:
        report['error'] = str(exc)
        report['passed'] = False
        return report
    report['ms'] = round((time.monotonic() - started) * 1000)
    report['size'] = list(image.size)
    report['single_colour'] = all(low == high for low, high in image.getextrema())
    try:
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        image.save(path, 'PNG')
    except (OSError, ValueError) as exc:
        report['error'] = f"could not save {path}: {exc}"
        report['passed'] = False
        return report
    if report['single_colour']:
        report['error'] = "KWin sent a picture of a single colour"
    report['passed'] = not report['single_colour']
    return report


def capture_check(folder: str) -> Dict[str, Any]:
    """Try every capture path on the running desktop and save what each returns, so the
    owner can check them by eye on a real Plasma session: spark-snip --capture-check."""
    os.makedirs(folder, exist_ok=True)
    report: Dict[str, Any] = {'folder': folder}
    attempts: Dict[str, Callable[[], Image.Image]] = {}
    try:
        kwin = KWinScreenShot()
    except ScreenReadError as exc:
        report['kwin'] = {'error': str(exc)}
        kwin = None
    if kwin is not None:
        try:
            report['kwin_version'] = kwin.version()
        except ScreenReadError as exc:
            report['kwin_version'] = str(exc)
        attempts.update({
            'kwin-workspace': kwin.workspace,
            'kwin-active-screen': kwin.active_screen,
            'kwin-active-window': kwin.active_window,
            'kwin-area': lambda: kwin.area(0, 0, 400, 300),
        })
    attempts['portal'] = portal_screenshot
    for name, take in attempts.items():
        started = time.monotonic()
        try:
            image = take()
            path = os.path.join(folder, f'{name}.png')
            image.save(path)
            report[name] = {'size': list(image.size), 'mode': image.mode, 'file': path,
                            'ms': round((time.monotonic() - started) * 1000)}
        except ScreenReadError as exc:
            report[name] = {'error': str(exc)}
    if kwin is not None:
        kwin.close()
    report['passed'] = all('error' not in report.get(name, {}) for name in attempts)
    return report
