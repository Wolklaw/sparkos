"""The tree of drives: parsing lsblk, free space, and which rows are the system's, Windows' or D:."""

import json
import os
import tempfile
import unittest

import support
from sparkdisks import model
from support import GB, MIB, find, tree


class Parse(unittest.TestCase):
    def test_loop_devices_are_left_out_unless_asked(self):
        paths = [d.path for d in tree()]
        self.assertNotIn('/dev/loop0', paths)
        shown = model.parse_lsblk(json.dumps(support.sample()), show_loop=True)
        self.assertIn('/dev/loop0', [d.path for d in shown])

    def test_zram_and_optical_are_not_drives(self):
        data = {'blockdevices': [
            {'name': 'zram0', 'path': '/dev/zram0', 'type': 'disk', 'size': 8 * GB},
            {'name': 'sr0', 'path': '/dev/sr0', 'type': 'rom', 'size': GB},
            support.disk('sparkx', GB, [])]}
        self.assertEqual([d.path for d in tree(data)], ['/dev/sparkx'])

    def test_sizes_and_starts_are_bytes(self):
        stick = find(tree(), '/dev/sparksb1')
        self.assertEqual(stick.start, MIB)
        self.assertEqual(stick.size, 4 * GB)
        self.assertEqual(stick.mounts, ['/run/media/x/stick'])
        self.assertEqual(stick.fsused, GB)

    def test_garbage_numbers_do_not_crash(self):
        data = {'blockdevices': [{'name': 'sparkx', 'path': '/dev/sparkx', 'type': 'disk',
                                  'size': 'abc', 'children': [{'name': 'p', 'type': 'part',
                                                               'size': None, 'start': 'x'}]}]}
        self.assertEqual(tree(data)[0].size, 0)


class FreeSpace(unittest.TestCase):
    def test_gap_after_the_last_partition(self):
        stick = find(tree(), '/dev/sparksb')
        free = [c for c in stick.children if c.kind == 'free']
        self.assertTrue(free)
        last = free[-1]
        self.assertEqual(last.start % MIB, 0)
        self.assertGreater(last.size, 5 * GB)
        self.assertEqual(last.parent, '/dev/sparksb')

    def test_free_never_overlaps_a_partition(self):
        for d in tree():
            parts = [c for c in d.children if c.kind == 'part']
            for f in (c for c in d.children if c.kind == 'free'):
                for p in parts:
                    self.assertFalse(f.start < p.end and p.start < f.end, (d.path, f.start))

    def test_a_drive_without_a_table_has_none(self):
        raw = support.disk('sparkraw', 4 * GB, [], pttype='')
        raw['pttype'] = None
        self.assertEqual([c for c in tree({'blockdevices': [raw]})[0].children], [])

    def test_extended_partition_counts_as_taken(self):
        container = support.part('sparkx1', 4 * GB, 1, '', parttype='0x5')
        d = support.disk('sparkx', 8 * GB, [container], pttype='dos')
        node = find(tree({'blockdevices': [d]}), '/dev/sparkx1')
        self.assertTrue(node.container)


class Marks(unittest.TestCase):
    def setUp(self):
        self.t = tree()

    def test_system_disk_and_its_system_partitions(self):
        self.assertTrue(find(self.t, '/dev/sparkn0').is_system)
        self.assertTrue(find(self.t, '/dev/sparkn0p1').is_system)       # /boot/efi
        self.assertTrue(find(self.t, '/dev/sparkn0p3').is_system)       # / and /var
        self.assertFalse(find(self.t, '/dev/sparkn0p2').is_system)      # the Games partition

    def test_windows_partitions(self):
        self.assertTrue(find(self.t, '/dev/sparkn0p2').windows)
        self.assertTrue(find(self.t, '/dev/sparksc2').windows)
        self.assertFalse(find(self.t, '/dev/sparksc1').windows)

    def test_d_and_its_whole_drive(self):
        self.assertTrue(find(self.t, '/dev/sparksa1').is_d)
        self.assertTrue(find(self.t, '/dev/sparksa').is_d)
        self.assertFalse(find(self.t, '/dev/sparksc').is_d)
        self.assertFalse(find(self.t, '/dev/sparkn0').is_d)

    def test_d_found_by_the_windows_drive_list(self):
        data = support.sample()
        data['blockdevices'][2]['children'][0]['mountpoints'] = [None]
        listing = [{'letter': 'D', 'device': '/dev/sparksc1'}]
        disks = tree(data, listing)
        self.assertTrue(find(disks, '/dev/sparksc1').is_d)
        self.assertTrue(find(disks, '/dev/sparksc').is_d)
        self.assertTrue(find(disks, '/dev/sparksc2').is_d)      # same drive: locked too
        self.assertEqual(find(disks, '/dev/sparksc1').letter, 'D')

    def test_d_found_by_partuuid_in_lowercase(self):
        listing = [{'letter': 'd', 'partuuid': 'SPARKSC1-UUID'}]
        self.assertTrue(find(tree(None, listing), '/dev/sparksc1').is_d)

    def test_other_letters_mark_windows_not_d(self):
        listing = [{'letter': 'E', 'device': '/dev/sparksc1'}]
        part = find(tree(None, listing), '/dev/sparksc1')
        self.assertTrue(part.windows)
        self.assertFalse(part.is_d)

    def test_a_usb_stick_is_never_marked_windows(self):
        data = support.sample()
        data['blockdevices'][3]['children'][1]['fstype'] = 'ntfs'
        data['blockdevices'][3]['children'][1]['parttype'] = support.BASIC_DATA
        self.assertFalse(find(tree(data), '/dev/sparksb2').windows)

    def test_windows_drive_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'w.json')
            self.assertEqual(model.load_windows_drives(path), [])        # missing
            with open(path, 'w') as f:
                f.write('{broken')
            self.assertEqual(model.load_windows_drives(path), [])        # broken
            with open(path, 'w') as f:
                json.dump([{'letter': 'D'}, 'junk'], f)
            self.assertEqual(model.load_windows_drives(path), [{'letter': 'D'}])


class Sizes(unittest.TestCase):
    def test_human_size(self):
        self.assertEqual(model.human_size(0), '0 B')
        self.assertEqual(model.human_size(1500), '1.5 KB')
        self.assertEqual(model.human_size(4 * GB), '4.0 GB')
        self.assertEqual(model.human_size(2 * 10 ** 12), '2.0 TB')

    def test_parse_size(self):
        cases = {'20': 20 * GB, '20 GB': 20 * GB, '512MB': 512 * 10 ** 6, '1,5 Go': int(1.5 * GB),
                 '1.5 gb': int(1.5 * GB), '2 GiB': 2 * 1024 ** 3, '100 Mo': 100 * 10 ** 6,
                 ' 3 T ': 3 * 10 ** 12}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(model.parse_size(text), want)
        for bad in ('', 'abc', 'GB', '12 parsecs', '1.2.3'):
            with self.subTest(bad=bad):
                self.assertIsNone(model.parse_size(bad))


if __name__ == '__main__':
    unittest.main()
