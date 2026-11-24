"""Game controllers, read straight from the kernel's evdev interface. No library needed.

Listing a pad uses /sys/class/input only, so it works without any permission. Reading its buttons
and sticks (and making it rumble) opens /dev/input/eventN, which the logged-in user may do
through the uaccess rule that steam-devices and game-devices-udev set on controllers.

Everything takes its folders as parameters so the tests can feed a fake /sys tree and recorded
event streams.
"""

import errno
import fcntl
import gzip
import os
import re
import struct
from typing import Dict, List, Optional, Set, Tuple

SYS_INPUT = "/sys/class/input"
SYS_POWER = "/sys/class/power_supply"
DEV_INPUT = "/dev/input"
FWUPD_QUIRKS = "/usr/share/fwupd/quirks.d/builtin.quirk.gz"

EV_SYN, EV_KEY, EV_ABS, EV_FF = 0x00, 0x01, 0x03, 0x15
SYN_DROPPED = 3
KEY_A = 30
BTN_MOUSE, BTN_JOYSTICK, BTN_GAMEPAD, BTN_TOUCH = 0x110, 0x120, 0x130, 0x14A
BTN_THUMBL, BTN_THUMBR = 0x13D, 0x13E
ABS_HAT0X, ABS_HAT0Y, ABS_HAT3Y = 0x10, 0x11, 0x17
FF_RUMBLE = 0x50
BUS = {0x03: "usb", 0x05: "bluetooth", 0x06: "virtual"}

EVENT = struct.Struct("llHHi")     # struct input_event on this machine
FF_EFFECT_SIZE = 48                # struct ff_effect, 64-bit; 32-bit machines are not supported


# — ioctl numbers (linux/input.h), computed the way _IOC does —
def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("E") << 8) | nr


def EVIOCGABS(axis: int) -> int:
    return _ioc(2, 0x40 + axis, 24)


def EVIOCGKEY(size: int) -> int:
    return _ioc(2, 0x18, size)


EVIOCSFF = _ioc(1, 0x80, FF_EFFECT_SIZE)
EVIOCRMFF = _ioc(1, 0x81, 4)

BUTTON_NAMES = {
    0x130: "A", 0x131: "B", 0x132: "C", 0x133: "X", 0x134: "Y", 0x135: "Z",
    0x136: "LB", 0x137: "RB", 0x138: "LT", 0x139: "RT", 0x13A: "BACK", 0x13B: "START",
    0x13C: "GUIDE", 0x13D: "L3", 0x13E: "R3",
    0x220: "UP", 0x221: "DOWN", 0x222: "LEFT", 0x223: "RIGHT",
}
# Buttons with the Linux gamepad names first, in the order they are drawn.
BUTTON_ORDER = (0x130, 0x131, 0x133, 0x134, 0x132, 0x135, 0x136, 0x137, 0x138, 0x139,
                0x13A, 0x13B, 0x13C, 0x13D, 0x13E)
DPAD_KEYS = {0x220: "up", 0x221: "down", 0x222: "left", 0x223: "right"}
AXIS_NAMES = {0: "X", 1: "Y", 2: "Z", 3: "RX", 4: "RY", 5: "RZ", 6: "THROTTLE", 7: "RUDDER",
              8: "WHEEL", 9: "GAS", 10: "BRAKE", 0x10: "HAT0X", 0x11: "HAT0Y"}


def button_name(code: int) -> str:
    return BUTTON_NAMES.get(code) or f"B{code:X}"


def axis_name(code: int) -> str:
    return AXIS_NAMES.get(code) or f"AXIS {code}"


# — listing —
def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def parse_bitmap(text: str) -> Set[int]:
    """The kernel prints capabilities as hex words, the highest word first. Bits that are set."""
    bits: Set[int] = set()
    word_bits = struct.calcsize("l") * 8
    words = text.split()
    for i, word in enumerate(reversed(words)):
        try:
            value = int(word, 16)
        except ValueError:
            return set()
        for bit in range(word_bits):
            if value >> bit & 1:
                bits.add(i * word_bits + bit)
    return bits


def looks_like_a_pad(keys: Set[int], axes: Set[int]) -> bool:
    """A joystick or gamepad, not a keyboard, mouse or touchpad that also reports buttons."""
    if KEY_A in keys or BTN_MOUSE in keys or BTN_TOUCH in keys:
        return False
    pad_buttons = [k for k in keys if BTN_JOYSTICK <= k < 0x140]   # BTN_TRIGGER ... BTN_THUMBR
    return len(pad_buttons) >= 4 and bool(axes)


