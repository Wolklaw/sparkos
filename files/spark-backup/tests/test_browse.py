"""Looking inside a snapshot and restoring from it. Plain folders in a temporary directory."""

import datetime as dt
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401
from sparkbackup import browse

WHEN = dt.datetime(2026, 11, 23, 2, 0)


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-backup-browse-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.snap = os.path.join(self.dir, 'snap')
        self.out = os.path.join(self.dir, 'out')
        os.makedirs(os.path.join(self.snap, 'alex', 'docs'))
        os.makedirs(self.out)
        self.write(os.path.join(self.snap, 'alex', 'docs', 'note.txt'), 'old')
        self.write(os.path.join(self.snap, 'alex', 'top.txt'), 'top')
        os.makedirs(os.path.join(self.snap, 'alex', 'empty'))
        self.secret = os.path.join(self.dir, 'secret.txt')
        self.write(self.secret, 'live system file')
        os.symlink(self.dir, os.path.join(self.snap, 'alex', 'out-link'))

    def write(self, path, text):
        with open(path, 'w') as f:
            f.write(text)

    def read(self, path):
        with open(path) as f:
            return f.read()


class Listing(Case):
    def test_folders_first_then_names(self):
        names = [e.name for e in browse.entries(self.snap, 'alex')]
        self.assertEqual(names, ['docs', 'empty', 'out-link', 'top.txt'])

    def test_a_link_is_listed_but_never_entered(self):
        link = next(e for e in browse.entries(self.snap, 'alex') if e.name == 'out-link')
        self.assertTrue(link.is_link)
        with self.assertRaises(browse.BrowseError):
            browse.entries(self.snap, 'alex/out-link')
        with self.assertRaises(browse.BrowseError):
            browse.entries(self.snap, 'alex/out-link/anything')

    def test_dotdot_is_refused(self):
        for rel in ('..', 'alex/../..', '../x', 'alex\\..\\..'):
            with self.subTest(rel=rel), self.assertRaises(browse.BrowseError):
                browse.entries(self.snap, rel)

    def test_snapshot_list_is_newest_first_and_knows_where_each_is(self):
        snaps = browse.snapshots(['2026-01-01_020000', '2026-01-02_020000'],
                                 ['2026-01-02_020000', '2026-01-03_020000', 'junk'])
        self.assertEqual([s.name for s in snaps],
                         ['2026-01-03_020000', '2026-01-02_020000', '2026-01-01_020000'])
        self.assertEqual([(s.local, s.copy) for s in snaps],
                         [(False, True), (True, True), (True, False)])


class Restore(Case):
    def test_here_is_beside_the_live_file_and_never_replaces_it(self):
        live = os.path.join(self.dir, 'live')
        os.makedirs(live)
        self.write(os.path.join(live, 'note.txt'), 'new')
        got = browse.restore(self.snap, 'alex/docs/note.txt', live, WHEN, beside=True)
        self.assertEqual(os.path.basename(got.path), 'note (restored 2026-11-23 02:00).txt')
        self.assertEqual(self.read(os.path.join(live, 'note.txt')), 'new')
        self.assertEqual(self.read(got.path), 'old')

    def test_a_second_restore_gets_a_number(self):
        one = browse.restore(self.snap, 'alex/top.txt', self.out, WHEN)
        two = browse.restore(self.snap, 'alex/top.txt', self.out, WHEN)
        self.assertEqual(os.path.basename(one.path), 'top.txt')
        self.assertEqual(os.path.basename(two.path), 'top (2).txt')

    def test_a_folder_comes_back_whole(self):
        got = browse.restore(self.snap, 'alex/docs', self.out, WHEN, beside=True)
        self.assertEqual(os.path.basename(got.path), 'docs (restored 2026-11-23 02:00)')
        self.assertEqual(self.read(os.path.join(got.path, 'note.txt')), 'old')

    def test_a_link_is_copied_as_a_link_not_followed(self):
        got = browse.restore(self.snap, 'alex/out-link', self.out, WHEN)
        self.assertTrue(os.path.islink(got.path))

    def test_the_whole_snapshot_or_nothing_cannot_be_restored(self):
        for rel in ('', '.', '/'):
            with self.subTest(rel=rel), self.assertRaises(browse.BrowseError):
                browse.restore(self.snap, rel, self.out, WHEN)

    def test_a_file_that_is_not_there(self):
        with self.assertRaises(browse.BrowseError):
            browse.restore(self.snap, 'alex/missing', self.out, WHEN)

    def test_paths_out_of_the_snapshot_are_refused(self):
        for rel in ('../secret.txt', 'alex/out-link/secret.txt', 'alex/../../secret.txt'):
            with self.subTest(rel=rel), self.assertRaises(browse.BrowseError):
                browse.restore(self.snap, rel, self.out, WHEN)
        self.assertEqual(os.listdir(self.out), [])

    def test_the_original_folder(self):
        self.assertEqual(browse.original_parent('alex/docs/note.txt', '/home'),
                         '/home/alex/docs')
        self.assertEqual(browse.original_parent('alex', '/home'), '/home')


if __name__ == '__main__':
    unittest.main()
