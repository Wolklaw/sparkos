"""A reference Spark Link phone, written from docs/spark-link-protocol.md alone. It shares no
protocol code with the PC side on purpose (only the key making), so the tests catch the PC
drifting from the document. The phone in Soot's Android app must behave the same way.

    phone = Phone(PhoneIdentity.create(folder), name='Pixel 8')
    reply = await phone.pair(link_info, code)          # sparklink:// link parsed by parse_link
    session = await phone.connect(host, port)          # mutual TLS + hello
    await session.send({'type': 'url.open', 'url': 'https://example.org'})
"""

import asyncio
import base64
import hashlib
import json
import os
import shutil
import ssl
import struct
import subprocess
import secrets
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

MAX_FRAME = 1 << 20
ALL_FEATURES = ['url', 'clipboard', 'files', 'notify', 'battery', 'ring']


class Rejected(Exception):
    """The PC's TLS stack refused this phone's certificate (it isn't paired)."""


def parse_link(link: str) -> Dict[str, str]:
    url = urlparse(link)
    if url.scheme != 'sparklink' or url.netloc != 'pair':
        raise ValueError('not a pairing link')
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    for key in ('v', 'host', 'port', 'id', 'fp', 'code'):
        if key not in q:
            raise ValueError(f'pairing link without {key}')
    return q


class PhoneIdentity:
    """What Soot keeps in the Android Keystore: a P-256 key and a self-signed certificate."""

    def __init__(self, folder: str, device_id: str):
        self.folder, self.id = folder, device_id
        self.key, self.cert = os.path.join(folder, 'key.pem'), os.path.join(folder, 'cert.pem')
        with open(self.cert, encoding='ascii') as f:
            self.der = ssl.PEM_cert_to_DER_cert(f.read())
        self.fp = hashlib.sha256(self.der).hexdigest()

    @classmethod
    def create(cls, folder: str, extensions: bool = False) -> 'PhoneIdentity':
        """Like Android's Keystore: v3, P-256, ecdsa-with-SHA256, CN = id. extensions=False
        gives no extensions at all (what KeyGenParameterSpec makes)."""
        os.makedirs(folder, exist_ok=True)
        device_id = secrets.token_hex(16)
        cnf = os.path.join(folder, 'req.cnf')
        with open(cnf, 'w', encoding='ascii') as f:
            f.write('[req]\ndistinguished_name=dn\nprompt=no\n[dn]\n[none]\n'
                    '[ext]\nbasicConstraints=critical,CA:FALSE\n'
                    'keyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n')
        cmd = [shutil.which('openssl') or 'openssl', 'req', '-x509', '-newkey', 'ec',
               '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-sha256', '-nodes',
               '-keyout', os.path.join(folder, 'key.pem'), '-out',
               os.path.join(folder, 'cert.pem'), '-days', '3650', '-subj', f'/CN={device_id}',
               '-config', cnf, '-extensions', 'ext' if extensions else 'none']
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       env=dict(os.environ, OPENSSL_CONF=cnf))
        return cls(folder, device_id)


def _client_ctx(ident: Optional[PhoneIdentity]) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE          # the PC is checked by its pinned fp instead
    if ident is not None:
        ctx.load_cert_chain(ident.cert, ident.key)
    return ctx


