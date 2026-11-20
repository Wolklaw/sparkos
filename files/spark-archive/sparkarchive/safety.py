"""Safe extraction: nothing an archive contains can land outside the folder it is extracted to.

The rules, for every format alike:

- A name is cleaned before use: backslashes count as separators, a leading "/" or drive letter
  is dropped (so "/etc/passwd" becomes "etc/passwd" inside the folder), and any name with a
  ".." part is refused outright, even one that would stay inside.
- Folders are walked one part at a time through open folder handles with O_NOFOLLOW, so a
  write can never pass through a link, whether the archive made it earlier or it was already
  there.
- A link from the archive is made only if its target is relative, stays inside the folder,
  and has ".." only at its start (so "x/../y" is refused: x could be a link itself); when
  everything is out, each link made is resolved once more and removed if it leads out.
- Hard links may only point at a file this same extraction wrote.
- Files are written under a temporary name and moved into place when complete, so a cancelled
  or failed file never leaves half a file, and a file being replaced stays whole until then.
- Devices, pipes and sockets are skipped; setuid, setgid and sticky bits are dropped; your
  umask applies; nothing is chowned.

Linux only (it needs openat and O_NOFOLLOW).
"""

import errno
import os
import secrets
import stat
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Parts = Tuple[str, ...]
CHUNK = 1 << 20

FILE, DIR, LINK, HARDLINK, OTHER = 'file', 'dir', 'link', 'hardlink', 'other'

O_DIR = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0) | \
    getattr(os, 'O_CLOEXEC', 0)


class Cancelled(Exception):
    pass


class Blocked(OSError):
    """The path runs through a link or a file, or out of the folder."""


def clean_parts(name: str) -> Optional[Parts]:
    """The safe relative path parts of an archive member name, or None if it must be skipped.

    'a/b.txt' -> ('a', 'b.txt'); '/etc/passwd' -> ('etc', 'passwd'); 'C:\\x\\y' -> ('x', 'y');
    '../x', 'a/../../x', 'a/../b' -> None; '' and '/' -> None."""
    if not name or '\0' in name:
        return None
    text = name.replace('\\', '/')
    if len(text) >= 2 and text[1] == ':' and text[0].isalpha():
        text = text[2:]
    parts = [p for p in text.split('/') if p not in ('', '.')]
    if not parts or any(p == '..' for p in parts):
        return None
    if any(len(os.fsencode(p)) > 255 for p in parts):
        return None
    return tuple(parts)


def is_root(name: str) -> bool:
    """'.', './' or '/': the folder itself (iso images list it). Not an entry to extract or to
    report."""
    return bool(name) and not [p for p in name.replace('\\', '/').split('/')
                               if p not in ('', '.')]


def link_target_ok(parts: Parts, target: str) -> bool:
    """A symlink at `parts` pointing at `target` stays inside the folder (read as written; the
    final check in SafeWriter.finish() resolves it for real)."""
    if not target or '\0' in target or target.startswith('/') or target.startswith('\\'):
        return False
    if len(target) >= 2 and target[1] == ':':
        return False
    depth = len(parts) - 1                    # folders above the link, inside the root
    named = False
    for piece in target.split('/'):
        if piece in ('', '.'):
            continue
        if piece == '..':
            # "x/../y" is refused: if x is itself a link, ".." leaves from where x points
            # (x -> "." makes x/.. the folder above the root)
            if named:
                return False
            depth -= 1
            if depth < 0:
                return False
        else:
            named = True
            depth += 1
    return True


def read_umask() -> int:
    try:
        with open('/proc/self/status', encoding='ascii', errors='replace') as f:
            for line in f:
                if line.startswith('Umask:'):
                    return int(line.split()[1], 8)
    except (OSError, ValueError, IndexError):
        pass
    return 0o022


