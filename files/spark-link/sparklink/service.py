"""The background service (spark-link --service, a systemd user unit started at login).

It listens for phones only while one is paired or the pairing screen is open. Every
connection is TLS 1.3: phones paired with this PC present their pinned certificate (mutual
TLS); a connection without a certificate may only send `pair`, with the one-time code shown on
this PC. Idle, it waits in the event loop and uses no CPU: no timers run without a phone
connected, and a connected phone's 30 s ping is the only regular wake-up.

The window and the command line talk to it over a Unix socket in $XDG_RUNTIME_DIR that only
this user can open (control requests below, one JSON object per line).
"""

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import logging
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from . import (APP_SLUG, FEATURES, FIRST_FRAME_TIMEOUT, IDLE_TIMEOUT, MAX_CHUNK,
               MAX_CONNECTIONS, MAX_FILE, OFFER_TIMEOUT, PAIR_CODE_TTL, PAIR_CONFIRM_TIMEOUT,
               PAIR_MAX_WRONG, PROTOCOL, SERVICE_TYPE)
from . import config, identity
from .devices import Device, Devices, clean_name
from .text import t
from .wire import Link, ProtocolError

log = logging.getLogger(APP_SLUG)

URL_RE = re.compile(r'^https?://[^\s\x00-\x1f\x7f]+$', re.IGNORECASE)
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
MAX_URL = 8192
CHUNK = MAX_CHUNK
LOW_BATTERY = 15
WINDOW_POLL_GRACE = 3.0          # no status request for this long: the window isn't open


def safe_text(value: Any, limit: int) -> str:
    """A string from the phone, fit for D-Bus and the disk: no lone surrogates, capped."""
    if not isinstance(value, str):
        return ''
    return value[:limit].encode('utf-8', 'replace').decode('utf-8')


def safe_filename(name: Any) -> str:
    """A bare file name the receiver can write: no folders, control characters or leading
    dots; at most 200 characters, the extension kept."""
    text = safe_text(name, 1024)
    text = text.replace('\\', '/').split('/')[-1]
    text = ''.join(c for c in text if c >= ' ' and c != '\x7f')
    text = text.strip().lstrip('.').strip()
    if not text:
        text = 'file'
    if len(text.encode('utf-8')) > 200:
        stem, dot, ext = text.rpartition('.')
        ext = ext[:20] if dot and len(ext) <= 20 else ''
        stem = (stem if dot else text)
        while len((stem + ('.' + ext if ext else '')).encode('utf-8')) > 200:
            stem = stem[:-1]
        text = stem + ('.' + ext if ext else '')
    return text


def unique_path(folder: str, name: str) -> str:
    """folder/name, or 'name (1).ext', 'name (2).ext'... reserved so nothing is overwritten."""
    stem, dot, ext = name.rpartition('.')
    if not dot or not stem:
        stem, ext = name, ''
    for n in range(0, 10000):
        candidate = name if n == 0 else (f'{stem} ({n}).{ext}' if ext else f'{stem} ({n})')
        path = os.path.join(folder, candidate)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.close(fd)
            return path
        except FileExistsError:
            continue
    raise OSError('no free file name')


_ADDR_CACHE: Tuple[float, List[str]] = (0.0, [])


def local_addresses() -> List[str]:
    """This PC's private IPv4 addresses, the one with the default route first (looked up at
    most every 10 s: the window asks every second)."""
    global _ADDR_CACHE
    if time.monotonic() - _ADDR_CACHE[0] < 10:
        return list(_ADDR_CACHE[1])
    found: List[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('192.0.2.1', 9))            # TEST-NET: nothing is sent
            found.append(s.getsockname()[0])
    except OSError:
        pass
    ip = shutil.which('ip')
    if ip:
        try:
            out = subprocess.run([ip, '-4', '-o', 'addr', 'show', 'scope', 'global'],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 timeout=3).stdout.decode('ascii', 'replace')
            for match in re.finditer(r'\binet (\d+\.\d+\.\d+\.\d+)/', out):
                found.append(match.group(1))
        except (OSError, subprocess.TimeoutExpired):
            pass
    out: List[str] = []
    for addr in found:
        try:
            if ipaddress.ip_address(addr).is_private and addr not in out \
                    and not addr.startswith('127.'):
                out.append(addr)
        except ValueError:
            pass
    _ADDR_CACHE = (time.monotonic(), out)
    return out


