"""The clip library: what is in ~/Videos/Clips (a folder per game), and where each clip's
thumbnail is cached. No window code here, so the tests can use it directly."""

import hashlib
import os
from typing import List, NamedTuple, Optional
from urllib.parse import quote

from .core import cache_dir, clips_dir

EXTENSIONS = ('.mp4', '.mkv', '.webm')


class Clip(NamedTuple):
    path: str
    game: str
    name: str            # the file name without its extension
    mtime: float
    size: int


def list_clips(root: Optional[str] = None) -> List[Clip]:
    """Every clip, newest first: files in the folder itself and one level of game folders.
    Half-written files (.part) and hidden ones are left out."""
    root = root or clips_dir()
    found: List[Clip] = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return found
    for entry in entries:
        if entry.startswith('.'):
            continue
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            try:
                names = os.listdir(path)
            except OSError:
                continue
            for name in names:
                _add(found, os.path.join(path, name), entry)
        else:
            _add(found, path, os.path.basename(root))
    found.sort(key=lambda c: (-c.mtime, c.path))
    return found


def _add(found: List[Clip], path: str, game: str) -> None:
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    if name.startswith('.') or ext.lower() not in EXTENSIONS:
        return
    try:
        st = os.stat(path)
    except OSError:
        return
    if os.path.isfile(path):
        found.append(Clip(path, game, stem, st.st_mtime, st.st_size))


def thumb_dir() -> str:
    path = os.path.join(cache_dir(), 'thumbs')
    os.makedirs(path, exist_ok=True)
    return path


def thumb_path(clip: Clip) -> str:
    """One cached JPEG per clip version: renaming or editing a file makes a new key."""
    key = f"{clip.path}|{clip.mtime}|{clip.size}".encode('utf-8', 'replace')
    return os.path.join(thumb_dir(), hashlib.sha1(key).hexdigest() + '.jpg')


def prune_thumbs(clips: List[Clip]) -> int:
    """Delete cached thumbnails of clips that are gone."""
    keep = {os.path.basename(thumb_path(c)) for c in clips}
    gone = 0
    for name in os.listdir(thumb_dir()):
        if name.endswith('.jpg') and name not in keep:
            try:
                os.remove(os.path.join(thumb_dir(), name))
                gone += 1
            except OSError:
                pass
    return gone


def path_to_uri(path: str) -> str:
    return 'file://' + quote(os.path.abspath(path))


def trimmed_name(folder: str, name: str) -> str:
    """A free file name for a trimmed copy: 'Name trimmed.mp4', 'Name trimmed 2.mp4'."""
    n = 1
    while True:
        suffix = ' trimmed' if n == 1 else f' trimmed {n}'
        path = os.path.join(folder, name + suffix + '.mp4')
        if not os.path.exists(path):
            return path
        n += 1
