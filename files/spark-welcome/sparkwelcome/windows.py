"""Bring your files from Windows: find Windows partitions, mount them read-only, find the
Windows user folders with something in them, plan the copy and copy.

Copy, never move: nothing here opens a file on the Windows disk for writing, and the disk is
mounted read-only. No window code, so the Spark Portal can reuse it."""

import json
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from .core import log, run, xdg_user_dir
from .strings import t

LSBLK_CMD = ['lsblk', '-J', '-b', '-o', 'NAME,PATH,FSTYPE,LABEL,MOUNTPOINT,SIZE']

# Windows folder, xdg-user-dir key, SparkOS fallback folder
FOLDERS = (
    ('Desktop', 'DESKTOP', 'Desktop'),
    ('Documents', 'DOCUMENTS', 'Documents'),
    ('Pictures', 'PICTURES', 'Pictures'),
    ('Videos', 'VIDEOS', 'Videos'),
    ('Music', 'MUSIC', 'Music'),
    ('Downloads', 'DOWNLOAD', 'Downloads'),
)
# Not people: the shared and template profiles, and service accounts.
SKIP_USERS = {'public', 'default', 'default user', 'all users', 'defaultapppool',
              'wdagutilityaccount'}
# Windows' own clutter, never worth copying.
IGNORED = {'desktop.ini', 'thumbs.db', 'ehthumbs.db', '$recycle.bin'}
RENAMED = f" ({t('win.renamed')})"      # ' (from Windows)', ' (de Windows)'
CHUNK = 1024 * 1024


# ─── Partitions ───────────────────────────────────────────────

@dataclass
class Partition:
    name: str              # sda3
    path: str              # /dev/sda3
    fstype: str            # ntfs, or BitLocker
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
    """(partitions, problem). problem is '' when lsblk ran."""
    code, out, err = run(LSBLK_CMD, timeout=10)
    if code != 0:
        return [], err.strip() or f"lsblk failed ({code})"
    return parse_lsblk(out), ''


_MOUNTED = re.compile(r'Mounted \S+ at (.+?)\.?\s*$', re.M)


def parse_mount_output(text: str) -> Optional[str]:
    match = _MOUNTED.search(text)
    return match.group(1).strip() if match else None


def explain_mount_error(text: str) -> str:
    low = text.lower()
    if any(word in low for word in ('unclean', 'dirty', 'hibernat', 'fast startup')):
        return t('win.err.hibernated')
    if 'not authorized' in low or 'notauthorized' in low or 'dismissed' in low:
        return t('win.err.password')
    if 'bitlocker' in low:
        return t('win.err.bitlocker')
    line = next((ln for ln in reversed(text.strip().splitlines()) if ln.strip()), '')
    return f"{t('win.err.generic')} {line}".strip()


def mount_read_only(part: Partition) -> Tuple[Optional[str], str]:
    """(mount point, problem). Uses the existing mount point when it's already mounted.
    udisksctl may ask for the user's password through the desktop's dialog."""
    if part.mountpoint:
        return part.mountpoint, ''
    if part.locked:
        return None, explain_mount_error('bitlocker')
    code, out, err = run(['udisksctl', 'mount', '-b', part.path, '-o', 'ro'], timeout=180)
    if code == 0:
        point = parse_mount_output(out)
        if point and os.path.isdir(point):
            log.info("mounted %s read-only at %s", part.path, point)
            return point, ''
    log.warning("mount %s failed (%s): %s %s", part.path, code, out.strip(), err.strip())
    return None, explain_mount_error(err + '\n' + out)


# ─── Windows user folders ─────────────────────────────────────

def _child(parent: str, wanted: str) -> Optional[str]:
    """parent/wanted, matching the name case-insensitively (NTFS isn't case-sensitive)."""
    try:
        with os.scandir(parent) as entries:
            for entry in entries:
                if entry.name.lower() == wanted.lower() and entry.is_dir(follow_symlinks=False):
                    return entry.path
    except OSError:
        pass
    return None


def _skipped(entry: os.DirEntry) -> bool:
    return entry.name.lower() in IGNORED or entry.is_symlink()


