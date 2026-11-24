"""A backup run, driven with a fake Btrfs and a temporary folder. rsync is the real one."""

import datetime as dt
import os
import shutil
import tempfile
import unittest

import support
from support import FakeBtrfs, FakeRunner, drive, make_home
from sparkbackup import config, state
from sparkbackup.engine import Backup, BackupError, exclusive, to_remove
from sparkbackup.runner import Result


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-backup-engine-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        os.environ['SPARK_BACKUP_RUN_DIR'] = os.path.join(self.dir, 'run')
        os.environ['SPARK_BACKUP_STATE_DIR'] = os.path.join(self.dir, 'state')
        self.home = make_home(self.dir)
        self.clock = dt.datetime(2026, 11, 23, 2, 0, 0)
        self.runner = FakeRunner()
        self.fs = FakeBtrfs(self.runner)
        self.drives = []

    def tick(self):
        self.clock += dt.timedelta(days=1)
        return self.clock

    def backup(self, **cfg):
        data = config.default()
        data.update(cfg)
        return Backup(data, self.runner, self.fs, source=self.home, drives=lambda: self.drives,
                      now=self.tick, host='pc', mount_base=os.path.join(self.dir, 'mnt'))

    def usb(self, **kw):
        folder = os.path.join(self.dir, 'usb')
        os.makedirs(folder, exist_ok=True)
        return drive(mountpoint=folder, **kw), folder


class KeepRule(unittest.TestCase):
    NAMES = [f'2026-01-0{d}_020000' for d in range(1, 8)]

    def test_keeps_the_newest(self):
        self.assertEqual(to_remove(self.NAMES, 3), self.NAMES[:4])

    def test_never_removes_the_newest_even_at_zero(self):
        self.assertEqual(to_remove(self.NAMES, 0), self.NAMES[:-1])

    def test_protected_ones_stay(self):
        self.assertEqual(to_remove(self.NAMES, 2, protect=[self.NAMES[0], 'not-there']),
                         self.NAMES[1:5])

    def test_nothing_to_remove(self):
        self.assertEqual(to_remove(self.NAMES, 99), [])


class LocalOnly(Case):
    def test_a_run_makes_a_snapshot_and_records_it(self):
        report = self.backup().run()
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['copy'], 'none')
        snap = os.path.join(self.home, '.spark-backup', 'snapshots', report['snapshot'])
        self.assertTrue(os.path.exists(os.path.join(snap, 'alex', 'docs', 'note.txt')))
        self.assertEqual(state.last_run()['snapshot'], report['snapshot'])
        self.assertIsNone(state.read_progress())

    def test_keeps_only_the_limit(self):
        backup = self.backup(keep_local=3)
        for _ in range(6):
            report = backup.run()
        self.assertEqual(len(backup.local()), 3)
        self.assertEqual(backup.local()[-1], report['snapshot'])
        self.assertEqual(report['removed'], 1)

    def test_a_folder_that_is_not_a_subvolume_is_refused_and_logged(self):
        backup = self.backup()
        backup.source = os.path.join(self.dir, 'missing')
        report = backup.run()
        self.assertFalse(report['ok'])
        self.assertIn('not a Btrfs subvolume', report['error'])
        self.assertEqual(state.last_run()['ok'], False)

    def test_two_runs_at_once_are_refused(self):
        backup = self.backup()
        with exclusive(backup.lock_path()):
            with self.assertRaises(BackupError):
                backup.run()

    def test_only_our_own_snapshots_can_be_removed(self):
        backup = self.backup()
        backup.run()
        os.makedirs(os.path.join(self.home, '.spark-backup', 'snapshots', 'other'))
        for bad in ('other', '../alex', '', '2026-11-24_020000/../..', '/etc'):
            with self.subTest(name=bad), self.assertRaises(BackupError):
                backup.remove_local(bad)
        self.assertTrue(os.path.isdir(os.path.join(self.home, 'alex')))
        self.assertEqual(self.fs.deleted, [])

    def test_removing_one_deletes_that_one(self):
        backup = self.backup()
        name = backup.run()['snapshot']
        backup.remove_local(name)
        self.assertEqual(backup.local(), [])
        self.assertEqual(len(self.fs.deleted), 1)

    def test_snapshot_failure_is_reported(self):
        self.fs.snapshot = lambda source, dest: Result(1, '', 'ERROR: no space')
        report = self.backup().run()
        self.assertFalse(report['ok'])
        self.assertIn('no space', report['error'])


