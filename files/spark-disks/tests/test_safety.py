"""The rules, one case at a time, on made-up drives that look like the owner's PC."""

import unittest

import support
from sparkdisks import safety
from support import GB, find, tree


class Rules(unittest.TestCase):
    def setUp(self):
        self.t = tree()

    def check(self, action, path):
        return safety.check(action, find(self.t, path), self.t)

    def free(self, disk_path):
        return [c for c in find(self.t, disk_path).children if c.kind == 'free'][-1]

    def test_d_is_look_only_for_every_action(self):
        for path in ('/dev/sparksa', '/dev/sparksa1'):
            for action in safety.ACTIONS:
                if action == 'smart':
                    continue
                with self.subTest(path=path, action=action):
                    v = self.check(action, path)
                    self.assertFalse(v.allowed)
                    self.assertEqual(v.key, 'refuse.d')

    def test_smart_is_allowed_everywhere_on_a_drive(self):
        for path in ('/dev/sparksa', '/dev/sparkn0', '/dev/sparksb', '/dev/sparksc'):
            self.assertTrue(self.check('smart', path).allowed, path)
        self.assertFalse(self.check('smart', '/dev/sparksb1').allowed)    # a partition, not a drive

    def test_the_running_system_cannot_be_touched(self):
        for action in ('unmount', 'format', 'delete', 'resize'):
            with self.subTest(action=action):
                for path in ('/dev/sparkn0p1', '/dev/sparkn0p3'):
                    v = self.check(action, path)
                    self.assertFalse(v.allowed, (action, path))
                    self.assertEqual(v.key, 'refuse.system')

    def test_system_disk_cannot_be_erased_or_written(self):
        self.assertEqual(self.check('erase', '/dev/sparkn0').key, 'refuse.system_disk')
        self.assertFalse(self.check('write_image', '/dev/sparkn0').allowed)
        self.assertFalse(self.check('format', '/dev/sparkn0').allowed)

    def test_games_partition_on_the_system_disk_needs_the_name_typed(self):
        for action in ('format', 'delete', 'resize'):
            v = self.check(action, '/dev/sparkn0p2')
            self.assertTrue(v.allowed, action)
            self.assertTrue(v.hard, action)

    def test_new_partition_on_the_system_disk_is_hard(self):
        v = safety.check('create', self.free('/dev/sparkn0'), self.t)
        self.assertTrue(v.allowed)
        self.assertTrue(v.hard)

    def test_windows_partition_on_another_drive_is_hard(self):
        self.assertTrue(self.check('format', '/dev/sparksc2').hard)

    def test_any_internal_drive_is_hard(self):
        self.assertTrue(self.check('format', '/dev/sparksc1').hard)
        self.assertTrue(self.check('erase', '/dev/sparksc').hard)

    def test_a_usb_stick_is_an_ordinary_confirmation(self):
        for action in ('format', 'delete', 'resize'):
            v = self.check(action, '/dev/sparksb2')
            self.assertTrue(v.allowed)
            self.assertEqual(v.level, 'ordinary')
        self.assertEqual(self.check('erase', '/dev/sparksb').level, 'ordinary')

    def test_image_only_to_removable_drives(self):
        self.assertTrue(self.check('write_image', '/dev/sparksb').allowed)
        self.assertEqual(self.check('write_image', '/dev/sparksc').key, 'refuse.not_removable')
        self.assertEqual(self.check('write_image', '/dev/sparksb1').key, 'refuse.not_drive')

    def test_eject_only_removable(self):
        self.assertTrue(self.check('eject', '/dev/sparksb').allowed)
        self.assertEqual(self.check('eject', '/dev/sparksc').key, 'refuse.not_removable')

    def test_mount_and_unmount_states(self):
        self.assertEqual(self.check('mount', '/dev/sparksb1').key, 'refuse.already_mounted')
        self.assertTrue(self.check('mount', '/dev/sparksb2').allowed)
        self.assertTrue(self.check('unmount', '/dev/sparksb1').allowed)
        self.assertEqual(self.check('unmount', '/dev/sparksb2').key, 'refuse.not_mounted')
        self.assertEqual(self.check('mount', '/dev/sparkn0p1').key, 'refuse.already_mounted')

    def test_mounted_stick_partition_gets_a_note(self):
        self.assertIn('note.unmounted_first', self.check('format', '/dev/sparksb1').notes)

    def test_only_free_space_takes_a_new_partition(self):
        self.assertEqual(self.check('create', '/dev/sparksb1').key, 'refuse.not_free')
        self.assertTrue(safety.check('create', self.free('/dev/sparksb'), self.t).allowed)

    def test_mbr_stops_at_four_primary_partitions(self):
        data = support.sample()
        stick = data['blockdevices'][3]
        stick['pttype'] = 'dos'
        stick['children'] = [support.part(f'sparksb{i}', GB, 1 + 2000 * i, 'ext4') for i in range(1, 5)]
        disks = tree(data)
        free = [c for c in find(disks, '/dev/sparksb').children if c.kind == 'free'][-1]
        self.assertEqual(safety.check('create', free, disks).key, 'refuse.four_primary')

    def test_free_space_cannot_be_formatted_or_deleted(self):
        free = self.free('/dev/sparksb')
        for action in ('format', 'delete', 'resize', 'mount', 'unmount'):
            self.assertFalse(safety.check(action, free, self.t).allowed, action)

    def test_a_drive_with_a_table_is_erased_not_formatted(self):
        self.assertEqual(self.check('format', '/dev/sparksb').key, 'refuse.has_table')

    def test_stacked_and_container_nodes_are_left_alone(self):
        data = support.sample()
        stick = data['blockdevices'][3]
        stick['children'][1]['children'] = [{'name': 'luks', 'path': '/dev/mapper/luks',
                                             'type': 'crypt', 'size': GB, 'mountpoints': [None]}]
        disks = tree(data)
        self.assertEqual(safety.check('format', find(disks, '/dev/mapper/luks'), disks).key,
                         'refuse.stacked')

    def test_gone_and_unknown(self):
        self.assertEqual(safety.check('format', None, self.t).key, 'refuse.gone')
        self.assertEqual(self.check('explode', '/dev/sparksb1').key, 'refuse.unknown')

    def test_tags(self):
        self.assertEqual(safety.tag_for(find(self.t, '/dev/sparksa1')), 'tag.d')
        self.assertEqual(safety.tag_for(find(self.t, '/dev/sparkn0')), 'tag.system')
        self.assertEqual(safety.tag_for(find(self.t, '/dev/sparkn0p2')), 'tag.windows')
        self.assertEqual(safety.tag_for(find(self.t, '/dev/sparksb')), 'tag.usb')
        self.assertEqual(safety.tag_for(find(self.t, '/dev/sparksc1')), '')


if __name__ == '__main__':
    unittest.main()
