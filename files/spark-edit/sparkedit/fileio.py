"""Reading and writing files the way they were: the same encoding, byte-order mark and line
endings. No Tk in here, so --self-test and the tests run without a display.

Saving writes a temporary file next to the original and swaps it in, so a crash halfway
through a save never leaves half a file. Files the user can't write are saved through
pkexec ("Save as administrator"), which copies a temporary file over the original.
"""

import errno
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

# codec name -> what the status bar shows
ENCODINGS = (
    ('utf-8', 'UTF-8'),
    ('utf-16-le', 'UTF-16 LE'),
    ('utf-16-be', 'UTF-16 BE'),
    ('cp1252', 'Windows-1252'),
    ('latin-1', 'Latin-1'),
)
BOMS = {'utf-8': b'\xef\xbb\xbf', 'utf-16-le': b'\xff\xfe', 'utf-16-be': b'\xfe\xff'}
NEWLINES = (('\n', 'LF'), ('\r\n', 'CRLF'), ('\r', 'CR'))
SNIFF = 64 * 1024


class BinaryFile(Exception):
    """The file has NUL bytes and no UTF-16 shape: it isn't text."""


class EncodeError(Exception):
    """A character can't be written in the file's encoding."""

    def __init__(self, encoding: str, char: str, line: int, col: int):
        super().__init__(f"{char!r} can't be written in {encoding}")
        self.encoding, self.char, self.line, self.col = encoding, char, line, col


@dataclass
class Format:
    encoding: str = 'utf-8'
    bom: bool = False
    newline: str = '\n'
    mixed: bool = False          # the file had more than one kind of line ending

    def label(self) -> str:
        name = dict(ENCODINGS).get(self.encoding, self.encoding.upper())
        return name + (' BOM' if self.bom and self.encoding == 'utf-8' else '')

    def newline_label(self) -> str:
        return dict(NEWLINES).get(self.newline, 'LF')

    def as_dict(self) -> dict:
        return {'encoding': self.encoding, 'bom': self.bom, 'newline': self.newline}

    @classmethod
    def from_dict(cls, data: dict) -> 'Format':
        fmt = cls()
        if isinstance(data, dict):
            if data.get('encoding') in dict(ENCODINGS):
                fmt.encoding = data['encoding']
            fmt.bom = bool(data.get('bom'))
            if data.get('newline') in dict(NEWLINES):
                fmt.newline = data['newline']
        return fmt


# ─── Reading ──────────────────────────────────────────────────

def _utf16_guess(sample: bytes) -> Optional[str]:
    """UTF-16 without a byte-order mark: mostly-ASCII text has a NUL in every other byte."""
    pairs = len(sample) // 2
    if pairs < 4:
        return None
    even = sample[0:pairs * 2:2].count(0)
    odd = sample[1:pairs * 2:2].count(0)
    if odd > pairs * 0.4 and even < pairs * 0.05:
        return 'utf-16-le'
    if even > pairs * 0.4 and odd < pairs * 0.05:
        return 'utf-16-be'
    return None


def detect(data: bytes) -> Tuple[str, bool]:
    """(codec, has byte-order mark) for these bytes. Raises BinaryFile for non-text."""
    for codec, bom in BOMS.items():
        if data.startswith(bom):
            return codec, True
    sample = data[:SNIFF]
    if b'\x00' in sample:
        guess = _utf16_guess(sample)
        if guess:
            try:
                data.decode(guess)
                return guess, False
            except UnicodeDecodeError:
                pass
        raise BinaryFile()
    try:
        data.decode('utf-8')
        return 'utf-8', False
    except UnicodeDecodeError:
        pass
    # Latin-1 and Windows-1252 differ only in bytes 0x80-0x9F: control characters nobody
    # types in Latin-1, curly quotes, dashes and the euro sign in Windows-1252
    if re.search(rb'[\x80-\x9f]', data):
        try:
            data.decode('cp1252')
            return 'cp1252', False
        except UnicodeDecodeError:
            pass
    return 'latin-1', False


def split_newlines(text: str) -> Tuple[str, str, bool]:
    """(text with '\\n' line endings, the file's own line ending, more than one kind?)"""
    if '\r' not in text:
        return text, '\n', False
    crlf = text.count('\r\n')
    cr = text.count('\r') - crlf
    lf = text.count('\n') - crlf
    counts = [(crlf, '\r\n'), (lf, '\n'), (cr, '\r')]
    kinds = sum(1 for n, _ in counts if n)
    newline = max(counts, key=lambda c: c[0])[1]
    return text.replace('\r\n', '\n').replace('\r', '\n'), newline, kinds > 1


def decode(data: bytes, encoding: Optional[str] = None,
           force: bool = False) -> Tuple[str, Format]:
    """Bytes from disk -> (text with '\\n' line endings, how to write it back).
    encoding: reopen with this codec instead of guessing. force: open binary files too."""
    if encoding:
        bom = BOMS.get(encoding)
        has_bom = bool(bom) and data.startswith(bom)
        body = data[len(bom):] if has_bom else data
        text = body.decode(encoding, errors='replace')
    else:
        try:
            encoding, has_bom = detect(data)
        except BinaryFile:
            if not force:
                raise
            encoding, has_bom = 'latin-1', False
        body = data[len(BOMS[encoding]):] if has_bom else data
        text = body.decode(encoding)
    text, newline, mixed = split_newlines(text)
    return text, Format(encoding, has_bom, newline, mixed)