class Pad:
    def __init__(self):
        self.name = ""
        self.path = ""                    # /dev/input/eventN
        self.bus = "other"                # usb, bluetooth, virtual, other
        self.vendor = 0
        self.product = 0
        self.uniq = ""
        self.keys: Set[int] = set()
        self.axes: Set[int] = set()
        self.has_rumble = False
        self.can_read = False
        self.can_write = False
        self.battery: Optional[Dict[str, str]] = None   # {"percent": "80", "level": "", "status": ""}

    @property
    def usb_id(self) -> str:
        return f"{self.vendor:04x}:{self.product:04x}"

    @property
    def key(self) -> str:
        return self.path

    def battery_text(self) -> str:
        if not self.battery:
            return ""
        b = self.battery
        text = f"{b['percent']} %" if b.get("percent") else b.get("level", "")
        if text and b.get("status", "").lower() == "charging":
            text += " +"
        return text


def find_battery(event_dir: str, uniq: str, power_dir: str = SYS_POWER) -> Optional[Dict[str, str]]:
    """The battery that belongs to a pad: its device is a parent of the pad's input device, or
    the pad's unique id (a Bluetooth address) is in the battery's name."""
    try:
        supplies = sorted(os.listdir(power_dir))
    except OSError:
        return None
    pad_real = os.path.realpath(event_dir)
    for name in supplies:
        base = os.path.join(power_dir, name)
        if _read(os.path.join(base, "scope")).lower() == "system":
            continue
        if _read(os.path.join(base, "type")).lower() not in ("", "battery"):
            continue
        parent = os.path.realpath(os.path.join(base, "device"))
        owned = os.path.isdir(os.path.join(base, "device")) and parent != "/" and \
            pad_real.startswith(parent.rstrip("/") + "/")
        named = bool(uniq) and uniq.lower() in name.lower()
        if not (owned or named):
            continue
        percent = _read(os.path.join(base, "capacity"))
        level = _read(os.path.join(base, "capacity_level"))
        if not percent.isdigit() and not level:
            continue
        return {"percent": percent if percent.isdigit() else "", "level": level,
                "status": _read(os.path.join(base, "status"))}
    return None


def scan(sys_input: str = SYS_INPUT, dev_input: str = DEV_INPUT,
         power_dir: str = SYS_POWER) -> List[Pad]:
    """Every game controller the kernel knows about. Needs no permission."""
    pads: List[Pad] = []
    try:
        names = sorted((n for n in os.listdir(sys_input) if re.fullmatch(r"event\d+", n)),
                       key=lambda n: int(n[5:]))
    except OSError:
        return pads
    for name in names:
        base = os.path.join(sys_input, name)
        dev = os.path.join(base, "device")
        keys = parse_bitmap(_read(os.path.join(dev, "capabilities", "key")))
        axes = parse_bitmap(_read(os.path.join(dev, "capabilities", "abs")))
        if not looks_like_a_pad(keys, axes):
            continue
        pad = Pad()
        pad.name = _read(os.path.join(dev, "name")) or name
        pad.path = os.path.join(dev_input, name)
        pad.uniq = _read(os.path.join(dev, "uniq"))
        pad.keys, pad.axes = keys, axes
        try:
            pad.bus = BUS.get(int(_read(os.path.join(dev, "id", "bustype")), 16), "other")
            pad.vendor = int(_read(os.path.join(dev, "id", "vendor")), 16)
            pad.product = int(_read(os.path.join(dev, "id", "product")), 16)
        except ValueError:
            pass
        pad.has_rumble = FF_RUMBLE in parse_bitmap(_read(os.path.join(dev, "capabilities", "ff")))
        pad.can_read = os.access(pad.path, os.R_OK)
        pad.can_write = os.access(pad.path, os.W_OK)
        pad.battery = find_battery(base, pad.uniq, power_dir)
        pads.append(pad)
    return pads


# — what fwupd can do for a pad —
def fwupd_plugin_for(vendor: int, product: int, quirks_path: str = FWUPD_QUIRKS) -> str:
    """The fwupd plugin that claims this USB id, read from the installed fwupd's own list.
    Empty when fwupd has no support for the model (or the list isn't there)."""
    wanted = f"[USB\\VID_{vendor:04X}&PID_{product:04X}]"
    try:
        opener = gzip.open if quirks_path.endswith(".gz") else open
        with opener(quirks_path, "rt", encoding="utf-8", errors="replace") as f:
            inside = False
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    inside = line.upper() == wanted
                elif inside and line.startswith("Plugin"):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


