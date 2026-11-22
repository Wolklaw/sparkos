"""Bring your files from Windows: find Windows partitions, mount them read-only, find the
Windows user folders with something in them, plan the copy and copy.

Windows often keeps the folders somewhere other than C:\\Users\\<name>\\Documents: in OneDrive
(Windows 11 offers it at setup) or on another drive. Where each one really is comes from the
account's own registry file (NTUSER.DAT, "User Shell Folders"), and the drive letters from the
SYSTEM registry file (MountedDevices). Both are read here as plain files, never written.

Copy, never move: nothing here opens a file on the Windows disk for writing, and the disk is
mounted read-only. No window code, so the Spark Portal can reuse it."""

import json
import os
import re
import shutil
import struct
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

from .core import log, run, xdg_user_dir
from .strings import t

LSBLK_CMD = ['lsblk', '-J', '-b', '-o', 'NAME,PATH,FSTYPE,LABEL,MOUNTPOINT,SIZE,PARTUUID']

# Windows folder, xdg-user-dir key, SparkOS fallback folder
FOLDERS = (
    ('Desktop', 'DESKTOP', 'Desktop'),
    ('Documents', 'DOCUMENTS', 'Documents'),
    ('Pictures', 'PICTURES', 'Pictures'),
    ('Videos', 'VIDEOS', 'Videos'),
    ('Music', 'MUSIC', 'Music'),
    ('Downloads', 'DOWNLOAD', 'Downloads'),
)
# Where Windows keeps each folder: its value name under "User Shell Folders" (lower case).
SHELL_VALUES = {
    'Desktop': 'desktop',
    'Documents': 'personal',
    'Pictures': 'my pictures',
    'Videos': 'my video',
    'Music': 'my music',
    'Downloads': '{374de290-123f-4565-9164-39c4925e467b}',
}
SHELL_FOLDERS_KEY = r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
# OneDrive's folder names in the languages Windows is most often set up in, for when the
# registry file can't be read.
ONEDRIVE_NAMES = {
    'Desktop': ('Desktop', 'Bureau', 'Escritorio', 'Área de Trabalho', 'Schreibtisch',
                'Scrivania'),
    'Documents': ('Documents', 'Documentos', 'Dokumente', 'Documenti'),
    'Pictures': ('Pictures', 'Images', 'Imágenes', 'Imagens', 'Bilder', 'Immagini'),
}
# Not people: the shared and template profiles, and service accounts.
SKIP_USERS = {'public', 'default', 'default user', 'all users', 'defaultapppool',
              'wdagutilityaccount'}
# Windows' own clutter, never worth copying.
IGNORED = {'desktop.ini', 'thumbs.db', 'ehthumbs.db', '$recycle.bin'}
RENAMED = f" ({t('win.renamed')})"      # ' (from Windows)', ' (de Windows)'
CHUNK = 1024 * 1024
# Space left free on SparkOS's disk after a copy, so updates and the desktop keep working.
RESERVE = 2 * 1024 ** 3


# ─── Partitions ───────────────────────────────────────────────

@dataclass
class Partition:
    name: str              # sda3
    path: str              # /dev/sda3
    fstype: str            # ntfs, or BitLocker
    label: str
    mountpoint: str
    size: int
    partuuid: str = ''     # GPT partition GUID, lower case; Windows' drive letters point at it

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
                                       (dev.get('mountpoint') or '').strip(), size,
                                       (dev.get('partuuid') or '').strip().lower()))
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
            part.mountpoint = point
            return point, ''
    log.warning("mount %s failed (%s): %s %s", part.path, code, out.strip(), err.strip())
    return None, explain_mount_error(err + '\n' + out)


# ─── Windows registry files (read-only) ───────────────────────

REG_SZ, REG_EXPAND_SZ, REG_BINARY = 1, 2, 3


