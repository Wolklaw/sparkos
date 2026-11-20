"""The real service against the reference phone (linkclient.py): pairing, reconnecting, every
v1 feature, and the failure cases (wrong code, wrong fingerprint, unpaired device, bad frames)."""

import asyncio
import base64
import hashlib
import os
import shutil
import socket
import ssl
import struct
import tempfile
import unittest

import harness
from linkclient import Phone, PhoneIdentity, Rejected, parse_link

HOST = '127.0.0.1'
NEED_OPENSSL = unittest.skipUnless(shutil.which('openssl'), 'needs the openssl command')


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 90))


class Base(unittest.TestCase):
    settings = None
    env = None

    def setUp(self):
        self.svc = harness.Service(self.settings, self.env).start()
        self.tmp = tempfile.mkdtemp(prefix='spark-link-phone-')

    def tearDown(self):
        self.svc.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def phone(self, name='Pixel 8', extensions=False, features=None) -> Phone:
        folder = tempfile.mkdtemp(dir=self.tmp)
        return Phone(PhoneIdentity.create(folder, extensions=extensions), name, features)

    async def pair(self, phone: Phone, answer=True):
        st = await self.svc.actl({'cmd': 'pair.start'})
        self.assertTrue(st['ok'])
        self.assertTrue(st['listening'], st)
        info = parse_link(st['pairing']['link'])
        task = asyncio.ensure_future(phone.pair(info, host=HOST))
        st = await self.svc.wait_status(lambda s: s['pairing'].get('request'))
        self.assertEqual(st['pairing']['request']['name'], phone.name)
        await self.svc.actl({'cmd': 'pair.answer', 'yes': answer})
        return await task, info

    async def paired_session(self, phone=None, **kw):
        phone = phone or self.phone(**kw)
        reply, info = await self.pair(phone)
        self.assertEqual(reply['type'], 'pair.ok', reply)
        session = await phone.connect(HOST, int(info['port']))
        await self.svc.wait_status(lambda s: any(d['connected'] for d in s['devices']))
        return phone, session, info


