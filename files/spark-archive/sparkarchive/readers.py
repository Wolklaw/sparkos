"""Reading archives. Each reader lists an archive and streams its members in order; none of
them writes anything (except the 7z command, which unpacks into a private staging folder that
the safe writer then takes files from one by one).

Which reader, in order of preference:
  zip                 Python's zipfile, then libarchive (WinZip AES), then the 7z command
  tar, tar.gz/bz2/xz  Python's tarfile, then libarchive
  tar.zst             Python's tarfile with compression.zstd (Python 3.14+), then libarchive
  7z, rar, iso        libarchive, then the 7z command (password-protected 7z, header-encrypted
                      7z, and anything libarchive can't decrypt)
  .gz .bz2 .xz .zst   (one compressed file) Python, then libarchive
"""

import os
import re
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
import zlib
import lzma
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Optional, Tuple

from . import formats
from . import libarchive as la
from .safety import DIR, FILE, HARDLINK, LINK, OTHER, Cancelled, Parts, clean_parts


class ArchiveProblem(Exception):
    """Base: something about the archive itself."""


class NeedPassword(ArchiveProblem):
    pass


class WrongPassword(ArchiveProblem):
    pass


class Unsupported(ArchiveProblem):
    """This reader can't do it; the next one might."""


class BadArchive(ArchiveProblem):
    """Damaged, cut short, or not an archive at all."""


@dataclass
class Entry:
    name: str                       # as stored in the archive
    kind: str                       # FILE, DIR, LINK, HARDLINK, OTHER
    size: int = -1                  # unpacked bytes, -1 if the archive doesn't say
    mtime: Optional[float] = None
    mode: int = 0
    target: str = ''                # where a link points
    encrypted: bool = False
    ref: Any = None

    @property
    def parts(self) -> Optional[Parts]:
        return clean_parts(self.name)

    @property
    def path(self) -> Optional[str]:
        p = self.parts
        return '/'.join(p) if p else None


Never = Callable[[], bool]


def _never() -> bool:
    return False


class Reader:
    backend = 'python'

    def __init__(self, path: str, kind: str, password: Optional[str] = None):
        self.path, self.kind, self.password = path, kind, password

    def list(self, cancelled: Never = _never) -> List[Entry]:
        out = []
        for entry, _data in self.items(cancelled, listing=True):
            out.append(entry)
        return out

    def items(self, cancelled: Never = _never, listing: bool = False,
              workdir: Optional[str] = None, on_progress: Optional[Callable[[float], None]] = None
              ) -> Iterator[Tuple[Entry, Any]]:
        """(entry, data) in archive order; data has read(n) for files, else None. With
        listing=True data is always None and member data is skipped."""
        raise NotImplementedError

    def close(self) -> None:
        pass


# ─── zip: Python's zipfile ────────────────────────────────────

ZIP_METHODS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA}
if hasattr(zipfile, 'ZIP_ZSTANDARD'):
    ZIP_METHODS.add(zipfile.ZIP_ZSTANDARD)


def _zip_time(info: zipfile.ZipInfo) -> Optional[float]:
    try:
        return time.mktime(tuple(info.date_time) + (0, 0, -1))
    except (OverflowError, ValueError):
        return None


