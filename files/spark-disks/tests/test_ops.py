"""ops.py is the last gate before a disk. These tests use a backend that only records what it was
asked, so a refused action can be shown to have touched nothing."""

import unittest

import support
from sparkdisks import safety
from sparkdisks.ops import BadInput, Ops, Refused, check_label, resize_modes
from support import GB, MIB, FakeBackend, find, tree


def make(**kw):
    backend = FakeBackend(**kw)
    return Ops(backend, tree), backend


class Refusals(unittest.TestCase):
    def test_nothing_reaches_the_backend_for_d_or_the_system(self):
        """Every change, on every row that is D: or the running system's, with every confirmation
        a caller could pass: refused, and the backend was never asked."""
        ops, backend = make()
        locked = [n for d in tree() for n in d.walk() if n.is_d or n.is_system]
        self.assertGreaterEqual(len(locked), 5)
        for node in locked:
            for confirm in ('', node.path.split('/')[-1], '/dev/sparkn0'):
                calls = [
                    lambda: ops.format(node.path, 'ext4', 'x', False, confirm),
                    lambda: ops.delete(node.path, confirm),
                    lambda: ops.resize(node.path, 10 * MIB, confirm),
                    lambda: ops.erase(node.path, 'gpt', confirm),
                    lambda: ops.image_target(node.path),
                ]
                if node.is_d or node.is_system:
                    calls.append(lambda: ops.unmount(node.path))
                for call in calls:
                    with self.subTest(node=node.path, confirm=confirm):
                        with self.assertRaises(Refused):
                            call()
        self.assertEqual(backend.calls, [])

    def test_d_cannot_be_mounted_or_ejected_either(self):
        ops, backend = make()
        for call in (lambda: ops.mount('/dev/sparksa1'), lambda: ops.eject('/dev/sparksa')):
            with self.assertRaises(Refused):
                call()
        self.assertFalse(backend.changed_anything())

    def test_d_can_be_asked_about_smart(self):
        ops, backend = make()
        ops.smart('/dev/sparksa')
        self.assertEqual(backend.calls, [('smart', '/dev/sparksa')])

    def test_a_path_that_is_not_there(self):
        ops, backend = make()
        with self.assertRaises(Refused) as caught:
            ops.format('/dev/sparknothing', 'ext4')
        self.assertEqual(caught.exception.verdict.key, 'refuse.gone')
        self.assertEqual(backend.calls, [])

    def test_hard_cases_need_the_device_name(self):
        ops, backend = make()
        for confirm in ('', 'sparksc1 ', '/dev/sparksc1', 'sparksc2', 'SPARKSC1'):
            with self.assertRaises(Refused) as caught:
                ops.format('/dev/sparksc1', 'ext4', '', False, confirm)
            self.assertEqual(caught.exception.verdict.key, 'refuse.typed')
        self.assertEqual(backend.calls, [])
        ops.format('/dev/sparksc1', 'ext4', 'Data', False, 'sparksc1')
        self.assertEqual(backend.calls, [('format', '/dev/sparksc1', 'ext4', 'Data', False)])

    def test_games_partition_on_the_system_disk_is_hard_but_possible(self):
        ops, backend = make()
        with self.assertRaises(Refused):
            ops.delete('/dev/sparkn0p2')
        self.assertEqual(backend.calls, [])
        ops.delete('/dev/sparkn0p2', 'sparkn0p2')
        self.assertEqual(backend.calls, [('unmount', '/dev/sparkn0p2'), ('delete', '/dev/sparkn0p2')])

    def test_a_stale_window_cannot_act_on_what_changed(self):
        """The window picked /dev/sparksb2 when it was a stick partition; now the drive is gone."""
        backend = FakeBackend()
        gone = {'on': False}

        def lister():
            disks = tree()
            return [d for d in disks if d.path != '/dev/sparksb'] if gone['on'] else disks
        ops = Ops(backend, lister)
        gone['on'] = True
        with self.assertRaises(Refused):
            ops.format('/dev/sparksb2', 'ext4')
        self.assertEqual(backend.calls, [])


