"""What is on this PC's drives, as a tree: drives, their partitions and the free space between
them. It reads `lsblk --json` (read only) and the Windows-drive list SparkOS keeps, and works out
which rows are the system's, Windows' or the locked D: drive. Nothing here writes anything."""

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

MIB = 1024 * 1024
SECTOR = 512                       # lsblk's START column counts 512-byte sectors

WINDOWS_STATE = os.environ.get('SPARKOS_WINDOWS_DRIVES_STATE', '/run/sparkos/windows-drives.json')

LSBLK_COLUMNS = ('NAME,PATH,TYPE,SIZE,FSTYPE,LABEL,MOUNTPOINTS,RM,HOTPLUG,MODEL,VENDOR,SERIAL,'
                 'PARTTYPE,PARTLABEL,PTTYPE,UUID,PARTUUID,RO,TRAN,START,FSUSED')

# What the running system stands on. A partition with any of these (or anything under them) is
# the system's: it can't be unmounted, formatted, deleted or resized from here.
SYSTEM_MOUNTS = frozenset(('/', '/boot', '/boot/efi', '/usr', '/etc', '/var', '/home',
                           '/var/home', '/sysroot', '[SWAP]'))
SYSTEM_PREFIXES = ('/sysroot/', '/boot/', '/usr/', '/var/lib/', '/var/home/')

D_MOUNTS = ('/var/mnt/d', '/mnt/d')

WINDOWS_PART_TYPES = frozenset((
    'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7',     # basic data (C:, D:, E:...)
    'e3c9e316-0b5c-4db8-817d-f92df00215ae',     # Microsoft reserved
    'de94bba4-06d1-4d40-a16a-bfd50179d6ac',     # Windows recovery environment
    'af9b60a0-1431-4f62-bc68-3311714a69ad',     # logical disk manager data
    '5808c8aa-7e8f-42e0-85d2-e1e90434cfb3',     # logical disk manager metadata
))
MBR_CONTAINERS = frozenset(('0x5', '0xf', '0x85'))          # extended partitions
HIDDEN_DISKS = ('zram', 'ram', 'sr', 'fd')                  # not drives
SWAP_AND_FRIENDS = frozenset(('swap', 'crypto_LUKS', 'LVM2_member', 'linux_raid_member',
                              'BitLocker', 'zfs_member', 'ceph_bluestore'))


@dataclass
class Node:
    """One row: a drive ('disk'), a partition ('part'), something stacked on a partition
    ('other': LUKS, LVM, RAID) or the free space between partitions ('free')."""
    kind: str
    path: str = ''
    name: str = ''
    size: int = 0
    start: int = 0                       # bytes from the start of the drive (partitions, free)
    fstype: str = ''
    label: str = ''
    mounts: List[str] = field(default_factory=list)
    removable: bool = False
    model: str = ''
    vendor: str = ''
    serial: str = ''
    parttype: str = ''
    partlabel: str = ''
    pttype: str = ''
    uuid: str = ''
    partuuid: str = ''
    read_only: bool = False
    tran: str = ''
    fsused: int = 0
    parent: str = ''                     # the drive's path, for partitions and free space
    children: List['Node'] = field(default_factory=list)
    # worked out by classify()
    letter: str = ''                     # the Windows drive letter, when SparkOS knows it
    is_d: bool = False                   # D:, or on the same drive as D:
    is_system: bool = False              # the running system uses it (or something on it)
    windows: bool = False
    container: bool = False              # an MBR extended partition: shown, never edited

    @property
    def end(self) -> int:
        return self.start + self.size

    @property
    def mounted(self) -> bool:
        return bool(self.mounts)

    @property
    def title(self) -> str:
        return ' '.join(p for p in (self.vendor, self.model) if p).strip()

    def walk(self) -> Iterable['Node']:
        yield self
        for child in self.children:
            yield from child.walk()


def is_system_mount(mountpoint: str) -> bool:
    return mountpoint in SYSTEM_MOUNTS or mountpoint.startswith(SYSTEM_PREFIXES)


