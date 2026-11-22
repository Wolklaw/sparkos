"""Copying, moving, renaming and deleting, in the background.

A Job runs in its own thread. The window reads its progress fields (no locks needed for
reading numbers), and can pause, resume or cancel it. When a name is already taken, the job
calls ask(source, target) from its thread; the window answers through Job.answer(), and the
job waits until it does. One answer can apply to all the clashes left."""

import errno
import os
import re
import shutil
import stat
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from .core import log

CHUNK = 8 * 1024 * 1024

REPLACE, SKIP, KEEP_BOTH, CANCEL = 'replace', 'skip', 'keep_both', 'cancel'


class Cancelled(Exception):
    pass


# ─── Names ───────────────────────────────────────────────────

_NUMBERED = re.compile(r'^(.*) \((\d+)\)$')


def split_ext(name: str) -> Tuple[str, str]:
    """'photo.tar.gz' -> ('photo', '.tar.gz'); '.bashrc' -> ('.bashrc', '');
    'folder' -> ('folder', '')."""
    lower = name.lower()
    for double in ('.tar.gz', '.tar.xz', '.tar.zst', '.tar.bz2', '.tar.lz'):
        if lower.endswith(double) and len(name) > len(double):
            return name[:-len(double)], name[-len(double):]
    dot = name.rfind('.')
    if dot <= 0:
        return name, ''
    return name[:dot], name[dot:]


def free_name(folder: str, name: str, is_dir: bool = False) -> str:
    """The first of 'name (2).ext', 'name (3).ext'... that isn't taken in folder."""
    stem, ext = (name, '') if is_dir else split_ext(name)
    m = _NUMBERED.match(stem)
    n = 2
    if m:
        stem, n = m.group(1), int(m.group(2)) + 1
    while True:
        candidate = f"{stem} ({n}){ext}"
        if not os.path.lexists(os.path.join(folder, candidate)):
            return candidate
        n += 1


def name_problem(name: str) -> Optional[str]:
    """Why a new name can't be used, as a text key; None when it's fine."""
    if not name or not name.strip():
        return 'name.empty'
    if '/' in name or '\0' in name:
        return 'name.slash'
    if name in ('.', '..'):
        return 'name.dots'
    if len(name.encode('utf-8', 'surrogateescape')) > 255:
        return 'name.long'
    return None


def is_inside(path: str, folder: str) -> bool:
    """True if path is folder itself or below it (real paths, so links don't fool it)."""
    p, f = os.path.realpath(path), os.path.realpath(folder)
    return p == f or p.startswith(f.rstrip(os.sep) + os.sep)


def rename(path: str, new_name: str) -> str:
    """Rename in place; refuses to replace something that exists (case-only renames work).
    Returns the new path."""
    problem = name_problem(new_name)
    if problem:
        raise ValueError(problem)
    folder = os.path.dirname(path)
    target = os.path.join(folder, new_name)
    if target == path:
        return path
    if os.path.lexists(target):
        try:
            same = os.path.samefile(path, target)      # 'a.txt' -> 'A.txt' on a FAT/NTFS drive
        except OSError:
            same = False
        if not same:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), target)
    os.rename(path, target)
    return target


def batch_names(names: List[str], pattern: str, start: int = 1) -> List[str]:
    """New names for a batch rename. The pattern uses # for a number (## pads to two digits),
    * for the old name without its extension; the extension is kept.
    'Trip ##' -> 'Trip 01.jpg', 'Trip 02.jpg'...; '* (old)' -> 'a (old).txt'."""
    out = []
    width = 0
    m = re.search(r'#+', pattern)
    if m:
        width = len(m.group(0))
    for i, name in enumerate(names):
        stem, ext = split_ext(name)
        new = pattern
        if m:
            number = str(start + i).zfill(width)
            new = new[:m.start()] + number + new[m.end():]
        new = new.replace('*', stem)
        out.append(new + ext)
    return out


def find_replace_names(names: List[str], find: str, replace: str,
                       case: bool = False) -> List[str]:
    if not find:
        return list(names)
    flags = 0 if case else re.IGNORECASE
    return [re.sub(re.escape(find), lambda _m: replace, n, flags=flags) for n in names]


def new_folder(folder: str, name: str) -> str:
    problem = name_problem(name)
    if problem:
        raise ValueError(problem)
    path = os.path.join(folder, name)
    os.mkdir(path)
    return path


