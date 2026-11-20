"""Reading archives. Each reader lists an archive and streams its members in order; none of
them writes anything (except the 7z and unrar commands, which unpack into a private staging
folder that the safe writer then takes files from one by one).

Which reader, in order of preference:
  zip                 Python's zipfile, then libarchive (WinZip AES), then the 7z command
  tar, tar.gz/bz2/xz  Python's tarfile, then libarchive
  tar.zst             Python's tarfile with compression.zstd (Python 3.14+), then libarchive
  7z, iso             libarchive, then the 7z command (password-protected 7z, header-encrypted
                      7z, and anything libarchive can't decrypt)
  rar                 libarchive, then the unrar command (password-protected RAR, RAR with
                      encrypted names), then the 7z command
  .gz .bz2 .xz .zst   (one compressed file) Python, then libarchive
  in several parts    .7z.001...: libarchive, then 7z; RAR volumes: libarchive, then unrar,
                      then 7z; split zip (.z01 ... .zip): the 7z command
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
from . import volumes as vol
from .core import log
from . import libarchive as la
from .safety import DIR, FILE, HARDLINK, LINK, OTHER, Cancelled, Parts, clean_parts
from .volumes import Volumes


REFUSED = 'refused'                 # the 7z command wouldn't write it: unsafe


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


class MissingPart(ArchiveProblem):
    """An archive in several parts, one of which isn't there. The message is its file name."""


class NeedsTool(Unsupported):
    """Only an outside command reads this, and it isn't installed."""

    def __init__(self, tool: str):
        super().__init__(f"the {tool} command is not installed")
        self.tool = tool


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

    def __init__(self, path: str, kind: str, password: Optional[str] = None,
                 volumes: Optional[Volumes] = None):
        self.path, self.kind, self.password = path, kind, password
        self.volumes = volumes
        self.used_names = False         # items() unpacked only the names it was given

    def list(self, cancelled: Never = _never) -> List[Entry]:
        out = []
        for entry, _data in self.items(cancelled, listing=True):
            out.append(entry)
        return out

    def items(self, cancelled: Never = _never, listing: bool = False,
              workdir: Optional[str] = None, on_progress: Optional[Callable[[float], None]] = None,
              names: Optional[List[str]] = None) -> Iterator[Tuple[Entry, Any]]:
        """(entry, data) in archive order; data has read(n) for files, else None. With
        listing=True data is always None and member data is skipped. `names`: the members
        wanted, as the listing named them. A reader that unpacks through an outside command
        unpacks only those; the others ignore it (the caller picks what it wants anyway)."""
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
    def __init__(self, path: str, kind: str, password: Optional[str] = None,
                 volumes: Optional[Volumes] = None):
        super().__init__(path, kind, password, volumes)
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

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None,
              names=None):
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
    def __init__(self, path: str, kind: str, password: Optional[str] = None,
                 volumes: Optional[Volumes] = None):
        super().__init__(path, kind, password, volumes)
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

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None,
              names=None):
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
    def __init__(self, path: str, kind: str, password: Optional[str] = None,
                 volumes: Optional[Volumes] = None):
        super().__init__(path, kind, password, volumes)
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

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None,
              names=None):
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

    def __init__(self, path: str, kind: str, password: Optional[str] = None,
                 volumes: Optional[Volumes] = None):
        super().__init__(path, kind, password, volumes)
        if not la.load():
            raise Unsupported("libarchive is not installed")
        self.raw = kind in formats.COMPRESSED

    def _problem(self, msg: str) -> ArchiveProblem:
        problem = _classify(msg)
        if self.kind == formats.RAR and isinstance(problem, (NeedPassword, WrongPassword)):
            return Unsupported("libarchive can't decrypt rar")   # a password won't help it
        return problem

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None,
              names=None):
        try:
            r = la.Reader(self.path, self.password, raw=self.raw,
                          parts=self.volumes.parts if self.volumes else None)
        except la.ArchiveError as exc:
            raise self._problem(str(exc)) from None
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
                    yield e, _LaData(r, self._problem)
            except la.ArchiveError as exc:
                raise self._problem(str(exc)) from None


class _LaData:
    def __init__(self, r: 'la.Reader', problem: Callable[[str], ArchiveProblem]):
        self.r, self.problem = r, problem

    def read(self, n: int = 1 << 20) -> bytes:
        try:
            return self.r.read(n if n and n > 0 else 1 << 20)
        except la.ArchiveError as exc:
            raise self.problem(str(exc)) from None


# ─── the 7z command ───────────────────────────────────────────