# — live state —
def classify_axes(info: Dict[int, Tuple[int, int, int, int]]) -> Dict[str, List]:
    """Sort a pad's axes into hats, triggers (resting at the bottom of their range), and stick
    axes, which are paired two by two in code order: (X, Y), then the next two. info is
    {axis: (value, minimum, maximum, flat)}, read while nothing is pressed."""
    hats, triggers, rest = [], [], []
    for code in sorted(info):
        value, low, high, _flat = info[code]
        span = max(1, high - low)
        if ABS_HAT0X <= code <= ABS_HAT3Y:
            hats.append(code)
        elif low >= 0 and (value - low) / span < 0.1 and span > 1:
            triggers.append(code)
        else:
            rest.append(code)
    sticks = [(rest[i], rest[i + 1]) for i in range(0, len(rest) - 1, 2)]
    loose = [rest[-1]] if len(rest) % 2 else []
    return {"hats": hats, "triggers": triggers + loose, "sticks": sticks}


class PadState:
    """Buttons and axes as the events arrive. No file in here: feed it events."""

    def __init__(self):
        self.buttons: Dict[int, bool] = {}
        self.axes: Dict[int, Tuple[int, int, int, int]] = {}
        self.layout: Dict[str, List] = {"hats": [], "triggers": [], "sticks": []}
        self.rest: Optional[Dict[int, float]] = None     # a drift measurement in progress
        self.drift: Dict[int, float] = {}                # finished: how far each stick strayed

    def set_axis(self, code: int, value: int, low: int, high: int, flat: int) -> None:
        self.axes[code] = (value, low, high, flat)

    def classify(self) -> None:
        self.layout = classify_axes(self.axes)

    def apply(self, etype: int, code: int, value: int) -> bool:
        """True when something visible changed."""
        if etype == EV_KEY:
            on = value != 0
            changed = self.buttons.get(code) != on
            self.buttons[code] = on
            return changed
        if etype == EV_ABS and code in self.axes:
            _v, low, high, flat = self.axes[code]
            self.axes[code] = (value, low, high, flat)
            if self.rest is not None:
                for pair in self.layout["sticks"]:
                    if code in pair:
                        self.rest[pair[0]] = max(self.rest.get(pair[0], 0.0),
                                                 self.stick(pair)[2])
            return True
        return False

    def axis(self, code: int) -> float:
        """-1 to 1 around the middle of the axis's range."""
        if code not in self.axes:
            return 0.0
        value, low, high, _flat = self.axes[code]
        if high <= low:
            return 0.0
        return max(-1.0, min(1.0, (value - low) / (high - low) * 2 - 1))

    def trigger(self, code: int) -> float:
        """0 to 1."""
        if code not in self.axes:
            return 0.0
        value, low, high, _flat = self.axes[code]
        if high <= low:
            return 0.0
        return max(0.0, min(1.0, (value - low) / (high - low)))

    def stick(self, pair: Tuple[int, int]) -> Tuple[float, float, float]:
        """x, y (-1 to 1, y down is positive) and how far from the middle, 0 to 1 (a pad whose
        corners reach past the circle is clipped to 1)."""
        x, y = self.axis(pair[0]), self.axis(pair[1])
        mag = (x * x + y * y) ** 0.5
        if mag > 1.0:                        # a square-gated pad's corner: keep the dot in the circle
            x, y, mag = x / mag, y / mag, 1.0
        return x, y, mag

    def flat(self, pair: Tuple[int, int]) -> float:
        """The deadzone the kernel reports for this stick, 0 to 1."""
        if pair[0] not in self.axes:
            return 0.0
        _v, low, high, flat = self.axes[pair[0]]
        return flat / max(1, (high - low) / 2)

    def dpad(self) -> Dict[str, bool]:
        out = {name: bool(self.buttons.get(code)) for code, name in DPAD_KEYS.items()}
        hx, hy = self.axes.get(ABS_HAT0X), self.axes.get(ABS_HAT0Y)
        if hx:
            mid = (hx[1] + hx[2]) / 2
            out["left"] |= hx[0] < mid
            out["right"] |= hx[0] > mid
        if hy:
            mid = (hy[1] + hy[2]) / 2
            out["up"] |= hy[0] < mid
            out["down"] |= hy[0] > mid
        return out

    # — rest drift: leave the sticks alone, see how far they wander —
    def start_rest(self) -> None:
        self.rest = {pair[0]: self.stick(pair)[2] for pair in self.layout["sticks"]}

    def finish_rest(self) -> Dict[int, float]:
        self.drift = dict(self.rest or {})
        self.rest = None
        return self.drift


