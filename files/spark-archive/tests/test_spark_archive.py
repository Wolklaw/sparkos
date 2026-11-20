"""Spark Archive tests. Every format, every path-escape case, passwords, overwrite questions,
Cancel, and the windows under Xvfb.

    cd files/spark-archive && python3 -m unittest discover -s tests -v

Linux only (the safe writer needs openat). Tests that need the 7z command, Python's zstd or a
display say so when they skip."""

import bz2
import gzip
import io
import lzma
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from sparkarchive import cli, formats  # noqa: E402
from sparkarchive import libarchive as la  # noqa: E402
from sparkarchive.jobs import (CANCEL, KEEP_BOTH, REPLACE, SKIP, CompressJob,  # noqa: E402
                               ExtractJob, Listing, ListJob, default_output, single_top)
from sparkarchive.readers import (LibarchiveReader, SevenZipReader, candidates,  # noqa: E402
                                  sevenzip)
from sparkarchive.safety import SafeWriter, clean_parts, link_target_ok  # noqa: E402
import makers  # noqa: E402

FIXTURES = os.path.join(HERE, 'fixtures')
LINUX = sys.platform.startswith('linux')
ROOT = LINUX and os.geteuid() == 0
HAS_7Z = sevenzip() is not None
HAS_LA = la.load() is not None
HAS_ZSTD = formats.has_zstd()

if not LINUX:
    raise unittest.SkipTest("Spark Archive's safe writer is Linux only")


class Answers:
    """A scripted asker: a list of answers per question, recording what was asked."""

    def __init__(self, password=None, overwrite=None):
        self.passwords = list(password or [])
        self.overwrites = list(overwrite or [])
        self.asked = []

    def __call__(self, question, info):
        self.asked.append((question, dict(info)))
        if question == 'password':
            return self.passwords.pop(0) if self.passwords else None
        if question == 'overwrite':
            return self.overwrites.pop(0) if self.overwrites else (SKIP, False)
        return None


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def tree(folder):
    """Every path under folder, relative, with a trailing / on folders and '-> x' on links."""
    out = []
    for top, dirs, files in os.walk(folder):
        for name in dirs + files:
            full = os.path.join(top, name)
            rel = os.path.relpath(full, folder).replace(os.sep, '/')
            if os.path.islink(full):
                out.append(f"{rel} -> {os.readlink(full)}")
            elif os.path.isdir(full):
                out.append(rel + '/')
            else:
                out.append(rel)
    return sorted(out)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-archive-test-')
        # dest/inner is the target; anything appearing in dest/ outside inner/ escaped
        self.outer = os.path.join(self.tmp, 'dest')
        self.dest = os.path.join(self.outer, 'inner')
        os.makedirs(self.dest)
        self.src = os.path.join(self.tmp, 'src')
        os.makedirs(self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.src, name)

    def extract(self, archive, asker=None, **kw):
        kw.setdefault('dest', self.dest)
        res = ExtractJob(archive, kw.pop('dest'), asker=asker or Answers(), **kw).run_here()
        return res

    def assert_contained(self):
        """Nothing next to inner/, nothing in the temp folder's top but dest and src."""
        self.assertEqual(sorted(os.listdir(self.outer)), ['inner'], "something escaped")
        self.assertEqual(sorted(os.listdir(self.tmp)), ['dest', 'src'], "something escaped")

    def reasons(self, res):
        return sorted((name, why.split(':')[0]) for name, why in res.problems)


# ─── names and links on paper ─────────────────────────────────

class TestRules(unittest.TestCase):
    def test_clean_parts(self):
        self.assertEqual(clean_parts('a/b.txt'), ('a', 'b.txt'))
        self.assertEqual(clean_parts('/etc/passwd'), ('etc', 'passwd'))
        self.assertEqual(clean_parts('C:\\Windows\\x.ini'), ('Windows', 'x.ini'))
        self.assertEqual(clean_parts('./a//b/'), ('a', 'b'))
        for bad in ('../x', 'a/../../x', 'a/../b', '..', '..\\x', 'a\\..\\..\\x', '', '/',
                    '.', 'a/\0b', 'x' * 256):
            self.assertIsNone(clean_parts(bad), bad)

    def test_link_targets(self):
        self.assertTrue(link_target_ok(('a', 'l'), '../b'))
        self.assertTrue(link_target_ok(('a', 'b', 'l'), '../../c/d'))
        self.assertTrue(link_target_ok(('l',), 'a/b'))
        self.assertFalse(link_target_ok(('l',), '../b'))
        self.assertFalse(link_target_ok(('a', 'l'), '../../b'))
        self.assertFalse(link_target_ok(('l',), '/etc/passwd'))
        self.assertFalse(link_target_ok(('l',), 'x/../y'))      # x could be a link itself
        self.assertFalse(link_target_ok(('l',), ''))
        self.assertFalse(link_target_ok(('l',), 'C:\\x'))

    def test_detect_by_content_not_name(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, 'renamed.dat')
            with zipfile.ZipFile(p, 'w') as zf:
                zf.writestr('a.txt', 'x')
            self.assertEqual(formats.detect(p), 'zip')
            p2 = os.path.join(tmp, 'notes.zip')
            with open(p2, 'w') as f:
                f.write('just text, named like a zip')
            self.assertIsNone(formats.detect(p2))
            self.assertEqual(formats.detect(os.path.join(FIXTURES, 'plain.7z')), '7z')
        finally:
            shutil.rmtree(tmp)

    def test_single_top(self):
        from sparkarchive.readers import Entry
        self.assertEqual(single_top([Entry('p/a', 'file'), Entry('p/b/c', 'file')]), 'p')
        self.assertIsNone(single_top([Entry('p/a', 'file'), Entry('q', 'file')]))
        self.assertIsNone(single_top([Entry('a.txt', 'file')]))