class Actions(unittest.TestCase):
    def test_mount_and_unmount(self):
        ops, backend = make()
        self.assertEqual(ops.mount('/dev/sparksb2'), '/run/media/x/sparksb2')
        ops.unmount('/dev/sparksb1')
        self.assertEqual(backend.calls, [('mount', '/dev/sparksb2'), ('unmount', '/dev/sparksb1')])

    def test_format_unmounts_first(self):
        ops, backend = make()
        ops.format('/dev/sparksb1', 'exfat', 'STICK')
        self.assertEqual(backend.calls[0], ('unmount', '/dev/sparksb1'))
        self.assertEqual(backend.calls[1], ('format', '/dev/sparksb1', 'exfat', 'STICK', False))

    def test_format_with_a_missing_tool(self):
        ops, backend = make(formats=['ext4'])
        with self.assertRaises(BadInput) as caught:
            ops.format('/dev/sparksb2', 'ntfs')
        self.assertEqual(caught.exception.key, 'bad.fs_unavailable')
        self.assertEqual(backend.calls, [])

    def test_create_partition(self):
        ops, backend = make()
        disks = tree()
        free = [c for c in find(disks, '/dev/sparksb').children if c.kind == 'free'][-1]
        ops.create('/dev/sparksb', free.start, 2 * GB // MIB * MIB, 'ext4', 'New')
        self.assertEqual(backend.calls, [('create', '/dev/sparksb', free.start,
                                          2 * GB // MIB * MIB, 'ext4', 'New', 'gpt')])

    def test_create_too_big_or_unaligned(self):
        ops, backend = make()
        free = [c for c in find(tree(), '/dev/sparksb').children if c.kind == 'free'][-1]
        for size in (free.size + MIB, 1000, MIB + 5, 0):
            with self.assertRaises(BadInput):
                ops.create('/dev/sparksb', free.start, size, 'ext4')
        with self.assertRaises(Refused):
            ops.create('/dev/sparksb', free.start + 5, MIB, 'ext4')    # no free block starts there
        self.assertEqual(backend.calls, [])

    def test_create_on_an_internal_drive_needs_the_name(self):
        ops, backend = make()
        free = [c for c in find(tree(), '/dev/sparksc').children if c.kind == 'free'][-1]
        with self.assertRaises(Refused):
            ops.create('/dev/sparksc', free.start, 10 * MIB, 'ext4')
        ops.create('/dev/sparksc', free.start, 10 * MIB, 'ext4', '', 'sparksc')
        self.assertEqual(len(backend.calls), 1)

    def test_create_on_d_is_refused(self):
        ops, backend = make()
        disks = tree()
        d_free = [c for c in find(disks, '/dev/sparksa').children if c.kind == 'free']
        start = d_free[-1].start if d_free else MIB
        with self.assertRaises(Refused):
            ops.create('/dev/sparksa', start, MIB, 'ext4', '', 'sparksa')
        self.assertEqual(backend.calls, [])

    def test_erase_a_stick(self):
        ops, backend = make()
        ops.erase('/dev/sparksb', 'dos')
        self.assertEqual(backend.calls, [('unmount', '/dev/sparksb1'), ('new_table', '/dev/sparksb', 'dos')])
        with self.assertRaises(BadInput):
            ops.erase('/dev/sparksb', 'amiga')

    def test_eject(self):
        ops, backend = make()
        ops.eject('/dev/sparksb')
        self.assertEqual(backend.calls, [('unmount', '/dev/sparksb1'), ('eject', '/dev/sparksb')])

    def test_smart_calls(self):
        ops, backend = make()
        ops.smart_update('/dev/sparkn0')
        ops.smart_selftest('/dev/sparkn0')
        self.assertEqual(backend.calls, [('smart_update', '/dev/sparkn0'), ('selftest', '/dev/sparkn0')])


class Resize(unittest.TestCase):
    def room(self, path):
        ops, _b = make()
        disks = tree()
        return ops.max_resize(find(disks, path), disks)

    def test_growing_resizes_the_partition_then_the_file_system(self):
        ops, backend = make()
        top = self.room('/dev/sparksb2')
        self.assertGreater(top, 2 * GB)
        ops.resize('/dev/sparksb2', 3 * GB)
        names = [c[0] for c in backend.calls if c[0].startswith('resize')]
        self.assertEqual(names, ['resize_partition', 'resize_fs'])

    def test_shrinking_resizes_the_file_system_then_the_partition(self):
        ops, backend = make(resize_mode=30)                 # can shrink while mounted
        ops.resize('/dev/sparksb1', 2 * GB)
        names = [c[0] for c in backend.calls if c[0] in ('unmount', 'resize_partition', 'resize_fs')]
        self.assertEqual(names, ['resize_fs', 'resize_partition'])

    def test_offline_only_shrink_unmounts_first(self):
        ops, backend = make(resize_mode=22)                 # ext4: shrink needs it unmounted
        ops.resize('/dev/sparksb1', 2 * GB)
        names = [c[0] for c in backend.calls if c[0] in ('unmount', 'resize_partition', 'resize_fs')]
        self.assertEqual(names, ['unmount', 'resize_fs', 'resize_partition'])

    def test_too_big_too_small_and_same(self):
        ops, backend = make()
        with self.assertRaises(BadInput):
            ops.resize('/dev/sparksb2', self.room('/dev/sparksb2') + 10 * MIB)
        with self.assertRaises(BadInput) as caught:
            ops.resize('/dev/sparksb1', 500 * 10 ** 6)       # holds 1 GB
        self.assertEqual(caught.exception.key, 'bad.too_small')
        with self.assertRaises(BadInput):
            ops.resize('/dev/sparksb2', 2 * GB)               # not a change (after MiB rounding)
        self.assertFalse(backend.changed_anything())

    def test_a_file_system_that_cannot_resize(self):
        ops, backend = make(resize_mode=0)
        with self.assertRaises(BadInput) as caught:
            ops.resize('/dev/sparksb2', 1 * GB)
        self.assertEqual(caught.exception.key, 'bad.cant_resize')
        self.assertFalse(backend.changed_anything())

    def test_modes(self):
        self.assertEqual(resize_modes(22, True, True), (True, False))       # ext4 grows mounted
        self.assertEqual(resize_modes(22, True, False), (True, True))       # but shrinks unmounted
        self.assertEqual(resize_modes(30, True, False), (True, False))      # online shrink
        self.assertEqual(resize_modes(6, False, True), (True, False))
        self.assertEqual(resize_modes(0, False, True), (False, False))
        self.assertEqual(resize_modes(2, True, True), (False, True))


class Labels(unittest.TestCase):
    def test_limits(self):
        check_label('ext4', 'a' * 16)
        check_label('vfat', 'STICK')
        for fs, label in (('ext4', 'a' * 17), ('vfat', 'x' * 12), ('xfs', 'y' * 13),
                          ('vfat', 'a/b'), ('ext4', 'a\nb'), ('exfat', 'é' * 8)):
            with self.subTest(fs=fs, label=label):
                with self.assertRaises(BadInput):
                    check_label(fs, label)

    def test_unknown_fs_is_not_limited(self):
        check_label('zfs', 'a' * 100)


class Everything(unittest.TestCase):
    def test_every_allowed_verdict_has_a_matching_ops_method(self):
        """safety.ACTIONS and the Ops methods stay in step."""
        ops, _b = make()
        for action in safety.ACTIONS:
            name = {'create': 'create', 'write_image': 'image_target'}.get(action, action)
            self.assertTrue(hasattr(ops, name), action)


if __name__ == '__main__':
    unittest.main()
