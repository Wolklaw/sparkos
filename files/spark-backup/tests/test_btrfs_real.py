"""Runs the real btrfs commands, but only on a throwaway filesystem you point it at:

    SPARK_BACKUP_TEST_BTRFS=/tmp/mnt/home python3 -m unittest tests/test_btrfs_real.py

The folder must be a user-owned subvolume of a loop-mounted image file (see the brief).
Skipped unless that variable is set. It refuses any folder that is not on a loop device, and
never /home."""

import datetime as dt
import os
import shutil
import subprocess
import unittest

import support  # noqa: F401
from sparkbackup import config, state
from sparkbackup.btrfs import Btrfs
from sparkbackup.engine import Backup
from sparkbackup.runner import Runner

ROOT = os.environ.get('SPARK_BACKUP_TEST_BTRFS', '')


def on_loop_device(path):
    if not path or not os.path.isdir(path) or os.path.realpath(path).startswith(('/home', '/var/home')):
        return False
    found = subprocess.run(['findmnt', '-no', 'SOURCE', '-T', path], capture_output=True,
                           text=True)
    return found.stdout.strip().startswith('/dev/loop')


SAFE = on_loop_device(ROOT)


@unittest.skipUnless(ROOT and SAFE and shutil.which('btrfs'), 'set SPARK_BACKUP_TEST_BTRFS')
class RealBtrfs(unittest.TestCase):
    def setUp(self):
        os.environ['SPARK_BACKUP_RUN_DIR'] = os.path.join(ROOT, '..', 'sb-run')
        os.environ['SPARK_BACKUP_STATE_DIR'] = os.path.join(ROOT, '..', 'sb-state')
        os.makedirs(os.path.join(ROOT, 'alex'), exist_ok=True)
        with open(os.path.join(ROOT, 'alex', 'f.txt'), 'w') as f:
            f.write('data')
        self.clock = dt.datetime.now().replace(microsecond=0)

    def tick(self):
        self.clock += dt.timedelta(seconds=1)
        return self.clock

    def test_snapshot_keep_and_remove(self):
        """Deleting a subvolume needs root (or the user_subvol_rm_allowed mount option), so as
        a normal user this checks everything up to the delete, and the delete only if allowed."""
        cfg = config.validate({'keep_local': 2})
        backup = Backup(cfg, Runner(), source=ROOT, drives=lambda: [], now=self.tick)
        self.assertTrue(Btrfs().is_subvolume(ROOT))
        for _ in range(4):
            report = backup.run()
            self.assertTrue(report['snapshot'], report)
        names = backup.local()
        self.assertGreaterEqual(len(names), 2)
        snap = os.path.join(ROOT, '.spark-backup', 'snapshots', names[-1])
        self.assertTrue(Btrfs().is_readonly(snap))
        self.assertTrue(Btrfs().is_subvolume(snap))
        with open(os.path.join(snap, 'alex', 'f.txt')) as f:
            self.assertEqual(f.read(), 'data')
        self.assertEqual(state.last_run()['snapshot'], names[-1])
        if os.geteuid() == 0:
            self.assertEqual(len(names), 2)
            for name in names:
                backup.remove_local(name)
            self.assertEqual(backup.local(), [])


if __name__ == '__main__':
    unittest.main()