def read_file(path: str, encoding: Optional[str] = None,
              force: bool = False) -> Tuple[str, Format, os.stat_result]:
    with open(path, 'rb') as f:
        st = os.fstat(f.fileno())
        data = f.read()
    text, fmt = decode(data, encoding, force)
    return text, fmt, st


def chunks(text: str, size: int) -> Iterator[str]:
    """Pieces of about `size` characters, each ending after a newline when there is one
    near the cut, so the editor never shows half a line while it loads."""
    pos, n = 0, len(text)
    while pos < n:
        end = min(n, pos + size)
        if end < n:
            cut = text.rfind('\n', pos + size // 2, end)
            if cut != -1:
                end = cut + 1
        yield text[pos:end]
        pos = end


# ─── Writing ──────────────────────────────────────────────────

def encode(text: str, fmt: Format) -> bytes:
    """Editor text ('\\n' endings) -> the bytes to write. Raises EncodeError."""
    if fmt.newline != '\n':
        text = text.replace('\n', fmt.newline)
    try:
        data = text.encode(fmt.encoding)
    except UnicodeEncodeError as exc:
        before = text[:exc.start].replace(fmt.newline, '\n') if fmt.newline != '\n' \
            else text[:exc.start]
        line = before.count('\n') + 1
        col = len(before) - (before.rfind('\n') + 1)
        raise EncodeError(dict(ENCODINGS).get(fmt.encoding, fmt.encoding),
                          text[exc.start], line, col) from None
    if fmt.bom and fmt.encoding in BOMS:
        data = BOMS[fmt.encoding] + data
    return data


def _umask() -> int:
    mask = os.umask(0o022)
    os.umask(mask)
    return mask


def write_file(path: str, data: bytes) -> os.stat_result:
    """Save safely: a temporary file in the same folder, flushed to disk, then swapped in.
    The original's permissions and group are kept and symlinks stay links (the file they
    point to is saved). Files with hard links, and files in folders you can't write but
    whose file you can, are written in place instead. Raises OSError."""
    real = os.path.realpath(path)
    folder = os.path.dirname(real) or '.'
    try:
        old = os.stat(real)
    except FileNotFoundError:
        old = None
    if old is not None and old.st_nlink > 1:
        return _write_in_place(real, data)
    try:
        fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(real) + '.',
                                   suffix='.spark-edit', dir=folder)
    except PermissionError:
        if old is not None and os.access(real, os.W_OK):
            return _write_in_place(real, data)
        raise
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if old is not None:
            os.chmod(tmp, stat.S_IMODE(old.st_mode))
            if hasattr(os, 'chown') and old.st_gid != os.stat(tmp).st_gid:
                try:
                    os.chown(tmp, -1, old.st_gid)
                except OSError:
                    pass
        else:
            os.chmod(tmp, 0o666 & ~_umask())
        os.replace(tmp, real)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _sync_folder(folder)
    return os.stat(real)


def _write_in_place(path: str, data: bytes) -> os.stat_result:
    with open(path, 'r+b') as f:
        f.truncate(0)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return os.stat(path)


def _sync_folder(folder: str) -> None:
    if os.name != 'posix':
        return
    try:
        fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def is_permission_error(exc: BaseException) -> bool:
    return isinstance(exc, PermissionError) or \
        (isinstance(exc, OSError) and exc.errno in (errno.EACCES, errno.EPERM))


def is_read_only_fs(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and exc.errno == errno.EROFS


def can_write(path: str) -> bool:
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    return os.access(os.path.dirname(os.path.abspath(path)) or '.', os.W_OK)


# ─── Save as administrator ────────────────────────────────────

def pkexec_path() -> Optional[str]:
    return os.environ.get('SPARK_EDIT_PKEXEC') or shutil.which('pkexec')


def admin_command(tmp: str, target: str) -> List[str]:
    """cp over the existing file keeps its owner and permissions; a new file gets the
    usual 0644. pkexec asks for the password through Plasma's own prompt."""
    cp = shutil.which('cp', path='/usr/bin:/bin') or '/usr/bin/cp'
    return [pkexec_path() or 'pkexec', cp, '--no-preserve=mode,ownership', '--', tmp, target]


def admin_write(path: str, data: bytes, temp_dir: str) -> Optional[str]:
    """Write `data` to `path` as root through pkexec. Blocks until the password prompt is
    answered, so call it from a worker thread. None when saved, else what went wrong;
    'cancelled' when the prompt was dismissed."""
    if not pkexec_path():
        return "pkexec isn't installed"
    target = os.path.realpath(path)
    fd, tmp = tempfile.mkstemp(prefix='admin-save-', dir=temp_dir)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        result = subprocess.run(admin_command(tmp, target), capture_output=True, text=True,
                                timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if result.returncode == 0:
        return None
    if result.returncode == 126:                     # dismissed, or wrong password three times
        return 'cancelled'
    return (result.stderr or result.stdout).strip() or f"pkexec exited with {result.returncode}"
