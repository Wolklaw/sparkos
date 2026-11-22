"""The mounted filesystems, how full they are, and the Windows drives SparkOS mounts at
/var/mnt/<letter> (with their status from /run/sparkos/windows-drives.json)."""

import json
import os
import re
from typing import Dict, List, Optional

from .core import home

WINDOWS_STATE = os.environ.get('SPARKOS_WINDOWS_DRIVES_STATE',
                               '/run/sparkos/windows-drives.json')
MOUNTINFO = '/proc/self/mountinfo'

# filesystems that hold files on a disk; everything else (proc, tmpfs, overlay, composefs for
# SparkOS's read-only system image...) isn't shown as a drive
DISK_FS = {'btrfs', 'ext4', 'ext3', 'ext2', 'xfs', 'ntfs3', 'ntfs', 'fuseblk', 'vfat', 'exfat',
           'f2fs', 'bcachefs', 'jfs', 'reiserfs', 'zfs', 'hfsplus', 'udf', 'iso9660'}
HIDDEN_TARGETS = ('/boot', '/sysroot', '/etc', '/usr', '/ostree')


def _unescape(text: str) -> str:
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), text)


class Mount:
    __slots__ = ('target', 'fstype', 'source', 'read_only', 'root')

    def __init__(self, target: str, fstype: str, source: str, read_only: bool, root: str = '/'):
        self.target, self.fstype, self.source = target, fstype, source
        self.read_only, self.root = read_only, root

    def __repr__(self) -> str:
        return f"Mount({self.target!r}, {self.fstype!r}, ro={self.read_only})"


def mounts(path: str = MOUNTINFO) -> List[Mount]:
    """Every mount, from /proc/self/mountinfo. read_only is true when either the mount or the
    filesystem itself is read-only."""
    out = []
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        left, sep, right = line.partition(' - ')
        if not sep:
            continue
        a, b = left.split(), right.split()
        if len(a) < 6 or len(b) < 2:
            continue
        options = set(a[5].split(','))
        super_options = set(b[2].split(',')) if len(b) > 2 else set()
        out.append(Mount(_unescape(a[4]), b[0], _unescape(b[1]),
                         'ro' in options or 'ro' in super_options, _unescape(a[3])))
    return out


def mount_targets(table: Optional[List[Mount]] = None) -> set:
    return {m.target for m in (mounts() if table is None else table)}


def mount_of(path: str, table: Optional[List[Mount]] = None) -> Optional[Mount]:
    """The mount a path is on: the longest mount target that contains it."""
    table = mounts() if table is None else table
    best = None
    for m in table:
        t = m.target.rstrip('/') or '/'
        if path == t or path.startswith(t.rstrip('/') + '/') or t == '/':
            if best is None or len(t) >= len(best.target.rstrip('/') or '/'):
                best = m
    return best


def windows_drives(path: Optional[str] = None) -> List[Dict]:
    """The entries of /run/sparkos/windows-drives.json: letter, label, device, mountpoint,
    mode (rw, ro or off) and problem. Empty when the file isn't there (not SparkOS, or no
    Windows drives)."""
    try:
        with open(path or WINDOWS_STATE, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and isinstance(item.get('letter'), str):
            out.append(item)
    return out


def _labels() -> Dict[str, str]:
    out = {}
    folder = '/dev/disk/by-label'
    try:
        for name in os.listdir(folder):
            target = os.path.realpath(os.path.join(folder, name))
            out[target] = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)),
                                 name)
    except OSError:
        pass
    return out


class Drive:
    """One thing the start screen shows a bar for."""

    __slots__ = ('path', 'label', 'fstype', 'source', 'read_only', 'letter', 'mode', 'problem',
                 'total', 'free', 'used', 'is_home', 'mounted')

    def __init__(self, path: str, label: str, fstype: str = '', source: str = '',
                 read_only: bool = False, letter: str = '', mode: str = '', problem: str = '',
                 mounted: bool = True):
        self.path, self.label, self.fstype, self.source = path, label, fstype, source
        self.read_only, self.letter, self.mode, self.problem = read_only, letter, mode, problem
        self.mounted = mounted
        self.total = self.free = self.used = None
        self.is_home = False

    def measure(self) -> None:
        """Fill total/free/used from statvfs. Free is what you can use (f_bavail); used is what
        the filesystem reports, which on btrfs counts compression, snapshots and shared copies
        its own way."""
        try:
            st = os.statvfs(self.path)
        except OSError:
            return
        self.total = st.f_blocks * st.f_frsize
        self.free = st.f_bavail * st.f_frsize
        self.used = max(0, self.total - st.f_bfree * st.f_frsize)

    def __repr__(self) -> str:
        return f"Drive({self.path!r}, {self.label!r})"


def list_drives(table: Optional[List[Mount]] = None,
                windows: Optional[List[Dict]] = None) -> List[Drive]:
    """The disks worth showing, one entry per device (btrfs mounts /var and /var/home from the
    same partition: that's one drive). Sizes aren't measured here (statvfs on a sleeping disk
    can take a moment); call measure() off the window's thread."""
    table = mounts() if table is None else table
    windows = windows_drives() if windows is None else windows
    by_mount = {os.path.normpath(w.get('mountpoint') or ''): w for w in windows}
    labels = _labels()
    h = os.path.realpath(home())
    seen: Dict[str, Drive] = {}
    order: List[str] = []
    for m in table:
        if m.fstype not in DISK_FS:
            continue
        if any(m.target == p or m.target.startswith(p + '/') for p in HIDDEN_TARGETS):
            continue
        if m.target.startswith(('/proc', '/sys', '/dev', '/run/user', '/var/lib/containers',
                                '/var/lib/docker')):
            continue
        key = m.source if m.source.startswith('/dev/') else m.target
        win = by_mount.get(os.path.normpath(m.target))
        if key in seen:
            drive = seen[key]
            if len(m.target) < len(drive.path):        # /var rather than /var/home
                drive.path, drive.read_only = m.target, m.read_only
            continue
        if win:
            letter = str(win.get('letter', '')).upper()
            label = win.get('label') or ''
            drive = Drive(m.target, label, m.fstype, m.source, m.read_only, letter,
                          win.get('mode', ''), win.get('problem', ''))
        else:
            label = labels.get(os.path.realpath(m.source), '') if m.source.startswith('/dev/') \
                else ''
            drive = Drive(m.target, label, m.fstype, m.source, m.read_only)
        seen[key] = drive
        order.append(key)
    out = [seen[k] for k in order]
    for d in out:
        d.is_home = h == d.path or h.startswith(d.path.rstrip('/') + '/')
    # Windows drives SparkOS found but couldn't mount ("off") still get a line, with why
    mounted_paths = {os.path.normpath(d.path) for d in out}
    for w in windows:
        mp = os.path.normpath(w.get('mountpoint') or '')
        if mp and mp not in mounted_paths and w.get('mode') == 'off':
            out.append(Drive(mp, w.get('label') or '', letter=str(w.get('letter', '')).upper(),
                             mode='off', problem=w.get('problem') or '', mounted=False))
    out.sort(key=lambda d: (0 if d.is_home else 1, d.letter or 'ZZ', d.path))
    return out
