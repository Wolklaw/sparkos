"""Your drives, open at every start: what the Drives step shows and does.

Windows drives (NTFS, BitLocker) are opened by SparkOS itself at every boot
(sparkos-windows-drives.service, /run/sparkos/windows-drives.json): this only reads its report.

Other drives with files on them (exFAT, FAT32, ext4, Btrfs, XFS) get an /etc/fstab line through
udisks (Block.AddConfigurationItem, called with gdbus so the desktop asks for the password),
then are mounted. Only ever adds a line and mounts: never formats, never removes anything.
No window code."""

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .core import log, run
from .strings import t

STATE = os.environ.get('SPARKOS_WINDOWS_DRIVES_STATE', '/run/sparkos/windows-drives.json')
CONF = '/etc/sparkos/windows-drives.conf'
FSTAB = os.environ.get('SPARK_WELCOME_FSTAB', '/etc/fstab')
BASE = '/var/mnt'
LSBLK_CMD = ['lsblk', '-J', '-b', '-o',
             'NAME,PATH,TYPE,FSTYPE,LABEL,UUID,PARTTYPE,MOUNTPOINTS,SIZE,HOTPLUG,PARTUUID']

DATA_FS = {'exfat', 'vfat', 'ext4', 'ext3', 'ext2', 'btrfs', 'xfs', 'f2fs'}
OWNER_FS = {'exfat', 'vfat'}          # no owners on disk: mounted as the user
SKIP_PARTTYPES = {
    'c12a7328-f81f-11d2-ba4b-00a0c93ec93b',   # EFI system
    'e3c9e316-0b5c-4db8-817d-f92df00215ae',   # Microsoft reserved
    'de94bba4-06d1-4d40-a16a-bfd50179d6ac',   # Windows Recovery
    '21686148-6449-6e6f-744e-656564454649',   # BIOS boot
    '0657fd6d-a4ab-43c4-84e5-0933c84b4f4f',   # Linux swap
}
SYSTEM_MOUNTS = {'/', '/boot', '/boot/efi', '/efi', '/var', '/home', '/sysroot', '/usr', '/etc',
                 '/sysroot/ostree/deploy', '[SWAP]'}
SKIP_DEVICE_TYPES = {'loop', 'rom', 'crypt', 'lvm'}


# ─── Windows drives (opened by SparkOS at boot) ──────────────

@dataclass
class WindowsDrive:
    letter: str
    label: str
    device: str
    mountpoint: str
    mode: str          # rw, ro, off
    problem: str

    @property
    def name(self) -> str:
        return f"{self.letter}:" if self.letter else (self.label or os.path.basename(self.device))

    @property
    def by_choice(self) -> bool:
        """Read-only because the conf says so, not because read-write failed."""
        return self.mode == 'ro' and not self.problem

    @property
    def locked(self) -> bool:
        return 'bitlocker' in self.problem.lower()

    @property
    def hibernated(self) -> bool:
        return self.mode == 'ro' and 'read-write failed' in self.problem


def parse_windows_drives(text: str) -> List[WindowsDrive]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    out = []
    for e in data if isinstance(data, list) else []:
        if not isinstance(e, dict):
            continue
        out.append(WindowsDrive(str(e.get('letter') or ''), str(e.get('label') or ''),
                                str(e.get('device') or ''), str(e.get('mountpoint') or ''),
                                str(e.get('mode') or 'off'), str(e.get('problem') or '')))
    out.sort(key=lambda d: (d.letter == '', d.letter, d.label))
    return out


def windows_drives(path: Optional[str] = None) -> Optional[List[WindowsDrive]]:
    """None when SparkOS hasn't reported (the service isn't there or hasn't run)."""
    try:
        with open(path or STATE, encoding='utf-8') as f:
            return parse_windows_drives(f.read())
    except OSError:
        return None


# ─── Other drives (added to /etc/fstab here) ─────────────────

@dataclass
class OtherDrive:
    name: str
    path: str
    fstype: str
    label: str
    uuid: str
    partuuid: str
    size: int
    mountpoints: Tuple[str, ...]
    added: bool = False            # already in /etc/fstab
    target: str = ''               # the folder it will open at, once picked

    @property
    def title(self) -> str:
        return self.label or os.path.basename(self.path)

    @property
    def open_now(self) -> str:
        return self.mountpoints[0] if self.mountpoints else ''


def _fstab_sources(text: str) -> Set[str]:
    out = set()
    for line in text.splitlines():
        fields = line.split()
        if fields and not fields[0].startswith('#'):
            out.add(fields[0])
    return out


def in_fstab(drive: OtherDrive, fstab_text: str) -> bool:
    sources = _fstab_sources(fstab_text)
    keys = {drive.path}
    if drive.uuid:
        keys |= {f'UUID={drive.uuid}', f'/dev/disk/by-uuid/{drive.uuid}'}
    if drive.partuuid:
        keys |= {f'PARTUUID={drive.partuuid}', f'/dev/disk/by-partuuid/{drive.partuuid}'}
    if drive.label:
        keys |= {f'LABEL={drive.label}', f'/dev/disk/by-label/{drive.label}'}
    return bool(sources & keys)


