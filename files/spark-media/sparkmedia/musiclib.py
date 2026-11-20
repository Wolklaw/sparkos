"""The music library: every song under the Music folder (and folders you add), grouped by
artist and album.

A background thread walks the folders and reads tags only for files that are new or changed
since last time; the index is kept in ~/.cache/spark-media/music.json and album covers in
~/.cache/spark-media/covers/. Nothing runs between scans: no file watching, no timers."""

import hashlib
import json
import os
import queue
import threading
import time
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from PIL import Image

from . import tags as tagreader
from .core import cache_dir, folder_cover, kind_of, log, natural_key
from .playlists import is_playlist

INDEX_VERSION = 1
FIELDS = ('path', 'mtime', 'size', 'title', 'artist', 'albumartist', 'album', 'track', 'disc',
          'year', 'genre', 'length')
COVER_SIZE = 320
BATCH = 250                  # songs per update sent to the window during a scan
SAVE_EVERY = 3000            # save the index this often during a long first scan


def index_path() -> str:
    return os.path.join(cache_dir(), 'music.json')


def covers_dir() -> str:
    return os.path.join(cache_dir(), 'covers')


def _sort_text(text: str) -> Tuple:
    low = text.casefold().strip()
    for article in ('the ', 'les ', 'le ', 'la ', "l'"):
        if low.startswith(article) and len(low) > len(article):
            low = low[len(article):]
            break
    return natural_key(low)


class Album:
    __slots__ = ('key', 'title', 'artist', 'year', 'songs', 'folder', 'length')

    def __init__(self, key: str, title: str):
        self.key, self.title = key, title
        self.artist = ''
        self.year = 0
        self.songs: List[Dict[str, Any]] = []
        self.folder = ''
        self.length = 0.0

    @property
    def cover_id(self) -> str:
        return hashlib.md5(self.key.encode('utf-8')).hexdigest()


def album_key(song: Dict[str, Any]) -> str:
    """Songs with the same album artist and album are one album. Without an album artist, the
    album is the album name in that folder, so a compilation stays together."""
    album = song.get('album') or ''
    if song.get('albumartist'):
        return f"a\x1f{song['albumartist'].casefold()}\x1f{album.casefold()}"
    if not album:
        return f"u\x1f{(song.get('artist') or '').casefold()}"
    return f"f\x1f{os.path.dirname(song['path'])}\x1f{album.casefold()}"


def display_title(song: Dict[str, Any]) -> str:
    return song.get('title') or os.path.splitext(os.path.basename(song['path']))[0]