class Hive:
    """Just enough of the Windows registry file format ("regf") to read values: keys, the four
    kinds of subkey list (lf, lh, li, ri) and values. Works on the file's bytes; any damage
    raises ValueError."""

    def __init__(self, data: bytes):
        if len(data) < 0x1000 + 32 or data[:4] != b'regf':
            raise ValueError('not a registry file')
        self.data = data
        self.root = self._u32(0x24)

    def _u16(self, pos: int) -> int:
        return struct.unpack_from('<H', self.data, pos)[0]

    def _u32(self, pos: int) -> int:
        return struct.unpack_from('<I', self.data, pos)[0]

    def _cell(self, offset: int) -> int:
        """File position of a cell's data (offsets count from the first hive bin)."""
        pos = 0x1000 + offset + 4
        if offset in (0, 0xFFFFFFFF) or pos + 4 > len(self.data):
            raise ValueError('bad cell offset')
        return pos

    def _text(self, pos: int, length: int, ascii_name: bool) -> str:
        raw = self.data[pos:pos + length]
        return raw.decode('latin-1') if ascii_name else raw.decode('utf-16-le', 'replace')

    def _list(self, offset: int, depth: int = 0) -> Iterator[int]:
        if depth > 3:
            raise ValueError('subkey lists nested too deep')
        pos = self._cell(offset)
        sig, count = self.data[pos:pos + 2], self._u16(pos + 2)
        if sig in (b'lf', b'lh'):
            for i in range(count):
                yield self._u32(pos + 4 + i * 8)
        elif sig == b'li':
            for i in range(count):
                yield self._u32(pos + 4 + i * 4)
        elif sig == b'ri':
            for i in range(count):
                yield from self._list(self._u32(pos + 4 + i * 4), depth + 1)

    def _key_name(self, nk: int) -> str:
        return self._text(nk + 0x4C, self._u16(nk + 0x48), bool(self._u16(nk + 2) & 0x20))

    def key(self, path: str) -> Optional[int]:
        """Position of the key at path (backslashes, any case), or None."""
        nk = self._cell(self.root)
        for part in filter(None, path.split('\\')):
            want = part.lower()
            if not self._u32(nk + 0x14):
                return None
            for offset in self._list(self._u32(nk + 0x1C)):
                child = self._cell(offset)
                if self.data[child:child + 2] == b'nk' and self._key_name(child).lower() == want:
                    nk = child
                    break
            else:
                return None
        return nk

    def values(self, path: str) -> Dict[str, Tuple[int, bytes]]:
        """{value name in lower case: (type, data)} of the key at path; {} if it's missing.
        Values over 16 KB (stored in another format) are left out: none needed here is."""
        nk = self.key(path)
        if nk is None:
            return {}
        out: Dict[str, Tuple[int, bytes]] = {}
        count = self._u32(nk + 0x24)
        if not count:
            return out
        table = self._cell(self._u32(nk + 0x28))
        for i in range(count):
            vk = self._cell(self._u32(table + i * 4))
            if self.data[vk:vk + 2] != b'vk':
                continue
            name = self._text(vk + 0x14, self._u16(vk + 2), bool(self._u16(vk + 0x10) & 1))
            size, vtype = self._u32(vk + 4), self._u32(vk + 0x0C)
            if size & 0x80000000:                     # up to 4 bytes, kept in the value itself
                raw = self.data[vk + 8:vk + 8 + min(size & 0x7FFFFFFF, 4)]
            elif size > 16344:
                continue
            else:
                pos = self._cell(self._u32(vk + 8))
                raw = self.data[pos:pos + size]
            out[name.lower()] = (vtype, raw)
        return out


def read_hive(path: Optional[str]) -> Optional[Hive]:
    if not path:
        return None
    try:
        with open(path, 'rb') as f:                  # read-only, like everything on the drive
            return Hive(f.read())
    except (OSError, ValueError, struct.error) as exc:
        log.info("registry file %s not read: %s", path, exc)
        return None


def reg_text(value: Optional[Tuple[int, bytes]]) -> Optional[str]:
    if not value or value[0] not in (REG_SZ, REG_EXPAND_SZ):
        return None
    return value[1].decode('utf-16-le', 'replace').split('\x00', 1)[0].strip() or None


def shell_folders(profile: str) -> Dict[str, str]:
    """{'Documents': '%USERPROFILE%\\OneDrive\\Documentos', 'Videos': 'D:\\Videos', ...} from
    the account's NTUSER.DAT; {} when it can't be read."""
    hive = read_hive(_child(profile, 'NTUSER.DAT', want_dir=False))
    if hive is None:
        return {}
    try:
        values = hive.values(SHELL_FOLDERS_KEY)
    except (ValueError, struct.error) as exc:
        log.info("User Shell Folders not read in %s: %s", profile, exc)
        return {}
    found = {}
    for key, value_name in SHELL_VALUES.items():
        text = reg_text(values.get(value_name))
        if text:
            found[key] = text
    return found


