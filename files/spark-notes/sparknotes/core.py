"""Everything that doesn't need a window: folders, settings, the notes on disk and the
clipboard history. No GTK in here, so the clipboard watcher (which starts for every copy)
stays quick."""

import fcntl
import hashlib
import json
import logging
import os
import shutil
import time
import unicodedata
import uuid
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Iterator, List, NamedTuple, Optional

from . import APP_SLUG

log = logging.getLogger(APP_SLUG)

CHROME = {
    'bg': '#04090b', 'panel': '#0a1517', 'panel2': '#0e1f22', 'hover': '#12292c',
    'line': '#143a3d', 'line2': '#1f6a66', 'text': '#d4f1ec', 'muted': '#6f9f98',
    'dim': '#3b6460', 'accent': '#3de8c8', 'on_accent': '#02130f', 'pink': '#ff4d8d',
    'ch_a': '#ff2e88', 'ch_b': '#22d8ff', 'gold': '#f4c95d',
}

MAX_TEXT_BYTES = 1024 * 1024          # a copy bigger than this is not kept
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES = 12                       # unpinned images kept, whatever the item limit
IMAGE_TYPES = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/bmp': 'bmp'}
PASSWORD_HINT = 'x-kde-passwordManagerHint'

DEFAULTS: Dict[str, Any] = {
    'max_items': 50,        # unpinned clipboard items kept
    'paused': False,        # "don't keep": the watcher ignores everything
    'images': True,         # keep copied images too
    'keep_alive': True,     # put the last item back when the program that copied it closes
    'glitch': True,
}
MAX_ITEMS_RANGE = (5, 500)

# --- Folders and the log ------------------------------------


def _xdg_dir(variable: str, fallback: str, create: bool = True, private: bool = False) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
            if private:
                os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def config_dir(create: bool = True) -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config', create)


def state_dir(create: bool = True) -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'), create)


def data_dir(create: bool = True) -> str:
    """~/.local/share/spark-notes: the notes and the clipboard history. Only you can read it."""
    return _xdg_dir('XDG_DATA_HOME', os.path.join('.local', 'share'), create, private=True)


def setup_logging() -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(os.path.join(state_dir(), f'{APP_SLUG}.log'),
                                      maxBytes=128 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())


def _write_atomic(path: str, data: bytes, mode: int = 0o600) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def fold(text: str) -> str:
    """Lower case, no accents: what search compares."""
    decomposed = unicodedata.normalize('NFD', text.casefold())
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


# --- Settings -----------------------------------------------


def clean_settings(data: Any) -> Dict[str, Any]:
    out = dict(DEFAULTS)
    if not isinstance(data, dict):
        return out
    n = data.get('max_items')
    if isinstance(n, int) and not isinstance(n, bool):
        out['max_items'] = max(MAX_ITEMS_RANGE[0], min(MAX_ITEMS_RANGE[1], n))
    for key in ('paused', 'images', 'keep_alive', 'glitch'):
        if isinstance(data.get(key), bool):
            out[key] = data[key]
    return out


def settings_path() -> str:
    return os.path.join(config_dir(), 'settings.json')


