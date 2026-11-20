"""Screenshots and other pictures from the catalog: downloaded only when an app's page opens,
kept in ~/.cache/spark-store/shots, and never sent anything but a plain HTTPS request."""

import hashlib
import os
import urllib.request
from typing import Optional, Tuple

from . import APP_NAME, VERSION
from .core import cache_dir, log

MAX_BYTES = 12 * 1024 * 1024
TIMEOUT = 20
KEEP = 400                           # files kept in the cache; the oldest go first


def shots_dir() -> str:
    path = os.path.join(cache_dir(), 'shots')
    os.makedirs(path, exist_ok=True)
    return path


def cached_path(url: str) -> str:
    ext = os.path.splitext(url.split('?')[0])[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
        ext = '.img'
    return os.path.join(shots_dir(), hashlib.sha1(url.encode()).hexdigest() + ext)


def fetch(url: str) -> Tuple[Optional[str], str]:
    """(local file, error). From the cache when it's there."""
    if not url.startswith('https://'):
        return None, 'not an https address'
    path = cached_path(url)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path, ''
    request = urllib.request.Request(url, headers={'User-Agent': f'{APP_NAME}/{VERSION}'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = response.read(MAX_BYTES + 1)
    except (OSError, ValueError) as exc:
        log.info("screenshot %s: %s", url, exc)
        return None, str(getattr(exc, 'reason', exc))
    if len(data) > MAX_BYTES:
        return None, 'too large'
    tmp = path + '.part'
    try:
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError as exc:
        return None, str(exc)
    trim()
    return path, ''


def trim() -> None:
    try:
        folder = shots_dir()
        files = [os.path.join(folder, n) for n in os.listdir(folder)]
        if len(files) <= KEEP:
            return
        files.sort(key=lambda p: os.path.getmtime(p))
        for path in files[:len(files) - KEEP]:
            os.unlink(path)
    except OSError:
        pass
