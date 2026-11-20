"""Download a pinned file, check its SHA-256, unpack it. Nothing else is trusted: not the
server, not the file name, not the size it announces. A mismatch deletes the file."""

import hashlib
import os
import shutil
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
from typing import Callable, Optional

from . import APP_SLUG, VERSION
from .core import cache_dir, ensure, log
from .sources import Download

CHUNK = 256 * 1024
Progress = Callable[[str, int, int], None]      # stage ('download', 'unpack'), done, total


class FetchError(Exception):
    """kind: 'network', 'mismatch', 'space', 'unpack', 'cancelled'"""

    def __init__(self, kind: str, detail: str = ''):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind, self.detail = kind, detail


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def free_bytes(path: str) -> int:
    while path and not os.path.exists(path):
        path = os.path.dirname(path)
    try:
        return shutil.disk_usage(path or '/').free
    except OSError:
        return 1 << 62


def download(item: Download, progress: Optional[Progress] = None,
             cancel: Optional[threading.Event] = None) -> str:
    """The verified archive in ~/.cache/spark-run, downloading it if it isn't there yet."""
    folder = ensure(cache_dir())
    final = os.path.join(folder, item.filename)
    if os.path.isfile(final) and os.path.getsize(final) == item.size \
            and sha256_of(final) == item.sha256:
        return final
    if free_bytes(folder) < item.size + (64 << 20):
        raise FetchError('space', folder)
    part = final + '.part'
    h = hashlib.sha256()
    done = 0
    request = urllib.request.Request(item.url, headers={'User-Agent': f'{APP_SLUG}/{VERSION}'})
    log.info("downloading %s from %s", item.name, item.url)
    try:
        with urllib.request.urlopen(request, timeout=30) as response, open(part, 'wb') as out:
            while True:
                if cancel is not None and cancel.is_set():
                    raise FetchError('cancelled')
                block = response.read(CHUNK)
                if not block:
                    break
                done += len(block)
                if done > item.size:
                    raise FetchError('mismatch', f"{item.filename} is larger than "
                                                 f"{item.size} bytes")
                h.update(block)
                out.write(block)
                if progress:
                    progress('download', done, item.size)
    except FetchError:
        _unlink(part)
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _unlink(part)
        raise FetchError('network', str(getattr(exc, 'reason', exc))) from exc
    got = h.hexdigest()
    if done != item.size or got != item.sha256:
        _unlink(part)
        log.error("%s: expected sha256 %s (%d bytes), got %s (%d bytes); deleted",
                  item.filename, item.sha256, item.size, got, done)
        raise FetchError('mismatch', f"{item.filename}: SHA-256 {got}")
    os.replace(part, final)
    log.info("%s verified: sha256 %s", item.filename, got)
    return final


def unpack(archive: str, item: Download, into: str,
           progress: Optional[Progress] = None) -> str:
    """Unpack the archive's top folder (item.folder) into `into`; returns its path. Unpacks
    to a temporary folder first and renames it, so a half-unpacked Wine is never used."""
    ensure(into)
    target = os.path.join(into, item.folder)
    if os.path.isdir(target):
        return target
    tmp = tempfile.mkdtemp(prefix='.unpack-', dir=into)
    try:
        with tarfile.open(archive, 'r:*') as tar:
            members = tar.getmembers()
            for m in members:
                name = m.name.lstrip('./')
                if os.path.isabs(m.name) or '..' in m.name.split('/') or \
                        not (name == item.folder or name.startswith(item.folder + '/')):
                    raise FetchError('unpack', f"unexpected path in archive: {m.name}")
            for i, m in enumerate(members):
                kwargs = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}
                tar.extract(m, tmp, **kwargs)
                if progress and (i % 200 == 0 or i == len(members) - 1):
                    progress('unpack', i + 1, len(members))
        os.replace(os.path.join(tmp, item.folder), target)
    except FetchError:
        raise
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise FetchError('space' if getattr(exc, 'errno', None) == 28 else 'unpack',
                         str(exc)) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return target


def fetch(item: Download, into: str, progress: Optional[Progress] = None,
          cancel: Optional[threading.Event] = None, keep_archive: bool = False) -> str:
    target = os.path.join(into, item.folder)
    if os.path.isdir(target):
        return target
    archive = download(item, progress, cancel)
    path = unpack(archive, item, into, progress)
    if not keep_archive:
        _unlink(archive)
    return path


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
