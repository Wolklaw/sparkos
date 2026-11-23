"""fwupd output parsing and the RGB command lines, from invented output."""

import json
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401
from sparkcontroller import fwupd, rgb

DEVICES = {"Devices": [
    {"Name": "System Firmware", "DeviceId": "aa", "Vendor": "ExampleBoard Inc.", "Version": "3602",
     "Flags": ["internal", "updatable", "needs-reboot"], "Plugin": "uefi_capsule"},
    {"Name": "Fancy NVMe 1TB", "DeviceId": "bb", "Vendor": "Example", "Version": "EXA01",
     "Flags": ["internal"]},
    {"Name": "Dock", "DeviceId": "cc", "Vendor": "Example", "Version": "1.0",
     "Flags": ["updatable"]},
    {"Name": "Nameless", "DeviceId": "dd", "Version": ""},
    "junk",
]}
UPDATES = {"Devices": [
    {"Name": "System Firmware", "DeviceId": "aa", "Vendor": "ExampleBoard Inc.", "Version": "3602",
     "Flags": ["updatable"],
     "Releases": [{"Version": "3701", "Summary": "Fixes", "Urgency": "medium",
                   "Description": "<p>Stability.</p><ul><li>One</li><li>Two</li></ul>",
                   "Size": 33554432, "RemoteId": "lvfs"}]},
    {"Name": "No release", "Version": "1"},
]}


class Parsing(unittest.TestCase):
    def test_devices_have_names_and_updatable_come_first(self):
        got = fwupd.parse_devices(json.dumps(DEVICES))
        self.assertEqual([d.id for d in got], ['aa', 'cc', 'bb'])

    def test_generic_names_get_the_vendor(self):
        first = fwupd.parse_devices(json.dumps(DEVICES))[0]
        self.assertEqual(first.title, 'ExampleBoard Inc. System Firmware')
        self.assertTrue(first.updatable and first.needs_reboot and first.internal)

    def test_notice_before_the_json(self):
        out = "Waiting for authentication...\n" + json.dumps(DEVICES)
        self.assertEqual(len(fwupd.parse_devices(out)), 3)

    def test_no_json_is_an_error(self):
        with self.assertRaises(ValueError):
            fwupd.parse_devices("Nothing here")

    def test_updates_carry_their_release(self):
        got = fwupd.parse_updates(json.dumps(UPDATES))
        self.assertEqual(len(got), 1)
        release = got[0].releases[0]
        self.assertEqual((release.version, release.size), ('3701', 33554432))
        self.assertEqual(release.description, "Stability.\n- One\n- Two")


class Runner:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, args, timeout):
        self.calls.append(args)
        return self.answers.pop(0)


class Commands(unittest.TestCase):
    def test_devices_and_updates(self):
        run = Runner((0, json.dumps(DEVICES)), (0, json.dumps(UPDATES)))
        fw = fwupd.Fwupd(run, '/usr/bin/fwupdmgr')
        self.assertEqual(len(fw.devices()), 3)
        self.assertEqual(len(fw.updates()), 1)
        self.assertIn('--json', run.calls[0])

    def test_nothing_to_update_is_not_an_error(self):
        fw = fwupd.Fwupd(Runner((2, 'No updatable devices')), '/usr/bin/fwupdmgr')
        self.assertEqual(fw.updates(), [])

    def test_failures_say_why(self):
        fw = fwupd.Fwupd(Runner((1, 'first\nCould not reach the daemon\n')), '/usr/bin/fwupdmgr')
        with self.assertRaisesRegex(RuntimeError, 'Could not reach'):
            fw.devices()

    def test_not_installed(self):
        self.assertFalse(fwupd.Fwupd(Runner(), '').available)


OPENRGB = """\
0: ASUS Aura Motherboard
  Type:           Motherboard
  Description:    AURA Motherboard
  Modes: [Direct] Static Breathing 'Spectrum Cycle' Off
  Zones: 'Addressable'
1: Logitech G502 SE
  Type:           Mouse
  Modes: Direct 'Static' Cycle
"""


class OpenRgb(unittest.TestCase):
    def test_parse_list(self):
        got = rgb.parse_openrgb_list(OPENRGB)
        self.assertEqual([(d['index'], d['name'], d['type']) for d in got],
                         [(0, 'ASUS Aura Motherboard', 'Motherboard'),
                          (1, 'Logitech G502 SE', 'Mouse')])
        self.assertEqual(got[0]['modes'], ['Direct', 'Static', 'Breathing', 'Spectrum Cycle',
                                           'Off'])

    def test_static_colour(self):
        modes = ['Direct', 'Static']
        args = rgb.openrgb_args(1, {"effect": "static", "color": "#FF2E88", "speed": "normal"},
                                modes)
        self.assertEqual(args, ['--device', '1', '--mode', 'Static', '--color', 'FF2E88'])

    def test_spectrum_has_no_colour_but_a_speed(self):
        args = rgb.openrgb_args(0, {"effect": "spectrum", "color": "#000000", "speed": "fast"},
                                ['Spectrum Cycle'])
        self.assertEqual(args, ['--device', '0', '--mode', 'Spectrum Cycle', '--speed', '90'])

    def test_off_without_an_off_mode_is_black_static(self):
        args = rgb.openrgb_args(1, {"effect": "off", "color": "#ffffff", "speed": "slow"},
                                ['Direct', 'Static'])
        self.assertEqual(args[-2:], ['--color', '000000'])

    def test_a_missing_effect_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            rgb.openrgb_args(0, {"effect": "breathing", "color": "#ffffff", "speed": "slow"},
                             ['Direct'])


class Settings(unittest.TestCase):
    def test_clean_setting(self):
        self.assertEqual(rgb.clean_setting({"effect": "nope", "color": "red", "speed": 3}),
                         rgb.DEFAULT_SETTING)
        got = rgb.clean_setting({"effect": "fade", "color": "#ABCDEF", "speed": "fast"})
        self.assertEqual(got, {"effect": "fade", "color": "#abcdef", "speed": "fast"})
        self.assertEqual(rgb.clean_setting(None), rgb.DEFAULT_SETTING)

    def test_save_and_load_per_device(self):
        folder = tempfile.mkdtemp(prefix='spark-controller-rgb-')
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = os.path.join(folder, 'rgb.json')
        rgb.save_saved({"openrgb:ASUS": {"effect": "static", "color": "#112233",
                                         "speed": "slow"}}, path)
        self.assertEqual(rgb.load_saved(path)["openrgb:ASUS"]["color"], "#112233")
        self.assertEqual(rgb.load_saved(os.path.join(folder, 'none.json')), {})

    def test_hex_to_rgb(self):
        self.assertEqual(rgb.hex_to_rgb('#ff2e88'), (255, 46, 136))


if __name__ == '__main__':
    unittest.main()
