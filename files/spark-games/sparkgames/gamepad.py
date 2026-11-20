"""Gamepads, read straight from the kernel's evdev devices with the standard library only.

  /sys/class/input/event<N>/device/capabilities/key   which buttons a device has; a gamepad has
                                                      BTN_SOUTH (the A / cross button)
  /dev/input/event<N>                                 its events, 24 bytes each: time, type,
                                                      code, value (the logged-in user can read
                                                      game controllers on SparkOS: udev's uaccess)

Nothing polls. While the window has focus, each gamepad's file and an inotify watch on
/dev/input are handed to Tk's event loop (createfilehandler), so Spark Games wakes only when a
button moves or a controller is plugged in. When the window loses focus every file is closed:
no wake-ups while a game runs, and no button presses meant for the game reach the library.
Devices are never grabbed, so other programs keep seeing them.

What the buttons do (names follow the Xbox layout; PlayStation and Nintendo pads report the
same positions):

  D-pad, left stick   move (held: repeats)      A   play / choose     B       back
  Y (and X)           search                    Start  game page      Guide   big screen
  LB / RB             previous / next store filter
"""

import ctypes
import ctypes.util
import os
import struct
import sys
from typing import Callable, Dict, List, Optional, Tuple

from .core import log

try:
    import fcntl
except ImportError:                       # Windows dev runs only: no gamepads
    fcntl = None  # type: ignore[assignment]

SYS_INPUT = '/sys/class/input'
DEV_INPUT = '/dev/input'

EVENT = struct.Struct('llHHi')           # struct input_event: timeval, type, code, value
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_DROPPED = 3

# buttons (linux/input-event-codes.h)
BTN_SOUTH, BTN_EAST, BTN_C, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x132, 0x133, 0x134
BTN_TL, BTN_TR = 0x136, 0x137
BTN_SELECT, BTN_START, BTN_MODE = 0x13a, 0x13b, 0x13c
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = 0x220, 0x221, 0x222, 0x223
ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y = 0x00, 0x01, 0x10, 0x11

# Xbox pads (xpad) report X as BTN_NORTH and Y as BTN_WEST; PlayStation pads report triangle
# as BTN_NORTH and square as BTN_WEST. Both mean "search", so either layout finds it.
BUTTONS: Dict[int, str] = {
    BTN_SOUTH: 'a', BTN_EAST: 'b', BTN_NORTH: 'y', BTN_WEST: 'y',
    BTN_START: 'start', BTN_MODE: 'guide', BTN_SELECT: 'select',
    BTN_TL: 'lb', BTN_TR: 'rb',
}
DPAD_BUTTONS = {BTN_DPAD_UP: 'up', BTN_DPAD_DOWN: 'down', BTN_DPAD_LEFT: 'left',
                BTN_DPAD_RIGHT: 'right'}
DIRECTIONS = ('up', 'down', 'left', 'right')

PRESS_AT = 0.55           # stick deflection that counts as a press (of the full range)
RELEASE_AT = 0.35         # ... and as a release (lower, so a stick at the edge doesn't flicker)
REPEAT_DELAY = 0.40       # seconds a direction is held before it repeats
REPEAT_EVERY = 0.11

# inotify (linux/inotify.h)
IN_ATTRIB, IN_CREATE, IN_DELETE = 0x4, 0x100, 0x200
IN_NONBLOCK, IN_CLOEXEC = 0o4000, 0o2000000

# EVIOCGABS(abs) = _IOR('E', 0x40 + abs, struct input_absinfo): value, min, max, fuzz, flat, res
ABSINFO = struct.Struct('6i')


def _eviocgabs(axis: int) -> int:
    return (2 << 30) | (ABSINFO.size << 16) | (ord('E') << 8) | (0x40 + axis)


# ─── Which devices are gamepads ───────────────────────────────

def _bits(text: str) -> set:
    """A sysfs capability bitmap ("7cdb0000 0 0 0 0", highest word first) as a set of bits."""
    word = struct.calcsize('l') * 8
    out = set()
    for i, chunk in enumerate(reversed(text.split())):
        try:
            value = int(chunk, 16)
        except ValueError:
            return set()
        bit = 0
        while value:
            if value & 1:
                out.add(i * word + bit)
            value >>= 1
            bit += 1
    return out


