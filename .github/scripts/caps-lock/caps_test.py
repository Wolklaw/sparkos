#!/usr/bin/env python3
"""Tests for sparkos-capslock (Caps Lock turns on and off when pressed). Run as root.

  caps_test.py device PROGRAM
      On a CI runner: makes a virtual test keyboard (uinput) that also has a scroll wheel, runs
      PROGRAM on it, presses keys on it and reads what comes out of the copy PROGRAM makes.
      Caps Lock must arrive as a whole press and release while the key is still down, the key's
      release must change nothing, and every other event must pass through unchanged.

  caps_test.py vm --seconds N
      In the boot-test VM: watches the copy of the VM's PS/2 keyboard that sparkos-capslock made,
      and the keyboard's Caps Lock light (set by the desktop, KWin), while the runner presses
      Caps Lock twice through QEMU and holds it 1.5 s each time. The light must change while the
      key is still held, both times: on at the first press, off at the second.
"""
import fcntl
import json
import os
import re
import select
import signal
import struct
import subprocess
import sys
import time

EV_SYN, EV_KEY, EV_REL, EV_MSC, EV_LED, EV_REP = 0x00, 0x01, 0x02, 0x04, 0x11, 0x14
SYN_REPORT = 0
KEY_A, KEY_C, KEY_CAPSLOCK, KEY_RIGHTCTRL, KEY_FN_F1 = 30, 46, 58, 97, 0x1D2
BTN_LEFT = 0x110
REL_X, REL_WHEEL, REL_WHEEL_HI_RES = 0x00, 0x08, 0x0B
MSC_SCAN = 0x04
LED_NUML, LED_CAPSL = 0, 1
BUS_USB = 0x03

EVENT = struct.Struct("llHHi")


def _ioc(direction, nr, size, kind):
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | nr


UI_SET_EVBIT = _ioc(1, 100, 4, "U")
UI_SET_KEYBIT = _ioc(1, 101, 4, "U")
UI_SET_RELBIT = _ioc(1, 102, 4, "U")
UI_SET_MSCBIT = _ioc(1, 104, 4, "U")
UI_SET_LEDBIT = _ioc(1, 105, 4, "U")
UI_DEV_SETUP = _ioc(1, 3, 92, "U")
UI_DEV_CREATE = _ioc(0, 1, 0, "U")
UI_DEV_DESTROY = _ioc(0, 2, 0, "U")
EVIOCGRAB = _ioc(1, 0x90, 4, "E")


def UI_GET_SYSNAME(n):
    return _ioc(2, 44, n, "U")


def EVIOCGNAME(n):
    return _ioc(2, 0x06, n, "E")


def EVIOCGLED(n):
    return _ioc(2, 0x19, n, "E")


failures = []


def check(ok, what):
    print(("   ok   " if ok else "   FAIL ") + what, flush=True)
    if not ok:
        failures.append(what)


def read_events(fd, seconds):
    """Every event that arrives on fd within the given time."""
    out, end = [], time.monotonic() + seconds
    while True:
        left = end - time.monotonic()
        if left <= 0:
            return out
        r, _, _ = select.select([fd], [], [], left)
        if r:
            try:
                data = os.read(fd, EVENT.size * 64)
            except BlockingIOError:
                continue
            for i in range(0, len(data), EVENT.size):
                _, _, t, c, v = EVENT.unpack_from(data, i)
                out.append((t, c, v))


def without_syn(events):
    return [e for e in events if e[0] != EV_SYN and not (e[0] == EV_MSC and e[1] == MSC_SCAN)]


class TestKeyboard:
    """A virtual keyboard with a scroll wheel, like the many wireless keyboard + mouse sets
    whose receiver puts both on one device."""

    def __init__(self, name):
        self.fd = os.open("/dev/uinput", os.O_RDWR | os.O_NONBLOCK)
        for ev in (EV_SYN, EV_KEY, EV_REL, EV_MSC, EV_LED, EV_REP):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        for key in list(range(1, 249)) + [KEY_FN_F1, BTN_LEFT]:
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, key)
        for rel in (REL_X, REL_WHEEL, REL_WHEEL_HI_RES):
            fcntl.ioctl(self.fd, UI_SET_RELBIT, rel)
        fcntl.ioctl(self.fd, UI_SET_MSCBIT, MSC_SCAN)
        for led in (LED_NUML, LED_CAPSL):
            fcntl.ioctl(self.fd, UI_SET_LEDBIT, led)
        fcntl.ioctl(self.fd, UI_DEV_SETUP, struct.pack("HHHH80sI", BUS_USB, 0x1209, 0x5ca1, 1, name.encode(), 0))
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        sysname = fcntl.ioctl(self.fd, UI_GET_SYSNAME(64), bytes(64)).rstrip(b"\0").decode()
        sysdir = f"/sys/devices/virtual/input/{sysname}"
        for _ in range(100):
            nodes = [n for n in os.listdir(sysdir) if n.startswith("event")] if os.path.isdir(sysdir) else []
            if nodes and os.path.exists(f"/dev/input/{nodes[0]}"):
                self.node = f"/dev/input/{nodes[0]}"
                break
            time.sleep(0.05)
        else:
            raise SystemExit("the test keyboard's device node never appeared")
        time.sleep(0.3)

    def send(self, *events):
        for t, c, v in events:
            os.write(self.fd, EVENT.pack(0, 0, t, c, v))
        os.write(self.fd, EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))

    def key(self, code, value):
        # A real keyboard sends the scan code first, in the same frame
        self.send((EV_MSC, MSC_SCAN, 0x70000 + code), (EV_KEY, code, value))

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


