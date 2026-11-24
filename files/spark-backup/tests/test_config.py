"""Settings, the schedule, the drive list, and the helper (with a fake systemctl)."""

import datetime as dt
import json
import os
import shutil
import tempfile
import unittest

import support
from sparkbackup import config, helper, schedule, targets


class Settings(unittest.TestCase):
    def test_defaults_are_off(self):
        cfg = config.validate({})
        self.assertFalse(cfg['enabled'])
        self.assertIsNone(cfg['target'])
        self.assertEqual((cfg['keep_local'], cfg['keep_target']), (7, 14))

    def test_a_good_file_round_trips(self):
        data = {'enabled': True, 'schedule': {'every': 'weekly', 'time': '03:30', 'weekday': 'Fri'},
                'keep_local': 5, 'keep_target': 30,
                'target': {'uuid': 'AAAA-1111', 'label': 'Backup', 'fstype': 'ext4'}}
        out = config.validate(json.loads(json.dumps(data)))
        self.assertEqual(out['schedule'], data['schedule'])
        self.assertEqual(out['target']['uuid'], 'AAAA-1111')

    def test_bad_values_are_refused(self):
        bad = [[], {'enabled': 'yes'}, {'keep_local': 0}, {'keep_local': 1000},
               {'keep_local': '5'}, {'keep_target': True},
               {'schedule': {'every': 'hourly'}}, {'schedule': {'time': '25:00'}},
               {'schedule': {'time': '2:00'}}, {'schedule': {'weekday': 'Funday'}},
               {'target': {'uuid': '../etc'}}, {'target': {'uuid': 'a b c d'}}, {'target': 5},
               {'target': {'uuid': 'AAAA-1111', 'label': 5}}]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(config.ConfigError):
                config.validate(data)

    def test_loads_refuses_junk_and_huge_files(self):
        for text in ('', 'not json', '[1]', ' ' * (config.MAX_FILE_BYTES + 5)):
            with self.subTest(text=text[:10]), self.assertRaises(config.ConfigError):
                config.loads(text)

    def test_a_missing_file_means_defaults(self):
        self.assertFalse(config.load('/nonexistent/spark-backup.json')['enabled'])

    def test_save_then_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'sub', 'config.json')
            config.save(config.validate({'enabled': True}), path)
            self.assertTrue(config.load(path)['enabled'])


class Schedule(unittest.TestCase):
    def cfg(self, **sched):
        return config.validate({'schedule': sched})

    def test_calendar_and_dropin(self):
        self.assertEqual(schedule.calendar(self.cfg(every='daily', time='02:00')),
                         '*-*-* 02:00:00')
        self.assertEqual(schedule.calendar(self.cfg(every='weekly', time='04:15', weekday='Wed')),
                         'Wed *-*-* 04:15:00')
        text = schedule.dropin(self.cfg())
        self.assertIn('OnCalendar=\n', text)
        self.assertIn('OnCalendar=*-*-* 02:00:00', text)

    def test_next_run(self):
        now = dt.datetime(2026, 11, 23, 10, 0)           # a Monday
        self.assertEqual(schedule.next_run(self.cfg(time='02:00'), now),
                         dt.datetime(2026, 11, 24, 2, 0))
        self.assertEqual(schedule.next_run(self.cfg(time='23:00'), now),
                         dt.datetime(2026, 11, 23, 23, 0))
        weekly = self.cfg(every='weekly', time='02:00', weekday='Mon')
        self.assertEqual(schedule.next_run(weekly, now), dt.datetime(2026, 11, 30, 2, 0))
        weekly = self.cfg(every='weekly', time='02:00', weekday='Sun')
        self.assertEqual(schedule.next_run(weekly, now), dt.datetime(2026, 11, 29, 2, 0))


LSBLK = {'blockdevices': [
    {'path': '/dev/nvme1n1', 'type': 'disk', 'model': 'Fast', 'rm': False, 'hotplug': False,
     'children': [
         {'path': '/dev/nvme1n1p4', 'type': 'part', 'fstype': 'btrfs', 'uuid': 'SYS-UUID',
          'label': 'sparkos', 'size': 500 * 1024 ** 3, 'fsavail': 10, 'mountpoints': ['/var', '/']},
         {'path': '/dev/nvme1n1p1', 'type': 'part', 'fstype': 'ntfs', 'uuid': 'NTFS-1',
          'label': 'E', 'size': 900 * 1024 ** 3, 'fsavail': 100, 'mountpoints': [None]}]},
    {'path': '/dev/sda', 'type': 'disk', 'model': 'USB Stick', 'rm': True, 'hotplug': True,
     'children': [
         {'path': '/dev/sda1', 'type': 'part', 'fstype': 'ext4', 'uuid': 'EXT-1', 'label': 'Away',
          'size': 200 * 1024 ** 3, 'fsavail': 150, 'mountpoints': ['/run/media/x/Away']},
         {'path': '/dev/sda2', 'type': 'part', 'fstype': 'vfat', 'uuid': 'FAT-1', 'label': 'Fat',
          'size': 64 * 1024 ** 3, 'mountpoints': [None]},
         {'path': '/dev/sda3', 'type': 'part', 'fstype': 'vfat', 'uuid': 'EFI-1', 'label': 'EFI',
          'size': 600 * 1024 ** 2, 'mountpoints': ['/boot/efi']},
         {'path': '/dev/sda4', 'type': 'part', 'fstype': 'swap', 'uuid': 'SW-1', 'size': 2 ** 30,
          'mountpoints': ['[SWAP]']}]},
    {'path': '/dev/sr0', 'type': 'rom', 'fstype': 'iso9660', 'uuid': 'CD', 'size': 1}]}


