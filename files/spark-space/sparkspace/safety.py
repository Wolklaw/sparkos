"""When Spark Space refuses to move something to the Trash.

Spark Space never deletes anything for good. Moving to the Trash is refused:
- anywhere on the D: drive (/var/mnt/d, or whatever SparkOS reports as D:): the owner's rule,
  it is never touched, read-only or not;
- on a read-only mount (the mount or its filesystem);
- when the folder holding it isn't writable for you (that's also where the Trash would fail);
- for the scan's top folder, your home, a mount point, or the system's own top folders;
- for something already in a trash folder;
- for Windows' own folders on a Windows drive (Windows, Program Files, ProgramData, the page
  and hibernation files...): trashing those from Linux breaks Windows.
"""

import os
from typing import Iterable, List, Optional

from . import drives
from .core import data_home, home

# never offered, wherever they are
PROTECTED_DIRS = frozenset(('/', '/var', '/var/home', '/home', '/usr', '/etc', '/boot', '/opt',
                            '/root', '/srv', '/var/mnt', '/mnt', '/media', '/run', '/tmp',
                            '/proc', '/sys', '/dev', '/sysroot', '/ostree'))
NEVER_DRIVE_LETTERS = ('d',)
# top-level names on a Windows drive that Windows needs (compared lower-case)
WINDOWS_SYSTEM = frozenset(('windows', 'program files', 'program files (x86)', 'programdata',
                            'pagefile.sys', 'hiberfil.sys', 'swapfile.sys', 'dumpstack.log.tmp',
                            'system volume information', '$recycle.bin', 'recovery', 'boot',
                            'bootmgr', 'efi', '$winreagent', '$windows.~bt', '$windows.~ws',
                            'config.msi', 'msocache', 'documents and settings'))
NEVER_DRIVE_PATHS = ('/var/mnt/d', '/mnt/d')


def _real(path: str) -> str:
    """The path with its folders resolved but not the last part: trashing a symlink moves the
    link, so the link itself is what's judged."""
    path = os.path.abspath(path)
    return os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))


def _inside(path: str, folder: str) -> bool:
    folder = folder.rstrip('/') or '/'
    return path == folder or path.startswith(folder.rstrip('/') + '/')


def never_paths(windows: Optional[List[dict]] = None) -> List[str]:
    """The folders that are never touched: /var/mnt/d and wherever SparkOS mounted D:."""
    out = list(NEVER_DRIVE_PATHS)
    for w in drives.windows_drives() if windows is None else windows:
        if str(w.get('letter', '')).lower() in NEVER_DRIVE_LETTERS and w.get('mountpoint'):
            out.append(os.path.normpath(w['mountpoint']))
    for p in list(out):
        real = os.path.realpath(p)
        if real not in out:
            out.append(real)
    return out


def trash_refusal(path: str, scan_root: Optional[str] = None,
                  table: Optional[List[drives.Mount]] = None,
                  windows: Optional[List[dict]] = None,
                  extra_never: Iterable[str] = ()) -> Optional[str]:
    """None when path may be moved to the Trash, else the key of the reason (text.py
    'refuse.<key>')."""
    real = _real(path)
    for p in list(never_paths(windows)) + list(extra_never):
        if _inside(real, p) or _inside(os.path.abspath(path), p):
            return 'd_drive'
    table = drives.mounts() if table is None else table
    targets = {m.target for m in table}
    h = os.path.realpath(home())
    if real in PROTECTED_DIRS or real == h or real in targets or \
            (scan_root and real == os.path.realpath(scan_root)):
        return 'protected'
    if _inside(real, os.path.join(os.path.realpath(data_home()), 'Trash')) or \
            any(part.startswith('.Trash') for part in real.split('/')):
        return 'in_trash'
    mount = drives.mount_of(real, table)
    if mount is not None and mount.read_only:
        return 'read_only'
    if mount is not None and mount.fstype in ('ntfs3', 'ntfs', 'fuseblk') and real != mount.target:
        top = real[len(mount.target.rstrip('/')) + 1:].split('/', 1)[0]
        if top.lower() in WINDOWS_SYSTEM:
            return 'windows_system'
    parent = os.path.dirname(real)
    try:
        if os.statvfs(parent).f_flag & os.ST_RDONLY:
            return 'read_only'
    except OSError:
        return 'gone'
    if not os.path.lexists(real):
        return 'gone'
    if not os.access(parent, os.W_OK | os.X_OK):
        return 'not_writable'
    return None


class Refused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def move_to_trash(path: str, **kw) -> str:
    """The only way Spark Space removes anything: checks trash_refusal() again right before
    moving, then moves to the freedesktop Trash. Returns where it went. Raises Refused,
    trash.NoTrash or OSError."""
    from . import trash
    reason = trash_refusal(path, **kw)
    if reason is not None:
        raise Refused(reason)
    return trash.trash(path)