class ZipReader(Reader):
    def __init__(self, path: str, kind: str, password: Optional[str] = None):
        super().__init__(path, kind, password)
        try:
            self.zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as exc:
            raise BadArchive(str(exc)) from None
        except OSError as exc:
            raise BadArchive(exc.strerror or str(exc)) from None
        for info in self.zf.infolist():
            if info.compress_type not in ZIP_METHODS:
                self.zf.close()
                raise Unsupported(f"zip method {info.compress_type}")   # 99: WinZip AES
            if info.flag_bits & 0x40:                                    # strong encryption
                self.zf.close()
                raise Unsupported("zip strong encryption")

    def entry(self, info: zipfile.ZipInfo) -> Entry:
        unix = info.external_attr >> 16 if info.create_system == 3 else 0
        if info.is_dir() or info.external_attr & 0x10:
            kind = DIR
        elif unix and stat.S_ISLNK(unix):
            kind = LINK
        elif unix and not stat.S_ISREG(unix) and stat.S_IFMT(unix):
            kind = OTHER
        else:
            kind = FILE
        mode = unix & 0o7777 if unix else (0o755 if kind == DIR else 0o644)
        return Entry(info.filename, kind, info.file_size, _zip_time(info), mode,
                     encrypted=bool(info.flag_bits & 0x1), ref=info)

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None):
        pwd = self.password.encode('utf-8') if self.password is not None else None
        for info in self.zf.infolist():
            if cancelled():
                raise Cancelled()
            e = self.entry(info)
            if listing or e.kind in (DIR, OTHER):
                yield e, None
                continue
            if e.encrypted and pwd is None:
                raise NeedPassword(e.name)
            try:
                handle = self.zf.open(info, pwd=pwd if e.encrypted else None)
            except RuntimeError as exc:                  # "Bad password for file"
                if 'password' in str(exc).lower():
                    raise WrongPassword(e.name) from None
                raise BadArchive(str(exc)) from None
            except NotImplementedError as exc:
                raise Unsupported(str(exc)) from None
            except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError) as exc:
                raise BadArchive(str(exc)) from None
            with handle:
                if e.kind == LINK:
                    e.target = handle.read(4096).decode('utf-8', 'surrogateescape')
                    yield e, None
                else:
                    yield e, _Guarded(handle, encrypted=e.encrypted)

    def close(self) -> None:
        self.zf.close()


class _Guarded:
    """Turns the read errors of Python's decompressors into BadArchive (or WrongPassword: a
    wrong zip password slips past the check byte 1 time in 256 and fails the CRC instead)."""

    def __init__(self, handle, encrypted: bool = False):
        self.handle, self.encrypted = handle, encrypted

    def read(self, n: int = -1) -> bytes:
        try:
            return self.handle.read(n)
        except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError, tarfile.TarError,
                ValueError) as exc:
            if self.encrypted and 'crc' in str(exc).lower():
                raise WrongPassword(str(exc)) from None
            raise BadArchive(str(exc) or type(exc).__name__) from None
        except OSError as exc:
            if exc.errno is None:                       # gzip: "CRC check failed" and similar
                raise BadArchive(str(exc)) from None
            raise


# ─── tar: Python's tarfile ────────────────────────────────────

class TarReader(Reader):
    def __init__(self, path: str, kind: str, password: Optional[str] = None):
        super().__init__(path, kind, password)
        self.compression = kind.split('.', 1)[1] if '.' in kind else None
        if self.compression == formats.ZST and not formats.has_zstd():
            raise Unsupported("this Python has no zstd")

    def _open(self):
        try:
            raw = formats.open_compressed(self.path, self.compression) if self.compression \
                else open(self.path, 'rb')
        except OSError as exc:
            raise BadArchive(exc.strerror or str(exc)) from None
        try:
            return raw, tarfile.open(fileobj=raw, mode='r|')
        except (tarfile.TarError, EOFError, zlib.error, lzma.LZMAError, OSError) as exc:
            raw.close()
            raise BadArchive(str(exc) or "not a tar archive") from None

    @staticmethod
    def entry(m: tarfile.TarInfo) -> Entry:
        if m.isdir():
            kind = DIR
        elif m.issym():
            kind = LINK
        elif m.islnk():
            kind = HARDLINK
        elif m.isreg():
            kind = FILE
        else:
            kind = OTHER
        return Entry(m.name, kind, m.size if kind == FILE else 0, float(m.mtime), m.mode,
                     m.linkname if kind in (LINK, HARDLINK) else '', ref=m)

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None):
        raw, tf = self._open()
        try:
            while True:
                if cancelled():
                    raise Cancelled()
                try:
                    m = tf.next()
                except (tarfile.TarError, EOFError, zlib.error, lzma.LZMAError) as exc:
                    raise BadArchive(str(exc) or "the archive ends early") from None
                except OSError as exc:
                    if exc.errno is None:
                        raise BadArchive(str(exc)) from None
                    raise
                if m is None:
                    return
                e = self.entry(m)
                if listing or e.kind != FILE:
                    yield e, None
                else:
                    yield e, _Guarded(tf.extractfile(m))
        finally:
            tf.close()
            raw.close()


