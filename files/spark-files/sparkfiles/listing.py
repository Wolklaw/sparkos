"""Reading a folder, and sorting and filtering what's in it. Plain os.scandir: a folder of
10,000 files is read in a few tens of milliseconds, so the window never waits on GIO here."""

import os
import re
import stat
import unicodedata
from typing import Iterable, List, Optional, Tuple

# file kinds: the icon, the grid's thumbnail, and the Type column
KINDS = {
    'image': ('jpg', 'jpeg', 'jpe', 'png', 'gif', 'webp', 'bmp', 'tif', 'tiff', 'avif', 'heic',
              'heif', 'ico', 'svg', 'jxl', 'raw', 'cr2', 'cr3', 'nef', 'arw', 'dng', 'orf',
              'rw2', 'xcf', 'psd', 'kra'),
    'video': ('mp4', 'mkv', 'webm', 'avi', 'mov', 'm4v', 'wmv', 'flv', 'mpg', 'mpeg', 'ts',
              'm2ts', 'ogv', '3gp'),
    'audio': ('mp3', 'flac', 'ogg', 'oga', 'opus', 'wav', 'm4a', 'aac', 'wma', 'aiff', 'aif',
              'mid', 'midi'),
    'archive': ('zip', '7z', 'rar', 'tar', 'gz', 'tgz', 'bz2', 'tbz2', 'xz', 'txz', 'zst',
                'tzst', 'lz', 'lzma', 'lz4', 'cab', 'iso', 'img'),
    'document': ('pdf', 'doc', 'docx', 'odt', 'rtf', 'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx',
                 'odp', 'epub', 'md', 'txt', 'log'),
    'code': ('py', 'sh', 'bash', 'js', 'ts', 'json', 'yaml', 'yml', 'toml', 'ini', 'conf', 'cfg',
             'c', 'h', 'cpp', 'hpp', 'rs', 'go', 'java', 'kt', 'cs', 'html', 'htm', 'css',
             'xml', 'desktop', 'service', 'lua', 'rb', 'php', 'sql', 'diff', 'patch'),
    'program': ('exe', 'msi', 'appimage', 'rpm', 'deb', 'flatpakref', 'bat', 'cmd', 'lnk',
                'jar', 'x86_64'),
}
EXT_KIND = {ext: kind for kind, exts in KINDS.items() for ext in exts}
THUMB_IMAGE = {'jpg', 'jpeg', 'jpe', 'png', 'gif', 'webp', 'bmp', 'tif', 'tiff', 'ico', 'avif',
               'heic', 'heif'}
THUMB_VIDEO = set(KINDS['video'])


class Entry:
    """One item in a folder. Plain attributes (no dataclass) to keep 10,000 of them cheap."""

    __slots__ = ('name', 'path', 'is_dir', 'is_link', 'broken', 'size', 'mtime', 'mode',
                 'ext', 'kind', 'hidden', 'key', 'uid', 'inode', 'dev')

    def __init__(self, name: str, path: str, is_dir: bool, size: int, mtime: float, mode: int,
                 is_link: bool = False, broken: bool = False, uid: int = -1, inode: int = 0,
                 dev: int = 0):
        self.name, self.path, self.is_dir = name, path, is_dir
        self.is_link, self.broken = is_link, broken
        self.size, self.mtime, self.mode = size, mtime, mode
        self.uid, self.inode, self.dev = uid, inode, dev
        dot = name.rfind('.')
        self.ext = name[dot + 1:].lower() if 0 < dot < len(name) - 1 and not is_dir else ''
        if name.lower().endswith(('.tar.gz', '.tar.xz', '.tar.zst', '.tar.bz2')):
            self.ext = name.lower().rsplit('.', 2)[-2] + '.' + self.ext
        if is_dir:
            self.kind = 'folder'
        elif self.ext.startswith('tar.'):
            self.kind = 'archive'
        elif not self.ext and mode & 0o111 and stat.S_ISREG(mode):
            self.kind = 'program'
        else:
            self.kind = EXT_KIND.get(self.ext, 'file')
        self.hidden = name.startswith('.') or name.endswith('~')
        self.key = natural_key(name)

    def __repr__(self) -> str:
        return f"Entry({self.name!r}{'/' if self.is_dir else ''})"

    @property
    def executable(self) -> bool:
        return bool(self.mode & 0o111) and not self.is_dir


_DIGITS = re.compile(r'(\d+)')