class Drives(unittest.TestCase):
    def setUp(self):
        self.drives = {d.uuid: d for d in targets.parse_drives(json.dumps(LSBLK), 'SYS-UUID')}

    def test_who_can_hold_backups(self):
        self.assertEqual(self.drives['EXT-1'].method, 'rsync')
        self.assertEqual(self.drives['NTFS-1'].method, 'rsync')
        self.assertTrue(self.drives['EXT-1'].removable)
        self.assertFalse(self.drives['NTFS-1'].removable)

    def test_the_system_disk_is_refused(self):
        self.assertFalse(self.drives['SYS-UUID'].usable)
        self.assertEqual(self.drives['SYS-UUID'].reason, 'refuse.system')

    def test_fat_is_refused_and_efi_swap_cd_are_not_listed(self):
        self.assertEqual(self.drives['FAT-1'].reason, 'refuse.fat')
        for gone in ('EFI-1', 'SW-1', 'CD'):
            self.assertNotIn(gone, self.drives)

    def test_usable_drives_come_first(self):
        listed = targets.parse_drives(json.dumps(LSBLK), 'SYS-UUID')
        flags = [d.usable for d in listed]
        self.assertEqual(flags, sorted(flags, reverse=True))

    def test_junk_gives_an_empty_list(self):
        for text in ('', 'x', '{}', '{"blockdevices": 5}'):
            self.assertEqual(targets.parse_drives(text), [])

    def test_the_backup_folder_is_ours_alone(self):
        self.assertEqual(targets.backup_root('/mnt/x', 'pc'), '/mnt/x/SparkBackup/pc')


class Helper(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-backup-helper-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        os.environ['SPARK_BACKUP_CONFIG'] = os.path.join(self.dir, 'etc', 'config.json')
        os.environ['SPARK_BACKUP_DROPIN'] = os.path.join(self.dir, 'timer.d', 'schedule.conf')
        os.environ['SPARK_BACKUP_SOURCE'] = os.path.join(self.dir, 'home')
        os.environ['SPARK_BACKUP_RUN_DIR'] = os.path.join(self.dir, 'run')
        for var in ('SPARK_BACKUP_CONFIG', 'SPARK_BACKUP_SOURCE', 'SPARK_BACKUP_RUN_DIR'):
            self.addCleanup(os.environ.pop, var, None)
        self.addCleanup(os.environ.pop, 'SPARK_BACKUP_DROPIN', None)
        self.calls = []

    def systemctl(self, *args):
        self.calls.append(args)
        return 0

    def test_saving_writes_the_file_the_timer_and_enables_it(self):
        text = json.dumps({'enabled': True, 'schedule': {'every': 'daily', 'time': '01:30'}})
        self.assertEqual(helper.save_config(text, self.systemctl), 0)
        self.assertTrue(config.load()['enabled'])
        with open(os.environ['SPARK_BACKUP_DROPIN']) as f:
            self.assertIn('01:30:00', f.read())
        self.assertEqual(self.calls, [('daemon-reload',), ('enable', '--now', 'spark-backup.timer')])

    def test_turning_off_disables_the_timer(self):
        text = json.dumps({'enabled': False})
        self.assertEqual(helper.save_config(text, self.systemctl), 0)
        self.assertEqual(self.calls[-1], ('disable', '--now', 'spark-backup.timer'))

    def test_bad_settings_write_nothing(self):
        self.assertEqual(helper.save_config('{"keep_local": -3}', self.systemctl), 2)
        self.assertFalse(os.path.exists(os.environ['SPARK_BACKUP_CONFIG']))
        self.assertEqual(self.calls, [])

    def test_a_failed_enable_is_reported(self):
        self.assertEqual(helper.save_config('{"enabled": true}', lambda *a: 1), 1)

    def test_usage(self):
        self.assertEqual(helper.main([]), 64)
        self.assertEqual(helper.main(['remove-snapshot']), 64)
        self.assertEqual(helper.main(['rm', '-rf', '/']), 64)

    def test_remove_refuses_anything_but_our_names(self):
        for name in ('..', '/home', 'x', '2026-01-01_020000/..'):
            with self.subTest(name=name):
                self.assertEqual(helper.main(['remove-snapshot', name]), 2)


if __name__ == '__main__':
    unittest.main()
