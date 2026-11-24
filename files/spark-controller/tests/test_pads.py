"""Pads: finding controllers, reading their state, rumble packing, and what fwupd can do.
No real controller is used. The fake tree and recorded events are in fakepad.py; a virtual pad
made through /dev/uinput stands in where the container allows it."""

import gzip
import json
import os
import shutil
import struct
import tempfile
import time
import unittest

import fakepad
import support
from fakepad import XBOX_AXES, XBOX_KEYS
from langcheck import clipped
from sparkcontroller import pads, text
from sparkcontroller.fwupd import FwDevice, Fwupd
from sparkcontroller.hwmon import Hwmon

EV_KEY, EV_ABS, EV_SYN = pads.EV_KEY, pads.EV_ABS, pads.EV_SYN


class Tree(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="spark-controller-pads-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.tree = fakepad.fake_sys(self.dir)

    def scan(self):
        return pads.scan(self.tree["sys"], self.tree["dev"], self.tree["power"])


class Listing(Tree):
    def test_bitmaps(self):
        self.assertEqual(pads.parse_bitmap("0"), set())
        self.assertEqual(pads.parse_bitmap("1b"), {0, 1, 3, 4})
        word = struct.calcsize("l") * 8
        self.assertEqual(pads.parse_bitmap("1 0"), {word})
        self.assertEqual(pads.parse_bitmap("nonsense"), set())

    def test_only_the_gamepad_is_listed(self):
        found = self.scan()
        self.assertEqual([p.name for p in found], ["Xbox Wireless Controller"])

    def test_keyboards_mice_touchpads_and_hat_only_keys_are_not_pads(self):
        for keys, axes in (([30, 31, 0x130, 0x131, 0x133, 0x134], [0, 1]),      # a keyboard
                           ([0x110, 0x111, 0x130, 0x131, 0x133, 0x134], [0, 1]),   # a mouse
                           ([0x161, 0x164, 0x198, 0x1B6], [0x10, 0x11]),         # system keys
                           ([0x130, 0x131], [0, 1])):                           # too few buttons
            with self.subTest(keys=keys):
                self.assertFalse(pads.looks_like_a_pad(set(keys), set(axes)))
        self.assertTrue(pads.looks_like_a_pad(set(XBOX_KEYS), set(XBOX_AXES)))

    def test_what_the_pad_is(self):
        pad = self.scan()[0]
        self.assertEqual((pad.bus, pad.usb_id, pad.has_rumble), ("bluetooth", "045e:028e", True))
        self.assertEqual(pad.path, self.tree["node"])
        self.assertTrue(pad.can_read and pad.can_write)

    def test_battery_by_address_and_the_laptop_battery_is_ignored(self):
        pad = self.scan()[0]
        self.assertEqual(pad.battery_text(), "64 % +")

    def test_battery_by_parent_device(self):
        real = os.path.join(self.dir, "devices", "hid0001")
        os.makedirs(os.path.join(real, "input", "input9", "event9"))
        sysinput = os.path.join(self.dir, "sys2", "event9")
        os.makedirs(os.path.dirname(sysinput))
        os.symlink(os.path.join(real, "input", "input9", "event9"), sysinput)
        ps = os.path.join(self.dir, "ps2", "hid-battery")
        support.put(os.path.join(ps, "capacity_level"), "Normal")
        os.symlink(real, os.path.join(ps, "device"))
        battery = pads.find_battery(sysinput, "", os.path.join(self.dir, "ps2"))
        self.assertEqual(battery["level"], "Normal")

    def test_no_battery_and_nothing_to_list(self):
        self.assertIsNone(pads.find_battery(self.tree["sys"], "", os.path.join(self.dir, "none")))
        self.assertEqual(pads.scan(os.path.join(self.dir, "nowhere")), [])

    def test_blocked_when_the_node_cannot_be_opened(self):
        if os.geteuid() == 0:
            self.skipTest("root can open anything")
        os.chmod(self.tree["node"], 0)
        pad = self.scan()[0]
        self.assertFalse(pad.can_read)

    def test_the_real_tree_scans_without_error(self):
        for pad in pads.scan():
            self.assertTrue(pad.path.startswith("/dev/input/event"))


class Axes(unittest.TestCase):
    def test_xbox_like_triggers_rest_at_the_bottom(self):
        info = {code: (low if code in (2, 5) else 0, low, high, flat)
                for code, (low, high, flat) in XBOX_AXES.items()}
        layout = pads.classify_axes(info)
        self.assertEqual(layout["sticks"], [(0, 1), (3, 4)])
        self.assertEqual(layout["triggers"], [2, 5])
        self.assertEqual(layout["hats"], [0x10, 0x11])

    def test_playstation_like_pad_numbers_them_differently(self):
        # sticks at 128 of 0..255 on X, Y, Z, RZ; triggers on RX, RY resting at 0
        info = {0: (128, 0, 255, 0), 1: (128, 0, 255, 0), 2: (128, 0, 255, 0),
                3: (0, 0, 255, 0), 4: (0, 0, 255, 0), 5: (128, 0, 255, 0), 0x10: (0, -1, 1, 0),
                0x11: (0, -1, 1, 0)}
        layout = pads.classify_axes(info)
        self.assertEqual(layout["sticks"], [(0, 1), (2, 5)])
        self.assertEqual(layout["triggers"], [3, 4])

    def test_an_odd_axis_is_shown_as_a_bar(self):
        info = {0: (0, -100, 100, 0), 1: (0, -100, 100, 0), 6: (0, -100, 100, 0)}
        layout = pads.classify_axes(info)
        self.assertEqual(layout["sticks"], [(0, 1)])
        self.assertEqual(layout["triggers"], [6])


def recorded(*events) -> bytes:
    return b"".join(pads.event_bytes(*e) for e in events)


class Reading(Tree):
    def reader(self):
        reader = pads.PadReader(self.tree["node"], set(XBOX_KEYS), set(XBOX_AXES))
        self.addCleanup(reader.close)
        for code, (low, high, flat) in XBOX_AXES.items():
            rest = low if code in (2, 5) else (low + high) // 2 if low < 0 and high > 1 else 0
            reader.state.set_axis(code, rest, low, high, flat)
        reader.state.classify()
        return reader

    def play(self, reader, *events) -> bool:
        with open(self.tree["node"], "ab") as f:
            f.write(recorded(*events))
        return reader.poll()

    def test_buttons_press_and_release(self):
        reader = self.reader()
        self.assertTrue(self.play(reader, (EV_KEY, fakepad.BTN_SOUTH, 1), (EV_SYN, 0, 0)))
        self.assertTrue(reader.state.buttons[fakepad.BTN_SOUTH])
        self.play(reader, (EV_KEY, fakepad.BTN_SOUTH, 0))
        self.assertFalse(reader.state.buttons[fakepad.BTN_SOUTH])

    def test_stick_trigger_and_dpad(self):
        reader = self.reader()
        self.play(reader, (EV_ABS, 0, 32767), (EV_ABS, 1, -32768), (EV_ABS, 5, 1023),
                  (EV_ABS, 0x10, -1))
        x, y, mag = reader.state.stick((0, 1))
        self.assertAlmostEqual(x, 0.7071, places=2)      # the corner is pulled into the circle
        self.assertAlmostEqual(y, -0.7071, places=2)
        self.assertEqual(mag, 1.0)
        self.assertEqual(reader.state.trigger(5), 1.0)
        self.assertEqual(reader.state.trigger(2), 0.0)
        self.assertTrue(reader.state.dpad()["left"])
        self.assertFalse(reader.state.dpad()["right"])

    def test_events_the_pad_does_not_have_change_nothing(self):
        reader = self.reader()
        self.assertFalse(self.play(reader, (EV_ABS, 0x2F, 5), (EV_SYN, 0, 0)))

    def test_deadzone_the_kernel_reports(self):
        reader = self.reader()
        self.assertAlmostEqual(reader.state.flat((0, 1)), 128 / 32768, places=4)

    def test_rest_drift_is_the_widest_wander(self):
        reader = self.reader()
        reader.state.start_rest()
        self.play(reader, (EV_ABS, 0, 1600), (EV_ABS, 0, 100), (EV_ABS, 3, -300))
        drift = reader.state.finish_rest()
        self.assertAlmostEqual(drift[0], 1600 / 32768 * (1 + 0), places=1)
        self.assertGreater(drift[3], 0)
        self.assertEqual(pads.suggested_deadzone(0), 0)
        self.assertEqual(pads.suggested_deadzone(0.049), 6)

    def test_a_vanished_pad_is_noticed(self):
        r, w = os.pipe()
        os.close(w)
        reader = self.reader()
        os.close(reader.fd)
        reader.fd = r
        reader.poll()                          # EOF is not an error, the pad is just quiet
        self.assertFalse(reader.gone)

    def test_the_event_struct_is_the_kernels(self):
        self.assertEqual(pads.EVENT.size, 24 if struct.calcsize("l") == 8 else 16)
        self.assertEqual(len(pads.event_bytes(1, 2, 3)), pads.EVENT.size)


class Rumble(unittest.TestCase):
    def test_ioctl_numbers_match_linux_input_h(self):
        self.assertEqual(pads.EVIOCSFF, 0x40304580)
        self.assertEqual(pads.EVIOCRMFF, 0x40044581)
        self.assertEqual(pads.EVIOCGABS(0), 0x80184540)
        self.assertEqual(pads.EVIOCGKEY(96), 0x80604518)

    def test_the_effect_is_48_bytes_with_both_motors(self):
        raw = pads.rumble_effect(65535, 1000, 600)
        self.assertEqual(len(raw), 48)
        etype, effect_id, _direction, _button, _interval, length, _delay = \
            struct.unpack_from("=HhHHHHH", raw)
        self.assertEqual((etype, effect_id, length), (pads.FF_RUMBLE, -1, 600))
        self.assertEqual(struct.unpack_from("=HH", raw, 16), (65535, 1000))

    def test_magnitudes_are_clamped(self):
        raw = pads.rumble_effect(-5, 999999, 100)
        self.assertEqual(struct.unpack_from("=HH", raw, 16), (0, 65535))


class Fwupd8BitDo(unittest.TestCase):
    QUIRKS = ("[USB\\VID_2DC8&PID_6001]\nPlugin = ebitdo\nFlags = will-disappear\n"
              "[USB\\VID_1234&PID_0001]\nPlugin = other\n")

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="spark-controller-quirk-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_the_installed_list_answers_by_usb_id(self):
        plain = os.path.join(self.dir, "a.quirk")
        with open(plain, "w") as f:
            f.write(self.QUIRKS)
        zipped = os.path.join(self.dir, "b.quirk.gz")
        with gzip.open(zipped, "wt") as f:
            f.write(self.QUIRKS)
        for path in (plain, zipped):
            self.assertEqual(pads.fwupd_plugin_for(0x2DC8, 0x6001, path), "ebitdo")
            self.assertEqual(pads.fwupd_plugin_for(0x2DC8, 0x6002, path), "")
        self.assertEqual(pads.fwupd_plugin_for(0x2DC8, 0x6001, os.path.join(self.dir, "none")), "")

    def test_controllers_among_fwupd_devices(self):
        def device(**kw):
            base = {"DeviceId": kw.get("id", "x"), "Name": "Thing", "Version": "1", "Flags": []}
            base.update(kw)
            return FwDevice(base)
        pad = pads.Pad()
        pad.bus, pad.vendor = "usb", 0x2DC8
        devices = [device(Name="SN30 Pro", Plugin="ebitdo"),
                   device(Name="Receiver", VendorId="USB:0x2DC8"),
                   device(Name="Xbox Wireless Controller"),
                   device(Name="NVMe Controller"), device(Name="USB Controller"),
                   device(Name="System Firmware")]
        found = [d.name for d in pads.firmware_for_pads(devices, [pad])]
        self.assertEqual(found, ["SN30 Pro", "Receiver", "Xbox Wireless Controller"])

    def test_update_one_device_never_all(self):
        seen = []

        def runner(args, timeout):
            seen.append(args)
            return 0, "done\n"
        fw = Fwupd(runner, "/usr/bin/fwupdmgr")
        fw.update("abc123")
        fw.update()
        self.assertEqual(seen[0], ["/usr/bin/fwupdmgr", "update", "abc123", "-y", "--no-reboot-check"])
        self.assertEqual(seen[1], ["/usr/bin/fwupdmgr", "update", "-y", "--no-reboot-check"])

    def test_vendor_id_and_guids_are_read(self):
        d = FwDevice({"Name": "A", "VendorId": "USB:0x2DC8", "Guid": ["g1"], "Plugin": "ebitdo"})
        self.assertEqual((d.vendor_id, d.guids), ("USB:0x2DC8", ["g1"]))


def uinput_ok() -> bool:
    try:
        with fakepad.UinputPad("Spark Test Probe") as probe:
            found = probe.find(2.0)
            return found is not None and found.can_read
    except OSError:
        return False


@unittest.skipUnless(uinput_ok(), "needs /dev/uinput and a readable node for the virtual pad")
class VirtualPad(unittest.TestCase):
    """A real /dev/input node, made by uinput: the kernel's own ioctls and event format."""

    def test_buttons_and_sticks_through_a_real_node(self):
        with fakepad.UinputPad() as virtual:
            pad = virtual.find()
            self.assertIsNotNone(pad)
            self.assertEqual((pad.bus, pad.usb_id), ("usb", "1234:5678"))
            self.assertEqual(sorted(pad.axes), sorted(XBOX_AXES))
            reader = pads.PadReader(pad.path, pad.keys, pad.axes)
            self.addCleanup(reader.close)
            self.assertEqual(reader.state.layout["sticks"], [(0, 1), (3, 4)])
            self.assertEqual(reader.state.layout["triggers"], [2, 5])
            self.assertAlmostEqual(reader.state.flat((0, 1)), 128 / 32768, places=4)
            virtual.send(EV_KEY, fakepad.BTN_EAST, 1)
            virtual.send(EV_ABS, 0, 32767)
            virtual.send(EV_ABS, 2, 1023)
            virtual.sync()
            end = time.time() + 2
            while time.time() < end and not reader.state.buttons.get(fakepad.BTN_EAST):
                reader.poll()
                time.sleep(0.02)
            self.assertTrue(reader.state.buttons[fakepad.BTN_EAST])
            self.assertAlmostEqual(reader.state.axis(0), 1.0, places=2)
            self.assertEqual(reader.state.trigger(2), 1.0)
            # a pad that is already held when Spark opens it is read from the kernel's state
            late = pads.PadReader(pad.path, pad.keys, pad.axes)
            self.addCleanup(late.close)
            self.assertTrue(late.state.buttons[fakepad.BTN_EAST])
            self.assertEqual(late.state.trigger(2), 1.0)

    def test_it_leaves_the_list_when_unplugged(self):
        with fakepad.UinputPad("Spark Test Gone") as virtual:
            self.assertIsNotNone(virtual.find())
        time.sleep(0.3)
        self.assertNotIn("Spark Test Gone", [p.name for p in pads.scan()])


try:
    import tkinter as tk
    tk.Tk().destroy()
    DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
except Exception:  # noqa: BLE001
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(Tree):
    def setUp(self):
        super().setUp()
        self.hw = os.path.join(self.dir, "hwmon")
        support.fake_tree(self.hw)
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.dir, "config")
        for var, value in (("SPARK_CONTROLLER_PADS_SYS", self.tree["sys"]),
                           ("SPARK_CONTROLLER_PADS_DEV", self.tree["dev"]),
                           ("SPARK_CONTROLLER_PADS_POWER", self.tree["power"])):
            os.environ[var] = value
            self.addCleanup(os.environ.pop, var, None)

    def pump(self, app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def open_pads(self):
        from sparkcontroller.app import App
        app = App(Hwmon(self.hw), tab="pads", use_usb=False)
        self.addCleanup(app.close)
        self.pump(app, 0.5)
        return app, app.views["pads"]

    def test_a_pad_is_listed_drawn_and_follows_the_events(self):
        app, view = self.open_pads()
        self.assertEqual(len(view.tree.get_children()), 1)
        self.assertIsNotNone(view.reader)
        view.reader.state.set_axis(0, 0, -32768, 32767, 128)
        with open(self.tree["node"], "ab") as f:
            f.write(recorded((EV_KEY, fakepad.BTN_SOUTH, 1), (EV_ABS, 0, 20000), (EV_SYN, 0, 0)))
        self.pump(app, 0.3)
        self.assertTrue(view.reader.state.buttons[fakepad.BTN_SOUTH])
        self.assertGreater(len(view.canvas.find_all()), 25)

    def test_arriving_and_leaving_tears_and_is_announced(self):
        app, view = self.open_pads()
        torn = []
        view.app.glitch.now = lambda *a, **k: torn.append(k.get("strong", False))
        fakepad.add_input(self.dir, "event8", "8BitDo Pro Fake", XBOX_KEYS, XBOX_AXES, bus=3,
                          vendor=0x2DC8, product=0x6001)
        view.refresh()
        self.assertEqual(torn, [False])
        self.assertIn("8BitDo Pro Fake", view.list_note.cget("text"))
        shutil.rmtree(os.path.join(self.tree["sys"], "event8"))
        view.refresh()
        self.assertEqual(torn, [False, True])

    def test_no_access_says_what_to_do(self):
        if os.geteuid() == 0:
            self.skipTest("root can open anything")
        os.chmod(self.tree["node"], 0)
        app, view = self.open_pads()
        self.assertIsNone(view.reader)
        texts = [view.canvas.itemcget(i, "text") for i in view.canvas.find_all()
                 if view.canvas.type(i) == "text"]
        self.assertTrue(any("input" in x for x in texts))

    def test_no_pad_says_so(self):
        for entry in os.listdir(self.tree["sys"]):
            shutil.rmtree(os.path.join(self.tree["sys"], entry))
        app, view = self.open_pads()
        self.assertEqual(view.list_note.cget("text"), text.t("pads.none"))

    def test_the_text_fits_at_the_smallest_window(self):
        app, view = self.open_pads()
        app.root.geometry("%dx%d" % app.root.minsize())
        self.pump(app, 0.4)
        self.assertEqual(clipped(app.root), [])


if __name__ == "__main__":
    unittest.main()