class Library:
    """Songs by path, and the views built from them (rebuilt when songs change)."""

    def __init__(self):
        self.songs: Dict[str, Dict[str, Any]] = {}
        self.playlists: List[str] = []
        self.roots: List[str] = []
        self._views: Optional[Dict[str, Any]] = None

    # ── loading and saving ──
    @classmethod
    def load(cls, path: Optional[str] = None) -> 'Library':
        lib = cls()
        path = path or index_path()
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if data.get('version') != INDEX_VERSION:
                return lib
            for row in data.get('songs', []):
                if isinstance(row, list) and len(row) == len(FIELDS):
                    song = dict(zip(FIELDS, row))
                    lib.songs[song['path']] = song
            lib.playlists = [p for p in data.get('playlists', []) if isinstance(p, str)]
            lib.roots = [p for p in data.get('roots', []) if isinstance(p, str)]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError) as exc:
            log.warning("music index unreadable, starting over: %s", exc)
            lib.songs.clear()
        return lib

    def save(self, path: Optional[str] = None) -> None:
        path = path or index_path()
        data = {'version': INDEX_VERSION, 'roots': self.roots, 'playlists': self.playlists,
                'songs': [[song.get(k) for k in FIELDS] for song in self.songs.values()]}
        tmp = f'{path}.{os.getpid()}.tmp'
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("could not save the music index: %s", exc)

    # ── changes ──
    def update(self, changed: Iterable[Dict[str, Any]], removed: Iterable[str] = ()) -> None:
        for song in changed:
            self.songs[song['path']] = song
        for path in removed:
            self.songs.pop(path, None)
        self._views = None

    # ── views ──
    def _build(self) -> Dict[str, Any]:
        albums: Dict[str, Album] = {}
        for song in self.songs.values():
            key = album_key(song)
            album = albums.get(key)
            if album is None:
                album = albums[key] = Album(key, song.get('album') or '')
                album.folder = os.path.dirname(song['path'])
            album.songs.append(song)
        artists: Dict[str, Dict[str, Any]] = {}
        for album in albums.values():
            album.songs.sort(key=lambda s: (s.get('disc') or 0, s.get('track') or 0,
                                            natural_key(os.path.basename(s['path']))))
            names = {s.get('albumartist') or s.get('artist') or '' for s in album.songs}
            album.artist = names.pop() if len(names) == 1 else ''
            album.year = max((s.get('year') or 0) for s in album.songs)
            album.length = sum((s.get('length') or 0) for s in album.songs)
            for song in album.songs:
                name = song.get('albumartist') or song.get('artist') or ''
                entry = artists.get(name.casefold())
                if entry is None:
                    entry = artists[name.casefold()] = {'name': name, 'albums': [], 'ids': set()}
                if id(album) not in entry['ids']:
                    entry['ids'].add(id(album))
                    entry['albums'].append(album)
        last = '￿'              # no name sorts after every name
        album_list = sorted(albums.values(), key=lambda a: (_sort_text(a.artist or last),
                                                            a.year, _sort_text(a.title or last)))
        artist_list = sorted(artists.values(), key=lambda a: _sort_text(a['name'] or last))
        for key, entry in artists.items():
            del entry['ids']
            entry['albums'].sort(key=lambda a: (a.year, _sort_text(a.title)))
            entry['songs'] = [s for a in entry['albums'] for s in a.songs
                              if (s.get('albumartist') or s.get('artist') or '').casefold() == key]
        songs = [s for a in album_list for s in a.songs]
        return {'albums': album_list, 'artists': artist_list, 'songs': songs,
                'by_key': albums, 'by_artist': artists}

    def views(self) -> Dict[str, Any]:
        if self._views is None:
            self._views = self._build()
        return self._views

    def albums(self) -> List[Album]:
        return self.views()['albums']

    def artists(self) -> List[Dict[str, Any]]:
        return self.views()['artists']

    def all_songs(self) -> List[Dict[str, Any]]:
        return self.views()['songs']

    def album(self, key: str) -> Optional[Album]:
        return self.views()['by_key'].get(key)

    def artist(self, name: str) -> Optional[Dict[str, Any]]:
        return self.views()['by_artist'].get(name.casefold())

    def song(self, path: str) -> Optional[Dict[str, Any]]:
        return self.songs.get(path)


def fold(text: str) -> str:
    """Lower case without accents: 'Céline' -> 'celine'."""
    text = unicodedata.normalize('NFKD', text.casefold())
    return ''.join(c for c in text if not unicodedata.combining(c))


def matches(words: Sequence[str], *fields: str) -> bool:
    """Every word of a search appears in one of the fields (case and accents ignored)."""
    hay = fold(' '.join(f for f in fields if f))
    return all(w in hay for w in words)


def search_words(text: str) -> List[str]:
    return [w for w in fold(text).split() if w]


# ─── Covers ───────────────────────────────────────────────────

def cover_path(cover_id: str) -> str:
    return os.path.join(covers_dir(), cover_id + '.jpg')