# ─── every format ─────────────────────────────────────────────

class TestFormats(Base):
    def make_tree(self):
        os.makedirs(self.path('photos/trip'))
        with open(self.path('photos/trip/a.bin'), 'wb') as f:
            f.write(os.urandom(70_000))
        with open(self.path('photos/café.txt'), 'w', encoding='utf-8') as f:
            f.write('été\n')
        os.symlink('trip/a.bin', self.path('photos/latest'))
        return read(self.path('photos/trip/a.bin'))

    def check_photos(self, folder, payload, link=True):
        self.assertEqual(read(os.path.join(folder, 'photos', 'trip', 'a.bin')), payload)
        with open(os.path.join(folder, 'photos', 'café.txt'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'été\n')
        if link:
            self.assertEqual(os.readlink(os.path.join(folder, 'photos', 'latest')), 'trip/a.bin')

    def test_zip(self):
        payload = self.make_tree()
        arc = os.path.join(self.tmp, 'photos.zip')
        with zipfile.ZipFile(arc, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(self.path('photos'), 'photos')
            zf.write(self.path('photos/trip'), 'photos/trip')
            zf.write(self.path('photos/trip/a.bin'), 'photos/trip/a.bin')
            zf.write(self.path('photos/café.txt'), 'photos/café.txt')
            info = zipfile.ZipInfo('photos/latest')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, 'trip/a.bin')
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.check_photos(self.dest, payload)
        self.assertEqual(res.problems, [])
        self.assert_contained()

    def test_tar_every_compression(self):
        payload = self.make_tree()
        modes = [('tar', 'w'), ('tar.gz', 'w:gz'), ('tar.bz2', 'w:bz2'), ('tar.xz', 'w:xz')]
        if HAS_ZSTD:
            modes.append(('tar.zst', 'w:zst'))
        for ext, mode in modes:
            with self.subTest(ext):
                arc = os.path.join(self.tmp, 'photos.' + ext)
                with tarfile.open(arc, mode) as tf:
                    tf.add(self.path('photos'), 'photos')
                    tf.add(self.path('photos/trip/a.bin'), 'photos/hard', recursive=False)
                self.assertEqual(formats.detect(arc), ext)
                out = os.path.join(self.dest, ext)
                os.mkdir(out)
                res = self.extract(arc, dest=out)
                self.assertTrue(res.ok, res)
                self.check_photos(out, payload)
                self.assertEqual(res.problems, [])
        self.assert_contained()

    def test_tar_hardlink(self):
        arc = os.path.join(self.tmp, 'h.tar')
        with tarfile.open(arc, 'w') as tf:
            data = b'linked'
            ti = tarfile.TarInfo('dir/orig.txt')
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
            hl = tarfile.TarInfo('dir/copy.txt')
            hl.type = tarfile.LNKTYPE
            hl.linkname = 'dir/orig.txt'
            tf.addfile(hl)
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'dir', 'copy.txt')), b'linked')

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_tar_zst_through_libarchive(self):
        """tar.zst also reads without Python's zstd, through libarchive."""
        payload = self.make_tree()
        arc = os.path.join(self.tmp, 'p.tar.zst')
        res = CompressJob([self.path('photos')], 'tar.zst', output=arc).run_here()
        self.assertTrue(res.ok, res)
        entries = LibarchiveReader(arc, 'tar.zst').list()
        listing = Listing(arc, 'tar.zst', entries, candidates('tar.zst').index(LibarchiveReader),
                          'libarchive', None)
        res = ExtractJob(arc, self.dest, listing=listing).run_here()
        self.assertTrue(res.ok, res)
        self.check_photos(self.dest, payload)

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_7z(self):
        res = self.extract(os.path.join(FIXTURES, 'plain.7z'))
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'hello.txt')), b'hello from spark\n')
        self.assertEqual(read(os.path.join(self.dest, 'docs', 'inner.txt')), b'inner file\n')
        self.assertEqual(read(os.path.join(self.dest, 'docs', 'café.txt')), b'accent\n')
        self.assert_contained()

    @unittest.skipUnless(HAS_7Z, "the 7z command is not installed")
    def test_7z_password(self):
        answers = Answers(password=['wrong', 'spark'])
        res = self.extract(os.path.join(FIXTURES, 'secret.7z'), answers)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'hello.txt')), b'hello from spark\n')
        self.assertEqual(read(os.path.join(self.dest, 'docs', 'café.txt')), b'accent\n')
        asked = [i['retry'] for q, i in answers.asked if q == 'password']
        self.assertEqual(asked, [False, True])
        self.assertEqual(sorted(os.listdir(self.dest)), ['docs', 'hello.txt'])   # no staging
        self.assert_contained()

    @unittest.skipUnless(HAS_7Z, "the 7z command is not installed")
    def test_7z_encrypted_names(self):
        """Header-encrypted 7z: even the listing needs the password."""
        arc = os.path.join(FIXTURES, 'secret-headers.7z')
        job = ListJob(arc, asker=Answers(password=['spark']))
        res = job.run_here()
        self.assertTrue(res.ok, res)
        self.assertIn('docs/inner.txt', [e.path for e in job.listing.entries])
        res = self.extract(arc, Answers(), listing=job.listing)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'docs', 'inner.txt')), b'inner file\n')

    def test_7z_password_cancel(self):
        if not HAS_7Z and not HAS_LA:
            self.skipTest("nothing reads 7z here")
        res = self.extract(os.path.join(FIXTURES, 'secret.7z'), Answers(password=[]))
        self.assertTrue(res.cancelled)
        self.assertEqual(os.listdir(self.dest), [])

    def test_zip_password(self):
        answers = Answers(password=['nope', 'spark'])
        res = self.extract(os.path.join(FIXTURES, 'zipcrypto.zip'), answers)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'docs', 'inner.txt')), b'inner file\n')
        self.assertEqual([i['retry'] for q, i in answers.asked if q == 'password'],
                         [False, True])

    def test_zip_aes(self):
        if not HAS_LA and not HAS_7Z:
            self.skipTest("neither libarchive nor 7z")
        res = self.extract(os.path.join(FIXTURES, 'aes.zip'), Answers(password=['spark']))
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'hello.txt')), b'hello from spark\n')
        self.assertEqual(os.listdir(self.dest).count('.spark-archive-'), 0)

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_rar5(self):
        arc = os.path.join(self.tmp, 'r5.rar')
        makers.rar5(arc, [('dir', 'docs'), ('file', 'docs/inner.txt', b'inner rar5\n'),
                          ('file', 'hello.txt', b'hello rar5\n'),
                          ('symlink', 'docs/link', 'inner.txt')])
        self.assertEqual(formats.detect(arc), 'rar')
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'hello.txt')), b'hello rar5\n')
        self.assertEqual(read(os.path.join(self.dest, 'docs', 'inner.txt')), b'inner rar5\n')
        self.assertEqual(os.readlink(os.path.join(self.dest, 'docs', 'link')), 'inner.txt')

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_rar4(self):
        arc = os.path.join(self.tmp, 'r4.rar')
        makers.rar4(arc, [('dir', 'docs'), ('file', 'docs/inner.txt', b'inner rar4\n'),
                          ('file', 'hello.txt', b'hello rar4\n')])
        self.assertEqual(formats.detect(arc), 'rar')
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'hello.txt')), b'hello rar4\n')
        self.assertEqual(read(os.path.join(self.dest, 'docs', 'inner.txt')), b'inner rar4\n')

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_iso(self):
        arc = os.path.join(self.tmp, 'disc.iso')
        big = os.urandom(5000)
        makers.iso9660(arc, {'HELLO.TXT': b'hello iso\n', 'BIG.BIN': big}, 'DOCS',
                       {'INNER.TXT': b'inner iso\n'})
        self.assertEqual(formats.detect(arc), 'iso')
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        found = {p.lower(): p for p in tree(self.dest)}
        self.assertIn('hello.txt', found, tree(self.dest))
        self.assertEqual(read(os.path.join(self.dest, found['hello.txt'])), b'hello iso\n')
        self.assertEqual(read(os.path.join(self.dest, found['big.bin'])), big)
        self.assertEqual(read(os.path.join(self.dest, found['docs/inner.txt'])), b'inner iso\n')

    def test_single_compressed_files(self):
        data = b'just one file\n' * 100
        kinds = [('gz', gzip.compress), ('bz2', bz2.compress), ('xz', lzma.compress)]
        if HAS_ZSTD:
            from compression import zstd
            kinds.append(('zst', zstd.compress))
        for ext, pack in kinds:
            with self.subTest(ext):
                arc = os.path.join(self.tmp, f'notes.txt.{ext}')
                with open(arc, 'wb') as f:
                    f.write(pack(data))
                self.assertEqual(formats.detect(arc), ext)
                res = self.extract(arc)
                self.assertTrue(res.ok, res)
                self.assertEqual(read(os.path.join(self.dest, 'notes.txt')), data)
                os.unlink(os.path.join(self.dest, 'notes.txt'))

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_other_formats_through_libarchive(self):
        """Kinds this app has no reader of its own for (here cpio) go to libarchive."""
        if not shutil.which('cpio'):
            self.skipTest("no cpio command to make one")
        os.makedirs(self.path('c'))
        with open(self.path('c/x.txt'), 'w') as f:
            f.write('cpio')
        arc = os.path.join(self.tmp, 'a.cpio')
        with open(arc, 'wb') as out:
            subprocess.run(['cpio', '-o', '-H', 'newc', '--quiet'], input=b'c\nc/x.txt\n',
                           stdout=out, cwd=self.src, check=True)
        self.assertEqual(formats.detect(arc), 'other')
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'c', 'x.txt')), b'cpio')

    def test_damaged(self):
        arc = os.path.join(self.tmp, 'cut.tar.gz')
        with tarfile.open(arc, 'w:gz') as tf:
            ti = tarfile.TarInfo('big.bin')
            blob = os.urandom(300_000)
            ti.size = len(blob)
            tf.addfile(ti, io.BytesIO(blob))
        with open(arc, 'r+b') as f:
            f.truncate(os.path.getsize(arc) // 2)
        res = self.extract(arc)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, 'damaged', res)
        self.assertNotIn('big.bin', os.listdir(self.dest))   # no half file under its name
        self.assertEqual([n for n in os.listdir(self.dest) if 'spark-part' in n], [])

    def test_not_an_archive(self):
        p = os.path.join(self.tmp, 'notes.zip')
        with open(p, 'w') as f:
            f.write('hello')
        res = self.extract(p)
        self.assertEqual(res.error, 'not_archive')


