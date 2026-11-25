"""Red Hat's virtio-win ISO (the Windows drivers for virtio disks, network and video).

What the brief expected does not exist: fedorapeople.org publishes only an md5 file (CHECKSUM)
and it lists the RPM, not the ISO. So the download is checked three ways instead:
 - HTTPS only, and a redirect to plain http is refused (the server sends one for the short
   'virtio-win.iso' names, so the versioned file in the archive folder is used);
 - the size matches what the server said;
 - the SHA-256 matches the one pinned below for that version. A version that is not pinned is
   still HTTPS-checked, and the app says so and shows its SHA-256 so it can be compared by hand.
A fake opener lets the tests run this with no network."""

import hashlib
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Optional, Tuple

BASE = 'https://fedorapeople.org/groups/virt/virtio-win/direct-downloads'
LISTING = f'{BASE}/stable-virtio/CHECKSUM'
# SHA-256 of virtio-win-<version>.iso, worked out from the file downloaded over HTTPS on 2026-11-24
PINNED = {
    '0.1.302': '303f7ae40dad495d6ae474fdc571df58958a4dbc5c37a522d80f9a203867949d',
}
CHUNK = 1024 * 1024
Progress = Callable[[int, int], None]
Opener = Callable[[str], 'object']


class VirtioError(Exception):
    pass


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith('https://'):
            raise VirtioError(f"the server sent the download to {newurl.split(':')[0]}, not https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener(url: str):
    if not url.lower().startswith('https://'):
        raise VirtioError("only https downloads are allowed")
    opener = urllib.request.build_opener(_HttpsOnly)
    return opener.open(urllib.request.Request(url, headers={'User-Agent': 'spark-boxes'}),
                       timeout=30)


def parse_version(listing: str) -> Optional[str]:
    """'0.1.302' from the CHECKSUM listing, which names virtio-win-0.1.302-1.noarch.rpm."""
    found = re.search(r'virtio-win-(\d+\.\d+\.\d+)-\d+\.noarch\.rpm', listing)
    return found.group(1) if found else None


def iso_url(version: str) -> str:
    return f'{BASE}/archive-virtio/virtio-win-{version}-1/virtio-win-{version}.iso'


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def check(path: str, version: str, expected_size: int = 0) -> Tuple[bool, str]:
    """(ok, sha256). ok is False on a wrong size or a SHA-256 that differs from the pinned one;
    an unpinned version is ok (the caller says it was not pinned)."""
    digest = sha256_file(path)
    if expected_size and os.path.getsize(path) != expected_size:
        return False, digest
    pinned = PINNED.get(version)
    return (pinned is None or pinned == digest), digest


def latest_version(opener: Opener = default_opener) -> str:
    try:
        with opener(LISTING) as r:
            version = parse_version(r.read(200000).decode('utf-8', 'replace'))
    except (urllib.error.URLError, OSError) as exc:
        raise VirtioError(f"couldn't reach fedorapeople.org: {exc}") from exc
    if not version:
        raise VirtioError("couldn't tell which virtio-win version is current")
    return version


def download(dest_dir: str, progress: Optional[Progress] = None, opener: Opener = default_opener,
             version: Optional[str] = None) -> Tuple[str, str, bool]:
    """Download the ISO into dest_dir. Returns (path, sha256, pinned). The file is written under
    a temporary name and renamed only after the checks pass; nothing is left behind on failure."""
    version = version or latest_version(opener)
    final = os.path.join(dest_dir, f'virtio-win-{version}.iso')
    part = final + '.part'
    os.makedirs(dest_dir, exist_ok=True)
    try:
        with opener(iso_url(version)) as r, open(part, 'wb') as out:
            total = int(r.headers.get('Content-Length') or 0) if getattr(r, 'headers', None) else 0
            done = 0
            for block in iter(lambda: r.read(CHUNK), b''):
                out.write(block)
                done += len(block)
                if progress:
                    progress(done, total)
        ok, digest = check(part, version, total)
        if not ok:
            raise VirtioError("the download does not match its checksum or size; it was deleted")
        os.replace(part, final)
    except (urllib.error.URLError, OSError) as exc:
        raise VirtioError(f"the download failed: {exc}") from exc
    finally:
        if os.path.exists(part):
            os.unlink(part)
    return final, digest, version in PINNED