@NEED_OPENSSL
class Pairing(Base):
    def test_not_listening_until_pairing(self):
        st = self.svc.status()
        self.assertFalse(st['listening'])
        with self.assertRaises(OSError):
            socket.create_connection((HOST, self.svc.port), 1).close()
        self.svc.ctl({'cmd': 'pair.start'})
        self.assertTrue(self.svc.status()['listening'])
        self.svc.ctl({'cmd': 'pair.cancel'})
        self.assertFalse(self.svc.status()['listening'])

    def test_link_matches_the_pc(self):
        st = self.svc.ctl({'cmd': 'pair.start'})
        info = parse_link(st['pairing']['link'])
        self.assertEqual(info['v'], '1')
        self.assertEqual(info['id'], st['pc']['id'])
        self.assertEqual(info['fp'], st['pc']['fp'])
        self.assertRegex(info['fp'], r'^[0-9a-f]{64}$')
        self.assertRegex(info['code'], r'^\d{6}$')
        self.assertEqual(info['code'], st['pairing']['code'])
        self.assertEqual(int(info['port']), self.svc.port)
        self.assertEqual(st['pc']['key'].replace(' ', ''), info['fp'][:16].upper())

    def test_pair_connect_hello(self):
        async def go():
            phone, s, info = await self.paired_session()
            self.assertEqual(phone.pc['id'], info['id'])
            hello = s.pc_hello
            self.assertEqual(hello['type'], 'hello')
            self.assertEqual(set(hello['features']),
                             {'url', 'files', 'notify', 'battery', 'ring'})   # no clipboard
            st = self.svc.status()
            self.assertFalse(st['pairing']['active'], 'pairing ends once paired')
            dev = st['devices'][0]
            self.assertEqual((dev['name'], dev['id']), ('Pixel 8', phone.ident.id))
            self.assertTrue(dev['connected'])
            self.assertEqual(dev['key'].replace(' ', ''), phone.ident.fp[:16].upper())
            # ping/pong
            pid = await s.send({'type': 'ping'})
            await s.expect('pong', re=pid)
            await s.close()
            await self.svc.wait_status(lambda st: not st['devices'][0]['connected'])
            # reconnect later, as after a drop
            s2 = await phone.connect(HOST, int(info['port']))
            await self.svc.wait_status(lambda st: st['devices'][0]['connected'])
            await s2.close()
        run(go())

    def test_phone_cert_with_extensions(self):
        async def go():
            _p, s, _i = await self.paired_session(extensions=True)
            await s.close()
        run(go())

    def test_wrong_code_then_too_many(self):
        async def go():
            phone = self.phone()
            st = await self.svc.actl({'cmd': 'pair.start'})
            info = parse_link(st['pairing']['link'])
            wrong = f"{(int(info['code']) + 1) % 10 ** 6:06d}"
            for i in range(5):
                reply = await phone.pair(info, code=wrong, host=HOST)
                self.assertEqual((reply['type'], reply['reason']), ('pair.fail', 'code'))
            st = await self.svc.actl({'cmd': 'status', 'peek': True})
            self.assertFalse(st['pairing']['active'], 'five wrong codes stop pairing')
            self.assertFalse(st['listening'])
            self.assertEqual(st['devices'], [])
        run(go())

    def test_declined(self):
        async def go():
            phone = self.phone()
            reply, _ = await self.pair(phone, answer=False)
            self.assertEqual((reply['type'], reply['reason']), ('pair.fail', 'declined'))
            self.assertEqual(self.svc.status()['devices'], [])
        run(go())

    def test_code_works_once(self):
        async def go():
            phone, s, info = await self.paired_session()
            await s.close()
            other = self.phone('Intruder')
            reply = await other.pair(info, host=HOST)        # the old code, after it was used
            self.assertEqual((reply['type'], reply['reason']), ('pair.fail', 'not-pairing'))
        run(go())

    def test_window_opened_when_nobody_watches(self):
        async def go():
            await self.paired_session()
            await self.svc.wait_action('show_window')
        run(go())

    def test_wrong_pc_fingerprint_is_refused_by_the_phone(self):
        async def go():
            phone = self.phone()
            st = await self.svc.actl({'cmd': 'pair.start'})
            info = parse_link(st['pairing']['link'])
            info['fp'] = hashlib.sha256(b'someone else').hexdigest()
            with self.assertRaises(ssl.SSLError):
                await phone.pair(info, host=HOST)
            st = await self.svc.actl({'cmd': 'status', 'peek': True})
            self.assertNotIn('request', st['pairing'], 'no code may reach a wrong PC')
        run(go())

    def test_unknown_phone_certificate_fails_the_handshake(self):
        async def go():
            phone, s, info = await self.paired_session()
            await s.close()
            stranger = self.phone('Stranger')
            stranger.pc = dict(phone.pc)                       # knows the PC, isn't paired
            with self.assertRaises((Rejected, ssl.SSLError, ConnectionError,
                                    asyncio.IncompleteReadError)):
                s2 = await stranger.connect(HOST, int(info['port']))
                await s2.recv(5)
        run(go())

    def test_no_certificate_may_only_pair(self):
        async def go():
            phone, s, info = await self.paired_session()
            await s.close()
            bare = await phone._open(HOST, int(info['port']), info['fp'], with_cert=False)
            await bare.send({'type': 'hello', 'v': 1, 'device': {'id': phone.ident.id,
                                                                 'name': 'x', 'kind': 'phone'},
                             'features': ['url']})
            self.assertTrue(await bare.closed_by_pc(5))
        run(go())

    def test_hello_with_another_id_is_closed(self):
        async def go():
            phone, s, info = await self.paired_session()
            await s.close()
            s2 = await phone.connect(HOST, int(info['port']), hello=False)
            await s2.send({'type': 'hello', 'v': 1, 'id': 0,
                           'device': {'id': 'f' * 32, 'name': 'x', 'kind': 'phone'},
                           'features': []})
            self.assertTrue(await s2.closed_by_pc(5))
        run(go())

    def test_pc_unpairs(self):
        async def go():
            phone, s, info = await self.paired_session()
            dev = phone.ident.id
            self.assertTrue((await self.svc.actl({'cmd': 'unpair', 'device': dev}))['ok'])
            await s.expect('unpair')
            self.assertTrue(await s.closed_by_pc(5))
            st = await self.svc.actl({'cmd': 'status', 'peek': True})
            self.assertEqual(st['devices'], [])
            self.assertFalse(st['listening'], 'no phone left: stop listening')
        run(go())

    def test_phone_unpairs_then_is_unknown(self):
        async def go():
            phone, s, info = await self.paired_session()
            other, s_other, _ = await self.paired_session(self.phone('Tablet'))
            await s.send({'type': 'unpair'})
            self.assertTrue(await s.closed_by_pc(5))
            st = await self.svc.wait_status(lambda st: len(st['devices']) == 1)
            self.assertEqual(st['devices'][0]['name'], 'Tablet')
            with self.assertRaises((Rejected, ssl.SSLError, ConnectionError,
                                    asyncio.IncompleteReadError)):
                s2 = await phone.connect(HOST, int(info['port']))
                await s2.recv(5)
            await s_other.close()
        run(go())

    def test_new_connection_replaces_old(self):
        async def go():
            phone, s, info = await self.paired_session()
            s2 = await phone.connect(HOST, int(info['port']))
            self.assertTrue(await s.closed_by_pc(5))
            pid = await s2.send({'type': 'ping'})
            await s2.expect('pong', re=pid)
            await s2.close()
        run(go())

    def test_oversize_frame_closes(self):
        async def go():
            _p, s, _i = await self.paired_session()
            s.writer.write(struct.pack('>I', (1 << 20) + 1))
            await s.writer.drain()
            self.assertTrue(await s.closed_by_pc(5))
        run(go())

    def test_garbage_json_closes(self):
        async def go():
            _p, s, _i = await self.paired_session()
            await s.send({}, raw=b'{not json')
            self.assertTrue(await s.closed_by_pc(5))
        run(go())

    def test_unknown_type_is_ignored(self):
        async def go():
            _p, s, _i = await self.paired_session()
            await s.send({'type': 'sms.send', 'to': '555'})
            pid = await s.send({'type': 'ping'})
            await s.expect('pong', re=pid)
            self.assertEqual([m['type'] for m in s.inbox], [])
            await s.close()
        run(go())