def is_d_mount(mountpoint: str) -> bool:
    return any(mountpoint == d or mountpoint.startswith(d + '/') for d in D_MOUNTS)


def removable_drive(disk: Node) -> bool:
    return disk.removable or disk.tran == 'usb'


def _int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _text(value) -> str:
    return str(value).strip() if value is not None else ''


def _node(entry: Dict, parent: str = '') -> Node:
    kind = entry.get('type') or ''
    kind = {'disk': 'disk', 'loop': 'disk', 'part': 'part'}.get(kind, 'other')
    mounts = [m for m in (entry.get('mountpoints') or []) if m]
    node = Node(
        kind=kind, path=_text(entry.get('path')), name=_text(entry.get('name')),
        size=_int(entry.get('size')), start=_int(entry.get('start')) * SECTOR,
        fstype=_text(entry.get('fstype')), label=_text(entry.get('label')), mounts=mounts,
        removable=bool(entry.get('rm')) or bool(entry.get('hotplug')),
        model=_text(entry.get('model')), vendor=_text(entry.get('vendor')),
        serial=_text(entry.get('serial')),
        parttype=_text(entry.get('parttype')).lower(), partlabel=_text(entry.get('partlabel')),
        pttype=_text(entry.get('pttype')), uuid=_text(entry.get('uuid')),
        partuuid=_text(entry.get('partuuid')).lower(), read_only=bool(entry.get('ro')),
        tran=_text(entry.get('tran')), fsused=_int(entry.get('fsused')), parent=parent)
    if node.parttype in MBR_CONTAINERS:
        node.container = True
    own_path = node.path if kind == 'disk' else parent
    for child in entry.get('children') or []:
        node.children.append(_node(child, own_path))
    return node


def parse_lsblk(text: str, show_loop: bool = False) -> List[Node]:
    """The drives from `lsblk --json --bytes` output. RAM disks, zram, optical drives and (unless
    asked for) loop devices are left out."""
    data = json.loads(text)
    disks = []
    for entry in data.get('blockdevices') or []:
        name = _text(entry.get('name'))
        kind = entry.get('type')
        if kind == 'loop' and not show_loop:
            continue
        if kind not in ('disk', 'loop') or any(name.startswith(h) for h in HIDDEN_DISKS):
            continue
        disks.append(_node(entry))
    return disks