def allowed_peer(host: str) -> bool:
    """Private, link-local and loopback addresses only (docs: Connection)."""
    try:
        addr = ipaddress.ip_address(host.split('%')[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_private or addr.is_link_local or addr.is_loopback


@dataclass
class PairRequest:
    device_id: str
    name: str
    fp: str
    cert: bytes
    answer: 'asyncio.Future[bool]'


@dataclass
class Pairing:
    code: str = ''
    expires: float = 0.0
    wrong: int = 0
    request: Optional[PairRequest] = None
    note: str = ''                      # why the last session ended, for the window

    @property
    def active(self) -> bool:
        return bool(self.code) and time.monotonic() < self.expires


@dataclass
class Transfer:
    key: str                            # "<device>:<in|out>:<offer id>"
    device: str
    direction: str                      # 'in' or 'out'
    offer: int
    name: str
    size: int
    sha256: str
    state: str = 'offered'              # offered, waiting, sending, receiving, done, failed...
    done: int = 0
    path: str = ''                      # out: the file sent; in: the final file
    part: str = ''                      # in: the partial file
    seq: int = 0
    hasher: Any = None
    handle: Any = None
    answer: Optional['asyncio.Future[bool]'] = None
    task: Optional['asyncio.Task'] = None
    started: float = field(default_factory=time.time)
    reason: str = ''


class Conn:
    """A phone connected over mutual TLS."""

    def __init__(self, device: Device, link: Link, peer: str):
        self.device, self.link, self.peer = device, link, peer
        self.features: Set[str] = set()
        self.since = time.time()
        self.task: Optional[asyncio.Task] = None


class Service:
    def __init__(self, settings: config.Settings, ident: identity.Identity, devices: Devices,
                 desktop, announce: bool = True, port: Optional[int] = None):
        self.settings, self.ident, self.devices, self.desktop = settings, ident, devices, desktop
        self.announce = announce
        self.port = settings.port if port is None else port
        self.bound_port = 0
        self.server: Optional[asyncio.AbstractServer] = None
        self.control_server = None
        self.announcer = None
        self.mdns_how = ''
        self.listen_error = ''
        self.pairing = Pairing()
        self.conns: Dict[str, Conn] = {}
        self.transfers: Dict[str, Transfer] = {}
        self.events: List[Dict[str, Any]] = []
        self.unauth = 0
        self.total = 0
        self.last_poll = 0.0
        self.last_remote_clip: Optional[str] = None
        self.clip_watching = False
        self.low_warned: Set[str] = set()
        self.ssl_ctx: Optional[ssl.SSLContext] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.stopped: Optional[asyncio.Event] = None
        self.rebuild_tls()

    # ───────────────────────── life ─────────────────────────

    async def run(self, control_path: Optional[str] = None) -> None:
        self.loop = asyncio.get_running_loop()
        self.stopped = asyncio.Event()
        if control_path:
            await self.start_control(control_path)
        await self.update_listening()
        await self.stopped.wait()
        await self.shutdown()

    def stop(self) -> None:
        if self.stopped is not None:
            self.stopped.set()

    async def shutdown(self) -> None:
        for conn in list(self.conns.values()):
            await conn.link.close()
        await self.stop_listening()
        if self.control_server is not None:
            self.control_server.close()
            self.control_server = None
        self.desktop.unwatch_clipboard()

    def rebuild_tls(self) -> None:
        """A fresh server context trusting exactly the paired phones' certificates. Used for
        each new connection, so pairing and unpairing take effect at once."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(self.ident.cert_path, self.ident.key_path)
        ctx.verify_mode = ssl.CERT_OPTIONAL          # no certificate: pairing only
        # a self-signed phone certificate in the store is its own trust anchor
        ctx.verify_flags = (ctx.verify_flags | getattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN', 0)) \
            & ~getattr(ssl, 'VERIFY_X509_STRICT', 0)
        cadata = self.devices.cadata()
        if cadata:
            ctx.load_verify_locations(cadata=cadata)
        self.ssl_ctx = ctx

    def should_listen(self) -> bool:
        return len(self.devices) > 0 or self.pairing.active

    async def update_listening(self) -> None:
        if self.should_listen() and self.server is None:
            await self.start_listening()
        elif not self.should_listen() and self.server is not None:
            await self.stop_listening()

    async def start_listening(self) -> None:
        try:
            self.server = await asyncio.start_server(self.on_connect, host=None, port=self.port,
                                                     reuse_address=True,
                                                     limit=2 * 1024 * 1024)
        except OSError as exc:
            self.listen_error = t('err.port', port=self.port, why=exc.strerror or str(exc))
            log.error("can't listen on port %s: %s", self.port, exc)
            self.server = None
            return
        self.listen_error = ''
        self.bound_port = self.server.sockets[0].getsockname()[1]
        log.info("listening on port %s", self.bound_port)
        if self.announce:
            from .mdns import Announcer
            self.announcer = self.announcer or Announcer()
            txt = {'v': str(PROTOCOL), 'id': self.ident.id, 'name': self.settings.display_name()}
            self.mdns_how = await self.loop.run_in_executor(
                None, self.announcer.start, self.settings.display_name(), self.bound_port, txt)

    async def stop_listening(self) -> None:
        if self.announcer is not None:
            await self.loop.run_in_executor(None, self.announcer.stop)
            self.mdns_how = ''
        if self.server is not None:
            self.server.close()
            self.server = None
            log.info("stopped listening (no paired phone, not pairing)")

    def event(self, text: str, kind: str = 'info') -> None:
        self.events.append({'t': time.time(), 'text': text, 'kind': kind})
        del self.events[:-30]

    def need_user(self) -> None:
        """Something waits for the user's answer: open the window unless it's already open."""
        if time.monotonic() - self.last_poll > WINDOW_POLL_GRACE:
            try:
                self.desktop.show_window()
            except Exception as exc:
                log.warning("couldn't open the window: %s", exc)

    # ───────────────────────── connections ─────────────────────────

    async def on_connect(self, reader: asyncio.StreamReader,
                         writer: asyncio.StreamWriter) -> None:
        peername = writer.get_extra_info('peername') or ('?', 0)
        host = str(peername[0])
        if not allowed_peer(host) or self.total >= MAX_CONNECTIONS:
            log.warning("refused a connection from %s (%s)", host,
                        'not on the local network' if not allowed_peer(host) else 'too many')
            writer.close()
            return
        self.total += 1
        link = Link(reader, writer)
        try:
            try:
                await writer.start_tls(self.ssl_ctx, ssl_handshake_timeout=FIRST_FRAME_TIMEOUT)
            except (ssl.SSLError, OSError, ConnectionError, asyncio.TimeoutError) as exc:
                log.info("TLS handshake with %s failed: %s", host, exc)
                return
            sslobj = writer.get_extra_info('ssl_object')
            der = sslobj.getpeercert(binary_form=True) if sslobj else None
            if der:
                device = self.devices.by_fp(identity.fingerprint_der(der))
                if device is None:              # trusted by a stale context; not any more
                    log.warning("certificate from %s isn't paired; closing", host)
                    return
                await self.serve_paired(device, link, host)
            else:
                if self.unauth >= 4:
                    return
                self.unauth += 1
                try:
                    await self.serve_pairing(link, host)
                finally:
                    self.unauth -= 1
        except (ProtocolError, asyncio.IncompleteReadError, asyncio.TimeoutError,
                ConnectionError, ssl.SSLError, OSError) as exc:
            log.info("connection from %s ended: %s", host, exc.__class__.__name__)
        except Exception:
            log.exception("connection from %s failed", host)
        finally:
            self.total -= 1
            await link.close()

    # ───────────────────────── pairing ─────────────────────────

    async def serve_pairing(self, link: Link, host: str) -> None:
        msg = await link.recv(FIRST_FRAME_TIMEOUT)
        if msg.get('type') != 'pair':
            log.info("unpaired connection from %s sent %r, not pair", host, msg.get('type'))
            return
        re_id = msg.get('id') if isinstance(msg.get('id'), int) else None

        async def fail(reason: str) -> None:
            await link.send({'type': 'pair.fail', 're': re_id, 'reason': reason})

        dev = msg.get('device') if isinstance(msg.get('device'), dict) else {}
        device_id = dev.get('id') if isinstance(dev.get('id'), str) else ''
        cert = identity.cert_from_b64(msg.get('cert'))
        code = msg.get('code')
        if not identity.ID_RE.match(device_id) or cert is None or not isinstance(code, str):
            await link.send({'type': 'error', 're': re_id, 'reason': 'bad-message'})
            return
        if not self.pairing.active:
            await fail('not-pairing')
            return
        if self.pairing.request is not None:
            await fail('busy')
            return
        if not hmac.compare_digest(code.encode('utf-8', 'replace'),
                                   self.pairing.code.encode('ascii')):
            self.pairing.wrong += 1
            log.warning("wrong pairing code from %s (%d of %d)", host, self.pairing.wrong,
                        PAIR_MAX_WRONG)
            if self.pairing.wrong >= PAIR_MAX_WRONG:
                self.end_pairing(t('pair.too_many'))
                self.event(t('pair.too_many'), 'error')
                await self.update_listening()
            await fail('code')
            return
        fp = identity.fingerprint_der(cert)
        if fp == self.ident.fp:
            await fail('declined')
            return
        name = clean_name(dev.get('name'))
        answer = self.loop.create_future()
        self.pairing.request = PairRequest(device_id, name, fp, cert, answer)
        log.info("pairing request from %s (%s), waiting for the user", name, host)
        self.need_user()
        try:
            yes = await asyncio.wait_for(asyncio.shield(answer), PAIR_CONFIRM_TIMEOUT)
        except asyncio.TimeoutError:
            self.end_pairing(t('pair.timeout'))
            await fail('timeout')
            await self.update_listening()
            return
        finally:
            if not answer.done():
                answer.cancel()
            self.pairing.request = None
        if not yes:
            self.end_pairing(t('pair.declined', name=name))
            await fail('declined')
            await self.update_listening()
            return
        old = self.devices.by_id(device_id)
        self.devices.add(device_id, name, cert)
        if old is not None and old.fp != fp and device_id in self.conns:
            await self.conns[device_id].link.close()
        self.rebuild_tls()
        self.end_pairing(t('pair.done', name=name))
        self.event(t('pair.done', name=name), 'ok')
        log.info("paired with %s", name)
        await link.send({'type': 'pair.ok', 're': re_id,
                         'device': {'id': self.ident.id, 'name': self.settings.display_name(),
                                    'kind': 'pc'}})
        await self.update_listening()

    def start_pairing(self) -> None:
        self.pairing = Pairing(code=f'{secrets.randbelow(10 ** 6):06d}',
                               expires=time.monotonic() + PAIR_CODE_TTL)

    def end_pairing(self, note: str = '') -> None:
        req = self.pairing.request
        if req is not None and not req.answer.done():
            req.answer.set_result(False)
        self.pairing = Pairing(note=note)

    def pairing_link(self, host: str) -> str:
        from urllib.parse import quote
        return (f'sparklink://pair?v={PROTOCOL}&host={host}&port={self.bound_port}'
                f'&id={self.ident.id}&fp={self.ident.fp}&code={self.pairing.code}'
                f'&name={quote(self.settings.display_name(), safe="")}')

    # ───────────────────────── paired phones ─────────────────────────

    async def serve_paired(self, device: Device, link: Link, host: str) -> None:
        msg = await link.recv(FIRST_FRAME_TIMEOUT)
        if msg.get('type') != 'hello' or not self._hello_ok(device, msg):
            log.warning("%s didn't start with a valid hello; closing", device.name)
            return
        conn = Conn(device, link, host)
        conn.features = self._features_of(msg)
        old = self.conns.get(device.id)
        self.conns[device.id] = conn
        if old is not None:
            await old.link.close()
        await link.send(self.hello())
        device.last_seen = time.time()
        log.info("%s connected from %s", device.name, host)
        self.event(t('ev.connected', name=device.name))
        self.update_clipboard_watch()
        try:
            while True:
                msg = await link.recv(IDLE_TIMEOUT)
                device.last_seen = time.time()
                await self.dispatch(conn, msg)
                if link.closed:
                    break
        finally:
            if self.conns.get(device.id) is conn:
                del self.conns[device.id]
                self.event(t('ev.disconnected', name=device.name))
                log.info("%s disconnected", device.name)
            for tr in [x for x in self.transfers.values()
                       if x.device == device.id and x.state in ('offered', 'waiting', 'sending',
                                                                'receiving')]:
                self.fail_transfer(tr, t('xfer.lost'))
            if self.devices.by_id(device.id) is device:
                self.devices.save()
            self.update_clipboard_watch()

    def _hello_ok(self, device: Device, msg: Dict[str, Any]) -> bool:
        dev = msg.get('device') if isinstance(msg.get('device'), dict) else {}
        v = msg.get('v')
        if not isinstance(v, int) or v < 1 or dev.get('id') != device.id:
            return False
        name = clean_name(dev.get('name'), device.name)
        if name != device.name:
            device.name = name
        return True

    @staticmethod
    def _features_of(msg: Dict[str, Any]) -> Set[str]:
        feats = msg.get('features')
        return {f for f in feats if f in FEATURES} if isinstance(feats, list) else set()

    def hello(self) -> Dict[str, Any]:
        return {'type': 'hello', 'v': PROTOCOL,
                'device': {'id': self.ident.id, 'name': self.settings.display_name(),
                           'kind': 'pc'},
                'features': self.settings.enabled()}

    def active(self, conn: Conn, feature: str) -> bool:
        return self.settings.features.get(feature, False) and feature in conn.features

    async def dispatch(self, conn: Conn, msg: Dict[str, Any]) -> None:
        kind = msg['type']
        mid = msg.get('id') if isinstance(msg.get('id'), int) else None
        link, dev = conn.link, conn.device

        async def refuse(reason: str) -> None:
            await link.send({'type': 'error', 're': mid, 'reason': reason})

        if kind == 'ping':
            await link.send({'type': 'pong', 're': mid})
        elif kind == 'pong':
            pass
        elif kind == 'hello':
            if not self._hello_ok(dev, msg):
                await link.close()
                return
            conn.features = self._features_of(msg)
            self.update_clipboard_watch()
        elif kind == 'unpair':
            self.devices.remove(dev.id)
            self.rebuild_tls()
            self.event(t('ev.unpaired_by_phone', name=dev.name))
            log.info("%s unpaired itself", dev.name)
            await link.close()
            await self.update_listening()
        elif kind == 'url.open':
            url = msg.get('url')
            if not self.active(conn, 'url'):
                await refuse('feature-off')
            elif not isinstance(url, str) or len(url) > MAX_URL or not URL_RE.match(url):
                await refuse('bad-message')
            else:
                await self.loop.run_in_executor(None, self.desktop.open_url, url)
                self.event(t('ev.link', name=dev.name))
        elif kind == 'clipboard.set':
            text = msg.get('text')
            if not self.active(conn, 'clipboard'):
                await refuse('feature-off')
            elif not isinstance(text, str):
                await refuse('bad-message')
            else:
                text = safe_text(text, 1 << 20)
                self.last_remote_clip = text
                await self.loop.run_in_executor(None, self.desktop.set_clipboard, text)
                for other in self.conns.values():      # a second phone gets it too
                    if other is not conn and self.active(other, 'clipboard'):
                        await other.link.send({'type': 'clipboard.set', 'text': text})
        elif kind == 'notify.posted':
            if not self.active(conn, 'notify'):
                await refuse('feature-off')
                return
            key = msg.get('key')
            if not isinstance(key, str) or not key or len(key) > 256:
                await refuse('bad-message')
                return
            app = clean_name(msg.get('app'), t('notify.app_unknown'))
            title = safe_text(msg.get('title'), 256).strip()
            body = safe_text(msg.get('text'), 4096).strip()
            summary = f'{app}: {title}' if title else app
            await self.loop.run_in_executor(
                None, lambda: self.desktop.notify(summary, body, key=f'{dev.id}/{key}',
                                                  app=f'{app} ({dev.name})'))
        elif kind == 'notify.removed':
            key = msg.get('key')
            if isinstance(key, str) and self.active(conn, 'notify'):
                await self.loop.run_in_executor(None, self.desktop.close_notification,
                                                f'{dev.id}/{key}')
        elif kind == 'battery':
            level, charging = msg.get('level'), msg.get('charging')
            if not self.active(conn, 'battery'):
                await refuse('feature-off')
            elif not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 100 \
                    or not isinstance(charging, bool):
                await refuse('bad-message')
            else:
                dev.battery, dev.charging = level, charging
                if level <= LOW_BATTERY and not charging:
                    if dev.id not in self.low_warned:
                        self.low_warned.add(dev.id)
                        await self.loop.run_in_executor(
                            None, lambda: self.desktop.notify(
                                t('battery.low_title', name=dev.name),
                                t('battery.low', level=level), key=f'{dev.id}/battery'))
                else:
                    self.low_warned.discard(dev.id)
        elif kind == 'ring':
            if not self.active(conn, 'ring'):
                await refuse('feature-off')
            else:
                await self.loop.run_in_executor(None, self.desktop.ring)
                await self.loop.run_in_executor(
                    None, lambda: self.desktop.notify(t('ring.here_title'),
                                                      t('ring.here', name=dev.name), urgency=2))
        elif kind == 'file.offer':
            await self.incoming_offer(conn, msg, mid)
        elif kind == 'file.chunk':
            await self.incoming_chunk(conn, msg)
        elif kind in ('file.accept', 'file.reject'):
            tr = self.transfers.get(f"{dev.id}:out:{msg.get('re')}")
            if tr and tr.answer is not None and not tr.answer.done():
                if kind == 'file.reject':
                    tr.reason = msg.get('reason') if isinstance(msg.get('reason'), str) else ''
                tr.answer.set_result(kind == 'file.accept')
        elif kind == 'file.done':
            tr = self.transfers.get(f"{dev.id}:out:{msg.get('re')}")
            if tr and tr.state in ('sending', 'sent'):
                if msg.get('ok') is True:
                    tr.state = 'done'
                    self.event(t('ev.sent', file=tr.name, name=dev.name), 'ok')
                else:
                    self.fail_transfer(tr, t('xfer.phone_check'))
        elif kind == 'file.cancel':
            fid = msg.get('file')
            for key in (f'{dev.id}:in:{fid}', f'{dev.id}:out:{fid}'):
                tr = self.transfers.get(key)
                if tr and tr.state not in ('done', 'failed', 'cancelled', 'rejected'):
                    self.fail_transfer(tr, t('xfer.cancelled_by', name=dev.name), 'cancelled')
        # anything else: ignored, so the protocol can grow

    # ───────────────────────── files in ─────────────────────────

    async def incoming_offer(self, conn: Conn, msg: Dict[str, Any], mid: Optional[int]) -> None:
        dev, link = conn.device, conn.link
        size, sha = msg.get('size'), msg.get('sha256')
        if mid is None or not isinstance(size, int) or isinstance(size, bool) or \
                not 0 <= size <= MAX_FILE or not isinstance(sha, str) or not SHA_RE.match(sha):
            await link.send({'type': 'error', 're': mid, 'reason': 'bad-message'})
            return
        key = f'{dev.id}:in:{mid}'
        if key in self.transfers and self.transfers[key].state not in ('done', 'failed',
                                                                        'rejected', 'cancelled'):
            await link.send({'type': 'file.reject', 're': mid, 'reason': 'busy'})
            return
        tr = Transfer(key, dev.id, 'in', mid, safe_filename(msg.get('name')), size, sha)
        self.transfers[key] = tr
        self._prune_transfers()
        if not self.active(conn, 'files'):
            return await self.reject_offer(tr, link, 'off')
        try:
            folder = self.desktop.downloads()
            free = shutil.disk_usage(folder).free
        except OSError:
            return await self.reject_offer(tr, link, 'space')
        if free < size + (64 << 20):
            return await self.reject_offer(tr, link, 'space')
        if dev.always_accept:
            await self.accept_offer(tr, link)
            return
        tr.state = 'waiting'
        tr.answer = self.loop.create_future()
        self.desktop.notify(t('offer.title', name=dev.name),
                            t('offer.body', file=tr.name, size=human_size(size)), key=key)
        self.need_user()
        tr.task = asyncio.ensure_future(self._await_offer(tr, link))

    async def _await_offer(self, tr: Transfer, link: Link) -> None:
        try:
            yes = await asyncio.wait_for(asyncio.shield(tr.answer), OFFER_TIMEOUT)
        except asyncio.TimeoutError:
            await self.reject_offer(tr, link, 'timeout')
            return
        except asyncio.CancelledError:
            return
        finally:
            self.desktop.close_notification(tr.key)
        if tr.state != 'waiting':
            return
        if yes:
            await self.accept_offer(tr, link)
        else:
            await self.reject_offer(tr, link, 'declined')

    async def reject_offer(self, tr: Transfer, link: Link, reason: str) -> None:
        tr.state, tr.reason = 'rejected', reason
        if not link.closed:
            await link.send({'type': 'file.reject', 're': tr.offer, 'reason': reason})

    async def accept_offer(self, tr: Transfer, link: Link) -> None:
        folder = self.desktop.downloads()
        fd, part = tempfile.mkstemp(prefix='.spark-link-', suffix='.part', dir=folder)
        tr.part, tr.handle = part, os.fdopen(fd, 'wb')
        tr.hasher = hashlib.sha256()
        tr.state, tr.seq = 'receiving', 0
        await link.send({'type': 'file.accept', 're': tr.offer})

    async def incoming_chunk(self, conn: Conn, msg: Dict[str, Any]) -> None:
        dev, link = conn.device, conn.link
        data: bytes = msg.get('_data', b'')
        tr = self.transfers.get(f"{dev.id}:in:{msg.get('file')}")
        if tr is None or tr.state != 'receiving':
            return                              # cancelled or unknown: drop the bytes
        last = msg.get('last') is True
        if msg.get('seq') != tr.seq or tr.done + len(data) > tr.size or \
                (not data and not (last and tr.size == 0 and tr.seq == 0)):
            self.fail_transfer(tr, t('xfer.broken'))
            await link.send({'type': 'file.cancel', 'file': tr.offer})
            return
        try:
            tr.handle.write(data)
        except OSError as exc:
            log.warning("writing %s failed: %s", tr.part, exc)
            self.fail_transfer(tr, t('xfer.disk', why=exc.strerror or str(exc)))
            await link.send({'type': 'file.cancel', 'file': tr.offer})
            return
        tr.hasher.update(data)
        tr.done += len(data)
        tr.seq += 1
        if not last:
            return
        tr.handle.close()
        tr.handle = None
        ok = tr.done == tr.size and hmac.compare_digest(tr.hasher.hexdigest(), tr.sha256)
        if ok:
            try:
                final = unique_path(self.desktop.downloads(), tr.name)
                os.replace(tr.part, final)
                os.chmod(final, 0o644)
                tr.path, tr.part, tr.state = final, '', 'done'
            except OSError as exc:
                log.warning("saving %s failed: %s", tr.name, exc)
                ok = False
        if ok:
            self.event(t('ev.received', file=os.path.basename(tr.path), name=dev.name), 'ok')
            self.desktop.notify(t('received.title', name=dev.name),
                                t('received.body', file=os.path.basename(tr.path)))
        else:
            self.fail_transfer(tr, t('xfer.check'))
        await link.send({'type': 'file.done', 're': tr.offer, 'ok': ok})

    def fail_transfer(self, tr: Transfer, why: str, state: str = 'failed') -> None:
        tr.state, tr.reason = state, why
        if tr.answer is not None and not tr.answer.done():
            tr.answer.set_result(False)
        if tr.task is not None and tr.direction == 'out' and not tr.task.done():
            tr.task.cancel()
        if tr.handle is not None:
            try:
                tr.handle.close()
            except OSError:
                pass
            tr.handle = None
        if tr.part:
            try:
                os.unlink(tr.part)
            except OSError:
                pass
            tr.part = ''
        self.desktop.close_notification(tr.key)
        self.event(t('ev.failed', file=tr.name, why=why), 'error')

    def _prune_transfers(self) -> None:
        finished = [k for k, x in self.transfers.items()
                    if x.state in ('done', 'failed', 'rejected', 'cancelled')]
        for key in finished[:-20]:
            del self.transfers[key]

    # ───────────────────────── files out ─────────────────────────

    async def send_files(self, conn: Conn, paths: List[str]) -> List[str]:
        errors = []
        for path in paths:
            try:
                st = os.stat(path)
            except OSError as exc:
                errors.append(f'{path}: {exc.strerror}')
                continue
            if not os.path.isfile(path) or st.st_size > MAX_FILE:
                errors.append(f'{path}: {t("send.not_file")}')
                continue
            sha = await self.loop.run_in_executor(None, file_sha256, path)
            if conn.link.closed:
                break
            mid = conn.link.new_id()
            tr = Transfer(f'{conn.device.id}:out:{mid}', conn.device.id, 'out', mid,
                          safe_filename(os.path.basename(path)), st.st_size, sha, path=path)
            tr.answer = self.loop.create_future()
            self.transfers[tr.key] = tr
            self._prune_transfers()
            await conn.link.send({'type': 'file.offer', 'id': mid, 'name': tr.name,
                                  'size': tr.size, 'sha256': sha})
            tr.task = asyncio.ensure_future(self._send_when_accepted(conn, tr))
        return errors

    async def _send_when_accepted(self, conn: Conn, tr: Transfer) -> None:
        try:
            yes = await asyncio.wait_for(asyncio.shield(tr.answer), OFFER_TIMEOUT + 30)
        except asyncio.TimeoutError:
            self.fail_transfer(tr, t('xfer.no_answer'))
            return
        except asyncio.CancelledError:
            return
        if not yes:
            if tr.state not in ('failed', 'cancelled'):
                tr.state = 'rejected'
                self.event(t('ev.rejected', file=tr.name, name=conn.device.name))
            return
        tr.state, link = 'sending', conn.link
        try:
            with open(tr.path, 'rb') as f:
                seq = 0
                while True:
                    data = f.read(CHUNK)
                    last = tr.done + len(data) >= tr.size or len(data) < CHUNK
                    await link.send({'type': 'file.chunk', 'file': tr.offer, 'seq': seq,
                                     'last': last}, data)
                    tr.done += len(data)
                    seq += 1
                    if last or tr.state != 'sending':
                        break
            if tr.state == 'sending':
                tr.state = 'sent'                # until the phone's file.done
        except asyncio.CancelledError:
            pass                                 # whoever cancelled told the phone
        except OSError as exc:
            self.fail_transfer(tr, t('xfer.disk', why=exc.strerror or str(exc)))
            if not link.closed:
                await link.send({'type': 'file.cancel', 'file': tr.offer})

    # ───────────────────────── clipboard out ─────────────────────────

    def update_clipboard_watch(self) -> None:
        want = any(self.active(c, 'clipboard') for c in self.conns.values())
        if want and not self.clip_watching:
            self.clip_watching = bool(self.desktop.watch_clipboard(self._local_clipboard))
        elif not want and self.clip_watching:
            self.desktop.unwatch_clipboard()
            self.clip_watching = False

    def _local_clipboard(self, text: str) -> None:
        """From the desktop's thread: the PC's clipboard changed."""
        if self.loop is not None:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._push_clip(text)))

    async def _push_clip(self, text: str) -> None:
        if text == self.last_remote_clip or not text:
            return                               # what a phone just sent: don't echo it
        text = safe_text(text, (1 << 20) - 1024)
        self.last_remote_clip = None
        for conn in list(self.conns.values()):
            if self.active(conn, 'clipboard') and not conn.link.closed:
                await conn.link.send({'type': 'clipboard.set', 'text': text})

    # ───────────────────────── control ─────────────────────────

    async def start_control(self, path: str) -> None:
        config.private_dir(os.path.dirname(path))
        if os.path.exists(path):
            try:
                _r, w = await asyncio.open_unix_connection(path)
                w.close()
                raise RuntimeError(t('err.running'))
            except (ConnectionRefusedError, FileNotFoundError):
                os.unlink(path)
        old = os.umask(0o177)
        try:
            self.control_server = await asyncio.start_unix_server(self.on_control, path=path,
                                                                  limit=1 << 20)
        finally:
            os.umask(old)
        os.chmod(path, 0o600)

    async def on_control(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        sock = writer.get_extra_info('socket')
        try:
            import struct
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                    struct.calcsize('3i'))
            _pid, uid, _gid = struct.unpack('3i', creds)
            if uid != os.getuid():
                writer.close()
                return
        except (OSError, AttributeError):
            writer.close()
            return
        import json
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    req = json.loads(line)
                    if not isinstance(req, dict):
                        raise ValueError('not an object')
                    reply = await self.control(req)
                except (ValueError, TypeError, KeyError) as exc:
                    reply = {'ok': False, 'error': f'bad request: {exc}'}
                writer.write((json.dumps(reply) + '\n').encode('utf-8'))
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            writer.close()

    def pick_conn(self, device_id: Optional[str]) -> Optional[Conn]:
        if device_id:
            return self.conns.get(device_id)
        return next(iter(sorted(self.conns.values(), key=lambda c: -c.since)), None)

    async def control(self, req: Dict[str, Any]) -> Dict[str, Any]:
        cmd = req.get('cmd')
        if cmd == 'status':
            if not req.get('peek'):
                self.last_poll = time.monotonic()
            return {'ok': True, **self.status()}
        if cmd == 'pair.start':
            self.start_pairing()
            await self.update_listening()
            return {'ok': True, **self.status()}
        if cmd == 'pair.cancel':
            self.end_pairing()
            await self.update_listening()
            return {'ok': True}
        if cmd == 'pair.answer':
            req_ = self.pairing.request
            if req_ is None or req_.answer.done():
                return {'ok': False, 'error': t('pair.nothing')}
            req_.answer.set_result(bool(req.get('yes')))
            return {'ok': True}
        if cmd == 'unpair':
            dev = self.devices.by_id(str(req.get('device')))
            if dev is None:
                return {'ok': False, 'error': t('err.no_device')}
            conn = self.conns.get(dev.id)
            if conn is not None:
                try:
                    await conn.link.send({'type': 'unpair'})
                except (OSError, ConnectionError):
                    pass
                await conn.link.close()
            self.devices.remove(dev.id)
            self.rebuild_tls()
            self.event(t('ev.unpaired', name=dev.name))
            await self.update_listening()
            return {'ok': True}
        if cmd == 'feature':
            name = req.get('name')
            if name not in FEATURES:
                return {'ok': False, 'error': f'unknown feature {name!r}'}
            self.settings.features[name] = bool(req.get('on'))
            self.settings.save()
            for conn in list(self.conns.values()):
                await conn.link.send(self.hello())
            self.update_clipboard_watch()
            return {'ok': True}
        if cmd == 'device.always_accept':
            dev = self.devices.by_id(str(req.get('device')))
            if dev is None:
                return {'ok': False, 'error': t('err.no_device')}
            dev.always_accept = bool(req.get('on'))
            self.devices.save()
            return {'ok': True}
        if cmd == 'file.answer':
            tr = self.transfers.get(str(req.get('key')))
            if tr is None or tr.answer is None or tr.answer.done() or tr.direction != 'in':
                return {'ok': False, 'error': t('err.no_offer')}
            tr.answer.set_result(bool(req.get('accept')))
            return {'ok': True}
        if cmd == 'transfer.cancel':
            tr = self.transfers.get(str(req.get('key')))
            if tr is None or tr.state in ('done', 'failed', 'rejected', 'cancelled'):
                return {'ok': False, 'error': t('err.no_offer')}
            conn = self.conns.get(tr.device)
            self.fail_transfer(tr, t('xfer.cancelled'), 'cancelled')
            if conn is not None:
                await conn.link.send({'type': 'file.cancel', 'file': tr.offer})
            return {'ok': True}
        if cmd in ('send.url', 'send.files', 'ring'):
            conn = self.pick_conn(req.get('device'))
            if conn is None:
                return {'ok': False, 'error': t('err.not_connected')}
            if cmd == 'ring':
                if not self.active(conn, 'ring'):
                    return {'ok': False, 'error': t('err.feature_off', name=conn.device.name)}
                await conn.link.send({'type': 'ring'})
                return {'ok': True}
            if cmd == 'send.url':
                url = req.get('url')
                if not isinstance(url, str) or len(url) > MAX_URL or not URL_RE.match(url):
                    return {'ok': False, 'error': t('err.bad_url')}
                if not self.active(conn, 'url'):
                    return {'ok': False, 'error': t('err.feature_off', name=conn.device.name)}
                await conn.link.send({'type': 'url.open', 'url': url})
                return {'ok': True}
            paths = req.get('paths')
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                return {'ok': False, 'error': 'paths must be a list'}
            if not self.active(conn, 'files'):
                return {'ok': False, 'error': t('err.feature_off', name=conn.device.name)}
            errors = await self.send_files(conn, paths)
            return {'ok': not errors or len(errors) < len(paths), 'errors': errors}
        if cmd == 'test.local_copy' and hasattr(self.desktop, 'local_copy'):
            self.desktop.local_copy(str(req.get('text', '')))
            return {'ok': True}
        if cmd == 'stop':
            self.stop()
            return {'ok': True}
        return {'ok': False, 'error': f'unknown command {cmd!r}'}

    def status(self) -> Dict[str, Any]:
        addrs = local_addresses()
        pairing: Dict[str, Any] = {'active': self.pairing.active, 'note': self.pairing.note}
        if self.pairing.active:
            host = addrs[0] if addrs else '127.0.0.1'
            pairing.update(code=self.pairing.code, link=self.pairing_link(host),
                           left=max(0, int(self.pairing.expires - time.monotonic())),
                           wrong=self.pairing.wrong)
            req = self.pairing.request
            if req is not None:
                pairing['request'] = {'name': req.name, 'key': identity.short_fp(req.fp)}
        devices = []
        for dev in self.devices.all():
            conn = self.conns.get(dev.id)
            devices.append({'id': dev.id, 'name': dev.name, 'connected': conn is not None,
                            'address': conn.peer if conn else '',
                            'last_seen': dev.last_seen, 'paired_at': dev.paired_at,
                            'battery': dev.battery, 'charging': dev.charging,
                            'always_accept': dev.always_accept, 'key': identity.short_fp(dev.fp),
                            'features': sorted(conn.features) if conn else []})
        transfers = [{'key': x.key, 'device': x.device, 'direction': x.direction,
                      'name': x.name, 'size': x.size, 'done': x.done, 'state': x.state,
                      'reason': x.reason, 'path': x.path if x.direction == 'in' else ''}
                     for x in self.transfers.values()]
        return {'pc': {'id': self.ident.id, 'name': self.settings.display_name(),
                       'key': identity.short_fp(self.ident.fp), 'fp': self.ident.fp,
                       'addresses': addrs},
                'listening': self.server is not None, 'port': self.bound_port or self.port,
                'error': self.listen_error, 'mdns': self.mdns_how,
                'features': dict(self.settings.features), 'pairing': pairing,
                'devices': devices, 'transfers': transfers, 'events': self.events[-10:],
                'clipboard': self.clip_watching}


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def human_size(n: int) -> str:
    size = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{n} B'


def run_service(announce: bool = True, port: Optional[int] = None) -> int:
    """spark-link --service"""
    import signal
    config.setup_logging(to_stderr=True)
    settings = config.Settings()
    try:
        ident = identity.load_or_create()
    except Exception as exc:
        log.error("no key: %s", exc)
        return 1
    fake = os.environ.get('SPARK_LINK_FAKE_DESKTOP')
    if fake:
        from .desktop import FakeDesktop
        desktop = FakeDesktop(fake)
    else:
        from .desktop import Desktop
        desktop = Desktop()
    service = Service(settings, ident, Devices(), desktop, announce=announce, port=port)

    async def main():
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, service.stop)
            except (NotImplementedError, RuntimeError):
                pass
        await service.run(config.control_path() if hasattr(socket, 'AF_UNIX') else None)

    try:
        asyncio.run(main())
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    log.info("stopped")
    return 0
