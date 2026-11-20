"""The parts on their own: file names from phones, addresses, names, the paired-phone store,
keys, the QR encoder, the strings table."""

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from sparklink import identity, qr                                  # noqa: E402
from sparklink.devices import Devices, clean_name                   # noqa: E402
from sparklink.service import (allowed_peer, human_size, safe_filename, safe_text,  # noqa: E402
                               unique_path)
from sparklink.text import EN                                       # noqa: E402


class Names(unittest.TestCase):
    def test_safe_filename(self):
        cases = {
            'photo.jpg': 'photo.jpg',
            '../../etc/passwd': 'passwd',
            '..\\..\\Windows\\win.ini': 'win.ini',
            '.bashrc': 'bashrc',
            '...': 'file',
            '': 'file',
            None: 'file',
            'a\x00b\nc.txt': 'abc.txt',
            '  spaced  .txt ': 'spaced  .txt',
            'résumé ✓.pdf': 'résumé ✓.pdf',
            '\udcff.txt': '?.txt',
        }
        for raw, want in cases.items():
            self.assertEqual(safe_filename(raw), want, raw)
        long = safe_filename('x' * 500 + '.jpeg')
        self.assertTrue(long.endswith('.jpeg'))
        self.assertLessEqual(len(long.encode('utf-8')), 200)
        self.assertLessEqual(len(safe_filename('é' * 300).encode('utf-8')), 200)

    def test_unique_path(self):
        folder = tempfile.mkdtemp()
        try:
            a = unique_path(folder, 'a.txt')
            b = unique_path(folder, 'a.txt')
            c = unique_path(folder, 'a.txt')
            d = unique_path(folder, 'noext')
            e = unique_path(folder, 'noext')
            self.assertEqual([os.path.basename(p) for p in (a, b, c, d, e)],
                             ['a.txt', 'a (1).txt', 'a (2).txt', 'noext', 'noext (1)'])
        finally:
            shutil.rmtree(folder)

    def test_clean_name(self):
        self.assertEqual(clean_name('Pixel 8'), 'Pixel 8')
        self.assertEqual(clean_name('  Sam‮\n  phone\t'), 'Sam phone')
        self.assertEqual(clean_name(''), 'Phone')
        self.assertEqual(clean_name(42), 'Phone')
        self.assertEqual(len(clean_name('x' * 200)), 64)

    def test_safe_text(self):
        self.assertEqual(safe_text('ok', 10), 'ok')
        self.assertEqual(safe_text('a\ud800b', 10), 'a?b')
        self.assertEqual(safe_text(None, 10), '')
        self.assertEqual(safe_text('abcdef', 3), 'abc')

    def test_human_size(self):
        self.assertEqual(human_size(12), '12 B')
        self.assertEqual(human_size(1536), '1.5 KB')
        self.assertEqual(human_size(5 << 30), '5.0 GB')


class Addresses(unittest.TestCase):
    def test_local_only(self):
        for ok in ('192.168.1.5', '10.0.0.2', '172.16.4.4', '127.0.0.1', '::1',
                   'fe80::1%eth0', 'fd12:3456::1', '::ffff:192.168.1.9', '169.254.3.3'):
            self.assertTrue(allowed_peer(ok), ok)
        for bad in ('8.8.8.8', '2001:4860:4860::8888', '::ffff:8.8.8.8', '100.64.1.1',
                    'not an address'):
            self.assertFalse(allowed_peer(bad), bad)


@unittest.skipUnless(identity.backend(), 'needs openssl or cryptography')
class Keys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_identity_is_made_once_and_private(self):
        a = identity.load_or_create(self.tmp)
        b = identity.load_or_create(self.tmp)
        self.assertEqual((a.id, a.fp), (b.id, b.fp))
        self.assertRegex(a.id, r'^[0-9a-f]{32}$')
        self.assertRegex(a.fp, r'^[0-9a-f]{64}$')
        self.assertRegex(identity.short_fp(a.fp), r'^[0-9A-F]{4}( [0-9A-F]{4}){3}$')
        if os.name == 'posix':
            for name in ('key.pem', 'cert.pem', 'id'):
                mode = stat.S_IMODE(os.stat(os.path.join(self.tmp, name)).st_mode)
                self.assertEqual(mode, 0o600, name)
            self.assertEqual(stat.S_IMODE(os.stat(self.tmp).st_mode), 0o700)
        self.assertEqual(sorted(os.listdir(self.tmp)), ['cert.pem', 'id', 'key.pem'])
        if shutil.which('openssl'):
            text = subprocess.run(['openssl', 'x509', '-in', a.cert_path, '-noout', '-text'],
                                  stdout=subprocess.PIPE, check=True).stdout.decode()
            self.assertIn('prime256v1', text)
            self.assertIn('ecdsa-with-SHA256', text)
            self.assertIn(f'CN={a.id}', text.replace('CN = ', 'CN='))

    def test_cert_from_b64(self):
        a = identity.load_or_create(self.tmp)
        self.assertEqual(identity.cert_from_b64(a.cert_b64), a.cert_der)
        for bad in (None, 42, '', 'not base64!' * 20, base64.b64encode(b'x' * 200).decode(),
                    'A' * 20000):
            self.assertIsNone(identity.cert_from_b64(bad), bad)

    def test_devices_store_keeps_only_matching_pins(self):
        a = identity.load_or_create(self.tmp)
        path = os.path.join(self.tmp, 'devices.json')
        store = Devices(path)
        dev = store.add('phone1', 'Pixel\x00 8', a.cert_der)
        self.assertEqual(dev.name, 'Pixel 8')
        self.assertEqual(Devices(path).by_fp(a.fp).id, 'phone1')
        self.assertIn('BEGIN CERTIFICATE', store.cadata())
        # someone edits the stored fp: that entry is no longer trusted
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        data['devices'][0]['fp'] = '0' * 64
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        self.assertEqual(len(Devices(path)), 0)
        store = Devices(path)
        store.add('phone1', 'x', a.cert_der)
        store.add('phone2', 'y', a.cert_der)                # same certificate, new id
        self.assertEqual([d.id for d in Devices(path).all()], ['phone2'])
        self.assertTrue(store.remove('phone2'))
        self.assertFalse(store.remove('phone2'))