def new_file(folder: str, name: str) -> str:
    problem = name_problem(name)
    if problem:
        raise ValueError(problem)
    path = os.path.join(folder, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    os.close(fd)
    return path


# ─── Jobs ────────────────────────────────────────────────────

class Job:
    """copy, move, delete (for good) or trash a list of paths. Start with start()."""

    def __init__(self, kind: str, sources: List[str], dest: Optional[str] = None,
                 ask: Optional[Callable[['Job', str, str], None]] = None,
                 on_done: Optional[Callable[['Job'], None]] = None):
        assert kind in ('copy', 'move', 'delete', 'trash', 'restore')
        self.kind, self.sources, self.dest = kind, list(sources), dest
        self.ask, self.on_done = ask, on_done
        self.total_bytes = self.done_bytes = 0
        self.total_files = self.done_files = 0
        self.current = ''
        self.state = 'waiting'       # waiting scanning running paused done cancelled
        self.errors: List[Tuple[str, str]] = []           # (path, why)
        self.created: List[str] = []                      # top-level results, to select
        self.pairs: List[Tuple[str, str]] = []            # (source, where it went)
        self.untrashable: List[str] = []                  # trash refused: offer delete
        self.started = 0.0
        self.finished = 0.0
        self._go = threading.Event()
        self._go.set()
        self._cancel = threading.Event()
        self._answer: Optional[Tuple[str, bool]] = None
        self._answered = threading.Event()
        self._apply_all: Optional[str] = None
        self.waiting_for_answer: Optional[Tuple[str, str]] = None
        self.thread: Optional[threading.Thread] = None
        self.restore_targets: Dict[str, str] = {}         # restore: trashed path -> where

    # control, from the window

    def start(self) -> 'Job':
        self.thread = threading.Thread(target=self._run, name=f'job-{self.kind}', daemon=True)
        self.thread.start()
        return self

    def pause(self) -> None:
        if self.state in ('running', 'scanning'):
            self._go.clear()
            self.state = 'paused'

    def resume(self) -> None:
        if self.state == 'paused':
            self.state = 'running'
            self._go.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._go.set()
        if self.waiting_for_answer:
            self.answer(CANCEL, False)

    def answer(self, choice: str, apply_all: bool = False) -> None:
        self._answer = (choice, apply_all)
        self._answered.set()

    @property
    def active(self) -> bool:
        return self.state in ('waiting', 'scanning', 'running', 'paused')

    @property
    def fraction(self) -> float:
        if self.total_bytes > 0:
            return min(1.0, self.done_bytes / self.total_bytes)
        if self.total_files > 0:
            return min(1.0, self.done_files / self.total_files)
        return 0.0

    def speed(self) -> float:
        elapsed = (self.finished or time.monotonic()) - self.started
        return self.done_bytes / elapsed if elapsed > 0.5 else 0.0

    def eta(self) -> Optional[float]:
        speed = self.speed()
        if speed <= 0 or self.total_bytes <= 0:
            return None
        return max(0.0, (self.total_bytes - self.done_bytes) / speed)

    # the thread

    def _check(self) -> None:
        if not self._go.is_set():
            self._go.wait()
        if self._cancel.is_set():
            raise Cancelled()

    def _run(self) -> None:
        self.started = time.monotonic()
        try:
            self.state = 'scanning'
            if self.kind in ('copy', 'move', 'delete'):
                self._scan()
            else:
                self.total_files = len(self.sources)
            if self.state == 'scanning':
                self.state = 'running'
            {'copy': self._copy_all, 'move': self._move_all, 'delete': self._delete_all,
             'trash': self._trash_all, 'restore': self._restore_all}[self.kind]()
            self.state = 'done'
        except Cancelled:
            self.state = 'cancelled'
        except Exception as exc:          # noqa: BLE001 - shown to the person, logged
            log.exception("%s job failed", self.kind)
            self.errors.append(('', str(exc)))
            self.state = 'done'
        self.finished = time.monotonic()
        if self.on_done:
            try:
                self.on_done(self)
            except Exception:             # noqa: BLE001
                log.exception("on_done")

    def _scan(self) -> None:
        for src in self.sources:
            self._check()
            try:
                st = os.lstat(src)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                if self.kind == 'move' and self.dest and self._same_device(src, self.dest):
                    self.total_files += 1          # a rename: one step, no bytes
                    continue
                for root, dirs, files in os.walk(src, onerror=lambda e: None):
                    self._check()
                    self.total_files += len(files) + len(dirs)
                    for name in files:
                        try:
                            st_f = os.lstat(os.path.join(root, name))
                            if stat.S_ISREG(st_f.st_mode):
                                self.total_bytes += st_f.st_size
                        except OSError:
                            pass
                self.total_files += 1
            else:
                self.total_files += 1
                if not (self.kind == 'move' and self.dest and self._same_device(src, self.dest)) \
                        and stat.S_ISREG(st.st_mode) and self.kind != 'delete':
                    self.total_bytes += st.st_size

    @staticmethod
    def _same_device(src: str, dest: str) -> bool:
        try:
            return os.lstat(src).st_dev == os.stat(dest).st_dev
        except OSError:
            return False

    def _decide(self, src: str, target: str) -> str:
        """What to do about a taken name: REPLACE, SKIP or KEEP_BOTH (CANCEL raises)."""
        if self._apply_all:
            return self._apply_all
        if self.ask is None:
            return SKIP
        self._answered.clear()
        self.waiting_for_answer = (src, target)
        self.ask(self, src, target)
        while not self._answered.wait(0.2):
            if self._cancel.is_set():
                break
        self.waiting_for_answer = None
        choice, apply_all = self._answer or (CANCEL, False)
        self._answer = None
        if choice == CANCEL or self._cancel.is_set():
            raise Cancelled()
        if apply_all:
            self._apply_all = choice
        return choice

    # copy and move

    def _target_for(self, src: str) -> Optional[str]:
        """Where src goes at the top level; None to skip it."""
        assert self.dest is not None
        name = os.path.basename(src.rstrip(os.sep))
        target = os.path.join(self.dest, name)
        if os.path.isdir(src) and not os.path.islink(src) and is_inside(self.dest, src):
            self.errors.append((src, 'error.into_itself'))
            return None
        if os.path.abspath(src) == os.path.abspath(target):
            if self.kind == 'move':
                return None                      # moving into the folder it's already in
            return os.path.join(self.dest, free_name(self.dest, name, os.path.isdir(src)))
        return target

    def _copy_all(self) -> None:
        for src in self.sources:
            self._check()
            target = self._target_for(src)
            if target is None:
                continue
            result = self._copy_item(src, target)
            if result:
                self.created.append(result)
                self.pairs.append((src, result))

    def _move_all(self) -> None:
        for src in self.sources:
            self._check()
            target = self._target_for(src)
            if target is None:
                continue
            result = self._move_item(src, target)
            if result and not os.path.lexists(src):
                self.created.append(result)
                self.pairs.append((src, result))
            elif result:
                self.created.append(result)

    def _resolve(self, src: str, target: str) -> Optional[str]:
        """target if it's free (or the person chose to replace it, which removes it), another
        free name for keep both, None to skip. Folders onto folders merge without asking."""
        if not os.path.lexists(target):
            return target
        src_dir = os.path.isdir(src) and not os.path.islink(src)
        dst_dir = os.path.isdir(target) and not os.path.islink(target)
        if src_dir and dst_dir:
            return target                         # merge
        try:
            if os.path.samefile(src, target):
                return None
        except OSError:
            pass
        choice = self._decide(src, target)
        if choice == SKIP:
            return None
        if choice == KEEP_BOTH:
            folder = os.path.dirname(target)
            return os.path.join(folder, free_name(folder, os.path.basename(target), src_dir))
        # replace
        if dst_dir:
            shutil.rmtree(target)
        else:
            os.unlink(target)
        return target

    def _copy_item(self, src: str, target: str) -> Optional[str]:
        try:
            target = self._resolve(src, target)
        except OSError as exc:
            self.errors.append((target, exc.strerror or str(exc)))
            return None
        if target is None:
            self._skip_count(src)
            return None
        self.current = src
        try:
            st = os.lstat(src)
        except OSError as exc:
            self.errors.append((src, exc.strerror or str(exc)))
            return None
        try:
            if stat.S_ISLNK(st.st_mode):
                os.symlink(os.readlink(src), target)
                self.done_files += 1
            elif stat.S_ISDIR(st.st_mode):
                if not os.path.isdir(target):
                    os.mkdir(target)
                self.done_files += 1
                try:
                    names = sorted(os.listdir(src))
                except OSError as exc:
                    self.errors.append((src, exc.strerror or str(exc)))
                    names = []
                for name in names:
                    self._check()
                    self._copy_item(os.path.join(src, name), os.path.join(target, name))
                try:
                    shutil.copystat(src, target)
                except OSError:
                    pass
            elif stat.S_ISREG(st.st_mode):
                self._copy_file(src, target, st)
                self.done_files += 1
            else:
                self.errors.append((src, 'error.special'))   # sockets, devices, pipes
                return None
        except Cancelled:
            raise
        except OSError as exc:
            self.errors.append((src, exc.strerror or str(exc)))
            return None
        return target

    def _copy_file(self, src: str, target: str, st: os.stat_result) -> None:
        done_before = self.done_bytes
        fsrc = os.open(src, os.O_RDONLY)
        try:
            fdst = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, st.st_mode & 0o7777)
        except OSError:
            os.close(fsrc)
            raise
        ok = False
        try:
            use_range = hasattr(os, 'copy_file_range')
            while True:
                self._check()
                n = 0
                if use_range:
                    try:
                        n = os.copy_file_range(fsrc, fdst, CHUNK)
                    except OSError as exc:
                        if exc.errno not in (errno.EXDEV, errno.ENOSYS, errno.EINVAL,
                                             errno.EOPNOTSUPP, errno.EBADF, errno.EPERM):
                            raise
                        use_range = False
                        continue
                else:
                    data = os.read(fsrc, CHUNK)
                    if data:
                        view = memoryview(data)
                        while view:
                            written = os.write(fdst, view)
                            view = view[written:]
                    n = len(data)
                if n == 0:
                    break
                self.done_bytes += n
            ok = True
        finally:
            os.close(fsrc)
            os.close(fdst)
            if not ok:
                self.done_bytes = done_before
                try:
                    os.unlink(target)            # never leave half a file behind
                except OSError:
                    pass
        try:
            shutil.copystat(src, target)
        except OSError:
            pass

    def _skip_count(self, src: str) -> None:
        try:
            if os.path.isdir(src) and not os.path.islink(src):
                for _root, dirs, files in os.walk(src):
                    self.done_files += len(dirs) + len(files)
                    for name in files:
                        try:
                            st_f = os.lstat(os.path.join(_root, name))
                            if stat.S_ISREG(st_f.st_mode):
                                self.done_bytes += st_f.st_size
                        except OSError:
                            pass
                self.done_files += 1
            else:
                self.done_files += 1
                st_s = os.lstat(src)
                if stat.S_ISREG(st_s.st_mode):
                    self.done_bytes += st_s.st_size
        except OSError:
            pass

    def _move_item(self, src: str, target: str) -> Optional[str]:
        self.current = src
        same_dev = self._same_device(src, os.path.dirname(target))
        try:
            resolved = self._resolve(src, target)
        except OSError as exc:
            self.errors.append((target, exc.strerror or str(exc)))
            return None
        if resolved is None:
            self.done_files += 1
            return None
        target = resolved
        if same_dev:
            src_dir = os.path.isdir(src) and not os.path.islink(src)
            if src_dir and os.path.isdir(target):
                # merge into an existing folder: move what's inside one by one
                for name in sorted(os.listdir(src)):
                    self._check()
                    self._move_item(os.path.join(src, name), os.path.join(target, name))
                try:
                    os.rmdir(src)
                except OSError:
                    pass                          # something inside was skipped
                self.done_files += 1
                return target
            try:
                os.rename(src, target)
                self.done_files += 1
                return target
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    self.errors.append((src, exc.strerror or str(exc)))
                    return None
        # another drive: copy, then remove what was copied without errors
        errors_before = len(self.errors)
        result = self._copy_item(src, target)
        if result is None or len(self.errors) > errors_before:
            return result
        try:
            if os.path.isdir(src) and not os.path.islink(src):
                shutil.rmtree(src)
            else:
                os.unlink(src)
        except OSError as exc:
            self.errors.append((src, exc.strerror or str(exc)))
        return result

    # delete and trash

    def _delete_all(self) -> None:
        for src in self.sources:
            self._check()
            self.current = src
            try:
                if os.path.isdir(src) and not os.path.islink(src):
                    for root, dirs, files in os.walk(src, topdown=False):
                        for name in files:
                            self._check()
                            path = os.path.join(root, name)
                            try:
                                os.unlink(path)
                            except OSError as exc:
                                self.errors.append((path, exc.strerror or str(exc)))
                            self.done_files += 1
                        for name in dirs:
                            path = os.path.join(root, name)
                            try:
                                if os.path.islink(path):
                                    os.unlink(path)
                                else:
                                    os.rmdir(path)
                            except OSError as exc:
                                self.errors.append((path, exc.strerror or str(exc)))
                            self.done_files += 1
                    os.rmdir(src)
                else:
                    os.unlink(src)
            except FileNotFoundError:
                pass
            except OSError as exc:
                self.errors.append((src, exc.strerror or str(exc)))
            self.done_files += 1

    def _trash_all(self) -> None:
        from . import trash
        for src in self.sources:
            self._check()
            self.current = src
            try:
                self.created.append(trash.trash(src))
            except trash.NoTrash:
                self.untrashable.append(src)
            except FileNotFoundError:
                pass
            except OSError as exc:
                self.errors.append((src, exc.strerror or str(exc)))
            self.done_files += 1

    def _restore_all(self) -> None:
        from . import trash
        for item in self.sources:            # paths inside a Trash/files folder
            self._check()
            self.current = item
            try:
                original = trash.original_path(item)
                if original is None:
                    self.errors.append((item, 'error.no_trashinfo'))
                    continue
                os.makedirs(os.path.dirname(original), exist_ok=True)
                target = self._resolve(item, original)
                if target is None:
                    continue
                trash.restore(item, target)
                self.created.append(target)
                self.restore_targets[item] = target
            except OSError as exc:
                self.errors.append((item, exc.strerror or str(exc)))
            self.done_files += 1