# ─── one compressed file: .gz .bz2 .xz .zst ───────────────────

class SingleReader(Reader):
    def __init__(self, path: str, kind: str, password: Optional[str] = None):
        super().__init__(path, kind, password)
        if kind == formats.ZST and not formats.has_zstd():
            raise Unsupported("this Python has no zstd")

    def _entry(self) -> Entry:
        from .core import stem
        name = stem(self.path)
        try:
            st = os.stat(self.path)
            mtime, mode = st.st_mtime, st.st_mode & 0o777
        except OSError:
            mtime, mode = None, 0o644
        return Entry(name, FILE, -1, mtime, mode)

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None):
        e = self._entry()
        if listing:
            yield e, None
            return
        try:
            with formats.open_compressed(self.path, self.kind) as f:
                yield e, _Guarded(f)
        except OSError as exc:
            if exc.errno is None:
                raise BadArchive(str(exc)) from None
            raise


# ─── libarchive (7z, rar, iso, and the fallback for the rest) ─

def _classify(msg: str) -> ArchiveProblem:
    low = msg.lower()
    if 'passphrase' in low or 'password' in low:
        if 'incorrect' in low or 'wrong' in low or 'invalid' in low:
            return WrongPassword(msg)
        return NeedPassword(msg)
    if 'encrypt' in low or 'crypt' in low or 'unsupported' in low or 'not supported' in low:
        return Unsupported(msg)
    return BadArchive(msg)


class LibarchiveReader(Reader):
    backend = 'libarchive'

    def __init__(self, path: str, kind: str, password: Optional[str] = None):
        super().__init__(path, kind, password)
        if not la.load():
            raise Unsupported("libarchive is not installed")
        self.raw = kind in formats.COMPRESSED

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None):
        try:
            r = la.Reader(self.path, self.password, raw=self.raw)
        except la.ArchiveError as exc:
            raise _classify(str(exc)) from None
        with r:
            try:
                for h in r.headers():
                    if cancelled():
                        raise Cancelled()
                    kind = la.kind_of(h)
                    name = h.name
                    if self.raw:
                        from .core import stem
                        name = stem(self.path)
                    target = h.hardlink if kind == HARDLINK else (h.symlink or '')
                    perm = h.perm
                    if self.kind == formats.ISO and not perm & 0o077:
                        perm = 0          # plain ISO 9660 has no modes: libarchive says 0400
                    e = Entry(name, kind, h.size if kind == FILE else 0, h.mtime, perm,
                              target, h.encrypted)
                    if listing or kind != FILE:
                        yield e, None
                        continue
                    if e.encrypted:
                        if self.kind in (formats.SEVENZIP, formats.RAR):
                            raise Unsupported("libarchive can't decrypt " + self.kind)
                        if self.password is None:
                            raise NeedPassword(e.name)
                    yield e, _LaData(r)
            except la.ArchiveError as exc:
                raise _classify(str(exc)) from None


class _LaData:
    def __init__(self, r: 'la.Reader'):
        self.r = r

    def read(self, n: int = 1 << 20) -> bytes:
        try:
            return self.r.read(n if n and n > 0 else 1 << 20)
        except la.ArchiveError as exc:
            raise _classify(str(exc)) from None


# ─── the 7z command ───────────────────────────────────────────

def sevenzip() -> Optional[str]:
    for name in ('7zz', '7z', '7za'):
        found = shutil.which(name)
        if found:
            return found
    return None