def load_settings(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(path or settings_path(), encoding='utf-8') as f:
            return clean_settings(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings: Dict[str, Any], path: Optional[str] = None) -> bool:
    try:
        _write_atomic(path or settings_path(),
                      json.dumps(clean_settings(settings), indent=2).encode('utf-8'))
        return True
    except OSError as exc:
        log.warning("couldn't save settings: %s", exc)
        return False


# --- Notes ---------------------------------------------------


class Note(NamedTuple):
    id: str
    title: str
    body: str
    pinned: bool
    updated: float

    def snippet(self, limit: int = 80) -> str:
        lines = [ln.strip() for ln in self.body.splitlines() if ln.strip()]
        return (lines[1] if len(lines) > 1 else '')[:limit]


def note_title(body: str) -> str:
    """The first line that has words in it, without Markdown heading marks."""
    for line in body.splitlines():
        line = line.strip().lstrip('#').strip()
        if line:
            return line[:120]
    return ''


class NoteStore:
    """One text file per note in <data>/notes/<id>.md, pins in pins.json, deleted notes in
    <data>/trash/. Writes are atomic, so a crash never leaves half a note."""

    def __init__(self, root: Optional[str] = None):
        self.root = root or data_dir()
        self.notes_dir = os.path.join(self.root, 'notes')
        self.trash_dir = os.path.join(self.root, 'trash')
        self.pins_path = os.path.join(self.root, 'pins.json')
        for d in (self.notes_dir, self.trash_dir):
            os.makedirs(d, mode=0o700, exist_ok=True)

    def _path(self, note_id: str) -> str:
        if not note_id or not all(c.isalnum() for c in note_id):
            raise ValueError(f"bad note id {note_id!r}")
        return os.path.join(self.notes_dir, note_id + '.md')

    def _pins(self) -> List[str]:
        try:
            with open(self.pins_path, encoding='utf-8') as f:
                data = json.load(f)
            return [p for p in data if isinstance(p, str)] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def load(self, note_id: str) -> Optional[Note]:
        path = self._path(note_id)
        try:
            with open(path, encoding='utf-8') as f:
                body = f.read()
            updated = os.path.getmtime(path)
        except (OSError, UnicodeDecodeError):
            return None
        return Note(note_id, note_title(body), body, note_id in self._pins(), updated)

    def save(self, note_id: str, body: str) -> bool:
        """Write the note. An empty one is not kept (and an old file for it is removed)."""
        path = self._path(note_id)
        try:
            if not body.strip():
                if os.path.exists(path):
                    os.unlink(path)
                return True
            _write_atomic(path, body.encode('utf-8'))
            return True
        except OSError as exc:
            log.warning("couldn't save note %s: %s", note_id, exc)
            return False

    def list(self, query: str = '') -> List[Note]:
        pins = set(self._pins())
        notes = []
        try:
            names = os.listdir(self.notes_dir)
        except OSError:
            return []
        for name in names:
            if name.endswith('.md'):
                note = self.load(name[:-3])
                if note is not None:
                    notes.append(note)
        words = fold(query).split()
        if words:
            notes = [n for n in notes if all(w in fold(n.body) for w in words)]
        notes.sort(key=lambda n: (n.id not in pins, -n.updated))
        return notes

    def set_pinned(self, note_id: str, pinned: bool) -> None:
        pins = [p for p in self._pins() if p != note_id]
        if pinned:
            pins.append(note_id)
        try:
            _write_atomic(self.pins_path, json.dumps(pins).encode('utf-8'))
        except OSError as exc:
            log.warning("couldn't save pins: %s", exc)

    def delete(self, note_id: str) -> bool:
        """Move to the trash folder (Undo puts it back; nothing is erased)."""
        try:
            shutil.move(self._path(note_id), os.path.join(self.trash_dir, note_id + '.md'))
            return True
        except (OSError, ValueError) as exc:
            log.warning("couldn't delete note %s: %s", note_id, exc)
            return False

    def restore(self, note_id: str) -> bool:
        try:
            shutil.move(os.path.join(self.trash_dir, note_id + '.md'), self._path(note_id))
            return True
        except (OSError, ValueError):
            return False


# --- Clipboard history -----------------------------------------


class Item(NamedTuple):
    id: str
    kind: str              # 'text' or 'image'
    text: str              # the text, or '' for an image
    mime: str              # the type to offer when copying again
    file: str              # image file name inside images/, or ''
    sha: str
    time: float
    pinned: bool
    size: int

    def preview(self, limit: int = 240) -> str:
        if self.kind == 'image':
            return ''
        flat = '\n'.join(ln.rstrip() for ln in self.text.strip().splitlines()[:4])
        return flat if len(flat) <= limit else flat[:limit - 1] + '…'


class History:
    """<data>/clipboard/history.json plus images/. Every change locks a file first, because the
    watcher, the popup and the notes window can all write at once."""

    def __init__(self, root: Optional[str] = None):
        self.dir = os.path.join(root or data_dir(), 'clipboard')
        self.images = os.path.join(self.dir, 'images')
        self.path = os.path.join(self.dir, 'history.json')
        self.lock_path = os.path.join(self.dir, '.lock')
        os.makedirs(self.images, mode=0o700, exist_ok=True)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with open(self.lock_path, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self) -> List[Item]:
        try:
            with open(self.path, encoding='utf-8') as f:
                raw = json.load(f).get('items', [])
        except (OSError, ValueError, AttributeError):
            return []
        items = []
        for r in raw:
            try:
                items.append(Item(str(r['id']), r['kind'], r.get('text', ''), r['mime'],
                                  r.get('file', ''), r['sha'], float(r['time']),
                                  bool(r.get('pinned')), int(r.get('size', 0))))
            except (KeyError, TypeError, ValueError):
                continue
        return items

    def _write(self, items: List[Item]) -> None:
        data = {'version': 1, 'items': [i._asdict() for i in items]}
        _write_atomic(self.path, json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _drop_files(self, dropped: List[Item], kept: List[Item]) -> None:
        still = {i.file for i in kept if i.file}
        for item in dropped:
            if item.file and item.file not in still:
                try:
                    os.unlink(os.path.join(self.images, os.path.basename(item.file)))
                except OSError:
                    pass

    def _trim(self, items: List[Item], limit: int) -> List[Item]:
        """Newest first. Pinned items never count and are never dropped."""
        kept, dropped, count, images = [], [], 0, 0
        for item in items:
            if item.pinned:
                kept.append(item)
                continue
            count += 1
            if item.kind == 'image':
                images += 1
            over = count > limit or (item.kind == 'image' and images > MAX_IMAGES)
            (dropped if over else kept).append(item)
        self._drop_files(dropped, kept)
        return kept

    def items(self) -> List[Item]:
        """Pinned first, then newest first."""
        items = self._read()
        items.sort(key=lambda i: (not i.pinned, -i.time))
        return items

    def _add(self, kind: str, text: str, mime: str, file: str, sha: str, size: int,
             limit: int) -> Item:
        with self._locked():
            items = self._read()
            now = time.time()
            old = next((i for i in items if i.sha == sha), None)
            if old is not None:      # copied again: move it to the top, keep its pin
                items = [i for i in items if i.sha != sha]
                item = old._replace(time=now, mime=mime)
            else:
                item = Item(uuid.uuid4().hex[:12], kind, text, mime, file, sha, now, False, size)
            items.append(item)
            items = self._trim(sorted(items, key=lambda i: -i.time), limit)
            self._write(items)
            return item

    def add_text(self, text: str, limit: int = DEFAULTS['max_items']) -> Optional[Item]:
        if not text.strip():
            return None
        data = text.encode('utf-8')
        if len(data) > MAX_TEXT_BYTES:
            log.info("copy of %d bytes is too big to keep", len(data))
            return None
        return self._add('text', text, 'text/plain;charset=utf-8', '',
                         hashlib.sha256(data).hexdigest()[:24], len(data), limit)

    def add_image(self, data: bytes, mime: str,
                  limit: int = DEFAULTS['max_items']) -> Optional[Item]:
        ext = IMAGE_TYPES.get(mime)
        if not ext or not data or len(data) > MAX_IMAGE_BYTES:
            return None
        sha = hashlib.sha256(data).hexdigest()[:24]
        name = f"{sha}.{ext}"
        path = os.path.join(self.images, name)
        if not os.path.exists(path):
            _write_atomic(path, data)
        return self._add('image', '', mime, name, sha, len(data), limit)

    def image_path(self, item: Item) -> str:
        return os.path.join(self.images, os.path.basename(item.file))

    def image_bytes(self, item: Item) -> bytes:
        with open(self.image_path(item), 'rb') as f:
            return f.read()

    def set_pinned(self, item_id: str, pinned: bool) -> None:
        with self._locked():
            items = [i._replace(pinned=pinned) if i.id == item_id else i for i in self._read()]
            self._write(items)

    def delete(self, item_id: str) -> None:
        with self._locked():
            items = self._read()
            kept = [i for i in items if i.id != item_id]
            self._drop_files([i for i in items if i.id == item_id], kept)
            self._write(kept)

    def clear(self, keep_pinned: bool = True) -> int:
        """Forget the history. Pinned items stay unless asked. Returns how many went."""
        with self._locked():
            items = self._read()
            kept = [i for i in items if i.pinned] if keep_pinned else []
            self._drop_files([i for i in items if i not in kept], kept)
            self._write(kept)
            return len(items) - len(kept)

    def search(self, query: str) -> List[Item]:
        words = fold(query).split()
        found = self.items()
        if not words:
            return found
        return [i for i in found if i.kind == 'text' and all(w in fold(i.text) for w in words)]

    def newest(self) -> Optional[Item]:
        items = sorted(self._read(), key=lambda i: -i.time)
        return items[0] if items else None


def ago(then: float, now: Optional[float] = None, language: Optional[str] = None) -> str:
    """'now', '5 min', '3 h', '2 d' (French: 'maintenant', '5 min', '3 h', '2 j')."""
    from .lang import ui_language
    fr = (language or ui_language()) == 'fr'
    seconds = max(0, int((now if now is not None else time.time()) - then))
    if seconds < 45:
        return 'maintenant' if fr else 'now'
    if seconds < 3600:
        return f"{max(1, seconds // 60)} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} {'j' if fr else 'd'}"


def human_size(n: int, language: Optional[str] = None) -> str:
    from .lang import local_units
    if n < 1024:
        return local_units(f"{n} B", language)
    if n < 1024 * 1024:
        return local_units(f"{n / 1024:.0f} KB", language)
    return local_units(f"{n / 1024 / 1024:.1f} MB", language)