def sevenzip() -> Optional[str]:
    for name in ('7zz', '7z', '7za'):
        found = shutil.which(name)
        if found:
            return found
    return None


def _run_7z(args: List[str], password: Optional[str], cancelled: Never,
            on_line: Optional[Callable[[str], None]] = None, asks: int = 1,
            cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Run 7z with the password on its stdin, never on the command line (where any user
    could read it in /proc). `asks`: how many times it may ask (making an archive can ask
    again to confirm)."""
    exe = sevenzip()
    if not exe:
        raise NeedsTool('7z')
    return run_tool(exe, args, ((password or '') + '\n') * asks, cancelled, on_line, cwd)


def run_tool(exe: str, args: List[str], stdin_text: str, cancelled: Never,
             on_line: Optional[Callable[[str], None]] = None,
             cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Run an archive command with `stdin_text` on its stdin, then closed: the way a password
    reaches it. Its own session, so it has no terminal to ask on instead, and Cancel stops it
    and anything it started. Returns (rc, stdout, stderr)."""
    env = dict(os.environ, LC_ALL='C.UTF-8', LANG='C.UTF-8')
    env.pop('RAR', None)                     # rar's and unrar's default switches
    proc = subprocess.Popen([exe] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True, env=env, cwd=cwd)
    try:
        if stdin_text:
            proc.stdin.write(stdin_text.encode('utf-8'))
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
    for pipe in (proc.stdout, proc.stderr):
        try:
            pipe.close()
        except OSError:
            pass
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
    """What 7z refused to write because it was unsafe (links leading out, writes through such
    links), if those are its only errors: their names, for the list of what was left out.
    None if any other error (damaged data, a full disk), which stays fatal."""
    errors = []
    for raw in err.splitlines():
        line = re.sub(r'[\x00-\x1f]', '', raw).strip()
        if 'ERROR:' in line:
            errors.append(line[line.index('ERROR:'):])
    if not errors:
        return None
    root = staging.rstrip('/') + '/'
    names = []
    for line in errors:
        if re.search(r'errno=(28|122)\b|no space|quota', line, re.I):
            return None
        pieces = [p.strip() for p in line.split(' : ')]
        inside = [p for p in pieces if p.startswith(root)]
        if inside:
            names.append(os.path.relpath(inside[0], staging))
        elif re.search(r'dangerous', line, re.I) and len(pieces) >= 2:
            names.append(pieces[1])
        else:
            return None
    return names


class SevenZipReader(Reader):
    backend = '7z'

    def __init__(self, path: str, kind: str, password: Optional[str] = None,
                 volumes: Optional[Volumes] = None):
        super().__init__(path, kind, password, volumes)
        if not sevenzip():
            raise NeedsTool('7z')

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

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None,
              names=None):
        if listing:
            for e in self.list(cancelled):
                yield e, None
            return
        if not workdir:
            raise ValueError("7z needs a staging folder")
        wanted = name_args(names)
        self.used_names = wanted is not None
        staging = tempfile.mkdtemp(prefix='.spark-archive-', dir=workdir)
        try:
            args = ['x', '-y', '-bsp1', '-bb0', '-sccUTF-8', '-o' + staging]
            if wanted:
                args.append('-spd')                 # names are names, not wildcards
            rc, out, err = _run_7z(args + ['--', self.path] + (wanted or []), self.password,
                                   cancelled, percent_lines(on_progress))
            refused = _refused_links(err, staging)
            if rc not in (0, 1) and not (rc == 2 and refused):
                log.warning("7z stopped with code %s: %s", rc, err.strip()[-2000:])
                raise _7z_problem(rc, out, err, self.password)
            for name in refused or ():
                # 7z wouldn't write these (unsafe); they go on the list of what was left out
                yield Entry(name, REFUSED), None
            if on_progress:
                on_progress(1.0)
            yield from staged_entries(staging)
        finally:
            shutil.rmtree(staging, ignore_errors=True)


class _Staged:
    """A file an outside command unpacked; the writer moves it into place instead of copying
    it."""

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


def staged_entries(staging: str) -> Iterator[Tuple[Entry, Any]]:
    """What an outside command unpacked into the staging folder, as entries for the safe
    writer: folders, links (their targets as written, which the writer checks again), files
    (moved into place, never followed), and anything else, which is left out."""
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
                yield Entry(base + f, LINK, 0, st.st_mtime, 0o777, os.readlink(full)), None
            elif stat.S_ISREG(st.st_mode):
                yield Entry(base + f, FILE, st.st_size, st.st_mtime,
                            st.st_mode & 0o7777), _Staged(full)
            else:
                yield Entry(base + f, OTHER, 0, st.st_mtime, 0), None


