"""Looking inside a snapshot and getting things back. Runs as the user: a snapshot keeps the
owners and permissions of the day it was taken, so you can read your own files and nobody
else's. Nothing here writes inside a snapshot, and nothing ever overwrites a file."""

import datetime as dt
import os
import shutil
import stat
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from . import SOURCE
from .btrfs import parse_name


class BrowseError(Exception):
    pass


@dataclass
class Snap:
    name: str
    when: dt.datetime
    local: bool = False
    copy: bool = False


@dataclass
class Entry:
    name: str
    is_dir: bool
    is_link: bool
    size: int
    mtime: float


@dataclass
class Restored:
    path: str
    errors: List[str]


def snapshots(local: Iterable[str], copies: Iterable[str]) -> List[Snap]:
    """Every snapshot, newest first, with where it is."""
    local, copies = set(local), set(copies)
    out = []
    for name in sorted(local | copies, reverse=True):
        when = parse_name(name)
        if when is not None:
            out.append(Snap(name, when, name in local, name in copies))
    return out


def label(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M")


def clean_rel(rel: str) -> str:
    """A path inside a snapshot, without a leading slash, '.', or '..'."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise BrowseError("a path can't go up")
    return "/".join(parts)


def inside(root: str, rel: str) -> str:
    """The real path of `rel` in `root`, refusing a symlink on the way (a link inside a
    snapshot could point out of it, at the live system)."""
    rel = clean_rel(rel)
    parts = rel.split("/") if rel else []
    here = root
    for i, part in enumerate(parts):
        here = os.path.join(here, part)
        if os.path.islink(here) and i < len(parts) - 1:
            raise BrowseError("a link can't be followed")
    return here


def entries(root: str, rel: str = "") -> List[Entry]:
    """The folder `rel` of a snapshot, folders first. A symlink is listed as a file and is
    never followed."""
    path = inside(root, rel)
    if os.path.islink(path) or not os.path.isdir(path):
        raise BrowseError("not a folder")
    out = []
    try:
        names = os.listdir(path)
    except OSError as exc:
        raise BrowseError(exc.strerror or str(exc)) from exc
    for name in names:
        try:
            info = os.lstat(os.path.join(path, name))
        except OSError:
            continue
        link = stat.S_ISLNK(info.st_mode)
        isdir = stat.S_ISDIR(info.st_mode)
        if not (link or isdir or stat.S_ISREG(info.st_mode)):
            continue                              # sockets, devices
        out.append(Entry(name, isdir, link, 0 if isdir else info.st_size, info.st_mtime))
    return sorted(out, key=lambda e: (not e.is_dir, e.name.lower()))


def _unique(parent: str, name: str) -> str:
    base, ext = os.path.splitext(name) if not os.path.isdir(os.path.join(parent, name)) \
        else (name, "")
    path, n = os.path.join(parent, name), 1
    while os.path.lexists(path):
        n += 1
        path = os.path.join(parent, f"{base} ({n}){ext}")
    return path


def _skip_special(_folder: str, names: List[str]) -> List[str]:
    out = []
    for name in names:
        try:
            mode = os.lstat(os.path.join(_folder, name)).st_mode
        except OSError:
            continue
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
            out.append(name)
    return out


def _copy(src: str, dest: str) -> List[str]:
    errors: List[str] = []
    if os.path.islink(src) or not os.path.isdir(src):
        try:
            shutil.copy2(src, dest, follow_symlinks=False)
        except OSError as exc:
            errors.append(f"{src}: {exc.strerror or exc}")
        return errors
    try:
        shutil.copytree(src, dest, symlinks=True, ignore_dangling_symlinks=True,
                        ignore=_skip_special, copy_function=shutil.copy2)
    except shutil.Error as exc:
        for item in exc.args[0]:
            errors.append(f"{item[0]}: {item[2]}")
    except OSError as exc:
        errors.append(f"{src}: {exc.strerror or exc}")
    return errors


def restore(root: str, rel: str, dest_parent: str, when: dt.datetime,
            beside: bool = False, now: Optional[Callable[[], dt.datetime]] = None) -> Restored:
    """Copy `rel` out of the snapshot into the folder `dest_parent`. With `beside`, the name is
    marked 'restored from <snapshot time>' so it sits next to the live file without touching
    it. Either way an existing name is never replaced: a number is added instead."""
    rel = clean_rel(rel)
    if not rel:
        raise BrowseError("choose a file or a folder first")
    src = inside(root, rel)
    if not os.path.lexists(src):
        raise BrowseError("it is not in this snapshot")
    name = os.path.basename(rel)
    if beside:
        stem, ext = os.path.splitext(name) if not os.path.isdir(src) or os.path.islink(src) \
            else (name, "")
        name = f"{stem} (restored {label(when)}){ext}"
    try:
        os.makedirs(dest_parent, exist_ok=True)
    except OSError as exc:
        raise BrowseError(f"{dest_parent}: {exc.strerror or exc}") from exc
    dest = _unique(dest_parent, name)
    errors = _copy(src, dest)
    if not os.path.lexists(dest):
        raise BrowseError(errors[0] if errors else "nothing was copied")
    return Restored(dest, errors)


def original_parent(rel: str, source: str = SOURCE) -> str:
    """Where `rel` lives on the running system: the same path under /home."""
    return os.path.dirname(os.path.join(source, clean_rel(rel)))

