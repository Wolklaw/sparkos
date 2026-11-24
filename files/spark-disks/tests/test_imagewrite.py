"""The image writer, with a temp file standing in for the stick. No real device is opened."""

import gzip
import lzma
import os
import tempfile
import threading
import unittest

import support
from sparkdisks import imagewrite
from sparkdisks.ops import BadInput, Ops, Refused
from support import FakeBackend, GB, tree

STICK = '/dev/sparksb'


class Write(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.device = os.path.join(self.dir.name, 'device')
        with open(self.device, 'wb') as f:
            f.truncate(8 * 1024 * 1024)
        self.backend = FakeBackend()
        self.ops = Ops(self.backend, tree)
        self.cancel = threading.Event()
        self.seen = []

    def fds(self, writes=1, reads=1):
        out = [os.open(self.device, os.O_WRONLY) for _ in range(writes)]
        out += [os.open(self.device, os.O_RDONLY) for _ in range(reads)]
        self.backend.fds = out

    def image(self, name='a.img', data=None):
        path = os.path.join(self.dir.name, name)
        data = data if data is not None else os.urandom(5 * 1024 * 1024 + 123)
        opener = {'.gz': gzip.open, '.xz': lzma.open}.get(os.path.splitext(name)[1], open)
        with opener(path, 'wb') as f:
            f.write(data)
        return path, data

    def run_write(self, path, target=STICK, verify=True):
        return imagewrite.write_image(self.ops, self.backend, path, target,
                                      lambda *a: self.seen.append(a), self.cancel, verify)

    def device_start(self, n):
        with open(self.device, 'rb') as f:
            return f.read(n)

    def test_plain_image_is_written_and_verified(self):
        path, data = self.image()
        self.fds()
        self.run_write(path)
        self.assertEqual(self.device_start(len(data)), data)
        phases = {a[0] for a in self.seen}
        self.assertEqual(phases, {'write', 'verify'})
        self.assertEqual(self.seen[-1][1:], (len(data), len(data)))
        self.assertEqual(self.backend.calls[0], ('unmount', '/dev/sparksb1'))

    def test_packed_images(self):
        for name in ('a.img.gz', 'a.img.xz'):
            with self.subTest(name=name):
                path, data = self.image(name, os.urandom(3 * 1024 * 1024 + 7))
                self.fds()
                self.run_write(path)
                self.assertEqual(self.device_start(len(data)), data)

    def test_verify_can_be_off(self):
        path, _d = self.image()
        self.fds(1, 0)
        self.run_write(path, verify=False)
        self.assertEqual([c[0] for c in self.backend.calls if c[0] == 'open'], ['open'])
        self.assertNotIn('verify', {a[0] for a in self.seen})

    def test_a_stick_that_does_not_keep_the_data_fails_verification(self):
        path, data = self.image()
        self.fds(0, 0)
        other = os.path.join(self.dir.name, 'other')
        with open(other, 'wb') as f:
            f.truncate(8 * 1024 * 1024)
        wfd = os.open(self.device, os.O_WRONLY)
        rfd = os.open(other, os.O_RDONLY)             # reads back something else
        self.backend.fds = [wfd, rfd]
        with self.assertRaises(imagewrite.VerifyFailed) as caught:
            self.run_write(path)
        self.assertEqual(caught.exception.offset, 0)

    def test_cancel_stops_the_write(self):
        path, _d = self.image()
        self.fds(1, 0)
        self.cancel.set()
        with self.assertRaises(imagewrite.Cancelled):
            self.run_write(path)
        self.assertEqual(self.device_start(16), bytes(16))

    def test_image_bigger_than_the_stick_is_refused_before_anything_happens(self):
        path = os.path.join(self.dir.name, 'big.img')
        with open(path, 'wb') as f:
            f.truncate(17 * GB)
        with self.assertRaises(BadInput) as caught:
            self.run_write(path)
        self.assertEqual(caught.exception.key, 'bad.image_big')
        self.assertEqual(self.backend.calls, [])

    def test_only_removable_drives(self):
        path, _d = self.image()
        for target in ('/dev/sparkn0', '/dev/sparksa', '/dev/sparksc', '/dev/sparksb1'):
            with self.subTest(target=target):
                with self.assertRaises(Refused):
                    self.run_write(path, target)
        self.assertEqual(self.backend.calls, [])

    def test_bad_files(self):
        with self.assertRaises(BadInput) as caught:
            self.run_write(os.path.join(self.dir.name, 'nope.img'))
        self.assertEqual(caught.exception.key, 'bad.image_missing')
        empty = os.path.join(self.dir.name, 'empty.img')
        open(empty, 'wb').close()
        with self.assertRaises(BadInput) as caught:
            self.run_write(empty)
        self.assertEqual(caught.exception.key, 'bad.image_empty')
        broken = os.path.join(self.dir.name, 'broken.img.gz')
        with open(broken, 'wb') as f:
            f.write(b'this is not gzip data' * 40)
        with self.assertRaises(BadInput) as caught:
            self.run_write(broken)
        self.assertEqual(caught.exception.key, 'bad.image_unreadable')
        self.assertEqual(self.backend.calls, [])

    def test_a_descriptor_for_another_device_is_refused(self):
        path, _d = self.image()
        self.fds(1, 0)
        real = imagewrite._same_device
        imagewrite._same_device = lambda fd, p: False
        self.addCleanup(setattr, imagewrite, '_same_device', real)
        with self.assertRaises(OSError):
            self.run_write(path)
        self.assertEqual(self.device_start(16), bytes(16))

    def test_sizes(self):
        path, data = self.image()
        self.assertEqual(imagewrite.image_size(path), len(data))
        gz, _d = self.image('b.img.gz')
        self.assertEqual(imagewrite.image_size(gz), 0)


if __name__ == '__main__':
    unittest.main()