MAX_NAME_ARGS = 2000
MAX_NAME_BYTES = 64 * 1024


def name_args(names: Optional[List[str]]) -> Optional[List[str]]:
    """The member names to give an outside command, or None to unpack everything: no
    selection, one too long for a command line, or a name the command would take for a list
    file or a switch."""
    if names is None:
        return None
    out = sorted({n.rstrip('/') for n in names if n.rstrip('/')})
    if not out or len(out) > MAX_NAME_ARGS or \
            sum(len(os.fsencode(n)) + 1 for n in out) > MAX_NAME_BYTES or \
            any(n[0] in '@-' or '\0' in n for n in out):
        return None
    return out


def percent_lines(on_progress: Optional[Callable[[float], None]]) -> Callable[[str], None]:
    """Turns a command's 'NN%' output into progress that never goes backwards."""
    seen = [0]

    def line(text: str) -> None:
        m = re.match(r'\s*(\d{1,3})%', text) or re.search(r'(\d{1,3})%\s*$', text)
        if m and on_progress:
            value = min(100, int(m.group(1)))
            if value > seen[0]:
                seen[0] = value
                on_progress(value / 100)
    return line


# ─── the unrar command ────────────────────────────────────────

def unrar() -> Optional[str]:
    return shutil.which('unrar')


# unrar's "Type:" words, most specific first
UNRAR_TYPES = (('hard link', HARDLINK), ('link', LINK), ('junction', LINK),
               ('directory', DIR), ('file', FILE))


