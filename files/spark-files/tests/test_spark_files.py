"""Spark Files tests. Plain unittest:

    python -m unittest discover -s files/spark-files/tests -v

File operation, trash, listing, thumbnail, service menu and search tests need no display.
Window tests need one (on CI: xvfb-run) and are skipped without it; the D-Bus tests need a
session bus (dbus-run-session) and are skipped without one.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-files-{var.lower()}-')
os.environ['SPARK_FILES_REDUCED_MOTION'] = '1'

from sparkfiles import VERSION, ops, servicemenus, thumbs, trash  # noqa: E402
from sparkfiles.listing import (filter_entries, list_dir, natural_key, read_entry,  # noqa: E402
                                sort_entries, type_label)
from sparkfiles.search import Search  # noqa: E402
from sparkfiles.text import t  # noqa: E402
from sparkfiles.xdnd import paths_to_uris, uris_to_paths  # noqa: E402

ROOT = os.getuid() == 0


def readb(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def have_display() -> bool:
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:     # noqa: BLE001
        return False


def have_bus() -> bool:
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        return False
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio
        Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return True
    except Exception:     # noqa: BLE001
        return False


DISPLAY = have_display()
BUS = have_bus()


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-files-test-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def path(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts)

    def write(self, rel: str, data: bytes = b'x') -> str:
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
        return p

    def run_job(self, job: ops.Job, timeout: float = 30) -> ops.Job:
        job.start()
        job.thread.join(timeout)
        self.assertFalse(job.thread.is_alive(), "the job didn't finish")
        return job


# ─── names ───────────────────────────────────────────────────

class Names(unittest.TestCase):
    def test_split_ext(self):
        self.assertEqual(ops.split_ext('photo.jpg'), ('photo', '.jpg'))
        self.assertEqual(ops.split_ext('backup.tar.gz'), ('backup', '.tar.gz'))
        self.assertEqual(ops.split_ext('.bashrc'), ('.bashrc', ''))
        self.assertEqual(ops.split_ext('README'), ('README', ''))

    def test_name_problems(self):
        self.assertEqual(ops.name_problem(''), 'name.empty')
        self.assertEqual(ops.name_problem('   '), 'name.empty')
        self.assertEqual(ops.name_problem('a/b'), 'name.slash')
        self.assertEqual(ops.name_problem('..'), 'name.dots')
        self.assertEqual(ops.name_problem('é' * 200), 'name.long')
        self.assertIsNone(ops.name_problem('Rapport final (v2).docx'))

    def test_batch_pattern(self):
        names = ['b.jpg', 'a.JPG', 'notes.tar.gz']
        self.assertEqual(ops.batch_names(names, 'Trip ##'),
                         ['Trip 01.jpg', 'Trip 02.JPG', 'Trip 03.tar.gz'])
        self.assertEqual(ops.batch_names(names, '* old', 5), ['b old.jpg', 'a old.JPG',
                                                               'notes old.tar.gz'])
        self.assertEqual(ops.batch_names(['x.txt'], 'n#', 9), ['n9.txt'])

    def test_find_replace(self):
        self.assertEqual(ops.find_replace_names(['IMG_1.jpg', 'img_2.jpg'], 'img_', 'Photo '),
                         ['Photo 1.jpg', 'Photo 2.jpg'])
        self.assertEqual(ops.find_replace_names(['IMG_1.jpg', 'img_2.jpg'], 'img_', 'P', True),
                         ['IMG_1.jpg', 'P2.jpg'])
        self.assertEqual(ops.find_replace_names(['a.b'], '.', '\\1'), ['a\\1b'])


class FreeName(TempDir):
    def test_numbers_go_up(self):
        self.write('a.txt')
        self.assertEqual(ops.free_name(self.dir, 'a.txt'), 'a (2).txt')
        self.write('a (2).txt')
        self.assertEqual(ops.free_name(self.dir, 'a.txt'), 'a (3).txt')
        self.assertEqual(ops.free_name(self.dir, 'a (2).txt'), 'a (3).txt')
        os.mkdir(self.path('dir.d'))
        self.assertEqual(ops.free_name(self.dir, 'dir.d', is_dir=True), 'dir.d (2)')


class Rename(TempDir):
    def test_rename_and_refuse_taken(self):
        a = self.write('a.txt', b'A')
        self.write('b.txt', b'B')
        with self.assertRaises(FileExistsError):
            ops.rename(a, 'b.txt')
        new = ops.rename(a, 'c.txt')
        self.assertEqual(readb(new), b'A')
        with self.assertRaises(ValueError):
            ops.rename(new, 'x/y')

    def test_case_only(self):
        a = self.write('photo.jpg')
        self.assertEqual(ops.rename(a, 'Photo.jpg'), self.path('Photo.jpg'))
        self.assertTrue(os.path.exists(self.path('Photo.jpg')))

    def test_new_folder_and_file(self):
        d = ops.new_folder(self.dir, 'New folder')
        self.assertTrue(os.path.isdir(d))
        with self.assertRaises(FileExistsError):
            ops.new_folder(self.dir, 'New folder')
        f = ops.new_file(self.dir, 'n.txt')
        self.assertEqual(os.path.getsize(f), 0)
        with self.assertRaises(FileExistsError):
            ops.new_file(self.dir, 'n.txt')


# ─── jobs ────────────────────────────────────────────────────

class Copy(TempDir):
    def tree(self):
        self.write('src/a.txt', b'a' * 1000)
        self.write('src/sub/b.bin', os.urandom(200_000))
        self.write('src/sub/deeper/c.txt', b'c')
        os.symlink('a.txt', self.path('src/link'))
        os.chmod(self.path('src/a.txt'), 0o640)
        os.utime(self.path('src/a.txt'), (1_600_000_000, 1_600_000_000))
        os.mkdir(self.path('dest'))

    def test_copies_a_tree_with_metadata(self):
        self.tree()
        job = self.run_job(ops.Job('copy', [self.path('src')], self.path('dest')))
        self.assertEqual(job.state, 'done')
        self.assertEqual(job.errors, [])
        out = self.path('dest', 'src')
        self.assertEqual(readb(os.path.join(out, 'sub/b.bin')),
                         readb(self.path('src/sub/b.bin')))
        self.assertTrue(os.path.islink(os.path.join(out, 'link')))
        self.assertEqual(os.readlink(os.path.join(out, 'link')), 'a.txt')
        st = os.stat(os.path.join(out, 'a.txt'))
        self.assertEqual(st.st_mode & 0o777, 0o640)
        self.assertEqual(int(st.st_mtime), 1_600_000_000)
        self.assertEqual(job.created, [out])
        self.assertEqual(job.done_bytes, job.total_bytes)
        self.assertEqual(job.fraction, 1.0)

    def test_copy_into_the_same_folder_keeps_both(self):
        a = self.write('a.txt', b'1')
        job = self.run_job(ops.Job('copy', [a], self.dir))
        self.assertEqual(job.created, [self.path('a (2).txt')])

    def test_folder_into_itself_is_refused(self):
        self.tree()
        job = self.run_job(ops.Job('copy', [self.path('src')], self.path('src/sub')))
        self.assertEqual(job.errors[0][1], 'error.into_itself')
        self.assertFalse(os.path.exists(self.path('src/sub/src')))

    def clash_setup(self):
        self.write('src/same.txt', b'new')
        self.write('src/other.txt', b'other-new')
        self.write('dest/same.txt', b'old')
        self.write('dest/other.txt', b'other-old')
        return [self.path('src/same.txt'), self.path('src/other.txt')]

    def test_clash_replace(self):
        srcs = self.clash_setup()
        asked = []
        job = ops.Job('copy', srcs, self.path('dest'),
                      ask=lambda j, s, d: (asked.append(d), j.answer(ops.REPLACE)))
        self.run_job(job)
        self.assertEqual(len(asked), 2)
        self.assertEqual(readb(self.path('dest/same.txt')), b'new')

    def test_clash_skip_for_all(self):
        srcs = self.clash_setup()
        asked = []
        job = ops.Job('copy', srcs, self.path('dest'),
                      ask=lambda j, s, d: (asked.append(d), j.answer(ops.SKIP, True)))
        self.run_job(job)
        self.assertEqual(len(asked), 1)                 # "do the same" answered the second
        self.assertEqual(readb(self.path('dest/same.txt')), b'old')
        self.assertEqual(readb(self.path('dest/other.txt')), b'other-old')

    def test_clash_keep_both(self):
        srcs = self.clash_setup()
        job = ops.Job('copy', srcs[:1], self.path('dest'),
                      ask=lambda j, s, d: j.answer(ops.KEEP_BOTH))
        self.run_job(job)
        self.assertEqual(readb(self.path('dest/same (2).txt')), b'new')
        self.assertEqual(readb(self.path('dest/same.txt')), b'old')

    def test_clash_cancel(self):
        srcs = self.clash_setup()
        job = ops.Job('copy', srcs, self.path('dest'), ask=lambda j, s, d: j.answer(ops.CANCEL))
        self.run_job(job)
        self.assertEqual(job.state, 'cancelled')

    def test_folders_merge(self):
        self.write('src/box/a.txt', b'a')
        self.write('dest/box/b.txt', b'b')
        self.run_job(ops.Job('copy', [self.path('src/box')], self.path('dest')))
        self.assertEqual(sorted(os.listdir(self.path('dest/box'))), ['a.txt', 'b.txt'])

    def test_pause_resume_and_cancel_leave_no_half_file(self):
        big = self.write('big.bin', b'\0' * (40 * 1024 * 1024))
        os.mkdir(self.path('dest'))
        job = ops.Job('copy', [big], self.path('dest'))
        old_chunk = ops.CHUNK
        ops.CHUNK = 64 * 1024                    # many small steps, so pausing lands mid-file
        self.addCleanup(setattr, ops, 'CHUNK', old_chunk)
        job.pause()
        job._go.clear()
        job.start()
        time.sleep(0.3)
        self.assertEqual(job.done_bytes, 0)       # paused before the first byte
        job.state = 'paused'
        job.resume()
        deadline = time.monotonic() + 10
        while job.done_bytes == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        job.cancel()
        job.thread.join(10)
        self.assertEqual(job.state, 'cancelled')
        self.assertFalse(os.path.exists(self.path('dest/big.bin')))

    @unittest.skipIf(ROOT, "root can read everything")
    def test_unreadable_file_is_reported_and_the_rest_copied(self):
        self.write('src/ok.txt', b'ok')
        bad = self.write('src/secret.txt', b'no')
        os.chmod(bad, 0)
        os.mkdir(self.path('dest'))
        job = self.run_job(ops.Job('copy', [self.path('src')], self.path('dest')))
        self.assertTrue(os.path.exists(self.path('dest/src/ok.txt')))
        self.assertEqual(len(job.errors), 1)
        self.assertTrue(job.errors[0][0].endswith('secret.txt'))


class Move(TempDir):
    def test_same_drive_is_a_rename(self):
        a = self.write('src/a.txt', b'a')
        os.mkdir(self.path('dest'))
        inode = os.stat(a).st_ino
        job = self.run_job(ops.Job('move', [self.path('src')], self.path('dest')))
        self.assertEqual(job.errors, [])
        self.assertFalse(os.path.exists(self.path('src')))
        self.assertEqual(os.stat(self.path('dest/src/a.txt')).st_ino, inode)
        self.assertEqual(job.pairs, [(self.path('src'), self.path('dest/src'))])

    def test_other_drive_copies_then_removes(self):
        self.write('src/a.txt', b'a')
        self.write('src/sub/b.txt', b'b')
        os.mkdir(self.path('dest'))
        job = ops.Job('move', [self.path('src')], self.path('dest'))
        job._same_device = lambda *_a: False           # as if dest were another drive
        self.run_job(job)
        self.assertEqual(job.errors, [])
        self.assertFalse(os.path.exists(self.path('src')))
        self.assertEqual(readb(self.path('dest/src/sub/b.txt')), b'b')

    def test_into_its_own_folder_does_nothing(self):
        a = self.write('a.txt')
        job = self.run_job(ops.Job('move', [a], self.dir))
        self.assertEqual(job.created, [])
        self.assertTrue(os.path.exists(a))

    def test_merge_moves_contents(self):
        self.write('src/box/a.txt', b'a')
        self.write('dest/box/b.txt', b'b')
        self.run_job(ops.Job('move', [self.path('src/box')], self.path('dest')))
        self.assertEqual(sorted(os.listdir(self.path('dest/box'))), ['a.txt', 'b.txt'])
        self.assertFalse(os.path.exists(self.path('src/box')))


class Delete(TempDir):
    def test_delete_tree(self):
        self.write('d/a/b/c.txt')
        os.symlink('/etc', self.path('d/link'))
        job = self.run_job(ops.Job('delete', [self.path('d')]))
        self.assertEqual(job.errors, [])
        self.assertFalse(os.path.exists(self.path('d')))
        self.assertTrue(os.path.isdir('/etc'))           # the link went, not what it points to


# ─── trash ───────────────────────────────────────────────────

class Trash(TempDir):
    def setUp(self):
        super().setUp()
        # the home trash inside the temporary folder: same drive as the files
        self.old = os.environ.get('XDG_DATA_HOME')
        os.environ['XDG_DATA_HOME'] = self.path('data')
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ['XDG_DATA_HOME'] = self.old

    def test_trash_and_restore(self):
        a = self.write('docs/report.txt', b'R')
        where = trash.trash(a)
        self.assertFalse(os.path.exists(a))
        self.assertTrue(where.startswith(self.path('data', 'Trash', 'files')))
        info = readb(trash.info_for(where)).decode('utf-8')
        self.assertIn('[Trash Info]', info)
        self.assertIn('Path=' + a.replace(' ', '%20'), info)
        self.assertRegex(info, r'DeletionDate=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d')
        self.assertEqual(trash.original_path(where), a)
        items = list(trash.items())
        self.assertEqual([i.original for i in items], [a])
        job = self.run_job(ops.Job('restore', [where]))
        self.assertEqual(job.created, [a])
        self.assertEqual(readb(a), b'R')
        self.assertEqual(trash.count(), 0)

    def test_same_name_twice(self):
        a = self.write('one/x.txt', b'1')
        b = self.write('two/x.txt', b'2')
        wa, wb = trash.trash(a), trash.trash(b)
        self.assertNotEqual(wa, wb)
        self.assertEqual(sorted(i.original for i in trash.items()), sorted([a, b]))

    def test_restore_onto_a_taken_name_asks(self):
        a = self.write('x.txt', b'old')
        where = trash.trash(a)
        self.write('x.txt', b'new one')
        job = ops.Job('restore', [where], ask=lambda j, s, d: j.answer(ops.KEEP_BOTH))
        self.run_job(job)
        self.assertEqual(readb(self.path('x (2).txt')), b'old')

    def test_paths_with_odd_characters(self):
        a = self.write('été %20 [1]/é #.txt', b'x')
        where = trash.trash(a)
        self.assertEqual(trash.original_path(where), a)

    def test_trash_job_and_empty(self):
        files = [self.write(f'f{i}.txt') for i in range(3)]
        job = self.run_job(ops.Job('trash', files))
        self.assertEqual(len(job.created), 3)
        self.assertEqual(trash.count(), 3)
        self.assertTrue(trash.is_trash_path(job.created[0]))
        self.assertEqual(trash.empty(), [])
        self.assertEqual(trash.count(), 0)


# ─── listing ─────────────────────────────────────────────────

class Listing(TempDir):
    def test_natural_sort_and_folders_first(self):
        for n in ('file10.txt', 'file2.txt', 'File1.txt', 'école.txt', 'zeta.txt'):
            self.write(n)
        os.mkdir(self.path('Zfolder'))
        names = [e.name for e in sort_entries(list_dir(self.dir))]
        self.assertEqual(names, ['Zfolder', 'école.txt', 'File1.txt', 'file2.txt',
                                 'file10.txt', 'zeta.txt'])
        names = [e.name for e in sort_entries(list_dir(self.dir), folders_first=False)]
        self.assertEqual(names[-2:], ['zeta.txt', 'Zfolder'])      # zeta < zfolder

    def test_sort_by_size_date_type(self):
        a = self.write('a.txt', b'x' * 10)
        b = self.write('b.jpg', b'x' * 1000)
        c = self.write('c.mp3', b'x' * 100)
        os.utime(a, (1, 300))
        os.utime(b, (1, 100))
        os.utime(c, (1, 200))
        entries = list_dir(self.dir)
        self.assertEqual([e.name for e in sort_entries(entries, 'size', True)],
                         ['b.jpg', 'c.mp3', 'a.txt'])
        self.assertEqual([e.name for e in sort_entries(entries, 'modified')],
                         ['b.jpg', 'c.mp3', 'a.txt'])
        self.assertEqual([e.name for e in sort_entries(entries, 'type')],
                         ['c.mp3', 'a.txt', 'b.jpg'])            # audio, document, image

    def test_filter(self):
        for n in ('Holiday photo.jpg', 'holiday.txt', 'work.jpg', '.secret'):
            self.write(n)
        entries = list_dir(self.dir)
        self.assertEqual(len(filter_entries(entries)), 3)
        self.assertEqual(len(filter_entries(entries, show_hidden=True)), 4)
        self.assertEqual(sorted(e.name for e in filter_entries(entries, 'HOLI')),
                         ['Holiday photo.jpg', 'holiday.txt'])
        self.assertEqual([e.name for e in filter_entries(entries, 'photo holiday')],
                         ['Holiday photo.jpg'])
        self.assertEqual(sorted(e.name for e in filter_entries(entries, '*.jpg')),
                         ['Holiday photo.jpg', 'work.jpg'])
        self.assertEqual([e.name for e in filter_entries(entries, 'ecole')], [])
        self.write('École.txt')
        self.assertEqual([e.name for e in filter_entries(list_dir(self.dir), 'ecole')],
                         ['École.txt'])

    def test_links_and_kinds(self):
        self.write('real.png')
        os.symlink('real.png', self.path('good'))
        os.symlink('missing', self.path('bad'))
        os.mkdir(self.path('dir.d'))
        by = {e.name: e for e in list_dir(self.dir)}
        self.assertTrue(by['good'].is_link and not by['good'].broken)
        self.assertTrue(by['bad'].broken)
        self.assertEqual(by['real.png'].kind, 'image')
        self.assertTrue(by['dir.d'].is_dir)
        self.assertEqual(by['dir.d'].kind, 'folder')
        self.assertEqual(type_label(by['real.png'], t),
                         t('kind.with_ext', ext='PNG', kind=t('kind.image')))
        self.assertEqual(type_label(by['bad'], t), t('kind.broken_link'))
        self.assertEqual(read_entry(self.path('real.png')).name, 'real.png')
        self.assertIsNone(read_entry(self.path('nope')))

    def test_ten_thousand_files_list_fast(self):
        folder = self.path('many')
        os.mkdir(folder)
        for i in range(10_000):
            open(os.path.join(folder, f'file {i}.txt'), 'w').close()
        start = time.monotonic()
        entries = sort_entries(filter_entries(list_dir(folder)))
        took = time.monotonic() - start
        self.assertEqual(len(entries), 10_000)
        self.assertEqual(entries[1].name, 'file 1.txt')
        self.assertLess(took, 1.0, f"listing 10,000 files took {took:.2f} s")

    def test_natural_key_is_total(self):
        names = ['a', 'A', 'a1', 'a01', 'a1b', '1', '']
        sorted(names, key=natural_key)                  # no TypeError between parts


# ─── thumbnails ──────────────────────────────────────────────

@unittest.skipIf(thumbs.Image is None, "needs Pillow")
class Thumbnails(TempDir):
    def setUp(self):
        super().setUp()
        self.old = os.environ.get('XDG_CACHE_HOME')
        os.environ['XDG_CACHE_HOME'] = self.path('cache')
        self.addCleanup(lambda: os.environ.__setitem__('XDG_CACHE_HOME', self.old))

    def photo(self, name='p.png', size=(800, 400)):
        from PIL import Image
        p = self.path(name)
        Image.new('RGB', size, (200, 10, 10)).save(p)
        return p

    def test_made_cached_and_shared_the_freedesktop_way(self):
        p = self.photo()
        mtime = os.stat(p).st_mtime
        img = thumbs.make(p, 'png', mtime, os.path.getsize(p))
        self.assertEqual(img.size, (128, 64))
        stored = thumbs.thumb_path(p, 'normal')
        self.assertTrue(stored.startswith(self.path('cache', 'thumbnails', 'normal')))
        from PIL import Image
        with Image.open(stored) as s:
            self.assertEqual(s.info['Thumb::URI'], thumbs.file_uri(p))
            self.assertEqual(int(s.info['Thumb::MTime']), int(mtime))
        self.assertEqual(oct(os.stat(stored).st_mode & 0o777), '0o600')
        self.assertIsNotNone(thumbs.cached(p, mtime))
        self.assertIsNone(thumbs.cached(p, mtime + 10))          # the file changed

    def test_uri_matches_the_spec(self):
        self.assertEqual(thumbs.file_uri('/home/a b/é.jpg'), 'file:///home/a%20b/%C3%A9.jpg')

    def test_broken_file_is_remembered(self):
        p = self.write('broken.jpg', b'not a jpeg')
        mtime = os.stat(p).st_mtime
        self.assertIsNone(thumbs.make(p, 'jpg', mtime, 10))
        self.assertTrue(thumbs.failed_before(p, mtime))

    def test_worker_delivers(self):
        p = self.photo('w.jpg')
        got = threading.Event()
        out = []
        th = thumbs.Thumbnailer(lambda path, m, img: (out.append(path), got.set()))
        self.addCleanup(th.stop)
        th.request(p, 'jpg', os.stat(p).st_mtime, os.path.getsize(p))
        self.assertTrue(got.wait(10))
        self.assertEqual(out, [p])


# ─── service menus ───────────────────────────────────────────

class ServiceMenus(TempDir):
    MENU = """[Desktop Entry]
