"""A small ctypes binding to libarchive's reading side: enough to list an archive and stream
its members. libarchive is already in SparkOS (rpm, ostree and flatpak need it), so 7z, rar
and iso need no new package and no outside program."""

import ctypes
import ctypes.util
from typing import Iterator, Optional, Tuple

OK, EOF, RETRY, WARN, FAILED, FATAL = 0, 1, -10, -20, -25, -30

AE_IFMT = 0o170000
AE_IFREG = 0o100000
AE_IFLNK = 0o120000
AE_IFDIR = 0o040000

_lib = None
_tried = False


class ArchiveError(Exception):
    pass


def _bind(lib) -> None:
    vp, cp, i = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    table = {
        'archive_version_string': ([], cp),
        'archive_read_new': ([], vp),
        'archive_read_support_filter_all': ([vp], i),
        'archive_read_support_format_all': ([vp], i),
        'archive_read_support_format_raw': ([vp], i),
        'archive_read_add_passphrase': ([vp, cp], i),
        'archive_read_open_filename': ([vp, cp, ctypes.c_size_t], i),
        'archive_read_next_header': ([vp, ctypes.POINTER(vp)], i),
        'archive_read_data': ([vp, vp, ctypes.c_size_t], ctypes.c_ssize_t),
        'archive_read_data_skip': ([vp], i),
        'archive_read_free': ([vp], i),
        'archive_error_string': ([vp], cp),
        'archive_format_name': ([vp], cp),
        'archive_entry_pathname': ([vp], cp),
        'archive_entry_pathname_utf8': ([vp], cp),
        'archive_entry_size': ([vp], ctypes.c_int64),
        'archive_entry_size_is_set': ([vp], i),
        'archive_entry_mtime': ([vp], ctypes.c_int64),
        'archive_entry_mtime_is_set': ([vp], i),
        'archive_entry_filetype': ([vp], ctypes.c_uint),
        'archive_entry_perm': ([vp], ctypes.c_uint),
        'archive_entry_symlink': ([vp], cp),
        'archive_entry_symlink_utf8': ([vp], cp),
        'archive_entry_hardlink': ([vp], cp),
        'archive_entry_hardlink_utf8': ([vp], cp),
        'archive_entry_is_encrypted': ([vp], i),
    }
    for name, (args, res) in table.items():
        fn = getattr(lib, name)
        fn.argtypes = args
        fn.restype = res


def load():
    """The libarchive library, or None if this system doesn't have it."""
    global _lib, _tried
    if _tried:
        return _lib
    _tried = True
    for name in (ctypes.util.find_library('archive'), 'libarchive.so.13', 'libarchive.so'):
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            _bind(lib)
        except (OSError, AttributeError):
            continue
        _lib = lib
        break
    return _lib


def version() -> Optional[str]:
    lib = load()
    if not lib:
        return None
    return (lib.archive_version_string() or b'').decode('ascii', 'replace')


def _text(utf8: Optional[bytes], raw: Optional[bytes]) -> Optional[str]:
    if utf8 is not None:
        return utf8.decode('utf-8', 'surrogateescape')
    if raw is not None:
        return raw.decode('utf-8', 'surrogateescape')
    return None


class Header:
    __slots__ = ('name', 'type', 'perm', 'size', 'mtime', 'symlink', 'hardlink', 'encrypted')

    def __init__(self, lib, e):
        self.name = _text(lib.archive_entry_pathname_utf8(e), lib.archive_entry_pathname(e)) or ''
        self.type = lib.archive_entry_filetype(e) & AE_IFMT
        self.perm = lib.archive_entry_perm(e) & 0o7777
        self.size = lib.archive_entry_size(e) if lib.archive_entry_size_is_set(e) else -1
        self.mtime = float(lib.archive_entry_mtime(e)) if lib.archive_entry_mtime_is_set(e) \
            else None
        self.symlink = _text(lib.archive_entry_symlink_utf8(e), lib.archive_entry_symlink(e))
        self.hardlink = _text(lib.archive_entry_hardlink_utf8(e), lib.archive_entry_hardlink(e))
        self.encrypted = bool(lib.archive_entry_is_encrypted(e))


class Reader:
    """One pass over an archive. Use as a context manager; iterate headers(), and call
    read(n) for the current member's bytes."""

    def __init__(self, path: str, password: Optional[str] = None, raw: bool = False):
        self.lib = load()
        if not self.lib:
            raise ArchiveError("libarchive is not installed")
        self.a = self.lib.archive_read_new()
        if not self.a:
            raise MemoryError("archive_read_new")
        self.lib.archive_read_support_filter_all(self.a)
        if raw:
            self.lib.archive_read_support_format_raw(self.a)
        else:
            self.lib.archive_read_support_format_all(self.a)
        if password is not None:
            self.lib.archive_read_add_passphrase(self.a, password.encode('utf-8'))
        rc = self.lib.archive_read_open_filename(self.a, path.encode('utf-8', 'surrogateescape'),
                                                 1 << 16)
        if rc < WARN:
            msg = self.error()
            self.close()
            raise ArchiveError(msg)
        self._buf = ctypes.create_string_buffer(1 << 20)

    def error(self) -> str:
        msg = self.lib.archive_error_string(self.a) if self.a else None
        return msg.decode('utf-8', 'replace') if msg else "unreadable archive"

    def format_name(self) -> str:
        name = self.lib.archive_format_name(self.a)
        return name.decode('ascii', 'replace') if name else ''

    def headers(self) -> Iterator[Header]:
        entry = ctypes.c_void_p()
        while True:
            rc = self.lib.archive_read_next_header(self.a, ctypes.byref(entry))
            if rc == EOF:
                return
            if rc < WARN:
                raise ArchiveError(self.error())
            yield Header(self.lib, entry)

    def read(self, n: int = 1 << 20) -> bytes:
        n = min(n, len(self._buf))
        got = self.lib.archive_read_data(self.a, self._buf, n)
        if got < 0:
            if got == RETRY:
                return self.read(n)
            raise ArchiveError(self.error())
        return ctypes.string_at(self._buf, got)

    def skip(self) -> None:
        if self.lib.archive_read_data_skip(self.a) < WARN:
            raise ArchiveError(self.error())

    def close(self) -> None:
        if self.a:
            self.lib.archive_read_free(self.a)
            self.a = None

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def kind_of(h: Header) -> str:
    if h.hardlink:
        return 'hardlink'
    if h.type == AE_IFDIR:
        return 'dir'
    if h.type == AE_IFLNK:
        return 'link'
    if h.type in (AE_IFREG, 0):
        return 'file'
    return 'other'


def first_header(path: str) -> Tuple[Optional[str], Optional[str]]:
    """(format name, error) for a quick look; used by the self-test."""
    try:
        with Reader(path) as r:
            for _h in r.headers():
                return r.format_name(), None
            return r.format_name(), None
    except ArchiveError as exc:
        return None, str(exc)
