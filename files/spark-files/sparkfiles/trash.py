"""The Trash, the freedesktop way (the same folders other desktops use), so things
trashed here can be restored there and the other way round.

Files in your home go to ~/.local/share/Trash. Files on another drive (a Windows drive under
/var/mnt, a USB stick) go to that drive's own .Trash-<uid> folder, so trashing never copies
gigabytes across drives. If a drive can't hold a trash folder (read-only, or no permission),
trash() raises NoTrash and the window offers to delete for good instead."""

import datetime
import os
import shutil
import stat
from typing import Iterator, List, Optional, Tuple
from urllib.parse import quote, unquote

from .core import data_home


class NoTrash(OSError):
    pass


class Trashed:
    """One item in a trash folder."""

    __slots__ = ('path', 'info', 'original', 'deleted')

    def __init__(self, path: str, info: str, original: str, deleted: str):
        self.path, self.info, self.original, self.deleted = path, info, original, deleted

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


def home_trash() -> str:
    return os.path.join(data_home(), 'Trash')


def _mount_point(path: str) -> str:
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def _ensure(trash_dir: str) -> None:
    for sub in ('files', 'info'):
        os.makedirs(os.path.join(trash_dir, sub), mode=0o700, exist_ok=True)


def _topdir_trash(topdir: str, create: bool = True) -> Optional[str]:
    """$topdir/.Trash/$uid when the admin made a shared one (sticky, not a link), else
    $topdir/.Trash-$uid."""
    uid = os.getuid()
    shared = os.path.join(topdir, '.Trash')
    try:
        st = os.lstat(shared)
        if stat.S_ISDIR(st.st_mode) and st.st_mode & stat.S_ISVTX:
            own = os.path.join(shared, str(uid))
            if create:
                _ensure(own)
            if os.path.isdir(own):
                return own
    except OSError:
        pass
    own = os.path.join(topdir, f'.Trash-{uid}')
    try:
        if create:
            _ensure(own)
        if os.path.isdir(own):
            st = os.lstat(own)
            if stat.S_ISDIR(st.st_mode) and st.st_uid == uid:
                return own
    except OSError:
        pass
    return None


def trash_for(path: str) -> Tuple[str, Optional[str]]:
    """(trash folder, topdir) for a path; topdir is None for the home trash, where the
    stored path is absolute."""
    home = home_trash()
    try:
        os.makedirs(home, mode=0o700, exist_ok=True)
        home_dev = os.stat(home).st_dev
    except OSError:
        home_dev = None
    try:
        dev = os.lstat(path).st_dev
    except OSError:
        raise
    if home_dev is not None and dev == home_dev:
        return home, None
    topdir = _mount_point(os.path.dirname(os.path.abspath(path)))
    found = _topdir_trash(topdir)
    if found is None:
        raise NoTrash(f"no trash folder on {topdir}")
    return found, topdir


def _info_text(stored: str) -> str:
    when = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    return f"[Trash Info]\nPath={quote(stored, safe='/')}\nDeletionDate={when}\n"


