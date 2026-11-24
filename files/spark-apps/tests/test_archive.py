import os
import stat
import tarfile
import tempfile
import unittest

from helpers import bundle_bytes
from sparkapps import archive


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spark-apps-arc-')
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, 'out')

    def extract(self, data, **kw):
        path = os.path.join(self.tmp.name, 'b.tar.gz')
        with open(path, 'wb') as f:
            f.write(data)
        return archive.extract(path, self.out, **kw)

    def refused(self, data, **kw):
        with self.assertRaises(archive.ArchiveError):
            self.extract(data, **kw)
        self.assertFalse(os.path.exists(self.out), "a refused bundle leaves nothing behind")

    def member(self, name, kind, linkname=''):
        info = tarfile.TarInfo(name)
        info.type, info.linkname = kind, linkname
        return info

    def test_plain_bundle(self):
        count = self.extract(bundle_bytes({'a.py': b'x', 'pkg/b.py': b'y', 'pkg/sub/c.txt': b'z'}))
        self.assertEqual(count, 3)
        with open(os.path.join(self.out, 'pkg', 'sub', 'c.txt')) as f:
            self.assertEqual(f.read(), 'z')

    def test_modes_ignore_the_archive(self):
        info = self.member('x', tarfile.REGTYPE)
        info.mode, info.size = 0o6777, 1                  # setuid, setgid, world-writable
        self.extract(bundle_bytes({}, [(info, b'1')]))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.out, 'x')).st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(os.stat(self.out).st_mode), 0o755)

    def test_absolute_path(self):
        self.refused(bundle_bytes({'/etc/evil': b'x'}))

    def test_dotdot(self):
        self.refused(bundle_bytes({'../evil': b'x'}))
        self.refused(bundle_bytes({'a/../../evil': b'x'}))
        self.refused(bundle_bytes({'a/./b': b'x'}))

    def test_backslash_and_empty(self):
        self.refused(bundle_bytes({'a\\b': b'x'}))
        self.refused(bundle_bytes({'a//b': b'x'}))

    def test_symlink(self):
        link = self.member('l', tarfile.SYMTYPE, '/etc/passwd')
        self.refused(bundle_bytes({'a.py': b'x'}, [(link, None)]))

    def test_symlink_then_write_through_it(self):
        link = self.member('d', tarfile.SYMTYPE, '/tmp')
        data = bundle_bytes({}, [(link, None)])
        self.refused(data)

    def test_hardlink(self):
        link = self.member('h', tarfile.LNKTYPE, 'a.py')
        self.refused(bundle_bytes({'a.py': b'x'}, [(link, None)]))

    def test_device_and_fifo(self):
        self.refused(bundle_bytes({'a.py': b'x'}, [(self.member('d', tarfile.CHRTYPE), None)]))
        self.refused(bundle_bytes({'a.py': b'x'}, [(self.member('f', tarfile.FIFOTYPE), None)]))

    def test_duplicate_name(self):
        info = self.member('a.py', tarfile.REGTYPE)
        info.size = 1
        self.refused(bundle_bytes({'a.py': b'x'}, [(info, b'y')]))

    def test_file_inside_a_file(self):
        self.refused(bundle_bytes({'a': b'x', 'a/b': b'y'}))

    def test_size_limits(self):
        self.refused(bundle_bytes({'a': b'x' * 100, 'b': b'y' * 100}), max_unpacked=150)

    def test_too_deep(self):
        self.refused(bundle_bytes({'/'.join(['d'] * 30) + '/f': b'x'}))

    def test_empty_and_garbage(self):
        self.refused(bundle_bytes({}))
        self.refused(b'this is not a tar.gz')
        self.refused(b'')


if __name__ == '__main__':
    unittest.main()
