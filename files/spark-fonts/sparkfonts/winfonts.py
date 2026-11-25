"""Fonts on a Windows drive: find the partition, mount it read-only, list its font folders.

The partition finding and the read-only mount are copied from Spark Welcome
(files/spark-welcome/sparkwelcome/windows.py), which this app can't import (each Spark app
stands alone, and live updates ship them separately). Copy only: nothing here opens a file on
the Windows disk for writing, and the disk is mounted with -o ro.

No window code."""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from . import fontfile
from .core import log, run

LSBLK_CMD = ['lsblk', '-J', '-b', '-o', 'NAME,PATH,FSTYPE,LABEL,MOUNTPOINT,SIZE,PARTUUID']
SYSTEM_FONTS = 'Fonts'                                        # under Windows
USER_FONTS = r'AppData\Local\Microsoft\Windows\Fonts'         # under Users\<name>
SKIP_USERS = {'public', 'default', 'default user', 'all users', 'defaultapppool',
              'wdagutilityaccount'}
MAX_FILES = 3000


@dataclass
class Partition:
    name: str
    path: str
    fstype: str
    label: str
    mountpoint: str
    size: int

    @property
    def locked(self) -> bool:
        return self.fstype.lower() == 'bitlocker'


def parse_lsblk(text: str) -> List[Partition]:
    """NTFS (and BitLocker-locked) partitions from `lsblk -J`, in disk order."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    found: List[Partition] = []

    def walk(devices):
        for dev in devices or []:
            if not isinstance(dev, dict):
                continue
            fstype = (dev.get('fstype') or '').strip()
            if fstype.lower() in ('ntfs', 'ntfs3', 'bitlocker'):
                name = dev.get('name') or ''
                try:
                    size = int(dev.get('size') or 0)
                except (TypeError, ValueError):
                    size = 0
                found.append(Partition(name, dev.get('path') or f'/dev/{name}', fstype,
                                       (dev.get('label') or '').strip(),
                                       (dev.get('mountpoint') or '').strip(), size))
            walk(dev.get('children'))

    walk(data.get('blockdevices') if isinstance(data, dict) else None)
    return found


def list_partitions() -> Tuple[List[Partition], str]:
    code, out, err = run(LSBLK_CMD, timeout=10)
    if code != 0:
        return [], err.strip() or f"lsblk failed ({code})"
    return parse_lsblk(out), ''


_MOUNTED = re.compile(r'Mounted \S+ at (.+?)\.?\s*$', re.M)


def explain_mount_error(text: str) -> str:
    """A key: hibernated, password, bitlocker or generic."""
    low = text.lower()
    if any(word in low for word in ('unclean', 'dirty', 'hibernat', 'fast startup')):
        return 'hibernated'
    if 'not authorized' in low or 'notauthorized' in low or 'dismissed' in low:
        return 'password'
    if 'bitlocker' in low:
        return 'bitlocker'
    return 'generic'


def mount_read_only(part: Partition) -> Tuple[Optional[str], str]:
    """(mount point, problem key). Uses the existing mount point when it's already mounted.
    udisksctl may ask for the password through the desktop's dialog."""
    if part.mountpoint:
        return part.mountpoint, ''
    if part.locked:
        return None, 'bitlocker'
    code, out, err = run(['udisksctl', 'mount', '-b', part.path, '-o', 'ro'], timeout=180)
    if code == 0:
        match = _MOUNTED.search(out)
        point = match.group(1).strip() if match else None
        if point and os.path.isdir(point):
            log.info("mounted %s read-only at %s", part.path, point)
            part.mountpoint = point
            return point, ''
    log.warning("mount %s failed (%s): %s %s", part.path, code, out.strip(), err.strip())
    return None, explain_mount_error(err + '\n' + out)


def child(parent: Optional[str], wanted: str) -> Optional[str]:
    """parent/wanted, matching the name case-insensitively (NTFS isn't case-sensitive)."""
    if not parent:
        return None
    try:
        with os.scandir(parent) as entries:
            for entry in entries:
                if entry.name.lower() == wanted.lower() and entry.is_dir(follow_symlinks=False):
                    return entry.path
    except OSError:
        pass
    return None


def walk_ci(base: Optional[str], rest: str) -> Optional[str]:
    path = base
    for part in filter(None, re.split(r'[\\/]+', rest)):
        path = child(path, part)
        if path is None:
            return None
    return path


@dataclass
class Source:
    where: str            # as Windows shows it: C:\Windows\Fonts
    path: str             # here


def windows_sources(root: str) -> List[Source]:
    """The font folders of a Windows drive mounted at root: Windows\\Fonts, and each account's
    AppData\\Local\\Microsoft\\Windows\\Fonts. Empty when root has no Windows folder."""
    windows = child(root, 'Windows')
    if windows is None:
        return []
    out: List[Source] = []
    system = child(windows, SYSTEM_FONTS)
    if system:
        out.append(Source(r'C:\Windows\Fonts', system))
    users = child(root, 'Users')
    try:
        entries = sorted(os.scandir(users), key=lambda e: e.name.lower()) if users else []
    except OSError:
        entries = []
    for entry in entries:
        if entry.name.lower() in SKIP_USERS or entry.is_symlink() \
                or not entry.is_dir(follow_symlinks=False):
            continue
        folder = walk_ci(entry.path, USER_FONTS)
        if folder:
            out.append(Source(f"C:\\Users\\{entry.name}\\{USER_FONTS}", folder))
    return out


def find_all(on_problem: Optional[Callable[[str, str], None]] = None) -> Tuple[List[Source], str]:
    """(font folders of every Windows drive that has them, problem). Mounts NTFS partitions
    read-only as needed (the desktop may ask for your password). problem is a key from
    explain_mount_error, 'no_drive' when there are no NTFS partitions, 'no_fonts' when
    there are some but none held Windows, or '' when something was found."""
    parts, problem = list_partitions()
    if problem:
        return [], 'generic'
    if not parts:
        return [], 'no_drive'
    sources: List[Source] = []
    last = ''
    for part in parts:
        point, bad = mount_read_only(part)
        if bad:
            last = bad
            if on_problem:
                on_problem(part.path, bad)
            continue
        sources += windows_sources(point)
    if sources:
        return sources, ''
    return [], last or 'no_fonts'


@dataclass
class Found:
    path: str
    name: str
    where: str


def list_files(sources: List[Source]) -> List[Found]:
    """TrueType, OpenType and collection files in the folders (by content), name order."""
    out: List[Found] = []
    for src in sources:
        try:
            names = sorted(os.listdir(src.path), key=str.lower)
        except OSError:
            continue
        for name in names:
            full = os.path.join(src.path, name)
            if len(out) >= MAX_FILES:
                return out
            if os.path.isfile(full) and not os.path.islink(full) \
                    and fontfile.sniff(full) in fontfile.INSTALLABLE:
                out.append(Found(full, name, src.where))
    return out