def suggested_deadzone(drift: float) -> int:
    """A deadzone, in percent, that hides a measured rest drift (0 to 1) with a little room."""
    return int(drift * 100 + 0.999) + 1 if drift > 0 else 0


class PadReader:
    """An open event node: non-blocking reads into a PadState."""

    def __init__(self, path: str, keys: Set[int], axes: Set[int]):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.state = PadState()
        self.keys, self.axes = keys, axes
        self.gone = False
        self.resync()
        self.state.classify()

    def resync(self) -> None:
        for code in sorted(self.axes):
            try:
                raw = fcntl.ioctl(self.fd, EVIOCGABS(code), bytes(24))
            except OSError:
                continue
            value, low, high, _fuzz, flat, _res = struct.unpack("6i", raw)
            self.state.set_axis(code, value, low, high, flat)
        size = (max(self.keys, default=0) // 8) + 1
        try:
            raw = fcntl.ioctl(self.fd, EVIOCGKEY(size), bytes(size))
            for code in self.keys:
                self.state.buttons[code] = bool(raw[code // 8] >> (code % 8) & 1)
        except OSError:
            pass

    def poll(self) -> bool:
        """Read what is waiting. True if something changed. Sets .gone when the pad left."""
        changed = False
        while True:
            try:
                data = os.read(self.fd, EVENT.size * 64)
            except BlockingIOError:
                break
            except OSError as exc:
                if exc.errno in (errno.ENODEV, errno.EIO):
                    self.gone = True
                break
            if not data:
                break
            changed |= self.feed(data)
        return changed

    def feed(self, data: bytes) -> bool:
        changed = False
        for offset in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _s, _us, etype, code, value = EVENT.unpack_from(data, offset)
            if etype == EV_SYN and code == SYN_DROPPED:
                self.resync()
                changed = True
            else:
                changed |= self.state.apply(etype, code, value)
        return changed

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


def event_bytes(etype: int, code: int, value: int) -> bytes:
    """One input_event as the kernel writes it (for tests and recorded streams)."""
    return EVENT.pack(0, 0, etype, code, value)


# — rumble —
def rumble_effect(strong: int, weak: int, milliseconds: int, effect_id: int = -1) -> bytes:
    """struct ff_effect for a rumble: strong and weak motor 0..65535, for some milliseconds."""
    head = struct.pack("=HhHHHHH2x", FF_RUMBLE, effect_id, 0, 0, 0, milliseconds, 0)
    body = struct.pack("=HH", max(0, min(65535, strong)), max(0, min(65535, weak)))
    return (head + body).ljust(FF_EFFECT_SIZE, b"\0")


class Rumble:
    """Uploads one rumble effect and plays it. Needs the event node open for writing, which the
    uaccess rule allows for the person at the PC."""

    def __init__(self, path: str):
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.effect = -1

    def play(self, strong: float, weak: float, milliseconds: int = 600) -> None:
        self.stop()
        buf = bytearray(rumble_effect(int(strong * 65535), int(weak * 65535), milliseconds))
        fcntl.ioctl(self.fd, EVIOCSFF, buf)
        self.effect = struct.unpack_from("=h", buf, 2)[0]
        os.write(self.fd, EVENT.pack(0, 0, EV_FF, self.effect, 1))

    def stop(self) -> None:
        if self.effect >= 0:
            try:
                os.write(self.fd, EVENT.pack(0, 0, EV_FF, self.effect, 0))
                fcntl.ioctl(self.fd, EVIOCRMFF, self.effect)
            except OSError:
                pass
            self.effect = -1

    def close(self) -> None:
        self.stop()
        try:
            os.close(self.fd)
        except OSError:
            pass


PAD_WORDS = ("gamepad", "game controller", "wireless controller", "dualsense", "dualshock",
             "joy-con", "joycon", "8bitdo", "xbox")


def firmware_for_pads(devices, pads: List[Pad]) -> list:
    """The fwupd devices that are game controllers: claimed by fwupd's ebitdo plugin, made by
    the same USB vendor as a connected pad, or named like one. devices are FwDevice objects."""
    vendors = {f"USB:0X{p.vendor:04X}" for p in pads if p.bus == "usb"}
    out = []
    for d in devices:
        text = f"{d.name} {d.summary}".lower()
        if d.plugin == "ebitdo" or d.vendor_id.upper() in vendors \
                or any(w in text for w in PAD_WORDS):
            out.append(d)
    return out