# ─── path escapes ─────────────────────────────────────────────

class TestEscapes(Base):
    def test_zip_names(self):
        arc = os.path.join(self.tmp, 'evil.zip')
        with zipfile.ZipFile(arc, 'w') as zf:
            zf.writestr('../escaped.txt', 'x')
            zf.writestr('ok/../../escaped2.txt', 'x')
            zf.writestr('..\\escaped3.txt', 'x')
            zf.writestr('/abs.txt', 'inside')
            zf.writestr('C:\\win\\drive.txt', 'inside')
            zf.writestr('fine.txt', 'fine')
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assert_contained()
        self.assertEqual(tree(self.dest), ['abs.txt', 'fine.txt', 'win/', 'win/drive.txt'])
        self.assertEqual([w for _n, w in self.reasons(res)], ['outside'] * 3)

    def test_zip_symlink_out(self):
        arc = os.path.join(self.tmp, 'evil.zip')
        with zipfile.ZipFile(arc, 'w') as zf:
            for name, target in (('up', '..'), ('etc', '/etc'), ('deep', 'a/../../..')):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(info, target)
            zf.writestr('up/escaped.txt', 'x')
            zf.writestr('etc/evil.conf', 'x')
        res = self.extract(arc)
        self.assert_contained()
        self.assertEqual(tree(self.dest), ['etc/', 'etc/evil.conf', 'up/', 'up/escaped.txt'])
        self.assertEqual(sorted(n for n, w in self.reasons(res) if w == 'link_out'),
                         ['deep', 'etc', 'up'])

    def tar(self, name, members):
        """members: (name, type, extra) with type 'file' (extra=bytes), 'sym'/'hard'
        (extra=target), 'dir', 'chr', 'fifo'."""
        arc = os.path.join(self.tmp, name)
        with tarfile.open(arc, 'w') as tf:
            for mname, kind, extra in members:
                ti = tarfile.TarInfo(mname)
                ti.mtime = 1700000000
                if kind == 'file':
                    ti.size = len(extra)
                    ti.mode = 0o644
                    tf.addfile(ti, io.BytesIO(extra))
                    continue
                ti.type = {'sym': tarfile.SYMTYPE, 'hard': tarfile.LNKTYPE, 'dir': tarfile.DIRTYPE,
                           'chr': tarfile.CHRTYPE, 'fifo': tarfile.FIFOTYPE}[kind]
                if kind in ('sym', 'hard'):
                    ti.linkname = extra
                if kind == 'chr':
                    ti.devmajor, ti.devminor = 1, 3
                tf.addfile(ti)
        return arc

    def evil_tar(self, skip=()):
        trap = self.outer                          # dest/: must end up holding only inner/
        return self.tar('evil.tar', [(n, k, trap if x == 'TRAP' else x)
                                     for n, k, x in self.EVIL_TAR if k not in skip])

    EVIL_TAR = [
        ('../escaped', 'file', b'x'),
        ('/abs', 'file', b'inside'),
        ('sneaky', 'sym', 'TRAP'),                 # absolute link to a real folder
        ('sneaky/escaped', 'file', b'x'),          # ...then a write through it
        ('up', 'sym', '..'),
        ('up/escaped', 'file', b'x'),
        ('here', 'sym', '.'),                      # inside, allowed
        ('trick', 'sym', 'here/../..'),            # x/.. trick: refused
        ('trick/escaped', 'file', b'x'),
        ('hard', 'hard', '../../etc/passwd'),      # hard link out
        ('hard2', 'hard', '/etc/passwd'),          # hard link to a file not in the archive
        ('hard3', 'hard', 'ok.txt'),               # ...or not written yet
        ('null', 'chr', None),
        ('pipe', 'fifo', None),
        ('ok.txt', 'file', b'ok'),
    ]

    def check_evil_tar(self, res):
        self.assert_contained()
        got = tree(self.dest)
        self.assertIn('abs', got)
        self.assertIn('ok.txt', got)
        self.assertIn('here -> .', got)
        for bad in ('up -> ..', 'trick -> here/../..', 'null', 'pipe', 'hard2', 'hard3'):
            self.assertNotIn(bad, got)
        self.assertFalse(any(g.startswith('sneaky ->') for g in got), got)
        self.assertNotIn('hard', got)
        self.assertEqual(read(os.path.join(self.dest, 'ok.txt')), b'ok')
        # the writes meant for the links went into real folders inside, or were refused
        for p in got:
            full = os.path.join(self.dest, p.split(' -> ')[0].rstrip('/'))
            self.assertTrue(os.path.realpath(full).startswith(os.path.realpath(self.dest)), p)

    def test_tar(self):
        arc = self.evil_tar()
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.check_evil_tar(res)
        reasons = dict(self.reasons(res))
        self.assertEqual(reasons.get('../escaped'), 'outside')
        self.assertEqual(reasons.get('null'), 'special')
        self.assertEqual(reasons.get('pipe'), 'special')
        self.assertEqual(reasons.get('trick'), 'link_out')

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_tar_through_libarchive(self):
        """The same hostile tar, read by libarchive (the reader 7z, rar and iso use)."""
        arc = self.evil_tar()
        entries = LibarchiveReader(arc, 'tar').list()
        listing = Listing(arc, 'tar', entries, candidates('tar').index(LibarchiveReader),
                          'libarchive', None)
        res = ExtractJob(arc, self.dest, listing=listing).run_here()
        self.assertTrue(res.ok, res)
        self.check_evil_tar(res)

    @unittest.skipUnless(HAS_7Z, "the 7z command is not installed")
    def test_tar_through_7z(self):
        """And through the 7z command and its staging folder."""
        arc = self.evil_tar(skip=('chr', 'fifo'))
        entries = SevenZipReader(arc, 'tar').list()
        listing = Listing(arc, 'tar', entries, candidates('tar').index(SevenZipReader), '7z',
                          None)
        res = ExtractJob(arc, self.dest, listing=listing).run_here()
        self.assertTrue(res.ok, res)
        self.assert_contained()
        got = tree(self.dest)
        self.assertIn('ok.txt', got)
        self.assertFalse([g for g in got if g.startswith('.spark-archive-')], got)
        for p in got:
            full = os.path.join(self.dest, p.split(' -> ')[0].rstrip('/'))
            self.assertTrue(os.path.realpath(full).startswith(os.path.realpath(self.dest)), p)

    def test_link_already_in_folder(self):
        """A link that was already in the target folder is never written through."""
        outside = os.path.join(self.outer, 'outside')
        os.mkdir(outside)
        os.symlink(outside, os.path.join(self.dest, 'shared'))
        arc = os.path.join(self.tmp, 'a.zip')
        with zipfile.ZipFile(arc, 'w') as zf:
            zf.writestr('shared/evil.txt', 'x')
            zf.writestr('fine.txt', 'x')
        res = self.extract(arc)
        self.assertEqual(os.listdir(outside), [])
        self.assertEqual(self.reasons(res), [('shared/evil.txt', 'in_the_way')])

    def test_replace_link_with_file_does_not_follow(self):
        """Replacing an existing link replaces the link, not the file it points to."""
        victim = os.path.join(self.outer, 'victim.txt')
        with open(victim, 'w') as f:
            f.write('keep me')
        os.symlink(victim, os.path.join(self.dest, 'note.txt'))
        arc = os.path.join(self.tmp, 'a.zip')
        with zipfile.ZipFile(arc, 'w') as zf:
            zf.writestr('note.txt', 'new')
        res = self.extract(arc, Answers(overwrite=[(REPLACE, False)]))
        self.assertTrue(res.ok, res)
        with open(victim) as f:
            self.assertEqual(f.read(), 'keep me')
        self.assertFalse(os.path.islink(os.path.join(self.dest, 'note.txt')))
        self.assertEqual(read(os.path.join(self.dest, 'note.txt')), b'new')

    def test_file_then_folder_same_name(self):
        arc = self.tar('t.tar', [('x', 'sym', 'y'), ('y', 'dir', None), ('x/inside', 'file',
                                                                           b'z')])
        res = self.extract(arc)
        self.assertNotIn('inside', os.listdir(os.path.join(self.dest, 'y')))
        self.assertEqual(self.reasons(res), [('x/inside', 'in_the_way')])

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_rar5_names_and_links(self):
        arc = os.path.join(self.tmp, 'evil.rar')
        makers.rar5(arc, [('file', '../escaped.txt', b'x'), ('symlink', 'etc', '/etc'),
                          ('symlink', 'up', '../..'), ('file', 'ok.txt', b'ok')])
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assert_contained()
        self.assertEqual(tree(self.dest), ['ok.txt'])
        self.assertEqual(self.reasons(res), [('../escaped.txt', 'outside'), ('etc', 'link_out'),
                                             ('up', 'link_out')])

    @unittest.skipUnless(HAS_LA, "libarchive is not installed")
    def test_rar4_names_and_links(self):
        arc = os.path.join(self.tmp, 'evil4.rar')
        makers.rar4(arc, [('file', '../escaped.txt', b'x'), ('symlink', 'up', '..'),
                          ('file', 'ok.txt', b'ok')])
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assert_contained()
        self.assertEqual(tree(self.dest), ['ok.txt'])

    def test_modes(self):
        arc = os.path.join(self.tmp, 'm.tar')
        with tarfile.open(arc, 'w') as tf:
            for name, mode in (('suid', 0o4755), ('noread', 0o000), ('script', 0o755)):
                ti = tarfile.TarInfo(name)
                ti.size, ti.mode = 1, mode
                tf.addfile(ti, io.BytesIO(b'x'))
        res = self.extract(arc)
        self.assertTrue(res.ok, res)
        self.assertEqual(os.stat(os.path.join(self.dest, 'suid')).st_mode & 0o7000, 0)
        self.assertTrue(os.stat(os.path.join(self.dest, 'noread')).st_mode & 0o600 == 0o600)
        self.assertTrue(os.access(os.path.join(self.dest, 'script'), os.X_OK))


