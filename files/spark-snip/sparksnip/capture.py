"""Reading the screen without a helper program.

Spark session: core.py runs grim (the compositor's wlr-screencopy). This module holds the
fallback, the XDG Desktop Portal's Screenshot call, which answers with a PNG file, and the
checks behind --self-test and --capture-check. It goes through PyGObject's Gio, which the
recorder already needs.
"""

import logging
import os
import secrets
import shutil
import tempfile
import time
from typing import Any, Callable, Dict, Tuple
from urllib.parse import unquote, urlparse

from PIL import Image

from . import APP_SLUG

log = logging.getLogger(APP_SLUG)

PORTAL_BUS = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
PORTAL_SCREENSHOT = 'org.freedesktop.portal.Screenshot'

CALL_TIMEOUT = 15            # seconds for the portal to accept the call
PORTAL_TIMEOUT = 60          # the portal may ask the user first

class ScreenReadError(Exception):
    """One way of reading the screen failed. The message says which and why."""


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
DESKTOPS = {      # what capture_order() sees on each kind of desktop
    'spark': {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
              'XDG_CURRENT_DESKTOP': 'sparkwl:Spark'},
    'gnome': {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
              'XDG_CURRENT_DESKTOP': 'GNOME'},
    'wlroots': {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
                'XDG_CURRENT_DESKTOP': 'sway'},
    'x11': {'XDG_SESSION_TYPE': 'x11', 'DISPLAY': ':0', 'XDG_CURRENT_DESKTOP': 'sway'},
}
ACTIONS = {'Image': 'spark-snip image', 'Text': 'spark-snip text', 'Video': 'spark-snip video'}


def orders_by_desktop() -> Dict[str, list]:
    from .core import capture_order
    keys = {'XDG_SESSION_TYPE', 'WAYLAND_DISPLAY', 'DISPLAY', 'XDG_CURRENT_DESKTOP',
            'SPARK_SNIP_CAPTURE'}
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
        path = os.path.join(base, 'applications', DESKTOP_FILE)
        if os.path.isfile(path) and path not in paths:
            paths.append(path)
    source = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          DESKTOP_FILE)
    if os.path.isfile(source):
        paths.append(source)
    return paths


def check_desktop_entry(path: str) -> Dict[str, Any]:
    """Has the three actions and carries no shortcut keys: the Spark compositor binds Print
    and Super+Shift+S/T/R itself (Spark Settings > Shortcuts)."""
    with open(path, encoding='utf-8') as f:
        lines = f.read().splitlines()
    actions: Dict[str, str] = {}
    current = ''
    for line in lines:
        if line.startswith('['):
            current = line.strip('[]').replace('Desktop Action ', '')
        elif line.startswith('Exec=') and current in ACTIONS:
            actions[current] = line.split('=', 1)[1]
    report = {'path': path, 'actions': actions,
              'has_shortcut_keys': any(line.startswith('X-') for line in lines)}
    report['passed'] = actions == ACTIONS and not report['has_shortcut_keys']
    return report


def self_check() -> Dict[str, Any]:
    """For --self-test (no display or desktop needed): the capture order in the Spark
    session starts with grim, and the desktop entry is in order. The live grim and portal
    calls need a real session; see capture_check()."""
    report: Dict[str, Any] = {}
    ok, detail = gio_ready()
    report['dbus'] = detail
    orders = orders_by_desktop()
    report['capture_order'] = orders
    report['spark_uses_grim'] = orders['spark'][:1] == ['grim']
    entries = [check_desktop_entry(path) for path in desktop_entry_paths()]
    report['desktop_entries'] = entries
    report['passed'] = ok and report['spark_uses_grim'] and all(e['passed'] for e in entries)
    return report


def capture_test(path: str) -> Dict[str, Any]:
    """spark-snip --capture-test FILE: one full-screen screenshot through grim only (no
    portal), saved as PNG. Run it in the Spark session. Fails when grim is missing or
    refuses, or sends a picture of a single colour (what a broken capture usually looks
    like; a real desktop never is one)."""
    from .core import CaptureError, _tool_screenshot
    report: Dict[str, Any] = {'method': 'grim', 'file': path}
    started = time.monotonic()
    try:
        if not shutil.which('grim'):
            raise CaptureError("grim: not installed")
        image = _tool_screenshot('grim')
    except (CaptureError, OSError) as exc:
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
        report['error'] = "grim sent a picture of a single colour"
    report['passed'] = not report['single_colour']
    return report


def capture_check(folder: str) -> Dict[str, Any]:
    """Try both capture paths on the running desktop and save what each returns, so the
    owner can check them by eye in the Spark session: spark-snip --capture-check."""
    from .core import CaptureError, _tool_screenshot
    os.makedirs(folder, exist_ok=True)
    report: Dict[str, Any] = {'folder': folder}
    attempts: Dict[str, Callable[[], Image.Image]] = {
        'grim': lambda: _tool_screenshot('grim'),
        'portal': portal_screenshot,
    }
    for name, take in attempts.items():
        started = time.monotonic()
        try:
            image = take()
            path = os.path.join(folder, f'{name}.png')
            image.save(path)
            report[name] = {'size': list(image.size), 'mode': image.mode, 'file': path,
                            'ms': round((time.monotonic() - started) * 1000)}
        except (ScreenReadError, CaptureError, OSError) as exc:
            report[name] = {'error': str(exc)}
    report['passed'] = all('error' not in report.get(name, {}) for name in attempts)
    return report
