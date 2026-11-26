"""The work: listing, extracting and compressing, each in a thread so the window never waits.

A job asks its questions (password, overwrite) through `asker(question, info)`, which the
window answers with a dialog and the tests answer with a function. Progress is plain
attributes the window reads ten times a second."""

import errno
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from . import formats
from . import volumes as vol
from .core import keep_both_name, log, stem, unique_path
from .readers import (REFUSED, ArchiveProblem, BadArchive, Entry, MissingPart, NeedPassword,
                      NeedsTool, SevenZipReader, UnrarReader, Unsupported, WrongPassword,
                      _run_7z, candidates, open_reader, percent_lines, sevenzip, unrar)
from .safety import (DIR, FILE, HARDLINK, LINK, OTHER, Blocked, Cancelled, SafeWriter,
                     clean_parts, is_root, link_target_ok)

Asker = Callable[[str, Dict[str, Any]], Any]

# answers to 'overwrite'
REPLACE, SKIP, KEEP_BOTH, CANCEL = 'replace', 'skip', 'keep', 'cancel'

# why something was left out (keys into text.py)
OUTSIDE = 'outside'            # name leads outside the folder (../, or only "/")
LINK_OUT = 'link_out'          # link points outside the folder
SPECIAL = 'special'            # device, pipe or socket
IN_THE_WAY = 'in_the_way'      # a folder or a link already there where a file should go
FAILED = 'failed'              # the system refused (permission and the like)
UNREADABLE = 'unreadable'      # compressing: couldn't read it

FATAL_ERRNOS = (errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EIO)


def no_questions(question: str, info: Dict[str, Any]) -> Any:
    """For callers with nobody to ask: no password, never overwrite."""
    if question == 'password':
        return None
    if question == 'overwrite':
        return SKIP, True
    return None


@dataclass
class Result:
    ok: bool = False
    cancelled: bool = False
    error: Optional[str] = None            # key into text.py
    detail: str = ''                       # what the library or the system said
    output: Optional[str] = None           # the folder extracted to, or the archive made
    files: int = 0
    folders: int = 0
    links: int = 0
    replaced: int = 0
    skipped: int = 0                       # you chose Skip
    problems: List[Tuple[str, str]] = field(default_factory=list)   # (name, why)


class Job:
    def __init__(self, asker: Asker = no_questions):
        self.asker = asker
        self._cancel = threading.Event()
        self.done_bytes = 0
        self.total_bytes = 0
        self.done_files = 0
        self.total_files = 0
        self.current = ''
        self.phase = 'reading'
        self.result: Optional[Result] = None
        self.thread: Optional[threading.Thread] = None
        self.started = time.monotonic()

    def start(self) -> 'Job':
        self.thread = threading.Thread(target=self._main, daemon=True)
        self.thread.start()
        return self

    def _main(self) -> None:
        try:
            self.result = self.run()
        except Exception as exc:                      # a bug: say so, don't hang the window
            log.exception("job failed")
            self.result = Result(error='bug', detail=f"{type(exc).__name__}: {exc}")
        self.phase = 'done'

    def run_here(self) -> Result:
        """Run in this thread (tests, command line)."""
        self._main()
        return self.result

    def cancel(self) -> None:
        self._cancel.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def fraction(self) -> Optional[float]:
        if self.total_bytes > 0:
            return min(1.0, self.done_bytes / self.total_bytes)
        if self.total_files > 0:
            return min(1.0, self.done_files / self.total_files)
        return None

    def _add_bytes(self, n: int) -> None:
        self.done_bytes += n

    def run(self) -> Result:
        raise NotImplementedError


# ─── listing ──────────────────────────────────────────────────

class Listing:
    """What an archive holds, and how it was read."""

    def __init__(self, path: str, kind: str, entries: List[Entry], reader_index: int,
                 backend: str, password: Optional[str],
                 volumes: Optional[vol.Volumes] = None):
        self.path, self.kind, self.entries = path, kind, entries
        self.reader_index, self.backend, self.password = reader_index, backend, password
        self.volumes = volumes          # an archive in several parts: all of them

    @property
    def style(self) -> Optional[str]:
        return self.volumes.style if self.volumes else None

    @property
    def open_path(self) -> str:
        """What a reader is given: the archive, or for a set of parts the one tools open."""
        return self.volumes.open_path if self.volumes else self.path

    @property
    def encrypted(self) -> bool:
        return any(e.encrypted for e in self.entries)

    @property
    def total_size(self) -> int:
        return sum(e.size for e in self.entries if e.kind == FILE and e.size > 0)

    @property
    def file_count(self) -> int:
        return sum(1 for e in self.entries if e.kind in (FILE, LINK, HARDLINK))