# ─── questions, Cancel, where things go ───────────────────────

class TestBehaviour(Base):
    def zip(self, name, files):
        arc = os.path.join(self.tmp, name)
        with zipfile.ZipFile(arc, 'w') as zf:
            for n, data in files.items():
                zf.writestr(n, data)
        return arc

    def test_overwrite_choices(self):
        for n in ('a.txt', 'b.txt', 'c.txt'):
            with open(os.path.join(self.dest, n), 'w') as f:
                f.write('old')
        arc = self.zip('o.zip', {'a.txt': 'new', 'b.txt': 'new', 'c.txt': 'new', 'd.txt': 'new'})
        answers = Answers(overwrite=[(REPLACE, False), (SKIP, False), (KEEP_BOTH, False)])
        res = self.extract(arc, answers)
        self.assertTrue(res.ok, res)
        self.assertEqual(read(os.path.join(self.dest, 'a.txt')), b'new')
        self.assertEqual(read(os.path.join(self.dest, 'b.txt')), b'old')
        self.assertEqual(read(os.path.join(self.dest, 'c.txt')), b'old')
        self.assertEqual(read(os.path.join(self.dest, 'c (2).txt')), b'new')
        self.assertEqual((res.replaced, res.skipped), (1, 1))
        self.assertEqual(len([q for q, _ in answers.asked if q == 'overwrite']), 3)

    def test_overwrite_for_all(self):
        for n in ('a.txt', 'b.txt'):
            with open(os.path.join(self.dest, n), 'w') as f:
                f.write('old')
        arc = self.zip('o.zip', {'a.txt': 'new', 'b.txt': 'new'})
        answers = Answers(overwrite=[(REPLACE, True)])
        res = self.extract(arc, answers)
        self.assertEqual(len(answers.asked), 1)
        self.assertEqual(res.replaced, 2)

    def test_cancel_takes_back_what_it_wrote(self):
        with open(os.path.join(self.dest, 'mine.txt'), 'w') as f:
            f.write('mine')
        with open(os.path.join(self.dest, 'z.txt'), 'w') as f:
            f.write('old')
        arc = self.zip('c.zip', {'new/a.txt': 'a', 'b.txt': 'b', 'z.txt': 'new'})
        res = self.extract(arc, Answers(overwrite=[(CANCEL, False)]))
        self.assertTrue(res.cancelled)
        self.assertEqual(sorted(os.listdir(self.dest)), ['mine.txt', 'z.txt'])
        self.assertEqual(read(os.path.join(self.dest, 'z.txt')), b'old')

    def test_cancel_midway_big_file(self):
        arc = os.path.join(self.tmp, 'big.tar')
        with tarfile.open(arc, 'w') as tf:
            ti = tarfile.TarInfo('big.bin')
            ti.size = 64 << 20
            tf.addfile(ti, io.BytesIO(bytes(ti.size)))
        job = ExtractJob(arc, self.dest, new_folder=True)
        original = job._add_bytes

        def slow(n):
            original(n)
            if job.done_bytes > (8 << 20):
                job.cancel()
        job._add_bytes = slow
        res = job.run_here()
        self.assertTrue(res.cancelled)
        self.assertEqual(os.listdir(self.dest), [])        # the new folder went too

    def test_extract_to_folder(self):
        arc = self.zip('report.zip', {'a.txt': 'a', 'b/c.txt': 'c'})
        res = self.extract(arc, new_folder=True)
        self.assertEqual(res.output, os.path.join(self.dest, 'report'))
        self.assertEqual(tree(self.dest), ['report/', 'report/a.txt', 'report/b/',
                                           'report/b/c.txt'])
        res = self.extract(arc, new_folder=True)                  # again: a new folder
        self.assertEqual(res.output, os.path.join(self.dest, 'report (2)'))

    def test_extract_to_folder_no_double_folder(self):
        arc = self.zip('project.zip', {'project/a.txt': 'a', 'project/src/b.py': 'b'})
        res = self.extract(arc, new_folder=True)
        self.assertEqual(res.output, self.dest)
        self.assertEqual(tree(self.dest), ['project/', 'project/a.txt', 'project/src/',
                                           'project/src/b.py'])

    def test_selection(self):
        arc = self.zip('s.zip', {'a.txt': 'a', 'docs/b.txt': 'b', 'docs/c/d.txt': 'd',
                                 'other.txt': 'o'})
        res = self.extract(arc, selection=['docs', 'a.txt'])
        self.assertTrue(res.ok, res)
        self.assertEqual(tree(self.dest), ['a.txt', 'docs/', 'docs/b.txt', 'docs/c/',
                                           'docs/c/d.txt'])

    def test_no_space_is_checked_first(self):
        arc = os.path.join(self.tmp, 'huge.zip')
        with zipfile.ZipFile(arc, 'w') as zf:
            info = zipfile.ZipInfo('huge.bin')
            zf.writestr(info, b'')
        job = ListJob(arc)
        job.run_here()
        job.listing.entries[0].size = 1 << 60                     # an archive that lies
        res = ExtractJob(arc, self.dest, listing=job.listing).run_here()
        self.assertEqual(res.error, 'no_space')

    def test_listing(self):
        arc = self.zip('l.zip', {'a.txt': 'abc', 'd/e.txt': 'hello'})
        job = ListJob(arc)
        self.assertTrue(job.run_here().ok)
        self.assertEqual(job.listing.file_count, 2)
        self.assertEqual(job.listing.total_size, 8)

    def test_cli_list(self):
        arc = self.zip('l.zip', {'a.txt': 'abc', '../evil': 'x'})
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE),
                                                           'spark_archive.py'), '--list', arc],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('a.txt', out.stdout)
        self.assertIn('left out', out.stdout)