def _unrar_problem(rc: int, out: str, err: str, password: Optional[str]) -> ArchiveProblem:
    text = (err + '\n' + out).strip()
    low = text.lower()
    missing = re.search(r'cannot find volume\s+(\S.*)', text, re.I)
    if missing:
        return MissingPart(os.path.basename(missing.group(1).strip()))
    # A wrong password: RAR 5 checks it first ("The specified password is incorrect");
    # RAR 4 can only tell by a checksum error ("Corrupt file or wrong password"). Without one,
    # unrar asks ("Enter password") and stops when it finds stdin closed.
    if 'password' in low and ('incorrect' in low or 'wrong' in low):
        return WrongPassword(text) if password else NeedPassword(text)
    if password is None and 'enter password' in low:
        return NeedPassword(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return BadArchive(lines[-1] if lines else f"unrar stopped with code {rc}")


class UnrarReader(Reader):
    """RARLAB's unrar (RPM Fusion's unrar package), for password-protected RAR 4 and 5,
    including archives whose names are encrypted too. It unpacks into a staging folder and the
    safe writer moves each file into place, as with the 7z command."""
    backend = 'unrar'

    def __init__(self, path: str, kind: str, password: Optional[str] = None,
                 volumes: Optional[Volumes] = None):
        super().__init__(path, kind, password, volumes)
        if kind != formats.RAR:
            raise Unsupported("unrar reads only rar")
        if not unrar():
            raise NeedsTool('unrar')

    def _run(self, args: List[str], cancelled: Never,
             on_line: Optional[Callable[[str], None]] = None) -> Tuple[int, str, str]:
        # -cfg-: no rar.ini, no RAR variable; -idc: no banner. The password goes on stdin,
        # which unrar reads when stdin isn't a terminal; without one stdin is closed, so a
        # question for a password ends unrar instead of waiting.
        stdin = self.password + '\n' if self.password is not None else ''
        return run_tool(unrar(), [args[0], '-cfg-', '-idc'] + args[1:], stdin, cancelled,
                        on_line)

    def list(self, cancelled=_never) -> List[Entry]:
        rc, out, err = self._run(['lt', '-y', '--', self.path], cancelled)
        if rc not in (0, 1):
            raise _unrar_problem(rc, out, err, self.password)
        entries: List[Entry] = []
        seen = set()
        fields: dict = {}

        def flush() -> None:
            name = fields.get('Name')
            if name is None or name in seen:      # volumes repeat a split file's header
                return
            seen.add(name)
            typ = fields.get('Type', 'File').lower()
            kind = next((k for word, k in UNRAR_TYPES if word in typ), FILE)
            digits = re.sub(r'\D', '', fields.get('Size', ''))
            size = int(digits) if digits else -1
            mtime = None
            when = fields.get('mtime') or fields.get('Modified') or ''
            if when:
                try:
                    mtime = time.mktime(time.strptime(when[:19], '%Y-%m-%d %H:%M:%S'))
                except (ValueError, OverflowError):
                    pass
            mode = 0
            unix = re.match(r'[-dl]([-rwxsStT]{9})$', fields.get('Attributes', '').strip())
            if unix:
                for i, ch in enumerate(unix.group(1)):
                    if ch not in '-ST':
                        mode |= 1 << (8 - i)
            entries.append(Entry(name, kind, size if kind == FILE else 0, mtime, mode,
                                 fields.get('Target', ''),
                                 'encrypt' in fields.get('Flags', '').lower()))

        for raw in out.splitlines():
            key, sep, value = raw.strip().partition(': ')
            if not sep:
                continue
            if key == 'Name':
                flush()
                fields = {}
            fields[key] = value
        flush()
        if self.password is not None and not any(e.encrypted for e in entries):
            for e in entries:                     # its names were encrypted: so is the rest
                e.encrypted = e.kind == FILE
        return entries

    def items(self, cancelled=_never, listing=False, workdir=None, on_progress=None,
              names=None):
        if listing:
            for e in self.list(cancelled):
                yield e, None
            return
        if not workdir:
            raise ValueError("unrar needs a staging folder")
        wanted = name_args(names)
        self.used_names = wanted is not None
        staging = tempfile.mkdtemp(prefix='.spark-archive-', dir=workdir)
        try:
            # x: with folders; -o+: replace (the staging folder starts empty); -y: yes to
            # every question. The folder to unpack to comes last, marked by its slash.
            rc, out, err = self._run(['x', '-o+', '-y', '--', self.path] + (wanted or [])
                                     + [staging + '/'], cancelled, percent_lines(on_progress))
            if rc == 10 and wanted:
                rc = 0           # none of the names matched: the caller unpacks it all instead
            if rc not in (0, 1):
                log.warning("unrar stopped with code %s: %s", rc, (err + out).strip()[-2000:])
                raise _unrar_problem(rc, out, err, self.password)
            if on_progress:
                on_progress(1.0)
            yield from staged_entries(staging)
        finally:
            shutil.rmtree(staging, ignore_errors=True)


# ─── choosing ─────────────────────────────────────────────────

def candidates(kind: str, style: Optional[str] = None) -> List[type]:
    """The readers for a kind of archive, best first. `style`: the kind of set of parts it
    is (volumes.SPLIT, RAR or ZIP), if it is one."""
    if style == vol.ZIP:
        return [SevenZipReader]
    if style == vol.RAR or kind == formats.RAR:
        return [LibarchiveReader, UnrarReader, SevenZipReader]
    if style == vol.SPLIT:
        return [LibarchiveReader, SevenZipReader]
    if kind == formats.ZIP:
        return [ZipReader, LibarchiveReader, SevenZipReader]
    if kind == formats.TAR or kind.startswith('tar.'):
        return [TarReader, LibarchiveReader, SevenZipReader]
    if kind in (formats.SEVENZIP, formats.ISO):
        return [LibarchiveReader, SevenZipReader]
    if kind in formats.COMPRESSED:
        return [SingleReader, LibarchiveReader]
    return [LibarchiveReader, SevenZipReader]


def open_reader(path: str, kind: str, password: Optional[str] = None,
                skip: int = 0, volumes: Optional[Volumes] = None) -> Reader:
    """The first reader (from the `skip`-th on) that takes this archive. For a set of parts,
    `path` is the part a command is given (volumes.open_path)."""
    last: Optional[Unsupported] = None
    tool: Optional[NeedsTool] = None
    for cls in candidates(kind, volumes.style if volumes else None)[skip:]:
        try:
            return cls(path, kind, password, volumes)
        except NeedsTool as exc:
            tool = tool or exc
        except Unsupported as exc:
            last = exc
    if tool:
        raise tool
    raise Unsupported(str(last) if last else "no reader for this archive")


def what_reads(kind: str, style: Optional[str] = None) -> List[str]:
    """For the self-test and the PR: which readers are available for a kind, in order."""
    names = []
    for cls in candidates(kind, style):
        if cls is LibarchiveReader and not la.load():
            continue
        if cls is SevenZipReader and not sevenzip():
            continue
        if cls is UnrarReader and not unrar():
            continue
        if cls in (TarReader, SingleReader) and kind.endswith(formats.ZST) and \
                not formats.has_zstd():
            continue
        names.append({ZipReader: 'zipfile', TarReader: 'tarfile', SingleReader: 'python',
                      LibarchiveReader: 'libarchive', SevenZipReader: '7z',
                      UnrarReader: 'unrar'}[cls])
    return names