def _run_7z(args: List[str], password: Optional[str], cancelled: Never,
            on_line: Optional[Callable[[str], None]] = None) -> Tuple[int, str, str]:
    """Run 7z with the password on its stdin, never on the command line (where any user
    could read it in /proc). A new session, so it has no terminal to ask on instead."""
    exe = sevenzip()
    if not exe:
        raise Unsupported("the 7z command is not installed")
    env = dict(os.environ, LC_ALL='C.UTF-8', LANG='C.UTF-8')
    proc = subprocess.Popen([exe] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True, env=env)
    try:
        proc.stdin.write(((password or '') + '\n').encode('utf-8'))
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    out_lines: List[str] = []
    err_chunks: List[bytes] = []
    reader = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    reader.start()
    buf = b''
    while True:
        if cancelled():
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                proc.kill()
            proc.wait()
            raise Cancelled()
        chunk = proc.stdout.read1(65536) if hasattr(proc.stdout, 'read1') else proc.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        # progress lines end in \r or \b runs; output lines in \n
        while True:
            m = re.search(rb'[\r\n\x08]', buf)
            if not m:
                break
            line, buf = buf[:m.start()], buf[m.end():]
            text = line.decode('utf-8', 'replace')
            if m.group() == b'\n':
                out_lines.append(text)
            if on_line and text.strip():
                on_line(text)
    if buf:
        out_lines.append(buf.decode('utf-8', 'replace'))
    rc = proc.wait()
    reader.join(5)
    err = b''.join(err_chunks).decode('utf-8', 'replace')
    return rc, '\n'.join(out_lines), err


def _7z_problem(rc: int, out: str, err: str, password: Optional[str]) -> ArchiveProblem:
    text = (err + '\n' + out)
    low = text.lower()
    if 'wrong password' in low or 'can not open encrypted archive' in low or \
            'cannot open encrypted archive' in low or 'data error in encrypted' in low:
        return NeedPassword(text.strip()) if not password else WrongPassword(text.strip())
    if 'unsupported method' in low:
        return Unsupported(text.strip())
    lines = [ln.strip() for ln in err.splitlines() if ln.strip()]
    return BadArchive(lines[-1] if lines else f"7z stopped with code {rc}")


def _refused_links(err: str, staging: str) -> Optional[List[str]]:
    """The links 7z said it couldn't make, if those are its only errors; else None."""
    errors = [ln.strip() for ln in err.splitlines() if ln.strip().startswith('ERROR')]
    if not errors:
        return None
    names = []
    for line in errors:
        if not re.search(r'Cannot create (hard |symbolic )?link', line, re.I):
            return None
        for piece in line.split(' : '):
            piece = piece.strip()
            if piece.startswith(staging.rstrip('/') + '/'):
                names.append(os.path.relpath(piece, staging))
                break
    return names