def has_content(path: str) -> bool:
    """True when the folder holds at least one real file, at any depth. Junctions (seen as
    symlinks) and Windows' desktop.ini clutter don't count."""
    stack = [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if _skipped(entry):
                        continue
                    if entry.is_file(follow_symlinks=False):
                        return True
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
        except OSError:
            continue
    return False


@dataclass
class SourceFolder:
    key: str          # Documents
    path: str         # /run/media/.../Users/Ann/Documents
    xdg: str          # DOCUMENTS
    fallback: str     # Documents
    size: Optional[int] = None
    files: Optional[int] = None


@dataclass
class WindowsUser:
    name: str
    path: str
    folders: List[SourceFolder] = field(default_factory=list)


def find_users(root: str) -> List[WindowsUser]:
    """Windows accounts under root/Users that have at least one non-empty standard folder."""
    users_dir = _child(root, 'Users')
    if not users_dir:
        return []
    found = []
    try:
        entries = sorted(os.scandir(users_dir), key=lambda e: e.name.lower())
    except OSError:
        return []
    for entry in entries:
        if entry.name.lower() in SKIP_USERS or entry.is_symlink() \
                or not entry.is_dir(follow_symlinks=False):
            continue
        user = WindowsUser(entry.name, entry.path)
        for key, xdg, fallback in FOLDERS:
            path = _child(entry.path, key)
            if path and not os.path.islink(path) and has_content(path):
                user.folders.append(SourceFolder(key, path, xdg, fallback))
        if user.folders:
            found.append(user)
    return found


def measure(path: str, cancel: Optional[threading.Event] = None) -> Tuple[int, int]:
    """(bytes, files) under path, as the copy would see them."""
    total = count = 0
    stack = [path]
    while stack and not (cancel and cancel.is_set()):
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if _skipped(entry):
                        continue
                    if entry.is_file(follow_symlinks=False):
                        try:
                            total += entry.stat(follow_symlinks=False).st_size
                            count += 1
                        except OSError:
                            pass
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
        except OSError:
            continue
    return total, count


def destination(folder: SourceFolder) -> str:
    return xdg_user_dir(folder.xdg, folder.fallback)


# ─── Copy plan ────────────────────────────────────────────────

COPY, SKIP = 'copy', 'skip'


@dataclass
class CopyItem:
    src: str
    dst: str
    size: int
    action: str              # COPY or SKIP (already there with the same size)
    renamed: bool = False    # a different file had the name; this one gets " (from Windows)"


@dataclass
class Plan:
    items: List[CopyItem] = field(default_factory=list)

    @property
    def to_copy(self) -> List[CopyItem]:
        return [i for i in self.items if i.action == COPY]

    @property
    def skipped(self) -> List[CopyItem]:
        return [i for i in self.items if i.action == SKIP]

    @property
    def bytes(self) -> int:
        return sum(i.size for i in self.to_copy)

    def extend(self, other: 'Plan') -> None:
        self.items.extend(other.items)


def _alt_name(path: str, n: int) -> str:
    folder, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    if stem.startswith('.') and not ext:          # .bashrc-style names have no extension
        stem, ext = name, ''
    tag = RENAMED if n == 1 else f" ({t('win.renamed')} {n})"
    return os.path.join(folder, f"{stem}{tag}{ext}")


def _free_dir(path: str, claimed: Set[str]) -> str:
    """A folder path that isn't a file: path itself, or 'name (from Windows)'."""
    n = 0
    candidate = path
    while (os.path.exists(candidate) and not os.path.isdir(candidate)) or \
            (candidate in claimed and not os.path.isdir(candidate)):
        n += 1
        candidate = _alt_name(path, n)
    return candidate


def plan_copy(src_root: str, dst_root: str, claimed: Optional[Set[str]] = None) -> Plan:
    """What copying src_root into dst_root would do, file by file. A file that's already
    there with the same size is skipped; a different file with the same name keeps its
    place and the copy is called 'name (from Windows).ext'."""
    claimed = set() if claimed is None else claimed
    plan = Plan()
    dir_map: Dict[str, str] = {src_root: _free_dir(dst_root, claimed)}
    for folder, dirs, files in os.walk(src_root, followlinks=False):
        dst_folder = dir_map.get(folder)
        if dst_folder is None:
            continue
        keep_dirs = []
        for name in sorted(dirs, key=str.lower):
            full = os.path.join(folder, name)
            if name.lower() in IGNORED or os.path.islink(full):
                continue
            keep_dirs.append(name)
            target = _free_dir(os.path.join(dst_folder, name), claimed)
            claimed.add(target)
            dir_map[full] = target
        dirs[:] = keep_dirs
        for name in sorted(files, key=str.lower):
            src = os.path.join(folder, name)
            if name.lower() in IGNORED or os.path.islink(src):
                continue
            try:
                size = os.stat(src).st_size
            except OSError:
                continue
            target = os.path.join(dst_folder, name)
            n, renamed, action = 0, False, COPY
            while True:
                if target in claimed:
                    pass                               # another planned file took this name
                elif not os.path.lexists(target):
                    break
                elif os.path.isfile(target) and not os.path.islink(target) \
                        and os.path.getsize(target) == size:
                    action = SKIP
                    break
                n += 1
                renamed = True
                target = _alt_name(os.path.join(dst_folder, name), n)
            claimed.add(target)
            plan.items.append(CopyItem(src, target, size, action, renamed and action == COPY))
    return plan


# ─── Copying ──────────────────────────────────────────────────

@dataclass
class Summary:
    copied: int = 0
    copied_bytes: int = 0
    skipped: int = 0
    failed: List[Tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False
    renamed: int = 0


def copy_plan(plan: Plan, progress: Optional[Callable[[int, int, str], None]] = None,
              cancel: Optional[threading.Event] = None) -> Summary:
    """Copy each planned file through a '.part' file, so a cancelled or failed copy leaves
    nothing half-written. progress(done_bytes, total_bytes, current_name) is called from
    this thread."""
    summary = Summary(skipped=len(plan.skipped))
    total, done = plan.bytes, 0
    for item in plan.to_copy:
        if cancel and cancel.is_set():
            summary.cancelled = True
            break
        if progress:
            progress(done, total, os.path.basename(item.src))
        if os.path.lexists(item.dst):                  # appeared since the plan was made
            summary.skipped += 1
            done += item.size
            continue
        tmp = item.dst + '.part'
        try:
            os.makedirs(os.path.dirname(item.dst), exist_ok=True)
            with open(item.src, 'rb') as src, open(tmp, 'wb') as dst:
                while True:
                    if cancel and cancel.is_set():
                        raise InterruptedError
                    chunk = src.read(CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
                    done += len(chunk)
                    if progress and len(chunk) == CHUNK:
                        progress(done, total, os.path.basename(item.src))
            try:
                shutil.copystat(item.src, tmp)
            except OSError:
                pass
            os.replace(tmp, item.dst)
            summary.copied += 1
            summary.copied_bytes += item.size
            summary.renamed += 1 if item.renamed else 0
        except InterruptedError:
            _remove(tmp)
            summary.cancelled = True
            break
        except OSError as exc:
            _remove(tmp)
            summary.failed.append((item.src, exc.strerror or str(exc)))
            log.warning("copy failed: %s: %s", item.src, exc)
    if progress:
        progress(total if not summary.cancelled else done, total, '')
    return summary


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