def _read(path: str) -> str:
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read().strip()
    except OSError:
        return ''


class Pad:
    def __init__(self, node: str, name: str, vendor: str):
        self.node, self.name, self.vendor = node, name, vendor

    def __repr__(self) -> str:
        return f'Pad({self.node!r}, {self.name!r})'


def find_pads(sys_root: str = SYS_INPUT, dev_root: str = DEV_INPUT) -> List[Pad]:
    """Every gamepad: an event device whose buttons include BTN_SOUTH."""
    try:
        names = sorted(n for n in os.listdir(dev_root) if n.startswith('event'))
    except OSError:
        return []
    pads = []
    for name in names:
        device = os.path.join(sys_root, name, 'device')
        if BTN_SOUTH not in _bits(_read(os.path.join(device, 'capabilities', 'key'))):
            continue
        pads.append(Pad(os.path.join(dev_root, name), _read(os.path.join(device, 'name')),
                        _read(os.path.join(device, 'id', 'vendor'))))
    return pads


# ─── Events to actions ────────────────────────────────────────

class Decoder:
    """Turns one pad's raw events into actions: ('press', name) and ('release', name).
    Directions come from the D-pad (a hat or four buttons) and the left stick."""

    def __init__(self, ranges: Optional[Dict[int, Tuple[int, int]]] = None):
        # axis -> (min, max); a pad whose ranges can't be read is assumed to be xpad's
        self.ranges = ranges or {}
        self.held: Dict[str, set] = {d: set() for d in DIRECTIONS}   # direction -> sources

    def _axis(self, axis: int, value: int) -> float:
        lo, hi = self.ranges.get(axis, (-32768, 32767))
        if hi <= lo:
            return 0.0
        return max(-1.0, min(1.0, (value - lo) * 2.0 / (hi - lo) - 1.0))

    def _set(self, direction: str, source: str, on: bool, out: List[Tuple[str, str]]):
        sources = self.held[direction]
        was = bool(sources)
        if on:
            sources.add(source)
        else:
            sources.discard(source)
        if bool(sources) != was:
            out.append(('press' if sources else 'release', direction))

    def feed(self, ev_type: int, code: int, value: int) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        if ev_type == EV_KEY:
            if code in DPAD_BUTTONS:
                self._set(DPAD_BUTTONS[code], 'button', value != 0, out)
            elif code in BUTTONS and value in (0, 1):          # 2 is the kernel's auto-repeat
                out.append(('press' if value else 'release', BUTTONS[code]))
        elif ev_type == EV_ABS:
            if code in (ABS_HAT0X, ABS_HAT0Y):
                neg, pos = ('left', 'right') if code == ABS_HAT0X else ('up', 'down')
                self._set(neg, 'hat', value < 0, out)
                self._set(pos, 'hat', value > 0, out)
            elif code in (ABS_X, ABS_Y):
                neg, pos = ('left', 'right') if code == ABS_X else ('up', 'down')
                x = self._axis(code, value)
                for direction, amount in ((neg, -x), (pos, x)):
                    held = 'stick' in self.held[direction]
                    if not held and amount >= PRESS_AT:
                        self._set(direction, 'stick', True, out)
                    elif held and amount < RELEASE_AT:
                        self._set(direction, 'stick', False, out)
        return out

    def release_all(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        for direction, sources in self.held.items():
            if sources:
                sources.clear()
                out.append(('release', direction))
        return out


def parse(data: bytes) -> List[Tuple[int, int, int]]:
    """Whole input_event records in data as (type, code, value)."""
    size = EVENT.size
    return [EVENT.unpack_from(data, i)[2:] for i in range(0, len(data) - size + 1, size)]


def pack(ev_type: int, code: int, value: int, stamp: float = 0.0) -> bytes:
    """One input_event, as the kernel writes it (for the tests' recorded events)."""
    sec = int(stamp)
    return EVENT.pack(sec, int((stamp - sec) * 1e6), ev_type, code, value)


# ─── inotify on /dev/input, through libc ──────────────────────

class Watch:
    """inotify on one folder; fileno() is readable when something in it was created, removed
    or had its permissions changed (udev grants access a moment after creating the node)."""

    def __init__(self, folder: str):
        self.fd = -1
        if not sys.platform.startswith('linux'):
            return
        name = ctypes.util.find_library('c') or 'libc.so.6'
        try:
            libc = ctypes.CDLL(name, use_errno=True)
            fd = libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
            if fd < 0:
                return
            if libc.inotify_add_watch(fd, os.fsencode(folder),
                                      IN_CREATE | IN_DELETE | IN_ATTRIB) < 0:
                os.close(fd)
                return
            self.fd = fd
        except (OSError, AttributeError):
            self.fd = -1

    def drain(self) -> bool:
        changed = False
        while self.fd >= 0:
            try:
                if not os.read(self.fd, 4096):
                    break
                changed = True
            except BlockingIOError:
                break
            except OSError:
                break
        return changed

    def close(self):
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1


# ─── The pads, in Tk's event loop ─────────────────────────────

class Gamepads:
    """Reads every gamepad while active. on_action(name) gets 'up', 'down', 'left', 'right'
    (repeated while held), 'a', 'b', 'y', 'start', 'guide', 'select', 'lb', 'rb'."""

    def __init__(self, root, on_action: Callable[[str], None], sys_root: str = SYS_INPUT,
                 dev_root: str = DEV_INPUT,
                 on_change: Optional[Callable[[str, bool], None]] = None):
        self.root, self.on_action, self.on_change = root, on_action, on_change
        self.pad_names: Dict[str, str] = {}             # node -> the device's name
        self.sys_root, self.dev_root = sys_root, dev_root
        self.active = False
        self.open: Dict[str, Tuple[int, Decoder, bytearray]] = {}     # node -> (fd, decoder, buf)
        self.watch: Optional[Watch] = None
        self._repeat_id: Optional[str] = None
        self._repeat_dir: Optional[str] = None
        self._rescan_id: Optional[str] = None
        self.supported = fcntl is not None and hasattr(root.tk, 'createfilehandler')
        self.denied: set = set()             # nodes we may not read yet (udev not done)
        self._seen_once = False              # no "connected" note for pads there at focus

    # active while the window has focus
    def set_active(self, on: bool):
        if not self.supported or on == self.active:
            return
        self.active = on
        if on:
            self.watch = Watch(self.dev_root)
            if self.watch.fd >= 0:
                self.root.tk.createfilehandler(self.watch.fd, _READABLE, self._watch_ready)
            self.rescan()
        else:
            self._stop_repeat()
            self._seen_once = False
            for node in list(self.open):
                self._close(node)
            if self.watch is not None:
                if self.watch.fd >= 0:
                    self.root.tk.deletefilehandler(self.watch.fd)
                self.watch.close()
                self.watch = None
            if self._rescan_id:
                self.root.after_cancel(self._rescan_id)
                self._rescan_id = None

    def names(self) -> List[str]:
        """The names of the controllers being read now."""
        return [self.pad_names.get(node) or node for node in self.open]

    def rescan(self):
        """Open pads that appeared, close ones that went away."""
        self._rescan_id = None
        if not self.active:
            return
        pads = {p.node: p for p in find_pads(self.sys_root, self.dev_root)}
        for node in list(self.open):
            if node not in pads:
                self._close(node, unplugged=True)
        for node, pad in pads.items():
            if node in self.open:
                continue
            try:
                fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0))
            except PermissionError:
                if node not in self.denied:
                    log.info("gamepad %s (%s): no permission to read it yet", node, pad.name)
                    self.denied.add(node)
                continue
            except OSError as exc:
                log.info("gamepad %s: %s", node, exc)
                continue
            self.denied.discard(node)
            self.open[node] = (fd, Decoder(_ranges(fd)), bytearray())
            self.pad_names[node] = pad.name
            self.root.tk.createfilehandler(fd, _READABLE,
                                           lambda _f, _m, n=node: self._ready(n))
            log.info("gamepad: %s (%s)", pad.name or 'unnamed', node)
            if self.on_change and self._seen_once:
                self.on_change(pad.name or node, True)
        self._seen_once = True

    def _watch_ready(self, _fd, _mask):
        if self.watch is not None and self.watch.drain() and self._rescan_id is None:
            # a new node gets its permissions a moment after it appears; wait for udev
            self._rescan_id = self.root.after(250, self.rescan)

    def _close(self, node: str, unplugged: bool = False):
        fd, decoder, _buf = self.open.pop(node)
        name = self.pad_names.pop(node, '')
        if unplugged and self.on_change:
            self.on_change(name or node, False)
        try:
            self.root.tk.deletefilehandler(fd)
        except Exception:          # noqa: BLE001 - Tk already gone
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        for _kind, name in decoder.release_all():
            if name == self._repeat_dir:
                self._stop_repeat()

    def _ready(self, node: str):
        entry = self.open.get(node)
        if entry is None:
            return
        fd, decoder, buf = entry
        while True:
            try:
                chunk = os.read(fd, EVENT.size * 64)
            except BlockingIOError:
                break
            except OSError:                    # unplugged: ENODEV
                self._close(node, unplugged=True)
                return
            if not chunk:
                self._close(node, unplugged=True)
                return
            buf.extend(chunk)
            if len(chunk) < EVENT.size * 64:
                break
        whole = len(buf) - len(buf) % EVENT.size
        events = parse(bytes(buf[:whole]))
        del buf[:whole]
        self.handle(decoder, events)

    def handle(self, decoder: Decoder, events: List[Tuple[int, int, int]]):
        for ev_type, code, value in events:
            if ev_type == EV_SYN and code == SYN_DROPPED:
                for _kind, name in decoder.release_all():
                    if name == self._repeat_dir:
                        self._stop_repeat()
                continue
            for kind, name in decoder.feed(ev_type, code, value):
                if kind == 'press':
                    self._fire(name)
                    if name in DIRECTIONS:
                        self._start_repeat(name)
                elif name == self._repeat_dir:
                    self._stop_repeat()

    def _fire(self, name: str):
        try:
            self.on_action(name)
        except Exception:          # noqa: BLE001 - a bad handler must not stop the reader
            log.exception("gamepad action %s failed", name)

    # a held direction repeats; the timer runs only while one is held
    def _start_repeat(self, direction: str):
        self._stop_repeat()
        self._repeat_dir = direction
        self._repeat_id = self.root.after(int(REPEAT_DELAY * 1000), self._repeat)

    def _repeat(self):
        if self._repeat_dir is None:
            return
        self._fire(self._repeat_dir)
        self._repeat_id = self.root.after(int(REPEAT_EVERY * 1000), self._repeat)

    def _stop_repeat(self):
        if self._repeat_id is not None:
            try:
                self.root.after_cancel(self._repeat_id)
            except Exception:      # noqa: BLE001
                pass
        self._repeat_id = None
        self._repeat_dir = None


_READABLE = 2          # tkinter.READABLE, without importing tkinter here


def _ranges(fd: int) -> Dict[int, Tuple[int, int]]:
    """The left stick's range, asked of the driver (xpad: -32768..32767, PlayStation: 0..255).
    A device that can't answer (the tests' recorded events) keeps xpad's range."""
    out: Dict[int, Tuple[int, int]] = {}
    if fcntl is None:
        return out
    for axis in (ABS_X, ABS_Y):
        try:
            data = fcntl.ioctl(fd, _eviocgabs(axis), bytes(ABSINFO.size))
            _value, lo, hi, _fuzz, _flat, _res = ABSINFO.unpack(data)
            if hi > lo:
                out[axis] = (lo, hi)
        except OSError:
            continue
    return out


def focused(root) -> bool:
    """Whether this app's window has the keyboard focus (focus_get is None when it doesn't)."""
    try:
        return root.focus_get() is not None
    except Exception:          # noqa: BLE001 - Tk's focus_get raises KeyError on some popups
        return False