def drive_letters(root: str) -> Dict[str, str]:
    """{'C': partition GUID, 'D': ...} from the SYSTEM registry file's MountedDevices (GPT
    disks; an MBR disk's entries have no GUID and are left out). {} when it can't be read."""
    config = _child(_child(root, 'Windows') or '', 'System32')
    hive = read_hive(_child(_child(config or '', 'config') or '', 'SYSTEM', want_dir=False))
    if hive is None:
        return {}
    try:
        values = hive.values('MountedDevices')
    except (ValueError, struct.error) as exc:
        log.info("MountedDevices not read: %s", exc)
        return {}
    letters = {}
    for name, (_vtype, raw) in values.items():
        match = re.fullmatch(r'\\dosdevices\\([a-z]):', name)
        if match and len(raw) == 24 and raw[:8] == b'DMIO:ID:':
            letters[match.group(1).upper()] = str(uuid.UUID(bytes_le=raw[8:24]))
    return letters


# ─── Windows user folders ─────────────────────────────────────

def _child(parent: str, wanted: str, want_dir: bool = True) -> Optional[str]:
    """parent/wanted, matching the name case-insensitively (NTFS isn't case-sensitive)."""
    if not parent:
        return None
    try:
        with os.scandir(parent) as entries:
            for entry in entries:
                if entry.name.lower() != wanted.lower():
                    continue
                if want_dir and entry.is_dir(follow_symlinks=False):
                    return entry.path
                if not want_dir and entry.is_file(follow_symlinks=False):
                    return entry.path
    except OSError:
        pass
    return None


def _walk_ci(base: str, rest: str) -> Optional[str]:
    """base + a Windows relative path ('OneDrive\\Desktop'), each part matched case-
    insensitively. None if a part is missing or is a junction."""
    path = base
    for part in filter(None, re.split(r'[\\/]+', rest)):
        if part in ('.', '..'):
            return None
        path = _child(path, part)
        if path is None:
            return None
    return path


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
    path: str         # /run/media/.../Users/Ann/OneDrive/Documentos
    xdg: str          # DOCUMENTS
    fallback: str     # Documents
    size: Optional[int] = None
    files: Optional[int] = None
    where: str = ''   # as Windows shows it: C:\Users\Ann\OneDrive\Documentos


@dataclass
class WindowsUser:
    name: str
    path: str
    folders: List[SourceFolder] = field(default_factory=list)


class Drives:
    """Windows paths to folders here: the Windows drive itself, and other drives found by
    their letter (mounted read-only when first needed)."""

    def __init__(self, root: str, windows: Optional[Partition] = None,
                 partitions: Optional[List[Partition]] = None):
        self.root = root
        self.partitions = partitions or []
        guids = drive_letters(root)
        self.by_letter: Dict[str, Partition] = {}
        for letter, guid in guids.items():
            part = next((p for p in self.partitions if p.partuuid == guid), None)
            if part is not None:
                self.by_letter[letter] = part
        self.windows_letter = 'C'
        if windows is not None and windows.partuuid:
            self.windows_letter = next((letter for letter, guid in sorted(guids.items())
                                        if guid == windows.partuuid), 'C')
        self.tried: Dict[str, Optional[str]] = {}

    def mount_point(self, letter: str) -> Optional[str]:
        letter = letter.upper()
        if letter == self.windows_letter:
            return self.root
        if letter not in self.tried:
            part = self.by_letter.get(letter)
            point = None
            if part is not None:
                point, problem = mount_read_only(part)
                if problem:
                    log.warning("drive %s: (%s) not opened: %s", letter, part.path, problem)
            self.tried[letter] = point
        return self.tried[letter]

    def resolve(self, text: str, profile: str, profile_where: str) -> Tuple[Optional[str], str]:
        """(folder here, the path as Windows shows it) for a "User Shell Folders" value."""
        match = re.match(r'%userprofile%(.*)$', text, re.I)
        if match:
            rest = match.group(1)
            return _walk_ci(profile, rest), profile_where + rest
        if '%' in text or text.startswith('\\\\'):
            return None, text                  # other variables, network shares: not here
        match = re.match(r'([A-Za-z]):[\\/]?(.*)$', text)
        if not match:
            return None, text
        point = self.mount_point(match.group(1))
        return (_walk_ci(point, match.group(2)) if point else None), text


def _onedrive_guess(profile: str, key: str) -> Optional[str]:
    """profile/OneDrive*/<the folder's name in a common language>, when it has files."""
    names = ONEDRIVE_NAMES.get(key)
    if not names:
        return None
    try:
        clouds = sorted(e.path for e in os.scandir(profile)
                        if e.name.lower().startswith('onedrive') and e.is_dir(follow_symlinks=False))
    except OSError:
        return None
    for cloud in clouds:
        for name in names:
            path = _child(cloud, name)
            if path and has_content(path):
                return path
    return None