class Rsync(Case):
    def test_copy_is_made_and_shares_unchanged_files(self):
        self.runner.real = {'rsync'}
        d, usb = self.usb()
        self.drives = [d]
        backup = self.backup(target={'uuid': d.uuid, 'label': 'Backup', 'fstype': 'ext4'})
        first = backup.run()
        second = backup.run()
        self.assertTrue(first['ok'] and second['ok'], (first, second))
        root = os.path.join(usb, 'SparkBackup', 'pc')
        self.assertEqual(sorted(os.listdir(root)), [first['snapshot'], second['snapshot']])
        one = os.stat(os.path.join(root, first['snapshot'], 'alex', 'top.txt'))
        two = os.stat(os.path.join(root, second['snapshot'], 'alex', 'top.txt'))
        self.assertEqual(one.st_ino, two.st_ino)
        self.assertEqual(state.load_history()['last_copied'], second['snapshot'])

    def test_the_drive_keeps_its_own_limit(self):
        self.runner.real = {'rsync'}
        d, usb = self.usb()
        self.drives = [d]
        backup = self.backup(keep_local=2, keep_target=3,
                             target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ext4'})
        for _ in range(5):
            report = backup.run()
        root = os.path.join(usb, 'SparkBackup', 'pc')
        self.assertEqual(len(os.listdir(root)), 3)
        self.assertEqual(len(backup.local()), 2)
        self.assertEqual(report['removed_copies'], 1)

    def test_ntfs_uses_flags_that_work_on_it(self):
        d, _usb = self.usb(fstype='ntfs')
        self.drives = [d]
        self.runner.answers['rsync'] = Result(0)
        self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ntfs'}).run()
        args = self.runner.commands('rsync')[0]
        self.assertIn('--no-perms', args)
        self.assertNotIn('--acls', args)

    def test_a_failed_copy_leaves_no_partial_and_keeps_the_snapshot(self):
        d, usb = self.usb()
        self.drives = [d]
        self.runner.answers['rsync'] = Result(11, '', 'rsync: write failed: No space left')
        backup = self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ext4'})
        report = backup.run()
        self.assertFalse(report['ok'])
        self.assertEqual(report['copy'], 'failed')
        self.assertIn('No space', report['error'])
        self.assertEqual(os.listdir(os.path.join(usb, 'SparkBackup', 'pc')), [])
        self.assertEqual(len(backup.local()), 1)

    def test_some_unreadable_files_are_a_warning_not_a_failure(self):
        d, _usb = self.usb()
        self.drives = [d]
        self.runner.answers['rsync'] = Result(23, '', 'rsync: send_files failed to open "x"\n')
        report = self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ext4'}).run()
        self.assertTrue(report['ok'])
        self.assertEqual(report['warnings'], 1)

    def test_old_partial_is_cleaned(self):
        self.runner.real = {'rsync'}
        d, usb = self.usb()
        self.drives = [d]
        backup = self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ext4'})
        stale = os.path.join(usb, 'SparkBackup', 'pc', '2026-11-25_020000.partial')
        os.makedirs(stale)
        with open(os.path.join(stale, 'junk'), 'w') as f:
            f.write('x')
        self.assertTrue(backup.run()['ok'])
        self.assertFalse(os.path.exists(os.path.join(stale, 'junk')))

    def test_excluded_folders_are_not_copied(self):
        self.runner.real = {'rsync'}
        d, usb = self.usb()
        self.drives = [d]
        os.makedirs(os.path.join(self.home, 'alex', '.cache'))
        with open(os.path.join(self.home, 'alex', '.cache', 'x'), 'w') as f:
            f.write('x')
        report = self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ext4'}).run()
        root = os.path.join(usb, 'SparkBackup', 'pc', report['snapshot'], 'alex')
        self.assertTrue(os.path.exists(os.path.join(root, 'top.txt')))
        self.assertFalse(os.path.exists(os.path.join(root, '.cache')))


class Drives(Case):
    def test_an_unplugged_drive_keeps_the_local_snapshot(self):
        report = self.backup(target={'uuid': 'GONE-0000', 'label': 'x', 'fstype': 'ext4'}).run()
        self.assertEqual(report['copy'], 'unplugged')
        self.assertTrue(report['ok'])

    def test_a_drive_that_cannot_hold_backups_is_not_written_to(self):
        d, usb = self.usb(fstype='vfat', method='', reason='refuse.fat')
        self.drives = [d]
        report = self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'vfat'}).run()
        self.assertEqual(report['copy'], 'failed')
        self.assertEqual(os.listdir(usb), [])
        self.assertEqual(self.runner.commands('rsync'), [])

    def test_an_unmounted_drive_is_mounted_by_uuid_and_unmounted_after(self):
        d, _usb = self.usb()
        d.mountpoint = None
        self.drives = [d]
        self.runner.answers['rsync'] = Result(0)
        self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ext4'}).run()
        mount = self.runner.commands('mount')[0]
        self.assertIn(f'UUID={d.uuid}', mount)
        self.assertIn('nosuid,nodev', mount)
        self.assertEqual(len(self.runner.commands('umount')), 1)

    def test_a_drive_that_will_not_mount_is_reported(self):
        d, _usb = self.usb()
        d.mountpoint = None
        self.drives = [d]
        self.runner.answers['mount'] = Result(32, '', 'mount: wrong fs type')
        report = self.backup(target={'uuid': d.uuid, 'label': 'x', 'fstype': 'ext4'}).run()
        self.assertEqual(report['copy'], 'failed')
        self.assertIn('wrong fs type', report['error'])