class TestCompress(Base):
    def make(self):
        os.makedirs(self.path('album/sub'))
        with open(self.path('album/sub/song.flac'), 'wb') as f:
            f.write(os.urandom(50_000))
        with open(self.path('album/notes.txt'), 'w') as f:
            f.write('notes ' * 1000)
        os.symlink('sub/song.flac', self.path('album/latest'))
        os.mkdir(self.path('album/empty'))

    def round_trip(self, fmt):
        self.make()
        res = CompressJob([self.path('album')], fmt).run_here()
        self.assertTrue(res.ok, res)
        self.assertEqual(res.output, self.path('album.' + fmt))
        out = ExtractJob(res.output, self.dest).run_here()
        self.assertTrue(out.ok, out)
        self.assertEqual(tree(os.path.join(self.dest, 'album')), tree(self.path('album')))
        self.assertEqual(read(os.path.join(self.dest, 'album/sub/song.flac')),
                         read(self.path('album/sub/song.flac')))
        self.assertEqual([n for n in os.listdir(self.src) if 'spark-part' in n], [])
        return res

    def test_zip(self):
        res = self.round_trip('zip')
        with zipfile.ZipFile(res.output) as zf:
            types = {i.filename: i.compress_type for i in zf.infolist()}
        self.assertEqual(types['album/sub/song.flac'], zipfile.ZIP_STORED)   # already packed
        self.assertEqual(types['album/notes.txt'], zipfile.ZIP_DEFLATED)

    def test_tar_zst(self):
        if not HAS_ZSTD and not shutil.which('zstd'):
            self.skipTest("no zstd here")
        self.round_trip('tar.zst')

    def test_names(self):
        self.make()
        with open(self.path('report.pdf'), 'w') as f:
            f.write('pdf')
        self.assertEqual(default_output([self.path('album')], 'zip'), self.path('album.zip'))
        self.assertEqual(default_output([self.path('report.pdf')], 'zip'), self.path('report.zip'))
        self.assertEqual(default_output([self.path('album'), self.path('report.pdf')], 'zip'),
                         self.path('src.zip'))
        with open(self.path('album.zip'), 'w') as f:
            f.write('taken')
        self.assertEqual(default_output([self.path('album')], 'zip'),
                         self.path('album (2).zip'))

    def test_cancel(self):
        with open(self.path('big.bin'), 'wb') as f:
            f.write(bytes(32 << 20))
        job = CompressJob([self.path('big.bin')], 'zip')
        job.cancel()
        res = job.run_here()
        self.assertTrue(res.cancelled)
        self.assertEqual(sorted(os.listdir(self.src)), ['big.bin'])

    @unittest.skipIf(ROOT, "root can read everything")
    def test_unreadable_file_is_reported(self):
        os.makedirs(self.path('d'))
        with open(self.path('d/secret'), 'w') as f:
            f.write('x')
        os.chmod(self.path('d/secret'), 0)
        with open(self.path('d/fine'), 'w') as f:
            f.write('y')
        res = CompressJob([self.path('d')], 'zip').run_here()
        self.assertTrue(res.ok)
        self.assertEqual([os.path.basename(n) for n, _ in res.problems], ['secret'])