def parse_other_drives(lsblk_json: str, fstab_text: str = '') -> List[OtherDrive]:
    """Partitions with files on them that aren't Windows drives, aren't part of SparkOS itself,
    and aren't plugged in by USB (those open by themselves when plugged in)."""
    try:
        devices = json.loads(lsblk_json).get('blockdevices') or []
    except (ValueError, AttributeError):
        return []
    out: List[OtherDrive] = []

    def walk(devs: Iterable[dict], hotplug: bool) -> None:
        for d in devs or []:
            if not isinstance(d, dict):
                continue
            plugged = hotplug or bool(d.get('hotplug'))
            name = d.get('name') or ''
            kind = (d.get('type') or '').lower()
            if name.startswith(('zram', 'loop', 'sr')) or kind in SKIP_DEVICE_TYPES:
                continue
            walk(d.get('children'), plugged)
            fstype = (d.get('fstype') or '').lower()
            if plugged or fstype not in DATA_FS:
                continue
            if (d.get('parttype') or '').lower() in SKIP_PARTTYPES:
                continue
            points = tuple(p for p in (d.get('mountpoints') or []) if p)
            if any(p in SYSTEM_MOUNTS or p.startswith(('/sysroot', '/boot', '/usr')) for p in points):
                continue
            drive = OtherDrive(name, d.get('path') or f'/dev/{name}', fstype, d.get('label') or '',
                               d.get('uuid') or '', d.get('partuuid') or '', int(d.get('size') or 0),
                               points)
            drive.added = in_fstab(drive, fstab_text)
            out.append(drive)

    walk(devices, False)
    return out


def list_other_drives() -> Tuple[List[OtherDrive], str]:
    code, out, err = run(LSBLK_CMD, timeout=15)
    if code != 0:
        return [], err.strip() or out.strip()
    try:
        with open(FSTAB, encoding='utf-8') as f:
            fstab = f.read()
    except OSError:
        fstab = ''
    return parse_other_drives(out, fstab), ''


def safe_name(text: str) -> str:
    """Same rule as sparkos-windows-drives: one safe folder name, or ''."""
    name = re.sub(r'[^a-z0-9._-]+', '-', text.lower()).strip('-.')
    return name if re.fullmatch(r'[a-z0-9][a-z0-9._-]*', name) else ''


def folder_for(drive: OtherDrive, taken: Set[str]) -> str:
    name = safe_name(drive.label) or safe_name(drive.uuid[:8]) or safe_name(drive.name) or 'drive'
    base, n = name, 2
    while name in taken:
        name, n = f'{base}-{n}', n + 1
    taken.add(name)
    return os.path.join(BASE, name)


def taken_names(base: str = BASE) -> Set[str]:
    try:
        return {n.lower() for n in os.listdir(base)}
    except OSError:
        return set()


def mount_options(fstype: str, uid: int, gid: int) -> str:
    opts = ['nosuid', 'nodev', 'nofail', 'x-gvfs-show', 'x-mount.mkdir', 'x-systemd.device-timeout=10s']
    if fstype in OWNER_FS:
        opts += [f'uid={uid}', f'gid={gid}', 'umask=022']
    return ','.join(opts)


def source_for(drive: OtherDrive) -> str:
    if drive.uuid:
        return f'UUID={drive.uuid}'
    if drive.partuuid:
        return f'PARTUUID={drive.partuuid}'
    return drive.path


def _bytes(text: str) -> str:
    """A GVariant bytestring literal for gdbus."""
    return "b'" + text.replace('\\', '\\\\').replace("'", "\\'") + "'"


def add_command(drive: OtherDrive, point: str, opts: str) -> List[str]:
    item = ("('fstab', {"
            f"'fsname': <{_bytes(source_for(drive))}>, "
            f"'dir': <{_bytes(point)}>, "
            f"'type': <{_bytes(drive.fstype)}>, "
            f"'opts': <{_bytes(opts)}>, "
            "'freq': <0>, 'passno': <0>})")
    return ['gdbus', 'call', '--system', '--interactive', '--timeout', '300',
            '--dest', 'org.freedesktop.UDisks2',
            '--object-path', f'/org/freedesktop/UDisks2/block_devices/{drive.name}',
            '--method', 'org.freedesktop.UDisks2.Block.AddConfigurationItem', item, '{}']


def explain_error(text: str) -> str:
    low = text.lower()
    if 'notauthorized' in low or 'not authorized' in low or 'dismissed' in low or 'cancel' in low:
        return t('drives.err.password')
    if 'wrong fs type' in low or 'bad superblock' in low or 'needs repair' in low:
        return t('drives.err.damaged')
    line = next((ln for ln in reversed(text.strip().splitlines()) if ln.strip()), '')
    return f"{t('drives.err.generic')} {line}".strip()


def add_drive(drive: OtherDrive, point: str) -> Tuple[str, str]:
    """(where it is open now or '', problem or ''). Adds the line, then opens it there."""
    opts = mount_options(drive.fstype, os.getuid(), os.getgid())
    if not drive.added:
        code, out, err = run(add_command(drive, point, opts), timeout=310)
        if code != 0:
            log.warning("fstab add for %s failed (%s): %s %s", drive.path, code, out.strip(), err.strip())
            return '', explain_error(err + '\n' + out)
        log.info("added %s to fstab at %s (%s)", drive.path, point, opts)
        drive.added = True
    if drive.open_now and drive.open_now != point:
        run(['udisksctl', 'unmount', '-b', drive.path], timeout=60)
    code, out, err = run(['udisksctl', 'mount', '-b', drive.path], timeout=180)
    if code == 0 or 'already mounted' in (err + out).lower():
        where = point if os.path.ismount(point) else (_mounted_at(out) or point)
        drive.mountpoints = (where,)
        if not os.access(where, os.W_OK):
            return where, t('drives.not_writable')
        return where, ''
    log.warning("mount %s failed (%s): %s %s", drive.path, code, out.strip(), err.strip())
    return '', t('drives.added_next_start')


_MOUNTED = re.compile(r'Mounted \S+ at (.+?)\.?\s*$', re.M)


def _mounted_at(text: str) -> str:
    m = _MOUNTED.search(text)
    return m.group(1).strip() if m else ''