class SevenZipReader(Reader):
    backend = '7z'

    def __init__(self, path: str, kind: str, password: Optional[str] = None):
        super().__init__(path, kind, password)
        if not sevenzip():
            raise Unsupported("the 7z command is not installed")

    def list(self, cancelled=_never) -> List[Entry]:
        rc, out, err = _run_7z(['l', '-slt', '-sccUTF-8', '--', self.path], self.password,
                               cancelled)
        if rc != 0:
            raise _7z_problem(rc, out, err, self.password)
        _, _, body = out.partition('\n----------\n')
        entries = []
        for block in re.split(r'\n\s*\n', body):
            fields = {}
            for line in block.splitlines():
                key, sep, value = line.partition(' = ')
                if sep:
                    fields[key.strip()] = value
            if 'Path' not in fields:
                continue
            attrs = fields.get('Attributes', '')
            unix = re.search(r'\s([-dlcbps])([-rwxsStT]{9})', ' ' + attrs)
            if fields.get('Folder') == '+' or attrs.startswith('D') or (unix and unix.group(1) == 'd'):
                kind = DIR
            elif unix and unix.group(1) == 'l' or fields.get('Symbolic Link'):
                kind = LINK
            else:
                kind = FILE
            try:
                size = int(fields.get('Size') or -1)
            except ValueError:
                size = -1
            mtime = None
            when = fields.get('Modified', '')
            if when:
                try:
                    mtime = time.mktime(time.strptime(when[:19], '%Y-%m-%d %H:%M:%S'))
                except (ValueError, OverflowError):
                    pass
            entries.append(Entry(fields['Path'], kind, size if kind == FILE else 0, mtime,
                                 0, fields.get('Symbolic Link', ''),
                                 fields.get('Encrypted') == '+'))
        return entries

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None):
        if listing:
            for e in self.list(cancelled):
                yield e, None
            return
        if not workdir:
            raise ValueError("7z needs a staging folder")
        staging = tempfile.mkdtemp(prefix='.spark-archive-', dir=workdir)
        try:
            def line(text: str) -> None:
                m = re.match(r'\s*(\d{1,3})%', text)
                if m and on_progress:
                    on_progress(int(m.group(1)) / 100)

            rc, out, err = _run_7z(['x', '-y', '-bsp1', '-bb0', '-sccUTF-8', '-o' + staging,
                                    '--', self.path], self.password, cancelled, line)
            refused = _refused_links(err, staging)
            if rc not in (0, 1) and not (rc == 2 and refused):
                raise _7z_problem(rc, out, err, self.password)
            for name in refused or ():
                # 7z wouldn't make these links (they lead out); report them like any other
                yield Entry(name, HARDLINK, 0, None, 0, '/'), None
            if on_progress:
                on_progress(1.0)
            for top, dirs, files in os.walk(staging, topdown=True, followlinks=False):
                dirs.sort()
                rel = os.path.relpath(top, staging)
                base = '' if rel == '.' else rel.replace(os.sep, '/') + '/'
                for d in list(dirs):
                    full = os.path.join(top, d)
                    st = os.lstat(full)
                    if stat.S_ISLNK(st.st_mode):         # os.walk lists links to folders here
                        dirs.remove(d)
                        files.append(d)
                        continue
                    yield Entry(base + d, DIR, 0, st.st_mtime, st.st_mode & 0o7777), None
                for f in sorted(files):
                    full = os.path.join(top, f)
                    st = os.lstat(full)
                    if stat.S_ISLNK(st.st_mode):
                        yield Entry(base + f, LINK, 0, st.st_mtime, 0o777,
                                    os.readlink(full)), None
                    elif stat.S_ISREG(st.st_mode):
                        yield Entry(base + f, FILE, st.st_size, st.st_mtime,
                                    st.st_mode & 0o7777), _Staged(full)
                    else:
                        yield Entry(base + f, OTHER, 0, st.st_mtime, 0), None
        finally:
            shutil.rmtree(staging, ignore_errors=True)


class _Staged:
    """A file 7z unpacked; the writer moves it into place instead of copying it."""

    def __init__(self, path: str):
        self.staged_path = path
        self._f = None

    def read(self, n: int = -1) -> bytes:
        if self._f is None:
            self._f = open(self.staged_path, 'rb')
        data = self._f.read(n)
        if not data:
            self._f.close()
        return data


# ─── choosing ─────────────────────────────────────────────────

def candidates(kind: str) -> List[type]:
    if kind == formats.ZIP:
        return [ZipReader, LibarchiveReader, SevenZipReader]
    if kind == formats.TAR or kind.startswith('tar.'):
        return [TarReader, LibarchiveReader, SevenZipReader]
    if kind in (formats.SEVENZIP, formats.RAR, formats.ISO):
        return [LibarchiveReader, SevenZipReader]
    if kind in formats.COMPRESSED:
        return [SingleReader, LibarchiveReader]
    return [LibarchiveReader, SevenZipReader]


def open_reader(path: str, kind: str, password: Optional[str] = None,
                skip: int = 0) -> Reader:
    """The first reader (from the `skip`-th on) that takes this archive."""
    last: Optional[Exception] = None
    for cls in candidates(kind)[skip:]:
        try:
            return cls(path, kind, password)
        except Unsupported as exc:
            last = exc
    raise Unsupported(str(last) if last else "no reader for this archive")


def what_reads(kind: str) -> List[str]:
    """For the self-test and the PR: which readers are available for a kind, in order."""
    names = []
    for cls in candidates(kind):
        if cls is LibarchiveReader and not la.load():
            continue
        if cls is SevenZipReader and not sevenzip():
            continue
        if cls in (TarReader, SingleReader) and kind.endswith(formats.ZST) and \
                not formats.has_zstd():
            continue
        names.append({ZipReader: 'zipfile', TarReader: 'tarfile', SingleReader: 'python',
                      LibarchiveReader: 'libarchive', SevenZipReader: '7z'}[cls])
    return names