def store_cover(cover_id: str, image: Image.Image) -> None:
    path = cover_path(cover_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        image = image.convert('RGB')
        image.thumbnail((COVER_SIZE, COVER_SIZE), Image.Resampling.LANCZOS)
        tmp = f'{path}.{os.getpid()}.tmp'
        image.save(tmp, 'JPEG', quality=88)
        os.replace(tmp, path)
    except OSError as exc:
        log.debug("could not cache cover %s: %s", cover_id, exc)


def load_cover(cover_id: str) -> Optional[Image.Image]:
    try:
        with Image.open(cover_path(cover_id)) as image:
            image.load()
            return image.copy()
    except (OSError, ValueError):
        return None


# ─── Scanning ─────────────────────────────────────────────────

def walk(roots: Sequence[str], stop: Optional[threading.Event] = None
         ) -> Tuple[Dict[str, Tuple[float, int]], List[str]]:
    """Every music file under the roots with (mtime, size), and every playlist. Hidden folders
    are skipped; a folder linked twice is walked once."""
    files: Dict[str, Tuple[float, int]] = {}
    playlist_files: List[str] = []
    seen: Set[str] = set()
    pending = [os.path.abspath(r) for r in roots if os.path.isdir(r)]
    while pending:
        if stop is not None and stop.is_set():
            break
        folder = pending.pop()
        try:
            real = os.path.realpath(folder)
        except OSError:
            continue
        if real in seen:
            continue
        seen.add(real)
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.name.startswith('.'):
                        continue
                    try:
                        if entry.is_dir():
                            pending.append(entry.path)
                        elif entry.is_file():
                            if kind_of(entry.name) == 'music':
                                st = entry.stat()
                                files[entry.path] = (st.st_mtime, st.st_size)
                            elif is_playlist(entry.name):
                                playlist_files.append(entry.path)
                    except OSError:
                        continue
        except OSError as exc:
            log.debug("cannot list %s: %s", folder, exc)
    playlist_files.sort(key=lambda p: natural_key(os.path.basename(p)))
    return files, playlist_files


class Scanner:
    """Brings a Library up to date with the disk in a thread. The window calls poll() from a
    Tk timer while running is True and applies what it gets; nothing touches Tk here."""

    def __init__(self, library: Library, roots: Sequence[str],
                 reader: Callable[[str, bool], Dict[str, Any]] = tagreader.read):
        self.library = library
        self.roots = [os.path.abspath(r) for r in roots]
        self.reader = reader
        self.events: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.stats: Dict[str, Any] = {}
        self.changed = False

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        known = {path: (song.get('mtime'), song.get('size'))
                 for path, song in self.library.songs.items()}
        album_keys = {path: album_key(song) for path, song in self.library.songs.items()}
        self.thread = threading.Thread(target=self._run, args=(known, album_keys), daemon=True,
                                       name='music-scan')
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self, known: Dict[str, Tuple[Any, Any]], album_keys: Dict[str, str]) -> None:
        started = time.monotonic()
        try:
            files, playlist_files = walk(self.roots, self.stop_event)
            walked = time.monotonic() - started
            if self.stop_event.is_set():
                return
            removed = [p for p in known if p not in files]
            todo = [p for p, stamp in files.items() if known.get(p) != stamp]
            todo.sort(key=lambda p: natural_key(p))
            self.events.put(('start', {'total': len(todo), 'removed': removed,
                                       'playlists': playlist_files, 'roots': self.roots}))
            try:
                have = {name[:-4] for name in os.listdir(covers_dir()) if name.endswith('.jpg')}
            except OSError:
                have = set()
            tried: Set[str] = set()
            batch: List[Dict[str, Any]] = []
            for i, path in enumerate(todo):
                if self.stop_event.is_set():
                    break
                guess_key = album_keys.get(path)
                guess_id = hashlib.md5(guess_key.encode('utf-8')).hexdigest() if guess_key else None
                want = guess_id is None or (guess_id not in have and guess_id not in tried)
                result = self.reader(path, want)
                song = dict(result['song'])
                song['mtime'], song['size'] = files[path]
                cover_id = hashlib.md5(album_key(song).encode('utf-8')).hexdigest()
                if cover_id not in have and cover_id not in tried:
                    tried.add(cover_id)
                    image = None
                    if result.get('cover'):
                        image = tagreader.cover_from_bytes(result['cover'])
                    elif not want:
                        image = tagreader.cover_from_bytes(
                            self.reader(path, True).get('cover') or b'')
                    if image is None:
                        folder_image = folder_cover(path)
                        if folder_image:
                            try:
                                with Image.open(folder_image) as source:
                                    source.draft('RGB', (COVER_SIZE * 2, COVER_SIZE * 2))
                                    image = source.convert('RGB')
                            except Exception:      # noqa: BLE001
                                image = None
                    if image is not None:
                        store_cover(cover_id, image)
                        have.add(cover_id)
                batch.append(song)
                if len(batch) >= BATCH:
                    self.events.put(('songs', batch))
                    batch = []
                    self.events.put(('progress', i + 1))
                    if (i + 1) % SAVE_EVERY < BATCH:
                        self.events.put(('save', None))
            if batch:
                self.events.put(('songs', batch))
            self.stats = {'files': len(files), 'read': len(todo), 'removed': len(removed),
                          'walk_s': round(walked, 3),
                          'total_s': round(time.monotonic() - started, 3)}
            log.info("music scan: %s", self.stats)
        except Exception as exc:      # noqa: BLE001
            log.exception("music scan failed")
            self.events.put(('error', str(exc)))
        finally:
            self.events.put(('done', self.stats))

    def poll(self, limit: int = 40) -> List[Tuple[str, Any]]:
        """Apply what the thread found to the library; return the events for the window."""
        out = []
        for _ in range(limit):
            try:
                what, data = self.events.get_nowait()
            except queue.Empty:
                break
            if what == 'start':
                if (data['removed'] or data['playlists'] != self.library.playlists
                        or data['roots'] != self.library.roots):
                    self.changed = True
                self.library.update((), data['removed'])
                self.library.playlists = data['playlists']
                self.library.roots = data['roots']
            elif what == 'songs':
                self.changed = True
                self.library.update(data)
            elif what == 'save':
                self.library.save()
            elif what == 'done':
                self.running = False
                if self.changed:                 # nothing to write after a quiet rescan
                    self.library.save()
            out.append((what, data))
        return out