class Session:
    """One open connection, after the handshake."""

    def __init__(self, reader, writer, pc_fp: str):
        self.reader, self.writer, self.pc_fp = reader, writer, pc_fp
        self.next_id = 1
        self.inbox: List[Dict[str, Any]] = []
        self.pc_hello: Optional[Dict[str, Any]] = None

    async def write_frame(self, payload: bytes) -> None:
        self.writer.write(struct.pack('>I', len(payload)) + payload)
        await self.writer.drain()

    async def read_frame(self, timeout: float) -> bytes:
        try:
            head = await asyncio.wait_for(self.reader.readexactly(4), timeout)
        except ssl.SSLError as exc:
            raise Rejected(str(exc)) from None
        (n,) = struct.unpack('>I', head)
        assert n <= MAX_FRAME, f'PC sent a frame of {n} bytes'
        return await asyncio.wait_for(self.reader.readexactly(n), timeout) if n else b''

    async def send(self, msg: Dict[str, Any], binary: Optional[bytes] = None,
                   raw: Optional[bytes] = None) -> int:
        if raw is not None:
            await self.write_frame(raw)
            return -1
        if 'id' not in msg:
            msg = dict(msg, id=self.next_id)
            self.next_id += 1
        data = json.dumps(msg).encode('utf-8')
        frames = struct.pack('>I', len(data)) + data
        if binary is not None:
            frames += struct.pack('>I', len(binary)) + binary
        self.writer.write(frames)
        await self.writer.drain()
        return msg['id']

    async def recv(self, timeout: float = 10.0) -> Dict[str, Any]:
        if self.inbox:
            return self.inbox.pop(0)
        return await self._read(timeout)

    async def _read(self, timeout: float) -> Dict[str, Any]:
        msg = json.loads((await self.read_frame(timeout)).decode('utf-8'))
        assert isinstance(msg, dict) and isinstance(msg.get('type'), str), msg
        assert isinstance(msg.get('id'), int), f'PC message without an id: {msg}'
        if msg['type'] == 'file.chunk':
            msg['_data'] = await self.read_frame(timeout)
        if msg['type'] == 'ping':                 # always answer, as the doc says
            await self.send({'type': 'pong', 're': msg['id']})
        return msg

    async def expect(self, kind: str, timeout: float = 10.0, **match) -> Dict[str, Any]:
        """The next message of this type (and fields); others wait in the inbox."""
        for i, msg in enumerate(self.inbox):
            if msg['type'] == kind and all(msg.get(k) == v for k, v in match.items()):
                return self.inbox.pop(i)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            left = deadline - loop.time()
            if left <= 0:
                raise asyncio.TimeoutError(f'no {kind} {match} (inbox: '
                                           f'{[m["type"] for m in self.inbox]})')
            msg = await self._read(left)
            if msg['type'] == kind and all(msg.get(k) == v for k, v in match.items()):
                return msg
            self.inbox.append(msg)

    async def closed_by_pc(self, timeout: float = 10.0) -> bool:
        """True once the PC closes the connection (or the TLS layer says it was refused)."""
        try:
            while True:
                await self._read(timeout)
        except (asyncio.IncompleteReadError, ConnectionError, Rejected, ssl.SSLError):
            return True
        except asyncio.TimeoutError:
            return False

    async def offer_file(self, name: str, data: bytes) -> int:
        return await self.send({'type': 'file.offer', 'name': name, 'size': len(data),
                                'sha256': hashlib.sha256(data).hexdigest()})

    async def send_chunks(self, offer: int, data: bytes, chunk: int = 65536) -> None:
        pieces = [data[i:i + chunk] for i in range(0, len(data), chunk)] or [b'']
        for seq, piece in enumerate(pieces):
            await self.send({'type': 'file.chunk', 'file': offer, 'seq': seq,
                             'last': seq == len(pieces) - 1}, piece)

    async def receive_file(self, offer: Dict[str, Any], timeout: float = 20.0) -> bytes:
        """Accept an offer from the PC, take the chunks, check them, answer file.done."""
        await self.send({'type': 'file.accept', 're': offer['id']})
        data, seq = b'', 0
        while True:
            msg = await self.expect('file.chunk', timeout, file=offer['id'])
            assert msg['seq'] == seq, (msg['seq'], seq)
            assert len(msg['_data']) <= 65536
            data += msg['_data']
            seq += 1
            if msg['last']:
                break
        ok = len(data) == offer['size'] and \
            hashlib.sha256(data).hexdigest() == offer['sha256']
        await self.send({'type': 'file.done', 're': offer['id'], 'ok': ok})
        return data

    async def close(self) -> None:
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 2)
        except Exception:
            pass


class Phone:
    def __init__(self, ident: PhoneIdentity, name: str = 'Test Phone',
                 features: Optional[List[str]] = None):
        self.ident, self.name = ident, name
        self.features = list(ALL_FEATURES if features is None else features)
        self.pc: Optional[Dict[str, str]] = None        # id, name, fp after pairing

    async def _open(self, host: str, port: int, fp: str, with_cert: bool) -> Session:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(
            host, int(port), ssl=_client_ctx(self.ident if with_cert else None)), 10)
        der = writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
        got = hashlib.sha256(der).hexdigest()
        if got != fp:
            writer.close()
            raise ssl.SSLError(f'PC certificate {got} is not the pinned {fp}')
        return Session(reader, writer, fp)

    async def pair(self, info: Dict[str, str], code: Optional[str] = None,
                   host: Optional[str] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """Pairing: TLS without a client certificate, pair with our certificate inside."""
        s = await self._open(host or info['host'], int(info['port']), info['fp'], False)
        try:
            mid = await s.send({'type': 'pair', 'v': 1, 'code': code or info['code'],
                                'device': {'id': self.ident.id, 'name': self.name,
                                           'kind': 'phone'},
                                'cert': base64.b64encode(self.ident.der).decode('ascii')})
            reply = await s.recv(timeout)
            assert reply.get('re') == mid, reply
            if reply['type'] == 'pair.ok':
                dev = reply['device']
                assert dev['kind'] == 'pc' and dev['id'] == info['id'], dev
                self.pc = {'id': dev['id'], 'name': dev['name'], 'fp': info['fp']}
            assert await s.closed_by_pc(5), 'the PC must close the pairing connection'
            return reply
        finally:
            await s.close()

    async def connect(self, host: str, port: int, hello: bool = True) -> Session:
        assert self.pc, 'pair first'
        s = await self._open(host, port, self.pc['fp'], True)
        if hello:
            await s.send({'type': 'hello', 'v': 1, 'id': 0,
                          'device': {'id': self.ident.id, 'name': self.name, 'kind': 'phone'},
                          'features': self.features})
            s.next_id = 1
            s.pc_hello = await s.expect('hello')
            assert s.pc_hello['device']['id'] == self.pc['id'], s.pc_hello
            assert s.pc_hello['v'] == 1 and s.pc_hello['device']['kind'] == 'pc'
        return s