def find_users(root: str, windows: Optional[Partition] = None,
               partitions: Optional[List[Partition]] = None) -> List[WindowsUser]:
    """Windows accounts under root/Users that have at least one non-empty standard folder,
    wherever Windows keeps it (the account folder, OneDrive, or another drive)."""
    users_dir = _child(root, 'Users')
    if not users_dir:
        return []
    found = []
    try:
        entries = sorted(os.scandir(users_dir), key=lambda e: e.name.lower())
    except OSError:
        return []
    drives: Optional[Drives] = None
    for entry in entries:
        if entry.name.lower() in SKIP_USERS or entry.is_symlink() \
                or not entry.is_dir(follow_symlinks=False):
            continue
        user = WindowsUser(entry.name, entry.path)
        shell = shell_folders(entry.path)
        if shell and drives is None:
            drives = Drives(root, windows, partitions)
        letter = drives.windows_letter if drives else 'C'
        profile_where = f"{letter}:\\Users\\{entry.name}"
        taken: Set[str] = set()
        for key, xdg, fallback in FOLDERS:
            path, where = None, ''
            if key in shell and drives is not None:
                path, where = drives.resolve(shell[key], entry.path, profile_where)
                if path and not has_content(path):
                    path = None
            if path is None:
                path = _child(entry.path, key)
                where = f"{profile_where}\\{os.path.basename(path or key)}"
                if path and not has_content(path):
                    path = None
            if path is None:
                path = _onedrive_guess(entry.path, key)
                if path:
                    where = profile_where + '\\' + os.path.relpath(path, entry.path) \
                        .replace(os.sep, '\\')
            if path is None or os.path.realpath(path) in taken:
                continue
            taken.add(os.path.realpath(path))
            user.folders.append(SourceFolder(key, path, xdg, fallback, where=where))
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


def free_space(path: str) -> Optional[int]:
    """Bytes free on the disk that holds path (its nearest existing parent), or None."""
    while path and not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


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


def plan_copy(src_root: str, dst_root: str, claimed: Optional[Set[str]] = None,
              cancel: Optional[threading.Event] = None) -> Plan:
    """What copying src_root into dst_root would do, file by file. A file that's already
    there with the same size is skipped; a different file with the same name keeps its
    place and the copy is called 'name (from Windows).ext'."""
    claimed = set() if claimed is None else claimed
    plan = Plan()
    dir_map: Dict[str, str] = {src_root: _free_dir(dst_root, claimed)}
    for folder, dirs, files in os.walk(src_root, followlinks=False):
        if cancel and cancel.is_set():
            break
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
    # Set instead of copying when the files don't fit: (bytes needed, bytes free).
    no_space: Optional[Tuple[int, int]] = None


def check_space(plan: Plan, dst: str) -> Optional[Tuple[int, int]]:
    """(needed, free) when the plan wouldn't leave RESERVE free on dst's disk, else None."""
    free = free_space(dst)
    if free is not None and plan.bytes + RESERVE > free:
        return plan.bytes, free
    return None


def copy_plan(plan: Plan, progress: Optional[Callable[[int, int, str], None]] = None,
              cancel: Optional[threading.Event] = None) -> Summary:
    """Copy each planned file through a hidden temporary file, so a cancelled or failed copy
    leaves nothing half-written, and never over a file that's already there. Copies get the
    Windows file's dates, not its permissions (no file comes out executable).
    progress(done_bytes, total_bytes, current_name) is called from this thread."""
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
        tmp = None
        start = done
        try:
            folder = os.path.dirname(item.dst)
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(item.dst)[:80] + '.',
                                       suffix='.part', dir=folder)
            os.fchmod(fd, 0o644)
            with open(item.src, 'rb') as src, os.fdopen(fd, 'wb') as dst:
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
                st = os.stat(item.src)
                os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
            except OSError:
                pass
            try:
                os.link(tmp, item.dst)                 # fails rather than replace a file
            except FileExistsError:
                summary.skipped += 1
                continue
            except OSError:
                if os.path.lexists(item.dst):
                    summary.skipped += 1
                    continue
                os.rename(tmp, item.dst)               # a disk without hard links
                tmp = None
            summary.copied += 1
            summary.copied_bytes += item.size
            summary.renamed += 1 if item.renamed else 0
        except InterruptedError:
            summary.cancelled = True
            break
        except OSError as exc:
            done = start + item.size
            summary.failed.append((item.src, exc.strerror or str(exc)))
            log.warning("copy failed: %s: %s", item.src, exc)
        finally:
            if tmp:
                _remove(tmp)
    if progress:
        progress(total if not summary.cancelled else done, total, '')
    return summary


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
