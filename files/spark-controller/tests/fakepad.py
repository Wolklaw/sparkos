"""Fake game controllers for the tests. Nothing here is a real controller.

fake_sys(): a /sys/class/input tree (plus /dev/input files and a power_supply folder) holding a
gamepad, a keyboard, a mouse and a battery. The "event" files are plain files, so a recorded
stream of input_events written into one is read like a real device.

UinputPad: a virtual gamepad made through /dev/uinput with raw ioctls (no library), for the
tests that read a real /dev/input node. Skipped where /dev/uinput isn't usable.
"""

import fcntl
import os
import struct
import time

import support
from sparkcontroller import pads

BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x133, 0x134
BTN_TL, BTN_TR, BTN_SELECT, BTN_START, BTN_MODE = 0x136, 0x137, 0x13A, 0x13B, 0x13C
XBOX_KEYS = [BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR, BTN_SELECT, BTN_START,
             BTN_MODE, 0x13D, 0x13E]
# axis: (minimum, maximum, flat)
XBOX_AXES = {0: (-32768, 32767, 128), 1: (-32768, 32767, 128), 2: (0, 1023, 0),
             3: (-32768, 32767, 128), 4: (-32768, 32767, 128), 5: (0, 1023, 0),
             0x10: (-1, 1, 0), 0x11: (-1, 1, 0)}


def bitmap(bits) -> str:
    """The kernel's hex-words form of a set of bit numbers."""
    width = struct.calcsize("l") * 8
    top = max(bits, default=0) // width
    words = []
    for i in range(top, -1, -1):
        value = sum(1 << (b - i * width) for b in bits if i * width <= b < (i + 1) * width)
        words.append(f"{value:x}")
    return " ".join(words)


def add_input(root: str, event: str, name: str, keys, axes, bus=3, vendor=0x045E, product=0x028E,
              uniq="", ff=()) -> str:
    base = os.path.join(root, "sys", "class", "input", event, "device")
    support.put(os.path.join(base, "name"), name)
    support.put(os.path.join(base, "uniq"), uniq)
    for part, value in (("bustype", bus), ("vendor", vendor), ("product", product)):
        support.put(os.path.join(base, "id", part), f"{value:04x}")
    support.put(os.path.join(base, "capabilities", "key"), bitmap(set(keys)))
    support.put(os.path.join(base, "capabilities", "abs"), bitmap(set(axes)))
    support.put(os.path.join(base, "capabilities", "ff"), bitmap(set(ff)))
    dev = os.path.join(root, "dev", "input")
    os.makedirs(dev, exist_ok=True)
    node = os.path.join(dev, event)
    open(node, "ab").close()
    return node


def fake_sys(root: str) -> dict:
    node = add_input(root, "event7", "Xbox Wireless Controller", XBOX_KEYS, XBOX_AXES,
                     bus=5, uniq="aa:bb:cc:dd:ee:ff", ff=[pads.FF_RUMBLE])
    add_input(root, "event3", "Fake Keyboard", [30, 31, 32] + list(range(1, 20)), [])
    add_input(root, "event4", "Fake Mouse", [0x110, 0x111, 0x112], [])
    add_input(root, "event5", "Fake Touchpad", [0x110, 0x14A, 0x145], [0, 1])
    add_input(root, "event6", "Fake System Control", [0x161, 0x164, 0x198, 0x1B6, 0x24E, 0x24F],
              [0x10, 0x11, 40])
    # a battery that names the pad's address, and one that belongs to the machine
    ps = os.path.join(root, "sys", "class", "power_supply")
    name = "ps-controller-battery-aa:bb:cc:dd:ee:ff"
    support.put(os.path.join(ps, name, "capacity"), 64)
    support.put(os.path.join(ps, name, "status"), "Charging")
    support.put(os.path.join(ps, name, "type"), "Battery")
    support.put(os.path.join(ps, "BAT0", "capacity"), 90)
    support.put(os.path.join(ps, "BAT0", "scope"), "System")
    return {"sys": os.path.join(root, "sys", "class", "input"),
            "dev": os.path.join(root, "dev", "input"), "power": ps, "node": node}


class UinputPad:
    """A virtual Xbox-like pad. Use as a context manager; raises OSError if /dev/uinput is
    unavailable."""
    UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045567
    UI_DEV_SETUP, UI_ABS_SETUP = 0x405C5503, 0x401C5504
    UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502

    def __init__(self, name="Spark Test Pad"):
        self.name = name
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            for etype in (pads.EV_KEY, pads.EV_ABS):
                fcntl.ioctl(self.fd, self.UI_SET_EVBIT, etype)
            for key in XBOX_KEYS:
                fcntl.ioctl(self.fd, self.UI_SET_KEYBIT, key)
            for code, (low, high, flat) in XBOX_AXES.items():
                fcntl.ioctl(self.fd, self.UI_SET_ABSBIT, code)
                fcntl.ioctl(self.fd, self.UI_ABS_SETUP,
                            struct.pack("=Hxx6i", code, 0, low, high, 0, flat, 0))
            setup = struct.pack("=HHHH80sI", 3, 0x1234, 0x5678, 1, self.name.encode(), 0)
            fcntl.ioctl(self.fd, self.UI_DEV_SETUP, setup)
            fcntl.ioctl(self.fd, self.UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise

    def send(self, etype: int, code: int, value: int) -> None:
        os.write(self.fd, pads.event_bytes(etype, code, value))

    def sync(self) -> None:
        self.send(pads.EV_SYN, 0, 0)

    def find(self, timeout=3.0):
        """The scanned Pad for this device, once its node exists, or None."""
        end = time.time() + timeout
        while time.time() < end:
            for pad in pads.scan():
                if pad.name == self.name:
                    return pad
            time.sleep(0.05)
        return None

    def close(self) -> None:
        try:
            fcntl.ioctl(self.fd, self.UI_DEV_DESTROY)
        finally:
            os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