class QR(unittest.TestCase):
    LINK = ('sparklink://pair?v=1&host=192.168.100.200&port=47100&id=' + '0123456789abcdef' * 2 +
            '&fp=' + '89abcdef' * 8 + '&code=042137&name=Rock%27s%20PC')

    def test_shape(self):
        m = qr.encode(self.LINK, 'M')
        size = len(m)
        self.assertEqual((size - 17) % 4, 0)
        self.assertTrue(all(len(row) == size for row in m))
        for x, y in ((0, 0), (size - 7, 0), (0, size - 7)):      # the three finder squares
            self.assertTrue(all(m[y][x + i] for i in range(7)))
            self.assertTrue(all(m[y + 6][x + i] for i in range(7)))
            self.assertFalse(m[y + 1][x + 1])
            self.assertTrue(m[y + 3][x + 3])
        self.assertTrue(m[size - 8][8], 'the dark module')

    def test_known_small_code(self):
        # 'HELLO' at level M, mask 0: checked against two other encoders
        m = qr.encode('HELLO', 'M', mask=0)
        self.assertEqual(len(m), 21)
        bits = ''.join('1' if v else '0' for v in m[8][:9])
        # format bits 0x5412 for M with mask 0: bits 14-9, the timing module, bits 8 and 7
        self.assertEqual(bits, '101010100')

    def test_too_long(self):
        with self.assertRaises(ValueError):
            qr.encode('x' * 3000, 'H')

    @unittest.skipUnless(shutil.which('zbarimg'), 'needs zbarimg')
    def test_scans(self):
        """A real QR reader reads back every level and several sizes."""
        tmp = tempfile.mkdtemp()
        try:
            for level in 'LMQH':
                for text in (self.LINK, 'x', 'https://example.org/' + 'a' * 300):
                    m = qr.encode(text, level)
                    path = os.path.join(tmp, 'code.pgm')
                    write_pgm(m, path)
                    out = subprocess.run(['zbarimg', '--raw', '-q', path],
                                         stdout=subprocess.PIPE, timeout=30)
                    self.assertEqual(out.stdout.decode().strip(), text, (level, len(text)))
        finally:
            shutil.rmtree(tmp)


def write_pgm(matrix, path, scale=4, border=4):
    size = len(matrix)
    side = (size + 2 * border) * scale
    rows = []
    for y in range(-border, size + border):
        row = bytearray()
        for x in range(-border, size + border):
            dark = 0 <= x < size and 0 <= y < size and matrix[y][x]
            row += bytes([0 if dark else 255]) * scale
        rows.extend([bytes(row)] * scale)
    with open(path, 'wb') as f:
        f.write(f'P5 {side} {side} 255\n'.encode('ascii') + b''.join(rows))


class Strings(unittest.TestCase):
    def test_every_key_used_exists(self):
        used = set()
        folder = os.path.join(APP, 'sparklink')
        for name in os.listdir(folder):
            if name.endswith('.py'):
                with open(os.path.join(folder, name), encoding='utf-8') as f:
                    used |= set(re.findall(r"\bt\('([a-z_.]+)'", f.read()))
        dynamic = {f'app.tab.{k}' for k in ('devices', 'pair', 'features')} | \
            {f'feat.{k}' for k in ('url', 'clipboard', 'files', 'notify', 'battery', 'ring')} |             {f'xfer.state.{k}' for k in ('waiting', 'offered', 'sending', 'sent', 'receiving',
                                         'done', 'failed', 'rejected', 'cancelled')}
        missing = sorted(k for k in used | dynamic if k not in EN and not k.endswith('.'))
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