@NEED_OPENSSL
class Features(Base):
    def test_url(self):
        async def go():
            _p, s, _i = await self.paired_session()
            await s.send({'type': 'url.open', 'url': 'https://wolklaw.dev/a?b=c'})
            await self.svc.wait_action('open_url', url='https://wolklaw.dev/a?b=c')
            for bad in ('javascript:alert(1)', 'file:///etc/passwd', 'https://x y',
                        '--help', 'https://' + 'a' * 9000):
                mid = await s.send({'type': 'url.open', 'url': bad})
                err = await s.expect('error', re=mid)
                self.assertEqual(err['reason'], 'bad-message')
            self.assertEqual(len(self.svc.actions('open_url')), 1)
            # the PC sends one
            r = await self.svc.actl({'cmd': 'send.url', 'url': 'https://example.org/'})
            self.assertTrue(r['ok'], r)
            msg = await s.expect('url.open')
            self.assertEqual(msg['url'], 'https://example.org/')
            r = await self.svc.actl({'cmd': 'send.url', 'url': 'ftp://example.org/'})
            self.assertFalse(r['ok'])
            await s.close()
        run(go())

    def test_feature_off_on_the_phone(self):
        async def go():
            _p, s, _i = await self.paired_session(features=['files'])
            mid = await s.send({'type': 'url.open', 'url': 'https://example.org'})
            self.assertEqual((await s.expect('error', re=mid))['reason'], 'feature-off')
            r = await self.svc.actl({'cmd': 'ring'})
            self.assertFalse(r['ok'])
            # the phone switches ring on with a new hello
            await s.send({'type': 'hello', 'v': 1, 'device': {'id': _p.ident.id,
                                                              'name': 'Pixel 8', 'kind': 'phone'},
                          'features': ['files', 'ring']})
            await asyncio.sleep(0.3)
            self.assertTrue((await self.svc.actl({'cmd': 'ring'}))['ok'])
            await s.expect('ring')
            await s.close()
        run(go())

    def test_clipboard_off_by_default_then_on(self):
        async def go():
            phone, s, _i = await self.paired_session()
            mid = await s.send({'type': 'clipboard.set', 'text': 'secret'})
            self.assertEqual((await s.expect('error', re=mid))['reason'], 'feature-off')
            self.assertEqual(self.svc.actions('set_clipboard'), [])
            await self.svc.actl({'cmd': 'feature', 'name': 'clipboard', 'on': True})
            hello = await s.expect('hello')
            self.assertIn('clipboard', hello['features'])
            await self.svc.wait_action('watch_clipboard')
            await s.send({'type': 'clipboard.set', 'text': 'from phone ✓'})
            await self.svc.wait_action('set_clipboard', text='from phone ✓')
            # the PC doesn't send it back
            await self.svc.actl({'cmd': 'test.local_copy', 'text': 'from phone ✓'})
            # something copied on the PC goes to the phone
            await self.svc.actl({'cmd': 'test.local_copy', 'text': 'from the PC'})
            msg = await s.expect('clipboard.set')
            self.assertEqual(msg['text'], 'from the PC')
            self.assertFalse(any(m['type'] == 'clipboard.set' for m in s.inbox))
            # and off again
            await self.svc.actl({'cmd': 'feature', 'name': 'clipboard', 'on': False})
            hello = await s.expect('hello')
            self.assertNotIn('clipboard', hello['features'])
            await self.svc.wait_action('unwatch_clipboard')
            await s.close()
            self.assertFalse(self.svc.status()['features']['clipboard'])
        run(go())

    def test_notifications(self):
        async def go():
            _p, s, _i = await self.paired_session()
            await s.send({'type': 'notify.posted', 'app': 'Messages', 'title': 'Sam',
                          'text': 'see <b>this</b> & that', 'key': 'k1'})
            row = await self.svc.wait_action('notify', summary='Messages: Sam')
            self.assertEqual(row['body'], 'see &lt;b&gt;this&lt;/b&gt; &amp; that')
            await s.send({'type': 'notify.posted', 'app': 'Mail‮', 'title': '',
                          'text': '', 'key': 'k2'})
            await self.svc.wait_action('notify', summary='Mail')
            await s.send({'type': 'notify.removed', 'key': 'k1'})
            await self.svc.wait_action('close_notification', id=row['id'])
            mid = await s.send({'type': 'notify.posted', 'app': 'x', 'title': 'y', 'text': ''})
            self.assertEqual((await s.expect('error', re=mid))['reason'], 'bad-message')
            await s.close()
        run(go())

    def test_battery(self):
        async def go():
            phone, s, _i = await self.paired_session()
            await s.send({'type': 'battery', 'level': 64, 'charging': True})
            st = await self.svc.wait_status(lambda st: st['devices'][0]['battery'] == 64)
            self.assertTrue(st['devices'][0]['charging'])
            self.assertEqual(self.svc.actions('notify'), [])
            await s.send({'type': 'battery', 'level': 12, 'charging': False})
            await self.svc.wait_action('notify', summary='Pixel 8: battery low')
            await s.send({'type': 'battery', 'level': 11, 'charging': False})
            mid = await s.send({'type': 'battery', 'level': 101, 'charging': False})
            self.assertEqual((await s.expect('error', re=mid))['reason'], 'bad-message')
            low = [r for r in self.svc.actions('notify') if 'battery' in r['summary']]
            self.assertEqual(len(low), 1, 'warns once per discharge')
            await s.close()
            # kept after the phone leaves
            st = await self.svc.wait_status(lambda st: not st['devices'][0]['connected'])
            self.assertEqual(st['devices'][0]['battery'], 11)
        run(go())

    def test_ring_both_ways(self):
        async def go():
            _p, s, _i = await self.paired_session()
            self.assertTrue((await self.svc.actl({'cmd': 'ring'}))['ok'])
            await s.expect('ring')
            await s.send({'type': 'ring'})
            await self.svc.wait_action('ring')
            await s.close()
            r = await self.svc.actl({'cmd': 'ring'})
            self.assertFalse(r['ok'], 'nothing connected')
        run(go())