def device_test(program):
    kbd = TestKeyboard("SparkOS Caps Lock test keyboard")
    print(f"test keyboard: {kbd.node}")
    proc = subprocess.Popen([program, kbd.node], stdout=subprocess.PIPE, text=True)
    line = ""
    r, _, _ = select.select([proc.stdout], [], [], 10)
    if r:
        line = proc.stdout.readline().strip()
    print(f"sparkos-capslock: {line}")
    m = re.search(r"the desktop reads (/dev/input/event\d+)", line)
    if not m:
        proc.kill()
        raise SystemExit("sparkos-capslock didn't make a copy of the keyboard")
    copy = m.group(1)
    out = os.open(copy, os.O_RDWR | os.O_NONBLOCK)
    name = fcntl.ioctl(out, EVIOCGNAME(256), bytes(256)).rstrip(b"\0").decode()
    check(name == "SparkOS Caps Lock test keyboard", f"the copy has the keyboard's name ({name!r})")

    probe = os.open(kbd.node, os.O_RDONLY | os.O_NONBLOCK)
    try:
        fcntl.ioctl(probe, EVIOCGRAB, 1)
        grabbed = False
        fcntl.ioctl(probe, EVIOCGRAB, 0)
    except OSError:
        grabbed = True
    os.close(probe)
    check(grabbed, "the keyboard itself is taken (EVIOCGRAB), so the desktop only reads the copy")

    print("-- Caps Lock pressed and held")
    kbd.key(KEY_CAPSLOCK, 1)
    got = without_syn(read_events(out, 0.3))
    check(got == [(EV_KEY, KEY_CAPSLOCK, 1), (EV_KEY, KEY_CAPSLOCK, 0)],
          f"press and release both arrive while the key is still down: {got}")
    kbd.key(KEY_CAPSLOCK, 2)
    got = without_syn(read_events(out, 0.2))
    check(got == [], f"the key's repeats are dropped: {got}")
    print("-- Caps Lock released")
    kbd.key(KEY_CAPSLOCK, 0)
    got = without_syn(read_events(out, 0.3))
    check(got == [], f"the key's own release is dropped: {got}")

    print("-- Caps Lock tapped with A pressed before Caps Lock is released (the case this fixes)")
    kbd.key(KEY_CAPSLOCK, 1)
    kbd.key(KEY_A, 1)
    kbd.key(KEY_CAPSLOCK, 0)
    kbd.key(KEY_A, 0)
    got = [e for e in without_syn(read_events(out, 0.3))]
    check(got == [(EV_KEY, KEY_CAPSLOCK, 1), (EV_KEY, KEY_CAPSLOCK, 0), (EV_KEY, KEY_A, 1), (EV_KEY, KEY_A, 0)],
          f"Caps Lock is fully released before A goes down: {got}")

    print("-- Other keys pass through unchanged")
    kbd.key(KEY_RIGHTCTRL, 1)
    kbd.key(KEY_C, 1)
    kbd.key(KEY_C, 0)
    kbd.key(KEY_RIGHTCTRL, 0)
    kbd.key(KEY_FN_F1, 1)
    kbd.key(KEY_FN_F1, 0)
    got = without_syn(read_events(out, 0.3))
    check(got == [(EV_KEY, KEY_RIGHTCTRL, 1), (EV_KEY, KEY_C, 1), (EV_KEY, KEY_C, 0), (EV_KEY, KEY_RIGHTCTRL, 0),
                  (EV_KEY, KEY_FN_F1, 1), (EV_KEY, KEY_FN_F1, 0)],
          f"Right Ctrl stays Right Ctrl, C, and a key above 255 (Fn+F1): {got}")
    kbd.key(KEY_A, 1)
    raw = read_events(out, 0.1)
    check((EV_MSC, MSC_SCAN, 0x70000 + KEY_A) in raw, "scan codes pass through")
    kbd.key(KEY_A, 2)
    kbd.key(KEY_A, 0)
    got = without_syn(read_events(out, 0.2))
    check(got == [(EV_KEY, KEY_A, 0)],
          f"the keyboard's repeats aren't doubled (the copy repeats by itself, like any keyboard): {got}")

    print("-- Mouse events on the same device pass through unchanged")
    kbd.send((EV_REL, REL_X, 7), (EV_REL, REL_WHEEL, 1), (EV_REL, REL_WHEEL_HI_RES, 120))
    kbd.send((EV_KEY, BTN_LEFT, 1))
    kbd.send((EV_KEY, BTN_LEFT, 0))
    got = without_syn(read_events(out, 0.3))
    check(got == [(EV_REL, REL_X, 7), (EV_REL, REL_WHEEL, 1), (EV_REL, REL_WHEEL_HI_RES, 120),
                  (EV_KEY, BTN_LEFT, 1), (EV_KEY, BTN_LEFT, 0)],
          f"movement, wheel, high-resolution wheel and buttons: {got}")

    print("-- The Caps Lock light goes back to the keyboard")
    read_events(kbd.fd, 0.1)
    os.write(out, EVENT.pack(0, 0, EV_LED, LED_CAPSL, 1) + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))
    got = [e for e in read_events(kbd.fd, 0.3) if e[0] == EV_LED]
    check(got == [(EV_LED, LED_CAPSL, 1)], f"the light set on the copy reaches the keyboard: {got}")

    print("-- Stopping it gives the keyboard back")
    os.close(out)
    proc.send_signal(signal.SIGTERM)
    try:
        code = proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "killed"
    check(code == 0, f"exits cleanly on SIGTERM (exit {code})")
    time.sleep(0.3)
    check(not os.path.exists(copy), "the copy is gone")
    probe = os.open(kbd.node, os.O_RDONLY | os.O_NONBLOCK)
    try:
        fcntl.ioctl(probe, EVIOCGRAB, 1)
        free = True
    except OSError:
        free = False
    os.close(probe)
    check(free, "the keyboard is free again")
    kbd.close()


