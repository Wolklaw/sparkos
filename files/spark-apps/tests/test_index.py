import json
import unittest

from helpers import (HAVE_OPENSSL, NOW, Fixture, entry_for, payload_text, sign_text,
                     signed_index)
from sparkapps import index as index_mod
from sparkapps.index import IndexError_

DATA = b'bundle'


@unittest.skipUnless(HAVE_OPENSSL, 'needs /usr/bin/openssl')
class IndexTests(Fixture):
    def apps(self):
        return {'spark-calc': entry_for('spark-calc', '1.0.1', DATA)}

    def load(self, data, key=None, **kw):
        kw.setdefault('now', NOW)
        return index_mod.load(data, key or self.pub, **kw)

    def test_good_index(self):
        index = self.load(signed_index(self.priv, self.apps(), serial=3))
        self.assertEqual(index.serial, 3)
        self.assertEqual(index.apps['spark-calc'].version, '1.0.1')

    def test_wrong_key(self):
        with self.assertRaises(IndexError_):
            self.load(signed_index(self.priv, self.apps()), key=self.pub2)

    def test_tampered_payload(self):
        envelope = json.loads(signed_index(self.priv, self.apps()))
        envelope['payload'] = envelope['payload'].replace('1.0.1', '9.9.9')
        with self.assertRaises(IndexError_):
            self.load(json.dumps(envelope).encode())

    def test_bad_signature_text(self):
        envelope = json.loads(signed_index(self.priv, self.apps()))
        for bad in ('', 'not base64!!', 'AAAA', 5, None):
            envelope['signature'] = bad
            with self.assertRaises(IndexError_, msg=repr(bad)):
                self.load(json.dumps(envelope).encode())

    def test_signature_over_other_payload(self):
        text = payload_text(self.apps(), serial=2)
        other = sign_text(self.priv, payload_text(self.apps(), serial=3))
        with self.assertRaises(IndexError_):
            self.load(index_mod.make_envelope(text, other).encode())

    def test_missing_key_file(self):
        with self.assertRaises(IndexError_):
            self.load(signed_index(self.priv, self.apps()), key=self.tmp + '/none.pub')

    def test_rollback_serial(self):
        data = signed_index(self.priv, self.apps(), serial=4)
        self.assertEqual(self.load(data, last_serial=4).serial, 4)    # same serial: fine
        with self.assertRaises(IndexError_) as ctx:
            self.load(data, last_serial=5)
        self.assertIn('older', str(ctx.exception))

    def test_expired(self):
        data = signed_index(self.priv, self.apps(), issued=NOW - 200, expires=NOW - 1)
        with self.assertRaises(IndexError_) as ctx:
            self.load(data)
        self.assertIn('expired', str(ctx.exception))

    def test_issued_in_the_future(self):
        data = signed_index(self.priv, self.apps(), issued=NOW + 3 * 86400,
                            expires=NOW + 9 * 86400)
        with self.assertRaises(IndexError_):
            self.load(data)

    def test_expires_before_issued(self):
        data = signed_index(self.priv, self.apps(), issued=NOW - 10, expires=NOW - 20)
        with self.assertRaises(IndexError_):
            self.load(data)

    def test_url_must_be_a_sparkos_release(self):
        for url in ('http://github.com/Wolklaw/sparkos/releases/download/x/y.tar.gz',
                    'https://evil.example/x.tar.gz', 'file:///etc/passwd'):
            apps = self.apps()
            apps['spark-calc']['url'] = url
            with self.assertRaises(IndexError_, msg=url):
                self.load(signed_index(self.priv, apps))

    def test_bad_entries(self):
        cases = [('slug', {'../x': entry_for('spark-calc', '1.0.1', DATA)}),
                 ('version', {'spark-calc': dict(self.apps()['spark-calc'], version='1.x')}),
                 ('sha', {'spark-calc': dict(self.apps()['spark-calc'], sha256='ab')}),
                 ('size', {'spark-calc': dict(self.apps()['spark-calc'], size=0)}),
                 ('huge', {'spark-calc': dict(self.apps()['spark-calc'], size=10 ** 10)}),
                 ('api', {'spark-calc': dict(self.apps()['spark-calc'], system_api='1')}),
                 ('bool', {'spark-calc': dict(self.apps()['spark-calc'], system_api=True)})]
        for name, apps in cases:
            with self.assertRaises(IndexError_, msg=name):
                self.load(signed_index(self.priv, apps))

    def test_not_json_and_wrong_shape(self):
        for data in (b'', b'{', b'[]', b'{"format": 2}', b'\xff\xfe',
                     json.dumps({'format': 1, 'payload': 5, 'signature': 'x'}).encode()):
            with self.assertRaises(IndexError_, msg=data):
                self.load(data)

    def test_too_big(self):
        with self.assertRaises(IndexError_):
            self.load(b' ' * (300 * 1024))

    def test_wrong_type(self):
        text = json.dumps({'type': 'other', 'format': 1})
        data = index_mod.make_envelope(text, sign_text(self.priv, text)).encode()
        with self.assertRaises(IndexError_):
            self.load(data)


if __name__ == '__main__':
    unittest.main()