class TestSafeWriter(Base):
    def test_no_dir_fd_through_link(self):
        os.symlink(self.outer, os.path.join(self.dest, 'out'))
        w = SafeWriter(self.dest)
        from sparkarchive.safety import Blocked
        with self.assertRaises(Blocked):
            w.write_file(('out', 'x'), io.BytesIO(b'x'))
        w.close()
        self.assertEqual(sorted(os.listdir(self.outer)), ['inner'])

    def test_undo(self):
        w = SafeWriter(self.dest)
        w.make_dir(('a', 'b'))
        w.write_file(('a', 'b', 'c'), io.BytesIO(b'c'))
        w.make_symlink(('a', 'l'), 'b/c')
        w.undo()
        self.assertEqual(os.listdir(self.dest), [])


class TestSelfTest(unittest.TestCase):
    def test_self_test(self):
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            code = cli.self_test()
        finally:
            sys.stdout = old
        print(out.getvalue())
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn('self-test passed', out.getvalue())


# ─── the windows (Xvfb) ───────────────────────────────────────

def display_ok():
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        return False
    try:
        import tkinter
        r = tkinter.Tk()
        r.destroy()
        return True
    except Exception:
        return False


HAS_DISPLAY = display_ok()


def pump(root, until, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        root.update()
        if until():
            return True
        time.sleep(0.01)
    return False


@unittest.skipUnless(HAS_DISPLAY, "no display (run under xvfb-run)")
class TestWindows(Base):
    def setUp(self):
        super().setUp()
        os.environ['XDG_CACHE_HOME'] = os.path.join(self.tmp, 'cache')
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.tmp, 'config')
        os.environ['XDG_STATE_HOME'] = os.path.join(self.tmp, 'state')

    def test_app_browse_and_extract(self):
        from sparkarchive.app import App
        arc = os.path.join(self.dest, 'pics.zip')
        with zipfile.ZipFile(arc, 'w') as zf:
            zf.writestr('pics/a.jpg', 'a' * 3000)
            zf.writestr('pics/deep/b.jpg', 'b')
            zf.writestr('../evil', 'x')
        started = time.monotonic()
        app = App(arc)
        try:
            self.assertTrue(pump(app.root, lambda: app.listing is not None), "never listed")
            took = time.monotonic() - started
            print(f"\nwindow + listing: {took * 1000:.0f} ms")
            tops = app.table.get_children()
            self.assertEqual(len(tops), 2)                       # pics/ and the unsafe one
            app._expand_iid('pics')
            self.assertIn('pics/deep', app.table.get_children('pics'))
            app.table.selection_set(['pics/deep'])
            app._update_buttons()
            self.assertTrue(app.b_selected.enabled)
            app.extract_all()
            self.assertTrue(pump(app.root, lambda: app.job is None), "extract never ended")
            self.assertEqual(read(os.path.join(self.dest, 'pics', 'a.jpg')), b'a' * 3000)
            self.assertTrue(app.result.winfo_ismapped())
            self.assert_contained()
        finally:
            app.root.destroy()

    def test_app_empty_and_dialogs_build(self):
        from sparkarchive.app import App
        app = App(None)
        try:
            pump(app.root, lambda: app.first_paint is not None, 5)
            self.assertTrue(app.empty.winfo_ismapped())
            app.root.after(200, lambda: [w.destroy() for w in app.root.winfo_children()
                                         if isinstance(w, __import__('tkinter').Toplevel)])
            self.assertIsNone(app.ask_password('x.7z', True))
            app.root.after(200, lambda: [w.destroy() for w in app.root.winfo_children()
                                         if isinstance(w, __import__('tkinter').Toplevel)])
            self.assertEqual(app.ask_overwrite({'name': 'a', 'path': 'a', 'new_size': 1,
                                                'old_size': 2, 'new_mtime': 0,
                                                'old_mtime': 0}), (CANCEL, False))
        finally:
            app.root.destroy()

    def test_job_window_extract_here_with_question(self):
        from sparkarchive.jobwindow import JobWindow
        arc = os.path.join(self.dest, 'q.zip')
        with zipfile.ZipFile(arc, 'w') as zf:
            zf.writestr('same.txt', 'new')
            zf.writestr('other.txt', 'other')
        with open(os.path.join(self.dest, 'same.txt'), 'w') as f:
            f.write('old')
        win = JobWindow('extract-here', [arc])
        asked = []

        def answer(info):
            asked.append(info['name'])
            return REPLACE, False
        win.ask_overwrite = answer
        try:
            pump(win.root, lambda: not win.root.winfo_exists() or win.job is None and
                 win.index >= 1, 15)
        except Exception:                                   # destroyed: done and clean
            pass
        self.assertEqual(asked, ['same.txt'])
        self.assertEqual(read(os.path.join(self.dest, 'same.txt')), b'new')
        self.assertEqual(read(os.path.join(self.dest, 'other.txt')), b'other')
        try:
            win.root.destroy()
        except Exception:
            pass

    def test_job_window_compress(self):
        from sparkarchive.jobwindow import JobWindow
        os.makedirs(self.path('folder'))
        with open(self.path('folder/a.txt'), 'w') as f:
            f.write('a')
        win = JobWindow('compress-zip', [self.path('folder')])
        try:
            pump(win.root, lambda: win.index >= 1 and win.job is None, 15)
        except Exception:
            pass
        self.assertTrue(os.path.isfile(self.path('folder.zip')))
        try:
            win.root.destroy()
        except Exception:
            pass


if __name__ == '__main__':
    unittest.main()
