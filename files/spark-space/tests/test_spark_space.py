"""Spark Space without a window: the scanner, the treemap layout, the safety rules, the trash,
file kinds, hints and the drive list. Everything works in temporary folders; nothing outside
them is written."""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-space-{var.lower()}-'))
os.environ['SPARK_SPACE_REDUCED_MOTION'] = '1'

from sparkspace import drives, hints, kinds, safety, scan, trash  # noqa: E402
from sparkspace.treemap import squarify  # noqa: E402

FIXTURES = os.path.join(HERE, 'fixtures')


def write(path: str, size: int) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(os.urandom(size) if size < 4096 else b'\1' * size)
    return path


def disk(path: str) -> int:
    return os.lstat(path).st_blocks * 512


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='spark-space-test-'))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for dirpath, dirnames, _files in os.walk(self.tmp):
            for d in dirnames:
                try:
                    os.chmod(os.path.join(dirpath, d), 0o755)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)


class Scanning(Temp):
    def test_sizes_add_up(self):
        a = write(os.path.join(self.tmp, 'a', 'one.bin'), 100_000)
        b = write(os.path.join(self.tmp, 'a', 'deep', 'two.bin'), 300_000)
        c = write(os.path.join(self.tmp, 'three.txt'), 10)
        s = scan.scan(self.tmp, threads=3)
        self.assertTrue(s.finished.is_set())
        files = disk(a) + disk(b) + disk(c)
        folders = sum(disk(p) for p in (self.tmp, os.path.join(self.tmp, 'a'),
                                        os.path.join(self.tmp, 'a', 'deep')))
        self.assertEqual(s.root.size, files + folders)
        self.assertEqual(s.root.count, 3)
        node_a = scan.find(s.root, os.path.join(self.tmp, 'a'))
        self.assertIsNotNone(node_a)
        self.assertEqual(node_a.count, 2)
        self.assertEqual(scan.find(s.root, b).path(), b)
        self.assertEqual(s.root.sorted_children()[0].name, 'a')
        self.assertEqual(s.unreadable_count, 0)

    def test_hard_link_counted_once(self):
        a = write(os.path.join(self.tmp, 'x', 'big.bin'), 200_000)
        os.link(a, os.path.join(self.tmp, 'y.bin'))
        s = scan.scan(self.tmp)
        shared = [n for n, _ in scan.iter_files(s.root) if n.flags & scan.SHARED]
        self.assertEqual(len(shared), 1)
        self.assertEqual(sum(n.size for n, _ in scan.iter_files(s.root)), disk(a))

    def test_symlinks_not_followed(self):
        outside = os.path.realpath(tempfile.mkdtemp(prefix='spark-space-outside-'))
        self.addCleanup(shutil.rmtree, outside, True)
        write(os.path.join(outside, 'huge.bin'), 500_000)
        os.symlink(outside, os.path.join(self.tmp, 'link-to-dir'))
        os.symlink(os.path.join(outside, 'huge.bin'), os.path.join(self.tmp, 'link-to-file'))
        s = scan.scan(self.tmp)
        self.assertLess(s.root.size, 100_000)
        for child in s.root.children:
            self.assertFalse(child.is_dir)
            self.assertTrue(child.flags & scan.LINK)

    @unittest.skipIf(os.name != 'posix' or os.geteuid() == 0, "root reads everything")
    def test_unreadable_folder_is_counted_not_fatal(self):
        write(os.path.join(self.tmp, 'ok', 'f.bin'), 5000)
        locked = os.path.join(self.tmp, 'locked')
        write(os.path.join(locked, 'secret.bin'), 50_000)
        os.chmod(locked, 0)
        s = scan.scan(self.tmp)
        self.assertTrue(s.finished.is_set())
        self.assertEqual(s.unreadable_count, 1)
        self.assertEqual(s.unreadable, [locked])
        node = scan.find(s.root, locked)
        self.assertTrue(node.flags & scan.UNREADABLE)

    def test_other_filesystems_left_out(self):
        write(os.path.join(self.tmp, 'mine', 'f.bin'), 5000)
        write(os.path.join(self.tmp, 'mnt', 'big.bin'), 400_000)
        mnt = os.path.join(self.tmp, 'mnt')
        s = scan.scan(self.tmp, mount_targets=[mnt])
        node = scan.find(s.root, mnt)
        self.assertTrue(node.flags & scan.OTHER_FS)
        self.assertEqual(node.size, 0)
        self.assertEqual(s.skipped_mounts, [mnt])
        whole = scan.scan(self.tmp, mount_targets=[mnt], one_filesystem=False)
        self.assertGreater(whole.root.size, 400_000)

    def test_cancel(self):
        for i in range(300):
            write(os.path.join(self.tmp, f'd{i % 30}', f'sub{i}', 'f.txt'), 10)
        s = scan.Scanner(self.tmp, threads=2)
        s.cancel()                       # cancelled before it starts: finishes, partial
        s.start()
        self.assertTrue(s.wait(10))
        self.assertTrue(s.cancelled.is_set())
        self.assertLess(s.progress()[0], 300)

    def test_missing_folder_raises(self):
        with self.assertRaises(OSError):
            scan.Scanner(os.path.join(self.tmp, 'nope')).start()

    def test_summary_and_remove(self):
        write(os.path.join(self.tmp, 'v', 'film.mkv'), 300_000)
        write(os.path.join(self.tmp, 'v', 'clip.mp4'), 100_000)
        write(os.path.join(self.tmp, 'm', 'model.gguf'), 200_000)
        write(os.path.join(self.tmp, 'steamapps', 'common', 'game', 'data.pak'), 150_000)
        s = scan.scan(self.tmp)
        summary = scan.summarize(s.root)
        self.assertEqual(summary.largest[0][0].name, 'film.mkv')
        self.assertEqual(summary.kinds['video'][1], 2)
        self.assertEqual(summary.kinds['models'][1], 1)
        self.assertEqual(summary.kinds['games'][1], 1)
        only = scan.summarize(s.root, kind='models')
        self.assertEqual([f.name for f, _ in only.largest], ['model.gguf'])
        film = scan.find(s.root, os.path.join(self.tmp, 'v', 'film.mkv'))
        before, v_before = s.root.size, film.parent.size
        scan.remove(film)
        self.assertEqual(s.root.size, before - film.size)
        self.assertEqual(scan.find(s.root, os.path.join(self.tmp, 'v')).size,
                         v_before - film.size)
        self.assertIsNone(scan.find(s.root, os.path.join(self.tmp, 'v', 'film.mkv')))