@NEED_OPENSSL
class Files(Base):
    async def offer_and_answer(self, s, name, data, accept=True):
        mid = await s.offer_file(name, data)
        st = await self.svc.wait_status(lambda st: any(
            x['state'] == 'waiting' for x in st['transfers']))
        key = next(x['key'] for x in st['transfers'] if x['state'] == 'waiting')
        await self.svc.actl({'cmd': 'file.answer', 'key': key, 'accept': accept})
        return mid

    def test_receive_files(self):
        async def go():
            _p, s, _i = await self.paired_session()
            data = os.urandom(200_000)
            mid = await self.offer_and_answer(s, 'photo.jpg', data)
            await s.expect('file.accept', re=mid)
            await s.send_chunks(mid, data)
            done = await s.expect('file.done', re=mid)
            self.assertTrue(done['ok'])
            path = os.path.join(self.svc.downloads, 'photo.jpg')
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), data)
            # same name again: kept beside it; a path in the name is dropped; empty file
            mid = await self.offer_and_answer(s, '../../photo.jpg', b'second')
            await s.expect('file.accept', re=mid)
            await s.send_chunks(mid, b'second')
            self.assertTrue((await s.expect('file.done', re=mid))['ok'])
            with open(os.path.join(self.svc.downloads, 'photo (1).jpg'), 'rb') as f:
                self.assertEqual(f.read(), b'second')
            mid = await self.offer_and_answer(s, '.bashrc', b'')
            await s.expect('file.accept', re=mid)
            await s.send_chunks(mid, b'')
            self.assertTrue((await s.expect('file.done', re=mid))['ok'])
            self.assertTrue(os.path.isfile(os.path.join(self.svc.downloads, 'bashrc')))
            self.assertEqual(sorted(os.listdir(self.svc.downloads)),
                             ['bashrc', 'photo (1).jpg', 'photo.jpg'], 'no .part left')
            await s.close()
        run(go())

    def test_damaged_file_is_not_kept(self):
        async def go():
            _p, s, _i = await self.paired_session()
            mid = await s.send({'type': 'file.offer', 'name': 'a.bin', 'size': 4,
                                'sha256': hashlib.sha256(b'abcd').hexdigest()})
            st = await self.svc.wait_status(lambda st: st['transfers'])
            await self.svc.actl({'cmd': 'file.answer', 'key': st['transfers'][0]['key'],
                                 'accept': True})
            await s.expect('file.accept', re=mid)
            await s.send_chunks(mid, b'abce')
            self.assertFalse((await s.expect('file.done', re=mid))['ok'])
            self.assertEqual(os.listdir(self.svc.downloads), [])
            await s.close()
        run(go())

    def test_decline_cancel_always_accept(self):
        async def go():
            phone, s, _i = await self.paired_session()
            mid = await self.offer_and_answer(s, 'no.txt', b'x', accept=False)
            self.assertEqual((await s.expect('file.reject', re=mid))['reason'], 'declined')
            # always accept
            await self.svc.actl({'cmd': 'device.always_accept', 'device': phone.ident.id,
                                 'on': True})
            data = os.urandom(300_000)
            mid = await s.offer_file('big.bin', data)
            await s.expect('file.accept', re=mid)
            # cancel half-way: the partial file goes
            await s.send({'type': 'file.chunk', 'file': mid, 'seq': 0, 'last': False},
                         data[:65536])
            await s.send({'type': 'file.cancel', 'file': mid})
            await self.svc.wait_status(lambda st: any(
                x['state'] == 'cancelled' for x in st['transfers']))
            self.assertEqual(os.listdir(self.svc.downloads), [])
            # out of order chunk: the PC stops it
            mid = await s.offer_file('order.bin', data)
            await s.expect('file.accept', re=mid)
            await s.send({'type': 'file.chunk', 'file': mid, 'seq': 3, 'last': False},
                         data[:10])
            await s.expect('file.cancel', file=mid)
            self.assertEqual(os.listdir(self.svc.downloads), [])
            # switched off
            await self.svc.actl({'cmd': 'feature', 'name': 'files', 'on': False})
            mid = await s.offer_file('off.txt', b'x')
            self.assertEqual((await s.expect('file.reject', re=mid))['reason'], 'off')
            await s.close()
        run(go())

    def test_send_files_to_phone(self):
        async def go():
            _p, s, _i = await self.paired_session()
            folder = tempfile.mkdtemp(dir=self.tmp)
            files = {'one.txt': b'hello phone', 'two.bin': os.urandom(150_000),
                     'empty': b''}
            paths = []
            for name, data in files.items():
                paths.append(os.path.join(folder, name))
                with open(paths[-1], 'wb') as f:
                    f.write(data)
            r = await self.svc.actl({'cmd': 'send.files', 'paths': paths +
                                     [os.path.join(folder, 'missing')]})
            self.assertTrue(r['ok'])
            self.assertEqual(len(r['errors']), 1)
            got = {}
            for _ in files:
                offer = await s.expect('file.offer')
                got[offer['name']] = await s.receive_file(offer)
            self.assertEqual(got, files)
            await self.svc.wait_status(lambda st: sum(
                x['state'] == 'done' for x in st['transfers']) == 3)
            # the phone declines one
            r = await self.svc.actl({'cmd': 'send.files', 'paths': paths[:1]})
            offer = await s.expect('file.offer')
            await s.send({'type': 'file.reject', 're': offer['id'], 'reason': 'declined'})
            await self.svc.wait_status(lambda st: any(
                x['state'] == 'rejected' for x in st['transfers']))
            await s.close()
        run(go())