def free_spaces(disk: Node) -> List[Node]:
    """The gaps of 1 MiB or more between a drive's partitions, aligned to 1 MiB. A drive with no
    partition table has none. (An MBR extended partition counts as taken.)"""
    if not disk.pttype or disk.size <= 0:
        return []
    low, high = MIB, (disk.size // MIB) * MIB - MIB      # GPT keeps 1 MiB at each end
    taken = sorted((c.start, c.end) for c in disk.children if c.kind == 'part' and c.size > 0)
    gaps, cursor = [], low
    for begin, end in taken + [(high, high)]:
        begin_aligned = (begin // MIB) * MIB
        if begin_aligned - cursor >= MIB:
            gaps.append(Node(kind='free', start=cursor, size=begin_aligned - cursor,
                             parent=disk.path, name='free'))
        cursor = max(cursor, -(-end // MIB) * MIB)
    return gaps


def load_windows_drives(path: str = '') -> List[Dict]:
    """The entries of /run/sparkos/windows-drives.json (letter, label, device, partuuid,
    mountpoint...). Empty when the file is missing or broken."""
    try:
        with open(path or WINDOWS_STATE, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def classify(disks: List[Node], windows: Optional[List[Dict]] = None) -> List[Node]:
    """Set is_system, is_d, windows, letter on every row, and add the free-space rows."""
    windows = windows or []
    for disk in disks:
        for node in disk.walk():
            node.is_system = any(is_system_mount(m) for m in node.mounts)
            node.is_d = any(is_d_mount(m) for m in node.mounts)
            for entry in windows:
                same = (entry.get('device') and entry.get('device') == node.path) or (
                    entry.get('partuuid') and node.partuuid
                    and str(entry['partuuid']).lower() == node.partuuid)
                if same and node.kind in ('part', 'disk'):
                    node.letter = str(entry.get('letter') or '').upper()
                    if node.letter == 'D':
                        node.is_d = True
        internal = not removable_drive(disk)
        for part in disk.children:
            if part.kind == 'part' and internal and (
                    part.parttype in WINDOWS_PART_TYPES or part.fstype in ('ntfs', 'BitLocker')):
                part.windows = True
            if part.letter:
                part.windows = True
        # a flag on a partition, or something under it, belongs to the partition and its drive
        for node in disk.walk():
            if node is disk:
                continue
            for under in node.walk():
                if under is node:
                    continue
                node.is_system = node.is_system or under.is_system
                node.is_d = node.is_d or under.is_d
        disk.is_system = disk.is_system or any(c.is_system for c in disk.children)
        disk.is_d = disk.is_d or any(c.is_d for c in disk.children)
        disk.windows = any(c.windows for c in disk.children)
        if disk.is_d:                         # the whole drive D: sits on is look-only
            for node in disk.walk():
                node.is_d = True
        disk.children = [c for c in disk.children if c.kind != 'free'] + free_spaces(disk)
        disk.children.sort(key=lambda c: (c.start, c.kind == 'free'))
    return disks


def list_devices(show_loop: Optional[bool] = None, windows_path: str = '') -> List[Node]:
    """Ask lsblk (read only) and classify the answer."""
    if show_loop is None:
        show_loop = os.environ.get('SPARK_DISKS_SHOW_LOOP') == '1'
    done = subprocess.run(['lsblk', '--json', '--bytes', '-o', LSBLK_COLUMNS],
                          capture_output=True, text=True, timeout=30)
    if done.returncode != 0:
        raise OSError((done.stderr or 'lsblk failed').strip())
    return classify(parse_lsblk(done.stdout, show_loop), load_windows_drives(windows_path))


def find(disks: List[Node], path: str) -> Optional[Node]:
    for disk in disks:
        for node in disk.walk():
            if node.path and node.path == path:
                return node
    return None


def find_free(disks: List[Node], disk_path: str, start: int) -> Optional[Node]:
    for disk in disks:
        if disk.path == disk_path:
            for node in disk.children:
                if node.kind == 'free' and node.start == start:
                    return node
    return None


def drive_of(disks: List[Node], node: Node) -> Optional[Node]:
    if node.kind == 'disk':
        return node
    return find(disks, node.parent)


_UNITS = {'': 10 ** 9, 'B': 1, 'O': 1, 'K': 10 ** 3, 'KB': 10 ** 3, 'KO': 10 ** 3, 'M': 10 ** 6,
          'MB': 10 ** 6, 'MO': 10 ** 6, 'G': 10 ** 9, 'GB': 10 ** 9, 'GO': 10 ** 9,
          'T': 10 ** 12, 'TB': 10 ** 12, 'TO': 10 ** 12, 'KIB': 1024, 'KIO': 1024,
          'MIB': MIB, 'MIO': MIB, 'GIB': 1024 ** 3, 'GIO': 1024 ** 3, 'TIB': 1024 ** 4,
          'TIO': 1024 ** 4}


def parse_size(text: str) -> Optional[int]:
    """'20', '20 GB', '512MB', '1,5 Go' -> bytes (a bare number is GB). None if it isn't a size."""
    cleaned = (text or '').strip().replace(',', '.').replace(' ', ' ')
    number = ''
    for i, ch in enumerate(cleaned):
        if ch.isdigit() or ch == '.':
            number += ch
        else:
            unit = cleaned[i:].strip().upper()
            break
    else:
        unit = ''
    try:
        value = float(number)
    except ValueError:
        return None
    factor = _UNITS.get(unit)
    return int(value * factor) if factor else None


def human_size(n: int) -> str:
    """1.5 GB (decimal units, as drive makers and Spark Files write them)."""
    value, unit = float(n), 'B'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1000 or unit == 'TB':
            break
        value /= 1000
    return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