class Treemap(unittest.TestCase):
    def check(self, sizes, w, h):
        rects = squarify(sizes, 10, 20, w, h)
        self.assertEqual(len(rects), len(sizes))
        total = sum(sizes)
        for size, (x, y, rw, rh) in zip(sizes, rects):
            self.assertGreaterEqual(x, 10 - 1e-6)
            self.assertGreaterEqual(y, 20 - 1e-6)
            self.assertLessEqual(x + rw, 10 + w + 1e-6)
            self.assertLessEqual(y + rh, 20 + h + 1e-6)
            self.assertAlmostEqual(rw * rh, size / total * w * h, delta=w * h * 1e-6)
        return rects

    def test_areas_match_sizes(self):
        self.check([6, 6, 4, 3, 2, 2, 1], 600, 400)
        self.check([1], 300, 200)
        self.check([100, 1, 1, 1], 50, 500)
        self.check(list(range(200, 0, -1)), 1000, 700)

    def test_blocks_do_not_overlap(self):
        rects = self.check([5, 4, 3, 2, 1, 1], 400, 300)
        for i, (x, y, w, h) in enumerate(rects):
            for (x2, y2, w2, h2) in rects[i + 1:]:
                overlap_w = min(x + w, x2 + w2) - max(x, x2)
                overlap_h = min(y + h, y2 + h2) - max(y, y2)
                self.assertFalse(overlap_w > 1e-6 and overlap_h > 1e-6)

    def test_empty(self):
        self.assertEqual(squarify([], 0, 0, 100, 100), [])