def natural_key(name: str) -> Tuple:
    """file2 before file10, case and accents ignored (é sorts with e), ties broken by the
    exact name so the order is stable."""
    folded = unicodedata.normalize('NFKD', name.casefold())
    folded = ''.join(c for c in folded if not unicodedata.combining(c))
    parts = _DIGITS.split(folded)
    return tuple((0, int(p), p) if i % 2 else (1, 0, p) for i, p in enumerate(parts)) + \
        ((2, 0, name),)


def read_entry(path: str) -> Optional[Entry]:
    """One file or folder, the way list_dir describes it; None if it's gone."""
    name = os.path.basename(path.rstrip(os.sep)) or path
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return _from_stat(name, path, st)


def _from_stat(name: str, path: str, lst: os.stat_result) -> Entry:
    is_link = stat.S_ISLNK(lst.st_mode)
    st, broken = lst, False
    if is_link:
        try:
            st = os.stat(path)
        except OSError:
            broken = True
    is_dir = stat.S_ISDIR(st.st_mode)
    return Entry(name, path, is_dir, 0 if is_dir else st.st_size, st.st_mtime, st.st_mode,
                 is_link, broken, st.st_uid, lst.st_ino, lst.st_dev)


def list_dir(folder: str) -> List[Entry]:
    """Everything in a folder, hidden files included (the view filters them). Raises OSError
    when the folder can't be read."""
    out: List[Entry] = []
    with os.scandir(folder) as it:
        for de in it:
            path = os.path.join(folder, de.name)
            try:
                lst = de.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(lst.st_mode):
                out.append(_from_stat(de.name, path, lst))
                continue
            is_dir = stat.S_ISDIR(lst.st_mode)
            out.append(Entry(de.name, path, is_dir, 0 if is_dir else lst.st_size, lst.st_mtime,
                             lst.st_mode, False, False, lst.st_uid, lst.st_ino, lst.st_dev))
    return out


def sort_entries(entries: Iterable[Entry], by: str = 'name', reverse: bool = False,
                 folders_first: bool = True) -> List[Entry]:
    """Sorted by name (natural), modified, size or type. Folders stay on top either way when
    folders_first; ties fall back to the name."""
    items = list(entries)
    if by == 'modified':
        items.sort(key=lambda e: (e.mtime, e.key), reverse=reverse)
    elif by == 'size':
        items.sort(key=lambda e: (e.size, e.key), reverse=reverse)
    elif by == 'type':
        items.sort(key=lambda e: (e.kind, e.ext, e.key), reverse=reverse)
    else:
        items.sort(key=lambda e: e.key, reverse=reverse)
    if folders_first:
        items = [e for e in items if e.is_dir] + [e for e in items if not e.is_dir]
    return items


def filter_entries(entries: Iterable[Entry], text: str = '', show_hidden: bool = False
                   ) -> List[Entry]:
    """Hidden files out unless asked for; the filter keeps names that contain every word
    typed (any order, case and accents ignored), or that match it as a pattern (*.jpg)."""
    items = [e for e in entries if show_hidden or not e.hidden]
    text = text.strip()
    if not text:
        return items
    match = name_matcher(text)
    return [e for e in items if match(e.name)]


def fold(text: str) -> str:
    text = unicodedata.normalize('NFKD', text.casefold())
    return ''.join(c for c in text if not unicodedata.combining(c))


def name_matcher(text: str):
    """A test for names: words must all appear; '*' and '?' make it a shell pattern."""
    import fnmatch
    text = text.strip()
    if any(c in text for c in '*?['):
        pattern = fold(text)
        return lambda name: fnmatch.fnmatchcase(fold(name), pattern)
    words = fold(text).split()
    return lambda name: all(w in fold(name) for w in words)


def type_label(entry: Entry, t) -> str:
    """The Type column: 'Folder', 'PNG image', 'Text'... t is text.t."""
    if entry.is_link and entry.broken:
        return t('kind.broken_link')
    if entry.is_dir:
        return t('kind.folder')
    label = t('kind.' + entry.kind)
    if entry.ext and entry.kind != 'file':
        if entry.kind == 'program':
            return f"{label} ({entry.ext.upper()})"
        return t('kind.with_ext', ext=entry.ext.upper(), kind=label)
    if entry.ext:
        return t('kind.file_ext', ext=entry.ext.upper())
    return label


def folder_count(path: str, show_hidden: bool = False) -> Optional[int]:
    try:
        with os.scandir(path) as it:
            return sum(1 for de in it if show_hidden or not de.name.startswith('.'))
    except OSError:
        return None
