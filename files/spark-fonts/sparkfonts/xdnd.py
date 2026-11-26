"""Drag and drop with other windows, which Tk doesn't do by itself: the XDND protocol
(version 5), the one every X11 and XWayland app speaks; the compositor's XWayland carries it to and from Wayland
apps.

Receiving: Tk gets the XDND client messages on its own windows; a generic event handler
registered in Tk's C library copies them out (it must not call back into Tcl), and they're
handled on the next turn of Tk's loop. The dropped data is read with Tk's own `selection get`.

Sending: when a drag started in Spark Files leaves its windows, Spark Files owns the
XdndSelection (Tk's `selection own`) and sends XDND messages to the window under the pointer
through a second, small X connection made with libX11 (ctypes).

If any of it can't be set up (no X11, Tk built differently), drag and drop stays inside Spark
Files and nothing else changes."""

import collections
import ctypes
import ctypes.util
import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote, unquote, urlparse

from .core import log

CLIENT_MESSAGE = 33
XDND_VERSION = 5
URI_LIST = 'text/uri-list'


def uris_to_paths(text: str) -> List[str]:
    out = []
    for line in text.replace('\r\n', '\n').split('\n'):
        line = line.strip().strip('\0')
        if not line or line.startswith('#'):
            continue
        if line.startswith('file://'):
            parsed = urlparse(line)
            if parsed.netloc not in ('', 'localhost', os.uname().nodename):
                continue
            out.append(unquote(parsed.path))
        elif line.startswith('/'):
            out.append(line)
    return out


def paths_to_uris(paths: Sequence[str]) -> str:
    return ''.join('file://' + quote(p, safe="/!$&'()*+,;=:@~-._") + '\r\n' for p in paths)


class _XAny(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong),
                ('send_event', ctypes.c_int), ('display', ctypes.c_void_p),
                ('window', ctypes.c_ulong)]


class _XClient(ctypes.Structure):
    _fields_ = _XAny._fields_ + [('message_type', ctypes.c_ulong), ('format', ctypes.c_int),
                                 ('l', ctypes.c_long * 5)]


class _XEvent(ctypes.Union):
    _fields_ = [('type', ctypes.c_int), ('any', _XAny), ('xclient', _XClient),
                ('pad', ctypes.c_long * 24)]


_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(_XEvent))


def _tk_library() -> Optional[str]:
    try:
        with open('/proc/self/maps', encoding='utf-8', errors='replace') as f:
            for line in f:
                path = line.split()[-1]
                name = os.path.basename(path)
                if path.startswith('/') and name.startswith(('libtk', 'libtcl9tk')) \
                        and '.so' in name:
                    return path
    except OSError:
        pass
    return None