class Safety(Temp):
    def table(self, read_only_at=None):
        mounts = [drives.Mount('/', 'btrfs', '/dev/x', False)]
        if read_only_at:
            mounts.append(drives.Mount(read_only_at, 'ext4', '/dev/y', True))
        return mounts

    def test_d_drive_never(self):
        for path in ('/var/mnt/d', '/var/mnt/d/Games/x.iso', '/mnt/d/a'):
            self.assertEqual(safety.trash_refusal(path, table=self.table(), windows=[]),
                             'd_drive', path)
        windows = [{'letter': 'D', 'mountpoint': os.path.join(self.tmp, 'dd'), 'mode': 'rw'}]
        f = write(os.path.join(self.tmp, 'dd', 'file.bin'), 10)
        self.assertEqual(safety.trash_refusal(f, table=self.table(), windows=windows), 'd_drive')
        with self.assertRaises(safety.Refused):
            safety.move_to_trash(f, table=self.table(), windows=windows)
        self.assertTrue(os.path.exists(f))

    def test_read_only_mount(self):
        ro = os.path.join(self.tmp, 'ro')
        f = write(os.path.join(ro, 'file.bin'), 10)
        self.assertEqual(safety.trash_refusal(f, table=self.table(ro), windows=[]), 'read_only')
        with self.assertRaises(safety.Refused) as caught:
            safety.move_to_trash(f, table=self.table(ro), windows=[])
        self.assertEqual(caught.exception.reason, 'read_only')
        self.assertTrue(os.path.exists(f))

    @unittest.skipIf(os.name != 'posix' or os.geteuid() == 0, "root can write anywhere")
    def test_not_writable_parent(self):
        f = write(os.path.join(self.tmp, 'locked', 'file.bin'), 10)
        os.chmod(os.path.dirname(f), 0o555)
        self.assertEqual(safety.trash_refusal(f, table=self.table(), windows=[]),
                         'not_writable')

    def test_protected_places(self):
        table = self.table()
        self.assertEqual(safety.trash_refusal(os.path.expanduser('~'), table=table,
                                              windows=[]), 'protected')
        self.assertEqual(safety.trash_refusal('/usr', table=table, windows=[]), 'protected')
        self.assertEqual(safety.trash_refusal(self.tmp, scan_root=self.tmp, table=table,
                                              windows=[]), 'protected')
        self.assertEqual(safety.trash_refusal(os.path.join(self.tmp, 'gone'), table=table,
                                              windows=[]), 'gone')

    def test_windows_system_folders(self):
        c = os.path.join(self.tmp, 'c')
        write(os.path.join(c, 'Windows', 'notepad.exe'), 10)
        user = write(os.path.join(c, 'Users', 'me', 'big.iso'), 10)
        table = [drives.Mount('/', 'btrfs', '/dev/x', False),
                 drives.Mount(c, 'ntfs3', '/dev/z', False)]
        self.assertEqual(safety.trash_refusal(os.path.join(c, 'Windows'), table=table,
                                              windows=[]), 'windows_system')
        self.assertEqual(safety.trash_refusal(os.path.join(c, 'pagefile.sys'), table=table,
                                              windows=[]), 'windows_system')
        self.assertIsNone(safety.trash_refusal(user, table=table, windows=[]))

    def test_move_to_trash_in_a_temp_home(self):
        data = os.path.join(self.tmp, 'data')
        old = os.environ.get('XDG_DATA_HOME')
        os.environ['XDG_DATA_HOME'] = data
        self.addCleanup(lambda: os.environ.__setitem__('XDG_DATA_HOME', old) if old
                        else os.environ.pop('XDG_DATA_HOME', None))
        f = write(os.path.join(self.tmp, 'stuff', 'old video.mkv'), 1000)
        where = safety.move_to_trash(f, windows=[])
        self.assertFalse(os.path.exists(f))
        self.assertEqual(where, os.path.join(data, 'Trash', 'files', 'old video.mkv'))
        with open(os.path.join(data, 'Trash', 'info', 'old video.mkv.trashinfo')) as info:
            text = info.read()
        self.assertIn('Path=' + f.replace(' ', '%20'), text)
        # the same name again goes in beside it, nothing overwritten
        f2 = write(os.path.join(self.tmp, 'stuff', 'old video.mkv'), 10)
        self.assertNotEqual(safety.move_to_trash(f2, windows=[]), where)
        # and something already in the trash isn't moved again
        self.assertEqual(safety.trash_refusal(where, windows=[]), 'in_trash')

    def test_no_permanent_delete_anywhere(self):
        """The package has no code that deletes files; only os.rename into a trash folder."""
        pkg = os.path.join(os.path.dirname(HERE), 'sparkspace')
        for name in os.listdir(pkg):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(pkg, name), encoding='utf-8') as f:
                code = f.read()
            for banned in ('rmtree', 'os.remove(', 'shutil.move', 'os.rmdir', 'unlink('):
                if name == 'trash.py' and banned == 'unlink(':
                    continue        # trash.py unlinks its own .trashinfo when a move fails
                self.assertNotIn(banned, code, f"{name}: {banned}")