def input_devices():
    """(name, sysfs path, event node) for each input device, from /proc/bus/input/devices."""
    devs = []
    for block in open("/proc/bus/input/devices").read().split("\n\n"):
        name = re.search(r'^N: Name="(.*)"$', block, re.M)
        sysfs = re.search(r"^S: Sysfs=(.*)$", block, re.M)
        handlers = re.search(r"^H: Handlers=(.*)$", block, re.M)
        event = re.search(r"\b(event\d+)\b", handlers.group(1)) if handlers else None
        if name and sysfs and event:
            devs.append((name.group(1), sysfs.group(1), f"/dev/input/{event.group(1)}"))
    return devs


def vm_test(seconds):
    devs = input_devices()
    kbd = [d for d in devs if d[0] == "AT Translated Set 2 keyboard" and not d[1].startswith("/devices/virtual/")]
    copy = [d for d in devs if d[0] == "AT Translated Set 2 keyboard" and d[1].startswith("/devices/virtual/")]
    print(f"keyboard: {kbd}\ncopy: {copy}", flush=True)
    if not kbd or not copy:
        raise SystemExit("FAIL: the PS/2 keyboard or its copy by sparkos-capslock isn't there")
    phys = os.open(kbd[0][2], os.O_RDONLY | os.O_NONBLOCK)
    out = os.open(copy[0][2], os.O_RDONLY | os.O_NONBLOCK)

    def light():
        return bool(fcntl.ioctl(phys, EVIOCGLED(8), bytes(8))[0] & (1 << LED_CAPSL))

    start = time.monotonic()
    caps, leds = [], []
    print("READY", flush=True)
    while time.monotonic() - start < seconds:
        r, _, _ = select.select([out], [], [], 0.02)
        now = time.monotonic() - start
        if r:
            data = os.read(out, EVENT.size * 64)
            for i in range(0, len(data), EVENT.size):
                _, _, t, c, v = EVENT.unpack_from(data, i)
                if t == EV_KEY and c == KEY_CAPSLOCK:
                    caps.append((round(now, 3), v))
        leds.append((round(now, 3), light()))

    print(json.dumps({"caps_events": caps}))
    changes = [leds[0]] + [b for a, b in zip(leds, leds[1:]) if a[1] != b[1]]
    print(json.dumps({"light_changes": changes}))
    initial = leds[0][1]
    downs = [t for t, v in caps if v == 1]
    ups = [t for t, v in caps if v == 0]
    check(len(downs) == 2 and len(ups) == 2,
          f"two Caps Lock presses reach the desktop, each a press and a release ({len(downs)} down, {len(ups)} up)")
    if len(downs) == 2 and len(ups) == 2:
        for n, (d, u) in enumerate(zip(downs, ups), 1):
            check(0 <= u - d <= 0.1, f"press {n}: the release arrives {int((u - d) * 1000)} ms after the press, "
                                     "while the key is still held (QEMU holds it 1.5 s)")
        for n, d in enumerate(downs, 1):
            want = (not initial) if n == 1 else initial
            held = [on for t, on in leds if d + 0.4 <= t <= d + 1.2]
            state = "on" if want else "off"
            check(bool(held) and all(on == want for on in held),
                  f"press {n}: the Caps Lock light is {state} while the key is still held "
                  f"(set by the desktop, {len(held)} samples between 0.4 s and 1.2 s after the press)")
    if all(on == initial for _, on in leds):
        print("   note: the light never changed, so nothing on the desktop side set it "
              "(no KWin running, or it doesn't reach the keyboard)")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "device":
        device_test(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "vm":
        vm_test(float(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 14)
    else:
        raise SystemExit(__doc__)
    if failures:
        print(f"{len(failures)} check(s) failed")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