@NEED_OPENSSL
@unittest.skipUnless(harness.SUBPROCESS, 'timeouts are scaled in a separate service process')
class Timeouts(Base):
    env = {'SPARK_LINK_TEST_TIMESCALE': '0.04'}       # idle 3 s, confirm and offer 4.8 s

    def test_idle_link_is_dropped(self):
        async def go():
            _p, s, _i = await self.paired_session()
            self.assertTrue(await s.closed_by_pc(10))
        run(go())

    def test_nobody_confirms(self):
        async def go():
            phone = self.phone()
            st = await self.svc.actl({'cmd': 'pair.start'})
            reply = await phone.pair(parse_link(st['pairing']['link']), host=HOST)
            self.assertEqual((reply['type'], reply['reason']), ('pair.fail', 'timeout'))
        run(go())

    def test_offer_times_out(self):
        async def go():
            _p, s, _i = await self.paired_session()
            mid = await s.offer_file('late.txt', b'x')
            pid = await s.send({'type': 'ping'})
            await s.expect('pong', re=pid)
            self.assertEqual((await s.expect('file.reject', 10, re=mid))['reason'], 'timeout')
            await s.close()
        run(go())

    def test_silent_unpaired_connection_is_dropped(self):
        async def go():
            self.svc.ctl({'cmd': 'pair.start'})
            r, w = await asyncio.open_connection(HOST, self.svc.port, ssl=_bare_ctx())
            try:
                data = await asyncio.wait_for(r.read(), 15)
                self.assertEqual(data, b'')
            finally:
                w.close()
        run(go())


def _bare_ctx():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


if __name__ == '__main__':
    unittest.main()
