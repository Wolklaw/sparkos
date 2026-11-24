"""The signed index: one JSON file that is an envelope around the real index.

    {"format": 1, "payload": "<the index, as JSON text>", "signature": "<base64>"}

The signature is cosign's `sign-blob` output (base64 of a DER ECDSA P-256 signature over the
SHA-256 of the payload's UTF-8 bytes), made with the same key that signs the OS image. It is
checked with `openssl dgst -sha256 -verify` against the public key baked into the image
(/usr/share/spark-apps/index-key.pub, a copy of cosign.pub). Nothing in the payload is read
before the signature checks out. One file, not a file and a .sig, so a client can never see a
new index with an old signature.

The payload:

    {"type": "sparkos-app-index", "format": 1, "serial": 7,
     "issued": "2026-11-24T12:00:00Z", "expires": "2026-12-24T12:00:00Z",
     "apps": {"spark-calc": {"version": "1.0.2", "system_api": 1, "url": "https://...",
                             "sha256": "<hex>", "size": 12345}}}
"""

import base64
import binascii
import calendar
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Dict, Optional

from . import INDEX_FORMAT, INDEX_TYPE, MAX_BUNDLE_BYTES, MAX_INDEX_BYTES, URL_PREFIX
from .paths import valid_slug, version_key

DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
MAX_SKEW = 24 * 3600        # an index issued more than a day in the future is refused
OPENSSL = '/usr/bin/openssl'


class IndexError_(Exception):
    """The index can't be trusted or understood. The message says why, in plain words."""


@dataclass(frozen=True)
class AppEntry:
    slug: str
    version: str
    system_api: int
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class Index:
    serial: int
    issued: float
    expires: float
    apps: Dict[str, AppEntry]


def parse_date(text) -> float:
    try:
        return float(calendar.timegm(time.strptime(text, DATE_FORMAT)))
    except (TypeError, ValueError):
        raise IndexError_(f"bad date {text!r}") from None


def format_date(epoch: float) -> str:
    return time.strftime(DATE_FORMAT, time.gmtime(epoch))


def verify_signature(payload: bytes, signature_b64: str, key_path: str,
                     openssl: str = OPENSSL) -> None:
    """Raises IndexError_ unless signature_b64 is a valid ECDSA/SHA-256 signature of payload."""
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, TypeError, ValueError):
        raise IndexError_("the signature isn't base64") from None
    if not 8 <= len(signature) <= 200:
        raise IndexError_("the signature has the wrong size")
    if not os.path.isfile(key_path):
        raise IndexError_("the image has no index key, so nothing can be verified")
    with tempfile.TemporaryDirectory(prefix='spark-apps-verify-') as tmp:
        payload_file, sig_file = os.path.join(tmp, 'payload'), os.path.join(tmp, 'sig')
        with open(payload_file, 'wb') as f:
            f.write(payload)
        with open(sig_file, 'wb') as f:
            f.write(signature)
        cmd = [openssl, 'dgst', '-sha256', '-verify', key_path, '-signature', sig_file,
               payload_file]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                  stdin=subprocess.DEVNULL, env={'PATH': '/usr/bin:/bin'})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IndexError_(f"openssl couldn't run: {exc}") from None
    if proc.returncode != 0 or 'Verified OK' not in proc.stdout:
        raise IndexError_("the signature doesn't match: this index isn't from SparkOS")


def _int(value, what: str, low: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise IndexError_(f"{what} must be a whole number")
    return value


def parse_payload(payload: dict) -> Index:
    if payload.get('type') != INDEX_TYPE or payload.get('format') != INDEX_FORMAT:
        raise IndexError_("not a SparkOS app index this version understands")
    serial = _int(payload.get('serial'), 'serial', 1)
    issued, expires = parse_date(payload.get('issued')), parse_date(payload.get('expires'))
    if expires <= issued:
        raise IndexError_("the index expires before it was issued")
    raw_apps = payload.get('apps')
    if not isinstance(raw_apps, dict):
        raise IndexError_("the index has no app list")
    apps: Dict[str, AppEntry] = {}
    for slug, raw in raw_apps.items():
        if not valid_slug(slug) or not isinstance(raw, dict):
            raise IndexError_(f"bad app entry {slug!r}")
        try:
            version_key(raw.get('version'))
        except ValueError:
            raise IndexError_(f"{slug}: bad version") from None
        url, sha = raw.get('url'), raw.get('sha256')
        if not isinstance(url, str) or not url.startswith(URL_PREFIX) or len(url) > 300 \
                or any(c.isspace() or ord(c) < 32 for c in url):
            raise IndexError_(f"{slug}: the download address isn't a SparkOS release")
        if not isinstance(sha, str) or not SHA256_RE.fullmatch(sha):
            raise IndexError_(f"{slug}: bad sha256")
        size = _int(raw.get('size'), f"{slug}: size", 1)
        if size > MAX_BUNDLE_BYTES:
            raise IndexError_(f"{slug}: the bundle is bigger than the limit")
        apps[slug] = AppEntry(slug, raw['version'], _int(raw.get('system_api'),
                                                         f"{slug}: system_api", 1),
                              url, sha, size)
    return Index(serial, issued, expires, apps)


def load(data: bytes, key_path: str, *, now: Optional[float] = None,
         last_serial: int = 0, openssl: str = OPENSSL) -> Index:
    """Check and read a downloaded index. Refuses: too big, not JSON, a bad signature, a serial
    lower than the last one seen (rollback), a date in the future or an index past its expiry."""
    if len(data) > MAX_INDEX_BYTES:
        raise IndexError_("the index is bigger than the limit")
    try:
        envelope = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise IndexError_("the index isn't JSON") from None
    if not isinstance(envelope, dict) or envelope.get('format') != INDEX_FORMAT:
        raise IndexError_("the index envelope isn't one this version understands")
    text, signature = envelope.get('payload'), envelope.get('signature')
    if not isinstance(text, str) or not isinstance(signature, str):
        raise IndexError_("the index envelope is incomplete")
    verify_signature(text.encode('utf-8'), signature, key_path, openssl)
    # signed: now it can be read
    try:
        payload = json.loads(text)
    except ValueError:
        raise IndexError_("the signed index isn't JSON") from None
    if not isinstance(payload, dict):
        raise IndexError_("the signed index isn't an object")
    index = parse_payload(payload)
    now = time.time() if now is None else now
    if index.serial < last_serial:
        raise IndexError_(f"this index (serial {index.serial}) is older than one already "
                          f"seen (serial {last_serial}): refused")
    if index.issued > now + MAX_SKEW:
        raise IndexError_("the index is dated in the future (is this PC's clock right?)")
    if index.expires <= now:
        raise IndexError_("the index has expired: it needs a newer one")
    return index


def make_envelope(payload_text: str, signature_b64: str) -> str:
    return json.dumps({"format": INDEX_FORMAT, "payload": payload_text,
                       "signature": signature_b64}, indent=1) + "\n"