def trash(path: str) -> str:
    """Move path to its trash; returns where it went. Raises NoTrash, FileNotFoundError or
    another OSError."""
    path = os.path.abspath(path)
    os.lstat(path)                                       # FileNotFoundError when it's gone
    trash_dir, topdir = trash_for(path)
    _ensure(trash_dir)
    stored = path if topdir is None else os.path.relpath(path, topdir)
    if topdir is not None and stored.startswith('..'):
        stored = path
    name = os.path.basename(path)
    info_dir, files_dir = os.path.join(trash_dir, 'info'), os.path.join(trash_dir, 'files')
    base, n = name, 1
    while True:
        info_path = os.path.join(info_dir, base + '.trashinfo')
        try:
            fd = os.open(info_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            n += 1
            stem, dot, ext = name.rpartition('.')
            base = f"{stem}.{n}.{ext}" if dot and stem else f"{name}.{n}"
            continue
        except OSError as exc:
            raise NoTrash(str(exc)) from exc
        if os.path.lexists(os.path.join(files_dir, base)):
            os.close(fd)
            os.unlink(info_path)
            n += 1
            stem, dot, ext = name.rpartition('.')
            base = f"{stem}.{n}.{ext}" if dot and stem else f"{name}.{n}"
            continue
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(_info_text(stored))
        break
    target = os.path.join(files_dir, base)
    try:
        os.rename(path, target)
    except OSError as exc:
        os.unlink(info_path)
        if exc.errno == 18:                              # EXDEV: shouldn't happen, but be safe
            raise NoTrash(str(exc)) from exc
        raise
    return target


def all_trash_dirs() -> List[str]:
    """The home trash and every mounted drive's trash that exists for this user."""
    out = []
    home = home_trash()
    if os.path.isdir(home):
        out.append(home)
    for mount in mount_points():
        found = _topdir_trash(mount, create=False)
        if found and found not in out:
            out.append(found)
    return out


def mount_points() -> List[str]:
    out = []
    try:
        with open('/proc/self/mounts', encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                target = parts[1].replace('\\040', ' ').replace('\\011', '\t')
                if parts[2] in ('proc', 'sysfs', 'devtmpfs', 'devpts', 'cgroup2', 'cgroup',
                                'securityfs', 'pstore', 'bpf', 'tracefs', 'debugfs',
                                'mqueue', 'hugetlbfs', 'configfs', 'fusectl', 'autofs',
                                'binfmt_misc', 'efivarfs', 'overlay', 'squashfs', 'nsfs',
                                'ramfs', 'composefs', 'erofs'):
                    continue
                if target.startswith(('/proc', '/sys', '/dev', '/run/user', '/sysroot',
                                      '/boot')):
                    continue
                out.append(target)
    except OSError:
        pass
    return out


def _parse_info(info_path: str) -> Tuple[Optional[str], str]:
    path, when = None, ''
    try:
        with open(info_path, encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('Path='):
                    path = unquote(line[5:].rstrip('\n'))
                elif line.startswith('DeletionDate='):
                    when = line[13:].strip()
    except OSError:
        pass
    return path, when


def _topdir_of(trash_dir: str) -> Optional[str]:
    if os.path.abspath(trash_dir) == os.path.abspath(home_trash()):
        return None
    parent = os.path.dirname(trash_dir)
    if os.path.basename(parent) == '.Trash':
        return os.path.dirname(parent)
    return parent


def items() -> Iterator[Trashed]:
    for trash_dir in all_trash_dirs():
        files_dir = os.path.join(trash_dir, 'files')
        info_dir = os.path.join(trash_dir, 'info')
        topdir = _topdir_of(trash_dir)
        try:
            names = os.listdir(files_dir)
        except OSError:
            continue
        for name in names:
            info = os.path.join(info_dir, name + '.trashinfo')
            stored, when = _parse_info(info)
            if stored is None:
                original = ''
            elif os.path.isabs(stored) or topdir is None:
                original = stored
            else:
                original = os.path.join(topdir, stored)
            yield Trashed(os.path.join(files_dir, name), info, original, when)


def is_trash_path(path: str) -> bool:
    """True for paths inside one of the trash 'files' folders."""
    path = os.path.abspath(path)
    for trash_dir in all_trash_dirs():
        files_dir = os.path.join(trash_dir, 'files')
        if path.startswith(files_dir + os.sep):
            return True
    return False


def info_for(item: str) -> Optional[str]:
    files_dir = os.path.dirname(item)
    if os.path.basename(files_dir) != 'files':
        return None
    return os.path.join(os.path.dirname(files_dir), 'info', os.path.basename(item) + '.trashinfo')


def original_path(item: str) -> Optional[str]:
    info = info_for(item)
    if not info:
        return None
    stored, _ = _parse_info(info)
    if stored is None:
        return None
    if os.path.isabs(stored):
        return stored
    topdir = _topdir_of(os.path.dirname(os.path.dirname(item)))
    return os.path.join(topdir, stored) if topdir else stored


def restore(item: str, target: str) -> None:
    info = info_for(item)
    os.rename(item, target)
    if info:
        try:
            os.unlink(info)
        except OSError:
            pass


def delete_item(item: str) -> None:
    info = info_for(item)
    if os.path.isdir(item) and not os.path.islink(item):
        shutil.rmtree(item)
    else:
        os.unlink(item)
    if info:
        try:
            os.unlink(info)
        except OSError:
            pass


def count() -> int:
    n = 0
    for trash_dir in all_trash_dirs():
        try:
            n += len(os.listdir(os.path.join(trash_dir, 'files')))
        except OSError:
            pass
    return n


def empty() -> List[Tuple[str, str]]:
    """Delete everything in every trash; returns (path, why) for what couldn't go."""
    errors = []
    for item in list(items()):
        try:
            delete_item(item.path)
        except OSError as exc:
            errors.append((item.path, exc.strerror or str(exc)))
    for trash_dir in all_trash_dirs():                  # orphan .trashinfo files
        info_dir = os.path.join(trash_dir, 'info')
        try:
            for name in os.listdir(info_dir):
                if not os.path.lexists(os.path.join(trash_dir, 'files', name[:-10])):
                    os.unlink(os.path.join(info_dir, name))
        except OSError:
            pass
        try:
            os.unlink(os.path.join(trash_dir, 'directorysizes'))
        except OSError:
            pass
    return errors