class Kinds(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(kinds.kind_of('a.MKV'), 'video')
        self.assertEqual(kinds.kind_of('backup.tar.gz'), 'archives')
        self.assertEqual(kinds.kind_of('llama.gguf'), 'models')
        self.assertEqual(kinds.kind_of('photo.jpeg'), 'images')
        self.assertEqual(kinds.kind_of('data.pak', in_games=True), 'games')
        self.assertEqual(kinds.kind_of('README'), 'other')
        self.assertTrue(kinds.is_game_dir('steamapps'))


class Hints(Temp):
    def test_hints_found(self):
        write(os.path.join(self.tmp, 'Steam', 'steamapps', 'shadercache', '730', 'a.bin'),
              2_000_000)
        write(os.path.join(self.tmp, '.var', 'app', 'org.example.App', 'cache', 'c.bin'),
              2_000_000)
        write(os.path.join(self.tmp, 'tiny', 'steamapps', 'shadercache', 'x'), 10)
        s = scan.scan(self.tmp)
        found = {h.key: h for h in hints.find_hints(s.root)}
        self.assertIn('shadercache', found)
        self.assertIn('app_cache', found)
        self.assertEqual(len([h for h in hints.find_hints(s.root)
                              if h.key == 'shadercache']), 1)     # the tiny one is skipped
        self.assertEqual(found['shadercache'].command, '')


class Drives(unittest.TestCase):
    def test_mountinfo_and_windows_state(self):
        table = drives.mounts(os.path.join(FIXTURES, 'mountinfo'))
        by_target = {m.target: m for m in table}
        self.assertTrue(by_target['/var/mnt/d'].read_only)
        self.assertFalse(by_target['/var/mnt/c'].read_only)
        self.assertEqual(by_target['/var/home'].fstype, 'btrfs')
        self.assertEqual(by_target['/var/mnt/my disk'].target, '/var/mnt/my disk')
        with open(os.path.join(FIXTURES, 'windows-drives.json')) as f:
            windows = json.load(f)
        if isinstance(windows, dict):
            windows = windows.get('drives', [])
        found = drives.list_drives(table, windows)
        paths = [d.path for d in found]
        self.assertIn('/var', paths)
        self.assertNotIn('/var/home', paths)          # same partition as /var: one drive
        self.assertNotIn('/usr', paths)
        letters = {d.letter: d for d in found if d.letter}
        self.assertEqual(sorted(letters), ['C', 'D', 'E'])
        self.assertTrue(letters['D'].read_only)
        self.assertEqual(letters['D'].label, 'Scrap')
        self.assertFalse(letters['E'].mounted)
        self.assertTrue(letters['E'].problem)
        self.assertEqual(drives.mount_of('/var/mnt/c/Users/x', table).target, '/var/mnt/c')

    def test_windows_state_file_from_env(self):
        tmp = tempfile.mkdtemp(prefix='spark-space-win-')
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, 'w.json')
        with open(path, 'w') as f:
            f.write('not json')
        self.assertEqual(drives.windows_drives(path), [])
        self.assertEqual(drives.windows_drives(os.path.join(tmp, 'missing.json')), [])


if __name__ == '__main__':
    unittest.main()