class SafeWriter:
    """Writes into one folder (`root`) through folder handles. Remembers what it created, so
    Cancel can take it away again."""

    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        self.root_fd = os.open(self.root, O_DIR)
        self.umask = read_umask()
        self._fds: Dict[Parts, int] = {}
        self.created: List[Tuple[Parts, str]] = []      # (parts, FILE/DIR/LINK) made new
        self.replaced = 0
        self.files: Dict[Parts, bool] = {}              # regular files written this run
        self.links: List[Parts] = []
        self.dir_times: Dict[Parts, float] = {}
        self.removed_links: List[str] = []              # links finish() found leading out

    # ─── folder handles ───────────────────────────────────────

    def _forget_fds(self) -> None:
        for fd in self._fds.values():
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds.clear()

    def close(self) -> None:
        self._forget_fds()
        if self.root_fd >= 0:
            try:
                os.close(self.root_fd)
            except OSError:
                pass
            self.root_fd = -1

    def dir_fd(self, parts: Sequence[str], create: bool = True) -> int:
        """A handle on the folder root/parts, made if missing. Raises Blocked if any part is a
        link or not a folder, FileNotFoundError if missing and create is False."""
        parts = tuple(parts)
        if not parts:
            return self.root_fd
        cached = self._fds.get(parts)
        if cached is not None:
            return cached
        parent = self.dir_fd(parts[:-1], create)
        name = parts[-1]
        try:
            fd = os.open(name, O_DIR, dir_fd=parent)
        except FileNotFoundError:
            if not create:
                raise
            try:
                os.mkdir(name, 0o755, dir_fd=parent)
                self.created.append((parts, DIR))
            except FileExistsError:
                pass
            fd = self._open_dir(parent, name, parts)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.EMLINK):
                raise Blocked(errno.ENOTDIR, f"{'/'.join(parts)} is a link or a file, "
                                             "not a folder") from None
            raise
        if len(self._fds) > 256:
            self._forget_fds()
        self._fds[parts] = fd
        return fd

    def _open_dir(self, parent: int, name: str, parts: Parts) -> int:
        try:
            return os.open(name, O_DIR, dir_fd=parent)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.EMLINK):
                raise Blocked(errno.ENOTDIR, f"{'/'.join(parts)} is a link or a file, "
                                             "not a folder") from None
            raise

    def lstat(self, parts: Parts) -> Optional[os.stat_result]:
        """What is at root/parts now (not following a link), or None. Raises Blocked if the
        folders above it run through a link."""
        try:
            parent = self.dir_fd(parts[:-1], create=False)
        except FileNotFoundError:
            return None
        try:
            return os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None

    # ─── modes ────────────────────────────────────────────────

    def file_mode(self, mode: int) -> int:
        return ((mode or 0o644) & 0o777 & ~self.umask) | 0o600

    def folder_mode(self, mode: int) -> int:
        return ((mode or 0o755) & 0o777 & ~self.umask) | 0o700

    # ─── making things ────────────────────────────────────────

    def make_dir(self, parts: Parts, mode: int = 0, mtime: Optional[float] = None) -> None:
        existed = parts in self._fds or self.lstat(parts) is not None
        fd = self.dir_fd(parts, create=True)
        if not existed:
            try:
                os.fchmod(fd, self.folder_mode(mode))
            except OSError:
                pass
        if mtime is not None:
            self.dir_times[parts] = mtime

    def remove(self, parts: Parts) -> None:
        """Delete a file or link that is in the way (never a folder)."""
        parent = self.dir_fd(parts[:-1], create=False)
        os.unlink(parts[-1], dir_fd=parent)

    def _temp_name(self) -> str:
        return f'.spark-part-{secrets.token_hex(6)}'

    def _commit(self, parent: int, tmp: str, name: str, parts: Parts, replace: bool,
                kind: str) -> None:
        """Move the finished temporary file into place. Without `replace`, never over anything
        that appeared in the meantime."""
        if replace:
            had = self._exists_at(parent, name)
            os.rename(tmp, name, src_dir_fd=parent, dst_dir_fd=parent)
            if had:
                self.replaced += 1
            else:
                self.created.append((parts, kind))
            return
        try:
            os.link(tmp, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        except FileExistsError:
            os.unlink(tmp, dir_fd=parent)
            raise
        except OSError as exc:
            if exc.errno not in (errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.EXDEV,
                                 errno.EMLINK, errno.ENOSYS, errno.EACCES):
                raise
            # a filesystem without hard links (FAT, exFAT): a plain rename, after one last look
            if self._exists_at(parent, name):
                os.unlink(tmp, dir_fd=parent)
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), name) from None
            os.rename(tmp, name, src_dir_fd=parent, dst_dir_fd=parent)
        else:
            os.unlink(tmp, dir_fd=parent)
        self.created.append((parts, kind))

    @staticmethod
    def _exists_at(parent: int, name: str) -> bool:
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def write_file(self, parts: Parts, source, mode: int = 0, mtime: Optional[float] = None,
                   replace: bool = False, on_bytes: Callable[[int], None] = lambda n: None,
                   cancelled: Callable[[], bool] = lambda: False) -> int:
        """Copy `source` (anything with read(n)) to root/parts. Returns the bytes written."""
        parent = self.dir_fd(parts[:-1], create=True)
        name = parts[-1]
        if self._is_dir_at(parent, name):
            raise IsADirectoryError(errno.EISDIR, "a folder with this name is in the way", name)
        tmp = self._temp_name()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | \
            getattr(os, 'O_CLOEXEC', 0)
        fd = os.open(tmp, flags, 0o600, dir_fd=parent)
        written = 0
        try:
            with os.fdopen(fd, 'wb', buffering=0) as out:
                while True:
                    if cancelled():
                        raise Cancelled()
                    block = source.read(CHUNK)
                    if not block:
                        break
                    view = memoryview(block)
                    while view:
                        n = out.write(view)
                        view = view[n:]
                    written += len(block)
                    on_bytes(len(block))
                os.fchmod(out.fileno(), self.file_mode(mode))
                if mtime is not None:
                    try:
                        os.utime(out.fileno(), (mtime, mtime))
                    except (OSError, OverflowError, ValueError):
                        pass
            self._commit(parent, tmp, name, parts, replace, FILE)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=parent)
            except OSError:
                pass
            raise
        self.files[parts] = True
        return written

    def move_in(self, parts: Parts, staged: str, mode: int = 0, replace: bool = False) -> int:
        """Move a file another tool unpacked (in a staging folder on the same disk) into place.
        Only a regular file is accepted."""
        st = os.lstat(staged)
        if not stat.S_ISREG(st.st_mode):
            raise Blocked(errno.EINVAL, "not a regular file")
        if st.st_nlink > 1:
            # a hard link the tool made, possibly to a file outside: copy it, never move the
            # link itself in
            fd = os.open(staged, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as src:
                return self.write_file(parts, src, mode or st.st_mode, st.st_mtime, replace)
        parent = self.dir_fd(parts[:-1], create=True)
        name = parts[-1]
        if self._is_dir_at(parent, name):
            raise IsADirectoryError(errno.EISDIR, "a folder with this name is in the way", name)
        tmp = self._temp_name()
        os.rename(staged, tmp, dst_dir_fd=parent)
        try:
            fd = os.open(tmp, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0), dir_fd=parent)
            try:
                os.fchmod(fd, self.file_mode(mode or st.st_mode))
            finally:
                os.close(fd)
            self._commit(parent, tmp, name, parts, replace, FILE)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=parent)
            except OSError:
                pass
            raise
        self.files[parts] = True
        return st.st_size

    def make_symlink(self, parts: Parts, target: str, replace: bool = False) -> None:
        if not link_target_ok(parts, target):
            raise Blocked(errno.EPERM, f"link leads outside the folder: {target}")
        parent = self.dir_fd(parts[:-1], create=True)
        name = parts[-1]
        if self._is_dir_at(parent, name):
            raise IsADirectoryError(errno.EISDIR, "a folder with this name is in the way", name)
        if replace:
            tmp = self._temp_name()
            os.symlink(target, tmp, dir_fd=parent)
            had = self._exists_at(parent, name)
            try:
                os.rename(tmp, name, src_dir_fd=parent, dst_dir_fd=parent)
            except BaseException:
                os.unlink(tmp, dir_fd=parent)
                raise
            if had:
                self.replaced += 1
            else:
                self.created.append((parts, LINK))
        else:
            os.symlink(target, name, dir_fd=parent)
            self.created.append((parts, LINK))
        self.links.append(parts)

    def make_hardlink(self, parts: Parts, target: Parts, replace: bool = False) -> None:
        """A hard link to a file this extraction wrote; a copy if the disk can't link."""
        if target not in self.files:
            raise Blocked(errno.EPERM, "hard link to a file that isn't in this extraction")
        src_parent = self.dir_fd(target[:-1], create=False)
        parent = self.dir_fd(parts[:-1], create=True)
        name = parts[-1]
        if self._is_dir_at(parent, name):
            raise IsADirectoryError(errno.EISDIR, "a folder with this name is in the way", name)
        tmp = self._temp_name()
        try:
            os.link(target[-1], tmp, src_dir_fd=src_parent, dst_dir_fd=parent,
                    follow_symlinks=False)
        except OSError as exc:
            if exc.errno in (errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.EXDEV,
                             errno.EMLINK, errno.ENOSYS, errno.EACCES):
                fd = os.open(target[-1], os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0),
                             dir_fd=src_parent)
                with os.fdopen(fd, 'rb') as src:
                    self.write_file(parts, src, mode=os.fstat(src.fileno()).st_mode,
                                    replace=replace)
                return
            raise
        try:
            self._commit(parent, tmp, name, parts, replace, FILE)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=parent)
            except OSError:
                pass
            raise
        self.files[parts] = True

    @staticmethod
    def _is_dir_at(parent: int, name: str) -> bool:
        try:
            return stat.S_ISDIR(os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode)
        except FileNotFoundError:
            return False

    # ─── the end ──────────────────────────────────────────────

    def inside(self, path: str) -> bool:
        return path == self.root or path.startswith(self.root.rstrip('/') + '/')

    def finish(self) -> List[str]:
        """Check every link made, resolved for real, and remove any that lead out. Then give
        folders their times from the archive. Returns the links removed."""
        for parts in self.links:
            full = os.path.join(self.root, *parts)
            if not self.inside(os.path.realpath(full)):
                try:
                    self.remove(parts)
                    self.removed_links.append('/'.join(parts))
                except OSError:
                    pass
        for parts, mtime in sorted(self.dir_times.items(), key=lambda kv: -len(kv[0])):
            try:
                fd = self.dir_fd(parts, create=False)
                os.utime(fd, (mtime, mtime))
            except (OSError, OverflowError, ValueError):
                pass
        self.close()
        return self.removed_links

    def undo(self) -> None:
        """Cancel: remove every file, link and folder this run created (newest first).
        Files it replaced stay replaced: they were whole when they went in."""
        self._forget_fds()
        for parts, kind in reversed(self.created):
            try:
                parent = self.dir_fd(parts[:-1], create=False)
                if kind == DIR:
                    gone = [p for p in self._fds if p[:len(parts)] == parts]
                    for p in gone:
                        os.close(self._fds.pop(p))
                    os.rmdir(parts[-1], dir_fd=parent)
                else:
                    os.unlink(parts[-1], dir_fd=parent)
            except OSError:
                pass
        self.created.clear()
        self.close()
