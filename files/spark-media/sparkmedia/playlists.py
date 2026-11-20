"""Playlist files: .m3u and .m3u8, read and written with paths relative to the playlist.

Spark Media's own playlists are plain .m3u8 files in Music/Playlists, so other players and
other computers can open them too."""

import os
import re
from typing import List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

from .core import log

PLAYLIST_EXT = frozenset(('m3u', 'm3u8'))
FOLDER_NAME = 'Playlists'


class Playlist:
    """What a playlist file holds: the files it lists (absolute), and what was left out."""

    def __init__(self, path: str, items: List[str], titles: List[Optional[str]],
                 durations: List[Optional[float]], skipped: List[str]):
        self.path = path
        self.items = items
        self.titles = titles
        self.durations = durations
        self.skipped = skipped          # streams (http://...) and lines that aren't paths

    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]


def is_playlist(path: str) -> bool:
    return os.path.splitext(path)[1][1:].lower() in PLAYLIST_EXT


def _decode(data: bytes, path: str) -> str:
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        if path.lower().endswith('.m3u8'):
            log.warning("%s is not valid UTF-8; reading it as Latin-1", path)
        return data.decode('cp1252', errors='replace')     # old Windows .m3u files


def _entry_path(line: str, base: str) -> Optional[str]:
    """One line of a playlist as an absolute local path, or None for a stream or junk."""
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]+://', line):
        url = urlparse(line)
        if url.scheme != 'file':
            return None
        line = unquote(url.path)
        if os.name == 'nt' and re.match(r'^/[a-zA-Z]:', line):
            line = line[1:]
    if os.sep == '/' and '\\' in line and not os.path.exists(os.path.join(base, line)):
        line = line.replace('\\', '/')           # written on Windows
        if re.match(r'^[a-zA-Z]:/', line):
            return None                          # C:\Music\... means nothing here
    if not os.path.isabs(line):
        line = os.path.join(base, line)
    return os.path.normpath(line)


def read(path: str) -> Playlist:
    """Read an .m3u or .m3u8. Missing files stay in the list (they may be on a drive that
    isn't plugged in); the player skips them."""
    with open(path, 'rb') as f:
        text = _decode(f.read(), path)
    base = os.path.dirname(os.path.abspath(path))
    items: List[str] = []
    titles: List[Optional[str]] = []
    durations: List[Optional[float]] = []
    skipped: List[str] = []
    title: Optional[str] = None
    duration: Optional[float] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            match = re.match(r'#EXTINF:\s*(-?[0-9.]+)[^,]*,(.*)$', line)
            if match:
                try:
                    duration = float(match.group(1))
                except ValueError:
                    duration = None
                if duration is not None and duration < 0:
                    duration = None
                title = match.group(2).strip() or None
            continue
        entry = _entry_path(line, base)
        if entry is None:
            skipped.append(line)
        else:
            items.append(entry)
            titles.append(title)
            durations.append(duration)
        title, duration = None, None
    return Playlist(os.path.abspath(path), items, titles, durations, skipped)


def relative_entry(item: str, base: str) -> str:
    """item relative to the playlist's folder, with forward slashes, when it can be."""
    item = os.path.abspath(item)
    try:
        rel = os.path.relpath(item, base)
    except ValueError:               # another drive (Windows)
        return item
    return rel.replace(os.sep, '/')


def write(path: str, items: Sequence[str],
          info: Optional[Sequence[Tuple[Optional[float], Optional[str]]]] = None) -> None:
    """Write an extended M3U in UTF-8, paths relative to the playlist. info gives
    (seconds, "Artist - Title") per item for the #EXTINF lines."""
    base = os.path.dirname(os.path.abspath(path))
    lines = ['#EXTM3U']
    for i, item in enumerate(items):
        seconds, title = (info[i] if info and i < len(info) else (None, None))
        if title or seconds:
            title = (title or os.path.splitext(os.path.basename(item))[0]).replace('\n', ' ')
            lines.append(f'#EXTINF:{int(round(seconds)) if seconds else -1},{title}')
        lines.append(relative_entry(item, base))
    data = ('\n'.join(lines) + '\n').encode('utf-8')
    os.makedirs(base, exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def safe_name(name: str) -> str:
    """A playlist name usable as a file name everywhere."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', ' ', name).strip().strip('.')
    return re.sub(r'\s+', ' ', name)[:120]


def folder(music_dir: str) -> str:
    return os.path.join(music_dir, FOLDER_NAME)


def new_path(music_dir: str, name: str) -> Optional[str]:
    """Where a new playlist called name goes; None if the name is empty or taken."""
    clean = safe_name(name)
    if not clean:
        return None
    path = os.path.join(folder(music_dir), clean + '.m3u8')
    return None if os.path.exists(path) else path


def find(roots: Sequence[str], limit: int = 2000) -> List[str]:
    """Playlist files in the Playlists folder and directly in each root, by name."""
    found = {}
    for root in roots:
        for where in (root, folder(root)):
            try:
                entries = list(os.scandir(where))
            except OSError:
                continue
            for entry in entries:
                if entry.is_file() and is_playlist(entry.name):
                    found[os.path.normcase(entry.path)] = entry.path
                    if len(found) >= limit:
                        break
    from .core import natural_key
    return sorted(found.values(), key=lambda p: natural_key(os.path.basename(p)))