class XDnd:
    """on_over(x_root, y_root, action) -> bool (would a drop be taken there?);
    on_leave(); on_drop(paths, action, x_root, y_root). Actions: 'copy', 'move', 'link',
    'ask'."""

    def __init__(self, root, on_over: Callable[[int, int, str], bool],
                 on_leave: Callable[[], None],
                 on_drop: Callable[[List[str], str, int, int], None]):
        self.root = root
        self.on_over, self.on_leave, self.on_drop = on_over, on_leave, on_drop
        self.ok = False
        self._events: 'collections.deque' = collections.deque()
        self._x = None
        self._dpy = None
        self._handler = None
        self._atoms: Dict[str, int] = {}
        self._names: Dict[int, str] = {}
        self._own_windows: set = set()
        # receiving
        self._source = 0
        self._target = 0
        self._accept = False
        self._pos = (0, 0)
        self._action = 'copy'
        # sending
        self.drag_paths: List[str] = []
        self.drag_target = 0
        self._send_to = 0
        self.drag_target_version = XDND_VERSION
        self.drag_accepted = False
        self.drag_source_window = 0
        self._waiting_status = False
        self._pending_pos: Optional[Tuple[int, int, str]] = None
        self._r = self._w = -1
        if os.environ.get('SPARK_FONTS_NO_XDND'):
            return
        try:
            self._setup()
            self.ok = True
        except Exception as exc:                          # noqa: BLE001
            log.info("drag and drop with other apps is off: %s", exc)

    # ─── set-up ──────────────────────────────────────────────

    def _setup(self) -> None:
        if self.root.tk.call('tk', 'windowingsystem') != 'x11':
            raise RuntimeError('not X11')
        x = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetAtomName.restype = ctypes.c_void_p
        x.XGetAtomName.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long,
                                 ctypes.POINTER(_XEvent)]
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                      ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_void_p, ctypes.c_int]
        x.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
            ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong)]
        x.XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]
        x.XSetErrorHandler.restype = ctypes.c_void_p
        display = os.environ.get('DISPLAY', '')
        try:
            display = self.root.winfo_screen() or display
        except Exception:                                 # noqa: BLE001
            pass
        dpy = x.XOpenDisplay(display.encode() if display else None)
        if not dpy:
            raise RuntimeError(f'cannot open display {display!r}')
        self._x, self._dpy = x, dpy
        # a window that's gone between our query and our message must not kill the app
        self._err = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(
            lambda _d, _e: 0)
        x.XSetErrorHandler(self._err)
        for name in ('XdndAware', 'XdndProxy', 'XdndEnter', 'XdndPosition', 'XdndStatus',
                     'XdndLeave', 'XdndDrop', 'XdndFinished', 'XdndSelection',
                     'XdndActionCopy', 'XdndActionMove', 'XdndActionLink', 'XdndActionAsk',
                     'XdndActionPrivate', 'XdndTypeList', URI_LIST, 'UTF8_STRING',
                     'text/plain;charset=utf-8', 'ATOM', 'WM_STATE'):
            atom = x.XInternAtom(dpy, name.encode(), 0)
            self._atoms[name] = atom
            self._names[atom] = name
        lib = _tk_library()
        if not lib:
            raise RuntimeError("Tk's library not found")
        tk_lib = ctypes.CDLL(lib)
        tk_lib.Tk_CreateGenericHandler.argtypes = [_HANDLER, ctypes.c_void_p]
        self._handler = _HANDLER(self._generic)
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)
        os.set_blocking(self._w, False)
        import tkinter
        self.root.tk.createfilehandler(self._r, tkinter.READABLE, self._drain)
        tk_lib.Tk_CreateGenericHandler(self._handler, None)
        self._tk_lib = tk_lib
        self._xdnd_types = {self._atoms[n] for n in ('XdndEnter', 'XdndPosition', 'XdndStatus',
                                                     'XdndLeave', 'XdndDrop', 'XdndFinished')}

    def close(self) -> None:
        if self._handler is not None:
            try:
                self._tk_lib.Tk_DeleteGenericHandler.argtypes = [_HANDLER, ctypes.c_void_p]
                self._tk_lib.Tk_DeleteGenericHandler(self._handler, None)
            except Exception:                             # noqa: BLE001
                pass
        if self._r >= 0:
            try:
                self.root.tk.deletefilehandler(self._r)
            except Exception:                             # noqa: BLE001
                pass
            for fd in (self._r, self._w):
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._r = self._w = -1
        self.ok = False

    def register(self, toplevel) -> None:
        """Mark a window as a drop target (call once it's mapped)."""
        if not self.ok:
            return
        try:
            toplevel.update_idletasks()
            wid = int(toplevel.wm_frame(), 16)
        except Exception:                                 # noqa: BLE001
            return
        version = ctypes.c_ulong(XDND_VERSION)
        self._x.XChangeProperty(self._dpy, wid, self._atoms['XdndAware'], 4, 32, 0,
                                ctypes.byref(version), 1)       # 4 = XA_ATOM, 0 = Replace
        self._x.XFlush(self._dpy)
        self._own_windows.add(wid)

    def unregister(self, toplevel) -> None:
        try:
            self._own_windows.discard(int(toplevel.wm_frame(), 16))
        except Exception:                                 # noqa: BLE001
            pass

    # ─── events from Tk's C side ─────────────────────────────

    def _generic(self, _cd, event_p) -> int:
        """Runs inside Tk's event processing: copy, wake the loop, never touch Tcl."""
        try:
            ev = event_p.contents
            if ev.type == CLIENT_MESSAGE and ev.xclient.message_type in self._xdnd_types:
                c = ev.xclient
                self._events.append((c.window, c.message_type, tuple(c.l)))
                try:
                    os.write(self._w, b'x')
                except OSError:
                    pass
        except Exception:                                 # noqa: BLE001
            pass
        return 0

    def _drain(self, _fd, _mask) -> None:
        try:
            while os.read(self._r, 4096):
                pass
        except (BlockingIOError, OSError):
            pass
        while self._events:
            window, kind, data = self._events.popleft()
            try:
                self._handle(window, self._names.get(kind, ''), data)
            except Exception:                             # noqa: BLE001
                log.exception("xdnd message")

    def _handle(self, window: int, kind: str, data: Tuple[int, ...]) -> None:
        if kind == 'XdndEnter':
            self._source, self._target = data[0], window
            version = (data[1] >> 24) & 0xff
            if data[1] & 1:
                types = self._type_list(data[0])
            else:
                types = [t for t in data[2:5] if t]
            self._accept = self._atoms[URI_LIST] in types and version >= 3
            if data[0] in self._own_windows:
                self._accept = False                       # our own drag: handled inside
        elif kind == 'XdndPosition':
            if data[0] != self._source:
                return
            x, y = (data[2] >> 16) & 0xffff, data[2] & 0xffff
            self._pos = (x, y)
            self._action = self._action_name(data[4])
            ok = self._accept and self.on_over(x, y, self._action)
            reply = self._atoms['XdndActionCopy']
            if self._action == 'move':
                reply = self._atoms['XdndActionMove']
            self._send(self._source, 'XdndStatus',
                       (window, (1 if ok else 0) | 2, 0, 0, reply if ok else 0))
        elif kind == 'XdndLeave':
            if data[0] == self._source:
                self._source = 0
                self.on_leave()
        elif kind == 'XdndDrop':
            if data[0] != self._source:
                return
            source = self._source
            self._source = 0
            paths: List[str] = []
            if self._accept:
                try:
                    text = self.root.tk.call('selection', 'get', '-displayof', self.root,
                                             '-selection', 'XdndSelection', '-type', URI_LIST)
                    paths = uris_to_paths(str(text))
                except Exception as exc:                  # noqa: BLE001
                    log.info("dropped data unreadable: %s", exc)
            done = self._atoms['XdndActionCopy'] if paths else 0
            self._send(source, 'XdndFinished', (window, 1 if paths else 0, done, 0, 0))
            self.on_leave()
            if paths:
                x, y = self._pos
                self.on_drop(paths, self._action, x, y)
        elif kind == 'XdndStatus':
            if data[0] == self.drag_target:
                self.drag_accepted = bool(data[1] & 1)
                self._waiting_status = False
                if self._pending_pos is not None:
                    x, y, action = self._pending_pos
                    self._pending_pos = None
                    self.drag_motion(x, y, action)
        elif kind == 'XdndFinished':
            if data[0] == self.drag_target or not self.drag_target:
                self._drag_reset()

    def _action_name(self, atom: int) -> str:
        return {'XdndActionMove': 'move', 'XdndActionLink': 'link',
                'XdndActionAsk': 'ask'}.get(self._names.get(atom, ''), 'copy')

    def _type_list(self, window: int) -> List[int]:
        actual_type, actual_format = ctypes.c_ulong(), ctypes.c_int()
        n, after, prop = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        status = self._x.XGetWindowProperty(
            self._dpy, window, self._atoms['XdndTypeList'], 0, 1024, 0, 4,
            ctypes.byref(actual_type), ctypes.byref(actual_format), ctypes.byref(n),
            ctypes.byref(after), ctypes.byref(prop))
        out: List[int] = []
        if status == 0 and prop.value:
            if actual_format.value == 32:
                arr = ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))
                out = [arr[i] for i in range(n.value)]
            self._x.XFree(prop)
        return out

    def _send(self, window: int, kind: str, data: Sequence[int]) -> None:
        ev = _XEvent()
        ev.xclient.type = CLIENT_MESSAGE
        ev.xclient.window = window
        ev.xclient.message_type = self._atoms[kind]
        ev.xclient.format = 32
        for i, value in enumerate(data):
            ev.xclient.l[i] = value
        self._x.XSendEvent(self._dpy, window, 0, 0, ctypes.byref(ev))
        self._x.XFlush(self._dpy)

    # ─── dragging out ────────────────────────────────────────

    def drag_start(self, widget, paths: Sequence[str]) -> bool:
        """Call when an internal drag leaves Spark Files' windows."""
        if not self.ok or not paths:
            return False
        self.drag_paths = list(paths)
        data = paths_to_uris(self.drag_paths)
        plain = '\n'.join(self.drag_paths)
        top = widget.winfo_toplevel()
        try:
            self.drag_source_window = int(top.wm_frame(), 16)
        except Exception:                                 # noqa: BLE001
            return False

        def provide(text):
            def handler(offset, length):
                offset, length = int(offset), int(length)
                return text[offset:offset + length]
            return handler

        try:
            for kind, text in ((URI_LIST, data), ('UTF8_STRING', plain),
                               ('text/plain;charset=utf-8', plain), ('STRING', plain)):
                cmd = top.register(provide(text))
                top.tk.call('selection', 'handle', '-selection', 'XdndSelection', '-type',
                            kind, top, cmd)
            top.tk.call('selection', 'own', '-selection', 'XdndSelection', top)
        except Exception as exc:                          # noqa: BLE001
            log.info("could not start dragging out: %s", exc)
            return False
        self.drag_target = 0
        self.drag_accepted = False
        return True

    @property
    def dragging_out(self) -> bool:
        return bool(self.drag_paths)

    def _window_under(self, x: int, y: int) -> Tuple[int, int, int]:
        """(XDND-aware window at x, y on the screen, where to send to, its version): the
        topmost window there, then down through its children until one is XDND-aware."""
        root = self._x.XDefaultRootWindow(self._dpy)
        window = root
        for _ in range(8):
            child = ctypes.c_ulong()
            wx, wy = ctypes.c_int(), ctypes.c_int()
            ok = self._x.XTranslateCoordinates(self._dpy, root, window, x, y, ctypes.byref(wx),
                                               ctypes.byref(wy), ctypes.byref(child))
            if not ok or not child.value:
                return 0, 0, 0
            window = child.value
            version = self._aware(window)
            if version:
                proxy = self._proxy(window)
                return window, proxy or window, version
        return 0, 0, 0

    def _prop_ulong(self, window: int, name: str) -> Optional[int]:
        actual_type, actual_format = ctypes.c_ulong(), ctypes.c_int()
        n, after, prop = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        status = self._x.XGetWindowProperty(
            self._dpy, window, self._atoms[name], 0, 1, 0, 0, ctypes.byref(actual_type),
            ctypes.byref(actual_format), ctypes.byref(n), ctypes.byref(after),
            ctypes.byref(prop))
        value = None
        if status == 0 and prop.value:
            if n.value >= 1 and actual_format.value == 32:
                value = ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))[0]
            self._x.XFree(prop)
        return value

    def _aware(self, window: int) -> int:
        return self._prop_ulong(window, 'XdndAware') or 0

    def _proxy(self, window: int) -> int:
        return self._prop_ulong(window, 'XdndProxy') or 0

    def drag_motion(self, x: int, y: int, action: str = 'copy') -> None:
        if not self.drag_paths:
            return
        window, send_to, version = self._window_under(x, y)
        if window in self._own_windows:
            window = send_to = 0
        if window != self.drag_target:
            if self.drag_target:
                self._send(self._send_to, 'XdndLeave', (self.drag_source_window, 0, 0, 0, 0))
            self.drag_target, self._send_to = window, send_to
            self.drag_target_version = min(version, XDND_VERSION)
            self.drag_accepted = False
            self._waiting_status = False
            self._pending_pos = None
            if window:
                types = [self._atoms[URI_LIST], self._atoms['UTF8_STRING'],
                         self._atoms['text/plain;charset=utf-8']]
                self._send(send_to, 'XdndEnter', (self.drag_source_window,
                                                  self.drag_target_version << 24, *types))
        if not self.drag_target:
            return
        if self._waiting_status:
            self._pending_pos = (x, y, action)
            return
        atom = self._atoms['XdndActionMove' if action == 'move' else 'XdndActionCopy']
        self._send(self._send_to, 'XdndPosition',
                   (self.drag_source_window, 0, (x << 16) | (y & 0xffff), 0, atom))
        self._waiting_status = True

    def drag_drop(self) -> bool:
        """The button was released outside Spark Files. True if a window took the drop."""
        if not self.drag_paths:
            return False
        dropped = False
        if self.drag_target and self.drag_accepted:
            self._send(self._send_to, 'XdndDrop', (self.drag_source_window, 0, 0, 0, 0))
            dropped = True
            # keep the selection until XdndFinished arrives, or give up after a while
            self.root.after(15000, self._drag_reset)
        else:
            if self.drag_target:
                self._send(self._send_to, 'XdndLeave', (self.drag_source_window, 0, 0, 0, 0))
            self._drag_reset()
        return dropped

    def drag_cancel(self) -> None:
        if self.drag_target:
            self._send(self._send_to, 'XdndLeave', (self.drag_source_window, 0, 0, 0, 0))
        self._drag_reset()

    def _drag_reset(self) -> None:
        self.drag_paths = []
        self.drag_target = 0
        self.drag_accepted = False
        self._waiting_status = False
        self._pending_pos = None
