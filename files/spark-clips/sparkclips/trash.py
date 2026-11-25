"""The Trash, the freedesktop way (the same folders Dolphin, Plasma and GNOME use), so things
trashed here can be restored there and the other way round.

Files in your home go to ~/.local/share/Trash. Files on another drive (a Windows drive under
/var/mnt, a USB stick) go to that drive's own .Trash-<uid> folder, so trashing never copies
gigabytes across drives. If a drive can't hold a trash folder (read-only, or no permission),
trash() raises NoTrash and Spark Clips says it can't be trashed. Spark Clips never deletes for
good, so this file has no delete or empty functions.

Copied from Spark Files (files/spark-files/sparkfiles/trash.py, the part up to trash()); keep
the two in step."""

import datetime
import os
import stat
from typing import Optional, Tuple
from urllib.parse import quote

from .core import data_home


class NoTrash(OSError):
    pass


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