class BtrfsTarget(Case):
    def target(self):
        d, usb = self.usb(fstype='btrfs', method='btrfs')
        self.drives = [d]
        return {'uuid': d.uuid, 'label': 'x', 'fstype': 'btrfs'}, usb

    def test_first_copy_is_a_full_send_then_incremental(self):
        target, usb = self.target()
        backup = self.backup(target=target)
        first = backup.run()
        second = backup.run()
        sends = [c for c in self.runner.calls if c[0] == 'send']
        self.assertEqual(sends[0][2], '')
        self.assertTrue(sends[1][2].endswith(first['snapshot']), sends[1])
        self.assertTrue(second['ok'])
        self.assertEqual(state.load_history()['last_copied'], second['snapshot'])

    def test_a_failed_receive_removes_only_the_half_copy(self):
        target, usb = self.target()
        backup = self.backup(target=target)
        self.assertTrue(backup.run()['ok'])
        self.fs.fail_receive = True
        report = backup.run()
        self.assertEqual(report['copy'], 'failed')
        root = os.path.join(usb, 'SparkBackup', 'pc')
        self.assertEqual(len(os.listdir(root)), 1)
        self.assertEqual(len(backup.local()), 2)

    def test_an_unfinished_copy_is_not_counted(self):
        target, usb = self.target()
        backup = self.backup(target=target)
        root = os.path.join(usb, 'SparkBackup', 'pc')
        os.makedirs(os.path.join(root, '2026-01-01_020000'))
        self.fs.unfinished.add('2026-01-01_020000')
        self.assertEqual(backup.copy_names(root, 'btrfs'), [])
        self.assertEqual(backup.copy_names(root, 'btrfs', check=False), ['2026-01-01_020000'])

    def test_the_last_copied_snapshot_is_kept_when_the_drive_was_away(self):
        target, usb = self.target()
        backup = self.backup(keep_local=1, target=target)
        copied = backup.run()['snapshot']
        self.drives = []
        for _ in range(3):
            report = backup.run()
        self.assertEqual(report['copy'], 'unplugged')
        self.assertEqual(backup.local(), [copied, report['snapshot']])


if __name__ == '__main__':
    unittest.main()