Type=Service
MimeType=application/zip;image/*;
Actions=one;two;
X-KDE-Submenu=Pack
X-KDE-Submenu[fr]=Emballer

[Desktop Action one]
Name=Do one
Name[fr]=Faire un
Exec=tool --one %F

[Desktop Action two]
Name=Do two
Exec=tool --two "%f" --uri %u
"""

    def setUp(self):
        super().setUp()
        self.old = os.environ.get('XDG_DATA_HOME')
        os.environ['XDG_DATA_HOME'] = self.path('data')
        self.old_dirs = os.environ.get('XDG_DATA_DIRS')
        os.environ['XDG_DATA_DIRS'] = self.path('none')
        self.addCleanup(self._back)
        self.write('data/kio/servicemenus/pack.desktop', self.MENU.encode())
        self.write('data/kio/servicemenus/dirs.desktop',
                   b"[Desktop Entry]\nType=Service\nMimeType=inode/directory;\n"
                   b"Actions=a;\n\n[Desktop Action a]\nName=Here\nExec=thing %f\n")

    def _back(self):
        os.environ['XDG_DATA_HOME'] = self.old
        if self.old_dirs is None:
            os.environ.pop('XDG_DATA_DIRS', None)
        else:
            os.environ['XDG_DATA_DIRS'] = self.old_dirs

    def test_actions_by_type(self):
        menus = servicemenus.load('fr')
        zip_actions = servicemenus.actions_for(menus, [('/a.zip', 'application/zip', False)])
        self.assertEqual([a.name for a in zip_actions], ['Faire un', 'Do two'])
        self.assertEqual(zip_actions[0].submenu, 'Emballer')
        both = servicemenus.actions_for(menus, [('/a.zip', 'application/zip', False),
                                                ('/b.png', 'image/png', False)])
        self.assertEqual(len(both), 2)
        mixed = servicemenus.actions_for(menus, [('/a.zip', 'application/zip', False),
                                                 ('/d', 'inode/directory', True)])
        self.assertEqual(mixed, [])
        dirs = servicemenus.actions_for(menus, [('/d', 'inode/directory', True)])
        self.assertEqual([a.name for a in dirs], ['Here'])

    def test_exec_fields(self):
        self.assertEqual(servicemenus.expand('tool --one %F', ['/a b', '/c']),
                         ['tool', '--one', '/a b', '/c'])
        self.assertEqual(servicemenus.expand('tool "%f" --uri %u %i', ['/a b']),
                         ['tool', '/a b', '--uri', 'file:///a b'])
        self.assertEqual(servicemenus.expand('x 100%%', ['/a']), ['x', '100%'])


# ─── search, drag and drop text ──────────────────────────────

class SearchBelow(TempDir):
    def test_finds_nested_and_skips_hidden(self):
        self.write('a/b/c/Report 2026.pdf')
        self.write('a/report-old.txt')
        self.write('.hidden/report.txt')
        self.write('a/other.txt')
        found, done = [], threading.Event()
        Search(self.dir, 'report', False, lambda s, batch: found.extend(batch),
               lambda s: done.set()).start()
        self.assertTrue(done.wait(10))
        self.assertEqual(sorted(e.name for e in found), ['Report 2026.pdf', 'report-old.txt'])
        found.clear()
        done.clear()
        Search(self.dir, '*.txt', True, lambda s, batch: found.extend(batch),
               lambda s: done.set()).start()
        self.assertTrue(done.wait(10))
        self.assertEqual(len(found), 3)

    def test_cancel(self):
        for i in range(200):
            self.write(f'd{i}/x{i}.txt')
        done = threading.Event()
        s = Search(self.dir, 'x', False, lambda *_a: None, lambda s: done.set())
        s.cancel()
        s.start()
        self.assertTrue(done.wait(10))
        self.assertLess(s.found, 200)


class UriLists(unittest.TestCase):
    def test_round_trip(self):
        paths = ['/home/me/a b.txt', '/tmp/été #1.png', '/x/%41.txt']
        text = paths_to_uris(paths)
        self.assertTrue(text.endswith('\r\n'))
        self.assertIn('file:///home/me/a%20b.txt', text)
        self.assertEqual(uris_to_paths(text), paths)

    def test_other_hosts_and_comments(self):
        self.assertEqual(uris_to_paths('# comment\r\nfile://otherhost/x\r\n'
                                       'file://localhost/y\r\n/z\n'), ['/y', '/z'])


# ─── the window ──────────────────────────────────────────────

@unittest.skipUnless(DISPLAY, "needs a display")
class Window(TempDir):
    @classmethod
    def setUpClass(cls):
        from sparkfiles.app import App
        cls.app = App()
        cls.app.quit = lambda: None                    # windows come and go between tests

    @classmethod
    def tearDownClass(cls):
        for w in list(cls.app.windows):
            w.destroy()
        cls.app.shutdown()

    def setUp(self):
        super().setUp()
        self.old_data = os.environ.get('XDG_DATA_HOME')
        os.environ['XDG_DATA_HOME'] = self.path('data')
        self.addCleanup(lambda: os.environ.__setitem__('XDG_DATA_HOME', self.old_data))
        for n in ('b.txt', 'a.txt', 'c.png'):
            self.write('folder/' + n, n.encode())
        os.mkdir(self.path('folder/sub'))
        self.app.settings.update({'view': 'list', 'sort': 'name', 'sort_reverse': False,
                                  'show_hidden': False, 'split': False, 'preview': False,
                                  'folders_first': True})
        self.w = self.app.new_window(self.path('folder'))
        self.addCleanup(self._close)
        self.wait_for(lambda: len(self.pane.view.entries) == 4)

    def _close(self):
        if self.w.winfo_exists():
            self.w.close()

    @property
    def pane(self):
        return self.w.active

    def pump(self, seconds: float = 0.05):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.root.update()
            time.sleep(0.005)

    def wait_for(self, cond, timeout: float = 5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.root.update()
            if cond():
                return
            time.sleep(0.01)
        self.fail("timed out waiting")

    def names(self):
        return [e.name for e in self.pane.view.entries]

    def key(self, keysym: str, widget=None, state: str = ''):
        widget = widget or self.pane.view.canvas
        widget.focus_force()
        self.pump(0.02)
        widget.event_generate(f'<{state}KeyPress-{keysym}>' if state else f'<KeyPress-{keysym}>')
        self.pump(0.05)

    def test_lists_sorted_folders_first(self):
        self.assertEqual(self.names(), ['sub', 'a.txt', 'b.txt', 'c.png'])
        self.pane.set_sort('name')                      # second click: reversed
        self.assertEqual(self.names(), ['sub', 'c.png', 'b.txt', 'a.txt'])
        self.pane.set_sort('size')
        self.assertEqual(self.names()[0], 'sub')

    def test_navigation_history(self):
        self.pane.go(self.path('folder/sub'))
        self.wait_for(lambda: self.names() == [])
        self.pane.back()
        self.wait_for(lambda: 'a.txt' in self.names())
        self.assertEqual(self.pane.view.selected, {self.path('folder/sub')})   # came from
        self.pane.forward()
        self.wait_for(lambda: self.pane.path == self.path('folder/sub'))
        self.pane.go_up()
        self.wait_for(lambda: self.pane.path == self.path('folder'))

    def test_type_to_filter(self):
        self.pane.view.canvas.focus_force()
        self.pane.type_to_filter('b')
        self.pump()
        self.assertEqual(self.names(), ['sub', 'b.txt'])     # 'sub' has a b too
        self.pane.type_to_filter('.')
        self.pump()
        self.assertEqual(self.names(), ['b.txt'])
        self.pane.escape()
        self.pump()
        self.assertEqual(len(self.names()), 4)

    def test_keyboard_selection(self):
        self.key('Down')
        self.key('Down')
        self.assertEqual(self.pane.view.selected, {self.path('folder/a.txt')})
        self.key('Down', state='Shift-')
        self.assertEqual(len(self.pane.view.selected), 2)
        self.pane.view.select_all()
        self.assertEqual(len(self.pane.view.selected), 4)

    def test_rename_in_place(self):
        self.pane.view.select_paths([self.path('folder/a.txt')])
        self.app.rename_selected(self.pane)
        self.pump()
        self.assertTrue(self.pane.view.renaming)
        e = self.pane.view._rename_entry
        self.assertEqual(e.selection_get(), 'a')            # the name without .txt
        e.delete(0, 'end')
        e.insert(0, 'renamed.txt')
        self.pane.view.commit_rename()
        self.wait_for(lambda: 'renamed.txt' in self.names())
        self.assertEqual(self.pane.view.selected, {self.path('folder/renamed.txt')})
        self.app.undo(self.pane)
        self.wait_for(lambda: 'a.txt' in self.names())

    def test_rename_onto_taken_name_is_refused(self):
        self.app.rename(self.pane, self.path('folder/a.txt'), 'b.txt')
        self.pump()
        self.assertEqual(readb(self.path('folder/b.txt')), b'b.txt')
        self.assertIn('b.txt', self.pane.message)

    def test_copy_paste_through_the_clipboard(self):
        self.pane.view.select_paths([self.path('folder/a.txt'), self.path('folder/c.png')])
        self.app.copy_selection(self.pane, cut=False)
        paths, cut = self.app.read_clipboard()
        self.assertEqual(sorted(paths), [self.path('folder/a.txt'), self.path('folder/c.png')])
        self.assertFalse(cut)
        self.pane.go(self.path('folder/sub'))
        self.wait_for(lambda: self.pane.path.endswith('sub'))
        self.app.paste(self.pane)
        self.wait_for(lambda: sorted(self.names()) == ['a.txt', 'c.png'])
        self.assertTrue(os.path.exists(self.path('folder/a.txt')))

    def test_cut_paste_moves(self):
        self.pane.view.select_paths([self.path('folder/b.txt')])
        self.app.copy_selection(self.pane, cut=True)
        self.assertEqual(self.app.cut_paths(), {self.path('folder/b.txt')})
        self.pane.go(self.path('folder/sub'))
        self.wait_for(lambda: self.pane.path.endswith('sub'))
        self.app.paste(self.pane)
        self.wait_for(lambda: self.names() == ['b.txt'])
        self.assertFalse(os.path.exists(self.path('folder/b.txt')))

    def test_trash_with_delete_and_undo(self):
        self.pane.view.select_paths([self.path('folder/a.txt')])
        self.key('Delete')
        self.wait_for(lambda: 'a.txt' not in self.names())
        self.assertEqual(trash.count(), 1)
        self.wait_for(lambda: bool(self.app.undo_stack))
        self.app.undo(self.pane)
        self.wait_for(lambda: 'a.txt' in self.names())
        self.assertEqual(trash.count(), 0)

    def test_trash_view_and_restore(self):
        trash.trash(self.path('folder/b.txt'))
        from sparkfiles.places import TRASH
        self.pane.go(TRASH)
        self.wait_for(lambda: self.names() == ['b.txt'])
        self.pane.view.select_all()
        self.app.restore(self.pane)
        self.wait_for(lambda: os.path.exists(self.path('folder/b.txt')))

    def test_new_folder_dialog(self):
        from sparkfiles import ui
        orig = ui.ask_text
        import sparkfiles.app as appmod
        appmod.ask_text = lambda *a, **k: 'Made here'
        self.addCleanup(setattr, appmod, 'ask_text', orig)
        self.app.new_folder(self.pane)
        self.wait_for(lambda: 'Made here' in self.names())
        self.assertEqual(self.pane.view.selected, {self.path('folder/Made here')})

    def test_watches_the_folder(self):
        if not self.app.bridge.context:
            self.skipTest("needs GIO")
        self.write('folder/appeared.txt')
        self.wait_for(lambda: 'appeared.txt' in self.names(), timeout=5)
        os.unlink(self.path('folder/appeared.txt'))
        self.wait_for(lambda: 'appeared.txt' not in self.names(), timeout=5)

    def test_hidden_toggle(self):
        self.write('folder/.dot')
        self.pane.reload()
        self.pump(0.3)
        self.assertNotIn('.dot', self.names())
        self.app.toggle_hidden()
        self.wait_for(lambda: '.dot' in self.names())
        self.app.toggle_hidden()
        self.wait_for(lambda: '.dot' not in self.names())

    def test_split_tabs_and_grid(self):
        self.w.toggle_split()
        self.pump()
        self.assertEqual(len(self.w.tab.panes), 2)
        other = self.w.tab.panes[0]
        self.assertIs(self.w.other_pane(self.pane), other)
        self.w.toggle_split()
        self.assertEqual(len(self.w.tab.panes), 1)
        self.w.new_tab(self.path('folder/sub'))
        self.pump()
        self.assertEqual(len(self.w.tabs), 2)
        self.w.close_tab()
        self.assertEqual(len(self.w.tabs), 1)
        self.app.set_view('grid')
        self.pump(0.2)
        self.assertEqual(self.pane.view.mode, 'grid')
        self.assertGreaterEqual(self.pane.view.columns(), 2)
        self.app.set_view('list')

    def test_search_below(self):
        self.write('folder/sub/deep/needle.txt')
        self.pane.start_search('needle')
        self.wait_for(lambda: self.pane.search is not None and self.pane.search.done
                      and self.names() == ['needle.txt'])
        self.pane.escape()
        self.wait_for(lambda: self.pane.mode == 'folder' and 'a.txt' in self.names())

    def test_drop_moves_on_the_same_drive(self):
        self.app.drop([self.path('folder/a.txt')], self.path('folder/sub'),
                      self.app.dnd.action(0, self.path('folder/sub')), self.pane)
        self.wait_for(lambda: os.path.exists(self.path('folder/sub/a.txt')))
        self.assertFalse(os.path.exists(self.path('folder/a.txt')))
        self.assertEqual(self.app.dnd.action(0x4, self.path('folder/sub')), 'copy')

    def test_ten_thousand_files_show_within_a_second(self):
        many = self.path('many')
        os.mkdir(many)
        for i in range(10_000):
            open(os.path.join(many, f'f{i}.txt'), 'w').close()
        start = time.monotonic()
        self.pane.go(many)
        self.wait_for(lambda: len(self.pane.view.entries) == 10_000, timeout=5)
        self.pump(0.01)
        took = time.monotonic() - start
        self.assertLess(took, 1.0, f"10,000 files took {took:.2f} s to show")
        start = time.monotonic()
        self.pane.view.top = self.pane.view.content_height() // 2
        self.pane.view.redraw(now=True)
        self.assertLess(time.monotonic() - start, 0.1)

    def test_properties_and_open_with_open(self):
        from sparkfiles.dialogs import OpenWith, Properties
        d = Properties(self.app, self.w, [self.path('folder/a.txt')])
        d.place_and_show()
        self.wait_for(lambda: 'B' in d.size_label.cget('text') or 'o' in
                      d.size_label.cget('text'))
        d.exec_check.toggle()
        d.apply()
        self.assertTrue(os.stat(self.path('folder/a.txt')).st_mode & 0o100)
        o = OpenWith(self.app, self.w, [self.path('folder/a.txt')])
        o.place_and_show()
        self.pump()
        o.cancel()

    def test_context_menus_build(self):
        import tkinter as tk
        orig = tk.Menu.tk_popup
        shown = []
        tk.Menu.tk_popup = lambda m, x, y, entry='': shown.append(m)
        self.addCleanup(setattr, tk.Menu, 'tk_popup', orig)
        ev = type('E', (), {'x_root': 10, 'y_root': 10})()
        self.app.context_menu(self.pane, ev, [self.pane.view.entries[1]])
        self.app.context_menu(self.pane, ev, [])
        self.app.context_menu(self.pane, ev, self.pane.view.entries)
        self.assertEqual(len(shown), 3)
        labels = [shown[0].entrycget(i, 'label') for i in range(shown[0].index('end') + 1)
                  if shown[0].type(i) not in ('separator',)]
        self.assertIn(t('menu.trash'), labels)
        self.assertIn(t('menu.properties'), labels)


@unittest.skipUnless(BUS and DISPLAY, "needs a session bus and a display")
class DBus(unittest.TestCase):
    """spark-files hands over to the running copy, and FileManager1.ShowItems opens a window
    on the file's folder with the file selected."""

    def test_show_items_and_hand_over(self):
        tmp = tempfile.mkdtemp(prefix='spark-files-dbus-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        target = os.path.join(tmp, 'wanted.txt')
        open(target, 'w').close()
        env = dict(os.environ)
        env['PYTHONPATH'] = APP_DIR
        proc = subprocess.Popen([sys.executable, os.path.join(APP_DIR, 'spark_files.py'),
                                 '--service'], env=env)
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            r = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'NameHasOwner',
                              GLib.Variant('(s)', ('org.freedesktop.FileManager1',)), None,
                              Gio.DBusCallFlags.NONE, 2000, None)
            if r.unpack()[0]:
                break
            time.sleep(0.1)
        else:
            self.fail("Spark Files didn't take org.freedesktop.FileManager1")
        bus.call_sync('org.freedesktop.FileManager1', '/org/freedesktop/FileManager1',
                      'org.freedesktop.FileManager1', 'ShowItems',
                      GLib.Variant('(ass)', (['file://' + target], '')), None,
                      Gio.DBusCallFlags.NONE, 5000, None)
        log = os.path.join(os.environ['XDG_STATE_HOME'], 'spark-files', 'spark-files.log')
        want = f"showing {tmp} with {target} selected"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if os.path.exists(log) and want in readb(log).decode('utf-8', 'replace'):
                break
            time.sleep(0.1)
        else:
            self.fail("ShowItems didn't open the folder with the file selected")
        from sparkfiles import gloop
        self.assertTrue(gloop.hand_over(['file://' + tmp], 'open'))
        self.assertIsNone(proc.poll(), "the service quit")
        out = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_files.py'), tmp],
                             env=env, timeout=20, capture_output=True)
        self.assertEqual(out.returncode, 0)                 # handed over and returned at once


class SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        import io
        from contextlib import redirect_stdout
        from sparkfiles.cli import self_test
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = self_test()
        self.assertEqual(code, 0, buf.getvalue())
        self.assertIn(VERSION, buf.getvalue())


if __name__ == '__main__':
    unittest.main()