def ask_password(job: Job, path: str, retry: bool) -> str:
    answer = job.asker('password', {'archive': os.path.basename(path), 'retry': retry})
    if answer is None:
        raise Cancelled()
    return answer


def find_archive(path: str) -> Tuple[str, Optional[vol.Volumes]]:
    """(kind, the set of parts it belongs to or None). Raises BadArchive('missing' or
    'not_archive') or MissingPart."""
    volumes = vol.find(path)
    if volumes and volumes.missing:
        raise MissingPart(volumes.missing)
    kind = formats.detect(volumes.first if volumes else path)
    if kind is None:
        if not os.path.exists(path):
            raise BadArchive('missing')
        raise BadArchive('not_archive')
    return kind, volumes


def unique_archives(paths: List[str]) -> List[str]:
    """The archives among `paths`, a set of parts counted once (the file manager passes every part
    that was selected)."""
    out, seen = [], set()
    for p in paths:
        try:
            found = vol.find(p)
        except OSError:
            found = None
        key = os.path.realpath(found.open_path if found else p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def read_listing(job: Job, path: str, password: Optional[str] = None) -> Listing:
    """List an archive, asking for a password if it needs one and trying the next reader
    when one can't do it. Raises ArchiveProblem or Cancelled."""
    kind, volumes = find_archive(path)
    style = volumes.style if volumes else None
    target = volumes.open_path if volumes else path
    order = candidates(kind, style)
    skip, first_bad, retry = 0, None, False
    tool: Optional[NeedsTool] = None
    while skip < len(order):
        try:
            reader = open_reader(target, kind, password, skip, volumes)
        except Unsupported as exc:
            raise first_bad or tool or exc
        index = order.index(type(reader))
        tool = tool or skipped_tool(order[skip:index])
        try:
            entries = reader.list(job.cancelled)
            return Listing(path, kind, entries, index, reader.backend, password, volumes)
        except (NeedPassword, WrongPassword) as exc:
            password = ask_password(job, path, retry=isinstance(exc, WrongPassword) or retry)
            retry = True
        except MissingPart:
            raise
        except Unsupported:
            skip = index + 1
        except BadArchive as exc:
            first_bad = first_bad or exc
            skip = index + 1
        finally:
            reader.close()
    raise first_bad or tool or Unsupported("no reader for this archive")


def skipped_tool(classes: List[type]) -> Optional[NeedsTool]:
    """Readers open_reader passed over because their command isn't installed: the first, as
    the thing to tell people (password-protected RAR needs unrar)."""
    for cls in classes:
        if cls is UnrarReader and not unrar():
            return NeedsTool('unrar')
        if cls is SevenZipReader and not sevenzip():
            return NeedsTool('7z')
    return None


class ListJob(Job):
    def __init__(self, path: str, asker: Asker = no_questions, password: Optional[str] = None):
        super().__init__(asker)
        self.path, self.password = path, password
        self.listing: Optional[Listing] = None

    def run(self) -> Result:
        try:
            self.listing = read_listing(self, self.path, self.password)
        except Cancelled:
            return Result(cancelled=True)
        except ArchiveProblem as exc:
            return problem_result(exc)
        except OSError as exc:
            return Result(error='read_failed', detail=exc.strerror or str(exc))
        return Result(ok=True, output=self.path)


def problem_result(exc: Exception) -> Result:
    msg = str(exc)
    if isinstance(exc, BadArchive) and msg in ('missing', 'not_archive'):
        return Result(error=msg)
    if isinstance(exc, MissingPart):
        return Result(error='missing_part', detail=msg)
    if isinstance(exc, NeedsTool):
        return Result(error='needs_' + exc.tool.replace('7z', 'sevenzip'), detail=exc.tool)
    if isinstance(exc, Unsupported):
        return Result(error='unsupported', detail=msg)
    if isinstance(exc, (NeedPassword, WrongPassword)):
        return Result(error='password', detail=msg)
    return Result(error='damaged', detail=msg)


# ─── extracting ───────────────────────────────────────────────

def single_top(entries: List[Entry]) -> Optional[str]:
    """The one folder everything is in, if there is exactly one top-level item and it is a
    folder."""
    tops: Set[str] = set()
    is_dir = False
    for e in entries:
        p = e.parts
        if not p:
            continue
        tops.add(p[0])
        if len(tops) > 1:
            return None
        if len(p) > 1 or e.kind == DIR:
            is_dir = True
    if len(tops) == 1 and is_dir:
        return next(iter(tops))
    return None


class ExtractJob(Job):
    """Extract `archive` into `dest`. With new_folder, into a new folder named after the
    archive inside `dest` (or straight into `dest` when the archive already holds just that
    one folder). `selection`: paths inside the archive (files or folders) to extract; None
    for everything."""

    def __init__(self, archive: str, dest: str, new_folder: bool = False,
                 selection: Optional[List[str]] = None, asker: Asker = no_questions,
                 password: Optional[str] = None, listing: Optional[Listing] = None):
        super().__init__(asker)
        self.archive = os.path.abspath(archive)
        self.dest = os.path.abspath(dest)
        self.new_folder = new_folder
        self.selection = {'/'.join(p) for p in (clean_parts(s) for s in selection or []) if p} \
            if selection is not None else None
        self.password = password if password is not None else (listing.password if listing
                                                               else None)
        self.listing = listing
        self.overwrite_all: Optional[str] = None
        self.result_obj = Result()

    def wanted(self, parts) -> bool:
        if self.selection is None:
            return True
        for i in range(1, len(parts) + 1):
            if '/'.join(parts[:i]) in self.selection:
                return True
        return False

    def run(self) -> Result:
        res = self.result_obj
        try:
            if self.listing is None:
                self.listing = read_listing(self, self.archive, self.password)
                self.password = self.listing.password
            listing = self.listing
        except Cancelled:
            res.cancelled = True
            return res
        except ArchiveProblem as exc:
            return problem_result(exc)
        except OSError as exc:
            return Result(error='read_failed', detail=exc.strerror or str(exc))

        listing.entries = [e for e in listing.entries
                           if not (e.kind == DIR and is_root(e.name))]
        chosen = [e for e in listing.entries if e.parts and self.wanted(e.parts)]
        self.chosen = chosen
        self.total_files = sum(1 for e in chosen if e.kind in (FILE, LINK, HARDLINK))
        self.total_bytes = sum(e.size for e in chosen if e.kind == FILE and e.size > 0)
        try:
            if any(e.encrypted for e in chosen) and self.password is None:
                self.password = ask_password(self, self.archive, retry=False)
        except Cancelled:
            res.cancelled = True
            return res

        # where
        made_root = None
        if not os.path.isdir(self.dest):
            return Result(error='no_folder', detail=self.dest)
        root = self.dest
        if self.new_folder:
            name = stem(self.archive)
            top = single_top(chosen)
            if not (top == name and not os.path.lexists(os.path.join(self.dest, name))):
                root = unique_path(self.dest, name)
                try:
                    os.mkdir(root)
                except OSError as exc:
                    return Result(error='cant_write', detail=f"{self.dest}: {exc.strerror}")
                made_root = root
        res.output = root
        if self.new_folder and root == self.dest:
            res.output = os.path.join(self.dest, stem(self.archive))   # its one folder

        # room
        try:
            st = os.statvfs(root)
            free = st.f_bavail * st.f_frsize
            if self.total_bytes > free:
                if made_root:
                    os.rmdir(made_root)
                return Result(error='no_space', detail=f"{self.total_bytes} {free}")
        except (OSError, AttributeError):
            pass

        try:
            writer = SafeWriter(root)
        except OSError as exc:
            return Result(error='cant_write', detail=f"{root}: {exc.strerror}")
        self.phase = 'writing'
        try:
            self._extract(writer, listing)
        except Cancelled:
            writer.undo()
            if made_root:
                try:
                    os.rmdir(made_root)
                except OSError:
                    pass
            res.cancelled = True
            res.replaced = writer.replaced
            return res
        except ArchiveProblem as exc:
            writer.finish()
            out = problem_result(exc)
            out.output, out.files, out.problems = root, res.files, res.problems
            return out
        except OSError as exc:
            writer.finish()
            key = 'no_space' if exc.errno in (errno.ENOSPC, errno.EDQUOT) else 'write_failed'
            return Result(error=key, detail=exc.strerror or str(exc), output=root,
                          files=res.files, problems=res.problems)
        for name in writer.finish():
            res.problems.append((name, LINK_OUT))
            res.links -= 1
        res.replaced = writer.replaced
        res.ok = True
        return res

    def _extract(self, writer: SafeWriter, listing: Listing) -> None:
        order = candidates(listing.kind, listing.style)
        skip = listing.reader_index
        done: Set[str] = set()
        retry = False
        first_bad: Optional[ArchiveProblem] = None
        tool: Optional[NeedsTool] = None
        # what an outside command (7z, unrar) is asked to unpack: only what was picked
        names = None if self.selection is None else [e.name for e in self.chosen]
        while True:
            try:
                reader = open_reader(listing.open_path, listing.kind, self.password, skip,
                                     listing.volumes)
            except Unsupported as exc:
                raise first_bad or tool or exc
            index = order.index(type(reader))
            tool = tool or skipped_tool(order[skip:index])
            base_bytes = self.done_bytes

            def staged_progress(fraction: float, base=base_bytes) -> None:
                left = max(0, self.total_bytes - base)
                self.done_bytes = base + int(left * fraction * 0.98)

            try:
                for e, data in reader.items(self.cancelled, workdir=writer.root,
                                            on_progress=staged_progress, names=names):
                    key = e.path or e.name
                    if key in done:
                        continue
                    parts = e.parts
                    if parts is not None and not self.wanted(parts):
                        continue
                    if parts is None and self.selection is not None:
                        continue
                    self.current = key
                    self._place(writer, e, parts, data)
                    done.add(key)
                if reader.used_names and any(
                        e.kind == FILE and e.path not in done for e in self.chosen):
                    # the command named some member differently than the listing did:
                    # unpack everything this time (what's already in place is skipped)
                    log.info("%s missed some picked names; unpacking all", reader.backend)
                    names = None
                    continue
                return
            except (NeedPassword, WrongPassword) as exc:
                self.password = ask_password(self, self.archive,
                                             retry=retry or isinstance(exc, WrongPassword))
                retry = True
            except MissingPart:
                raise
            except (Unsupported, BadArchive) as exc:
                # the next reader may manage; for a set of parts even when this one called
                # it damaged (one reader may not follow every kind of volume). If none does,
                # the first real problem is the one to tell.
                if isinstance(exc, BadArchive):
                    if tool:
                        raise tool          # the reader for this isn't installed: say that
                    if not listing.volumes:
                        raise
                    first_bad = first_bad or exc
                if index + 1 >= len(order):
                    raise first_bad or tool or exc
                skip = index + 1
            finally:
                reader.close()

    def _decide(self, e: Entry, parts, st: os.stat_result) -> str:
        if self.overwrite_all:
            return self.overwrite_all
        answer = self.asker('overwrite', {
            'name': parts[-1], 'path': '/'.join(parts), 'folder': self.result_obj.output,
            'new_size': e.size, 'new_mtime': e.mtime, 'old_size': st.st_size,
            'old_mtime': st.st_mtime, 'old_is_link': stat.S_ISLNK(st.st_mode)})
        choice, for_all = answer if isinstance(answer, tuple) else (answer, False)
        if choice == CANCEL or choice is None:
            raise Cancelled()
        if for_all and choice in (REPLACE, SKIP, KEEP_BOTH):
            self.overwrite_all = choice
        return choice

    def _place(self, writer: SafeWriter, e: Entry, parts, data) -> None:
        res = self.result_obj
        name = e.path or e.name
        if parts is None and e.kind == DIR and is_root(e.name):
            return                                      # the folder itself
        if e.kind == REFUSED:
            res.problems.append((e.name, REFUSED))
            return
        if parts is None:
            res.problems.append((e.name, OUTSIDE))
            self._count_skip(e)
            return
        if e.kind == OTHER:
            res.problems.append((name, SPECIAL))
            self._count_skip(e)
            return
        if e.kind == LINK and not link_target_ok(parts, e.target):
            res.problems.append((name, LINK_OUT))
            self._count_skip(e)
            return
        if e.kind == HARDLINK and clean_parts(e.target) not in writer.files:
            # only to a file this extraction wrote; never to one already on the disk
            res.problems.append((name, LINK_OUT if clean_parts(e.target) else OUTSIDE))
            self._count_skip(e)
            return
        replace = False
        try:
            st = writer.lstat(parts)
            if st is not None:
                if e.kind == DIR and stat.S_ISDIR(st.st_mode):
                    pass                                    # merge into the existing folder
                elif stat.S_ISDIR(st.st_mode):
                    res.problems.append((name, IN_THE_WAY))
                    self._count_skip(e)
                    return
                else:
                    choice = self._decide(e, parts, st)
                    if choice == SKIP:
                        res.skipped += 1
                        self._count_skip(e)
                        return
                    if e.kind == DIR:
                        if choice != REPLACE:           # a folder can't sit next to a file
                            res.problems.append((name, IN_THE_WAY))
                            return
                        writer.remove(parts)
                    elif choice == KEEP_BOTH:
                        folder = parts[:-1]
                        parts = folder + (keep_both_name(
                            parts[-1], lambda n: writer.lstat(folder + (n,)) is not None),)
                    else:
                        replace = True
            if e.kind == DIR:
                writer.make_dir(parts, e.mode, e.mtime)
                res.folders += 1
            elif e.kind == FILE:
                staged = getattr(data, 'staged_path', None)
                if staged:
                    self._add_bytes(0)
                    writer.move_in(parts, staged, e.mode, replace)
                else:
                    writer.write_file(parts, data, e.mode, e.mtime, replace, self._add_bytes,
                                      self.cancelled)
                res.files += 1
                self.done_files += 1
            elif e.kind == LINK:
                writer.make_symlink(parts, e.target, replace)
                res.links += 1
                self.done_files += 1
            elif e.kind == HARDLINK:
                writer.make_hardlink(parts, clean_parts(e.target), replace)
                res.files += 1
                self.done_files += 1
        except Blocked:
            res.problems.append((name, IN_THE_WAY if e.kind != LINK else LINK_OUT))
            self._count_skip(e)
        except (IsADirectoryError, FileExistsError, NotADirectoryError):
            res.problems.append((name, IN_THE_WAY))
            self._count_skip(e)
        except OSError as exc:
            if exc.errno in FATAL_ERRNOS:
                raise
            res.problems.append((name, FAILED + ':' + (exc.strerror or str(exc))))
            self._count_skip(e)

    def _count_skip(self, e: Entry) -> None:
        if e.kind in (FILE, LINK, HARDLINK):
            self.done_files += 1
        if e.kind == FILE and e.size > 0:
            self.done_bytes += e.size


# ─── compressing ──────────────────────────────────────────────

ZIP, SEVEN_Z, TAR_ZST = 'zip', '7z', 'tar.zst'
FORMATS = (ZIP, SEVEN_Z, TAR_ZST)
PASSWORD_FORMATS = (ZIP, SEVEN_Z)          # zip: AES-256 or ZipCrypto; 7z: AES-256, names too
AES, ZIPCRYPTO = 'aes', 'zipcrypto'        # how a zip is encrypted
# the three kinds of password archive the dialogs offer: (kind, format, zip encryption)
PASSWORD_KINDS = (('zip-any', ZIP, ZIPCRYPTO), ('zip-strong', ZIP, AES), ('7z', SEVEN_Z, AES))
DEFAULT_PASSWORD_KIND = 'zip-strong'
# already compressed: storing is as small and much faster than deflating again
STORE_EXT = {'.zip', '.7z', '.rar', '.gz', '.tgz', '.bz2', '.xz', '.zst', '.lz', '.lzma',
             '.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.heic', '.jxl', '.mp3', '.ogg',
             '.opus', '.flac', '.m4a', '.aac', '.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v',
             '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.epub', '.jar', '.apk',
             '.appimage', '.flatpak', '.rpm', '.deb', '.iso', '.woff', '.woff2', '.pdf'}


def default_output(sources: List[str], fmt: str) -> str:
    """photos/ -> photos.zip next to it; several items -> named after their folder."""
    first = os.path.abspath(sources[0]).rstrip('/')
    folder = os.path.dirname(first) or '/'
    if len(sources) == 1:
        name = os.path.basename(first)
        if os.path.isfile(first) and not os.path.islink(first):
            name = os.path.splitext(name)[0] or name
    else:
        name = os.path.basename(folder.rstrip('/')) or 'archive'
    if name.startswith('.') and len(name) > 1:
        name = name[1:]
    return unique_path(folder, name or 'archive', '.' + fmt)


class _Counting:
    """A source file that counts what is read from it and stops on Cancel."""

    def __init__(self, f, job: Job):
        self.f, self.job = f, job

    def read(self, n: int = -1) -> bytes:
        if self.job.cancelled():
            raise Cancelled()
        data = self.f.read(n)
        self.job.done_bytes += len(data)
        return data


class CompressJob(Job):
    """Make one archive of `sources`. zip without a password and tar.zst are written here
    with Python; 7z, and zip with a password, by the 7z command, with the password on its
    stdin. A zip's password is AES-256 (zip_encryption=AES, strong; Windows' own zip tool
    can't open it) or ZipCrypto (ZIPCRYPTO: opens anywhere, weak). A 7z with a password is
    AES-256 with its file names encrypted too."""

    def __init__(self, sources: List[str], fmt: str = ZIP, output: Optional[str] = None,
                 asker: Asker = no_questions, password: Optional[str] = None,
                 zip_encryption: str = AES):
        super().__init__(asker)
        if fmt not in FORMATS:
            raise ValueError(fmt)
        if password and fmt not in PASSWORD_FORMATS:
            raise ValueError(f"{fmt} can't have a password")
        if zip_encryption not in (AES, ZIPCRYPTO):
            raise ValueError(zip_encryption)
        self.zip_encryption = zip_encryption
        self.sources = [os.path.abspath(s).rstrip('/') or '/' for s in sources]
        self.fmt = fmt
        self.output = output
        self.password = password or None

    @property
    def with_7z(self) -> bool:
        return self.fmt == SEVEN_Z or self.password is not None

    def _walk(self, out_tmp: str, res: Result) -> List[Tuple[str, str, os.stat_result]]:
        items = []
        for src in self.sources:
            base = os.path.dirname(src)
            try:
                st = os.lstat(src)
            except OSError as exc:
                res.problems.append((src, UNREADABLE + ':' + (exc.strerror or str(exc))))
                continue
            items.append((src, os.path.basename(src), st))
            if stat.S_ISDIR(st.st_mode):
                errors: List[OSError] = []
                for top, dirs, files in os.walk(src, followlinks=False, onerror=errors.append):
                    if self.cancelled():
                        raise Cancelled()
                    dirs.sort()
                    for name in dirs + sorted(files):
                        full = os.path.join(top, name)
                        if full == out_tmp:
                            continue
                        try:
                            items.append((full, os.path.relpath(full, base).replace(os.sep, '/'),
                                          os.lstat(full)))
                        except OSError as exc:
                            res.problems.append((full, UNREADABLE + ':' + (exc.strerror or '')))
                for exc in errors:
                    res.problems.append((exc.filename or src,
                                         UNREADABLE + ':' + (exc.strerror or str(exc))))
        return items

    def run(self) -> Result:
        res = Result()
        out = self.output or default_output(self.sources, self.fmt)
        folder = os.path.dirname(out)
        if self.with_7z and not sevenzip():
            return Result(error='needs_sevenzip', detail='7z')
        tmp = os.path.join(folder, f'.{os.path.basename(out)}.spark-part-{os.getpid()}')
        try:
            items = self._walk(tmp, res)
        except Cancelled:
            return Result(cancelled=True)
        if not items:
            return Result(error='nothing', problems=res.problems)
        self.total_files = sum(1 for _p, _a, st in items if not stat.S_ISDIR(st.st_mode))
        self.total_bytes = sum(st.st_size for _p, _a, st in items if stat.S_ISREG(st.st_mode))
        self.phase = 'writing'
        private = None
        try:
            if self.with_7z:
                # 7z won't write over a file that is already there, even an empty one: it
                # makes the archive in a private folder next to where it goes
                private = tempfile.mkdtemp(prefix='.spark-archive-', dir=folder)
                tmp = os.path.join(private, 'new.' + self.fmt)
            else:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
                os.close(fd)
        except OSError as exc:
            return Result(error='cant_write', detail=f"{folder}: {exc.strerror}")

        def clean() -> None:
            _unlink(tmp)
            if private:
                shutil.rmtree(private, ignore_errors=True)

        try:
            if self.with_7z:
                self._seven(tmp, items, res)
            elif self.fmt == ZIP:
                self._zip(tmp, items, res)
            else:
                self._tar_zst(tmp, items, res)
            # into place, never over a file that appeared meanwhile
            final = out if not os.path.lexists(out) else unique_path(
                folder, os.path.basename(out)[:-len(self.fmt) - 1], '.' + self.fmt)
            try:
                os.link(tmp, final)
                os.unlink(tmp)
            except OSError:
                os.rename(tmp, final)
            clean()
        except Cancelled:
            clean()
            return Result(cancelled=True)
        except NeedsTool as exc:
            clean()
            return problem_result(exc)
        except OSError as exc:
            clean()
            key = 'no_space' if exc.errno in (errno.ENOSPC, errno.EDQUOT) else 'write_failed'
            return Result(error=key, detail=exc.strerror or str(exc), problems=res.problems)
        except BaseException:
            clean()
            raise
        res.output = final
        res.ok = True
        return res

    def _seven(self, tmp: str, items, res: Result) -> None:
        """7z and password-protected zip, with the 7z command, run once per source folder
        (a file manager's selection is one folder; a search result can span several)."""
        leave_out = []
        for path, arc, st in items:
            mode = st.st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
                res.problems.append((path, SPECIAL))      # 7z would wait on a pipe forever
                leave_out.append(arc)
            elif stat.S_ISREG(mode) and not os.access(path, os.R_OK):
                res.problems.append((path, UNREADABLE + ':' + os.strerror(errno.EACCES)))
                leave_out.append(arc)
            elif stat.S_ISDIR(mode):
                res.folders += 1
            elif stat.S_ISLNK(mode):
                res.links += 1
            else:
                res.files += 1
        args = ['a', '-y', '-bsp1', '-bb0', '-snl', '-sccUTF-8', '-scsUTF-8', '-spd', '-mx=5']
        if self.fmt == SEVEN_Z:
            args += ['-t7z'] + (['-p', '-mhe=on'] if self.password else [])
        else:
            method = '-mem=ZipCrypto' if self.zip_encryption == ZIPCRYPTO else '-mem=AES256'
            # -mcu=on: non-ASCII names marked as UTF-8, which Windows and Python read right
            args += ['-tzip', '-mcu=on'] + (['-p', method] if self.password else [])
        if leave_out:
            listfile = os.path.join(os.path.dirname(tmp), 'leave-out.txt')
            with open(listfile, 'w', encoding='utf-8', errors='surrogateescape') as f:
                f.write('\n'.join(leave_out) + '\n')
            args.append('-x@' + listfile)
        groups: Dict[str, List[str]] = {}
        for src in self.sources:
            groups.setdefault(os.path.dirname(src) or '/', []).append(os.path.basename(src))

        def progress(fraction: float) -> None:
            self.done_bytes = int(self.total_bytes * fraction)

        for cwd, names in groups.items():
            if self.cancelled():
                raise Cancelled()
            self.current = names[0]
            # -p with no value: 7z asks, and reads the answer from stdin (it may ask again
            # to confirm, or when adding to the archive the first folder made)
            rc, out, err = _run_7z(args + ['--', tmp] + names, self.password, self.cancelled,
                                   percent_lines(progress), asks=3, cwd=cwd)
            if rc == 1:                                    # warnings: some files unread
                for line in err.splitlines():
                    m = re.match(r'^(.*\S) : (.+)$', line.strip())
                    if m and not line.startswith(('WARNING', 'ERROR')):
                        item = (os.path.join(cwd, m.group(1)), UNREADABLE + ':' + m.group(2))
                        if item not in res.problems:
                            res.problems.append(item)
            elif rc != 0:
                text = (err + '\n' + out).strip()
                log.warning("7z a stopped with code %s: %s", rc, text[-2000:])
                if re.search(r'no space|errno=28|disk full', text, re.I):
                    raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
                lines = [ln for ln in err.splitlines() if ln.strip()] or [f"7z code {rc}"]
                raise OSError(errno.EIO, lines[-1].strip())
        self.done_bytes = self.total_bytes
        self.done_files = self.total_files

    def _zip(self, tmp: str, items, res: Result) -> None:
        with zipfile.ZipFile(tmp, 'w', allowZip64=True) as zf:
            for path, arc, st in items:
                if self.cancelled():
                    raise Cancelled()
                self.current = arc
                date = time.localtime(max(st.st_mtime, 315532800))[:6]   # zip starts in 1980
                if stat.S_ISDIR(st.st_mode):
                    info = zipfile.ZipInfo(arc + '/', date)
                    info.external_attr = ((stat.S_IFDIR | (st.st_mode & 0o7777)) << 16) | 0x10
                    info.create_system = 3
                    zf.writestr(info, b'')
                    res.folders += 1
                    continue
                if stat.S_ISLNK(st.st_mode):
                    info = zipfile.ZipInfo(arc, date)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    try:
                        zf.writestr(info, os.fsencode(os.readlink(path)))
                        res.links += 1
                    except OSError as exc:
                        res.problems.append((path, UNREADABLE + ':' + (exc.strerror or '')))
                    self.done_files += 1
                    continue
                if not stat.S_ISREG(st.st_mode):
                    res.problems.append((path, SPECIAL))
                    continue
                try:
                    src = open(path, 'rb')
                except OSError as exc:
                    res.problems.append((path, UNREADABLE + ':' + (exc.strerror or str(exc))))
                    self.done_bytes += st.st_size
                    self.done_files += 1
                    continue
                with src:
                    info = zipfile.ZipInfo(arc, date)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | (st.st_mode & 0o777)) << 16
                    store = os.path.splitext(arc)[1].lower() in STORE_EXT
                    info.compress_type = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
                    if not store:
                        info.compress_level = 6
                    info.file_size = st.st_size
                    with zf.open(info, 'w', force_zip64=st.st_size > 0x7FFFFFFF) as dst:
                        while True:
                            if self.cancelled():
                                raise Cancelled()
                            block = src.read(1 << 20)
                            if not block:
                                break
                            dst.write(block)
                            self.done_bytes += len(block)
                res.files += 1
                self.done_files += 1

    def _tar_zst(self, tmp: str, items, res: Result) -> None:
        import tarfile
        proc = None
        if formats.has_zstd():
            from compression import zstd
            try:
                workers = max(1, min(8, (os.cpu_count() or 2) - 1))
                out = zstd.ZstdFile(tmp, 'w', level=3,
                                    options={zstd.CompressionParameter.nb_workers: workers})
            except (zstd.ZstdError, ValueError, TypeError, AttributeError):
                out = zstd.ZstdFile(tmp, 'w', level=3)
        else:
            import shutil
            import subprocess
            exe = shutil.which('zstd')
            if not exe:
                raise OSError(errno.ENOSYS, "zstd is not available (no Python zstd, no zstd "
                                            "command)")
            proc = subprocess.Popen([exe, '-q', '-3', '-T0', '-f', '-o', tmp],
                                    stdin=subprocess.PIPE)
            out = proc.stdin
        try:
            with tarfile.open(fileobj=out, mode='w|', format=tarfile.PAX_FORMAT) as tf:
                for path, arc, st in items:
                    if self.cancelled():
                        raise Cancelled()
                    self.current = arc
                    if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)
                            or stat.S_ISLNK(st.st_mode)):
                        res.problems.append((path, SPECIAL))
                        continue
                    try:
                        info = tf.gettarinfo(path, arc)
                    except OSError as exc:
                        res.problems.append((path, UNREADABLE + ':' + (exc.strerror or '')))
                        continue
                    if info.isreg():
                        try:
                            src = open(path, 'rb')
                        except OSError as exc:
                            res.problems.append((path, UNREADABLE + ':' +
                                                 (exc.strerror or str(exc))))
                            self.done_bytes += st.st_size
                            self.done_files += 1
                            continue
                        with src:
                            tf.addfile(info, _Counting(src, self))
                        res.files += 1
                        self.done_files += 1
                    else:
                        tf.addfile(info)
                        if info.isdir():
                            res.folders += 1
                        else:
                            res.links += 1
                            self.done_files += 1
        finally:
            out.close()
            if proc is not None:
                if proc.wait() != 0 and not self.cancelled():
                    raise OSError(errno.EIO, "zstd failed")


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
