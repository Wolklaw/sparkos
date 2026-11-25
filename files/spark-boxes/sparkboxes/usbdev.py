"""The host's USB devices, and which ones may be given to a machine.

A device is never offered when something on it is the running system or the D: drive (the same
mount lists Spark Disks uses), or when any of it is mounted on this PC at all (handing a mounted
drive to a machine corrupts it). Everything reads sysfs and /proc/self/mountinfo, so tests can
point it at a made-up tree."""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SYSTEM_MOUNTS = frozenset(('/', '/boot', '/boot/efi', '/usr', '/etc', '/var', '/home',
                           '/var/home', '/sysroot', '[SWAP]'))
SYSTEM_PREFIXES = ('/sysroot/', '/boot/', '/usr/', '/var/lib/', '/var/home/')
D_MOUNTS = ('/var/mnt/d', '/mnt/d')
HUB_CLASS = '09'


@dataclass
class UsbDevice:
    busnum: int
    devnum: int
    vendor: str            # 4 hex digits
    product: str
    name: str
    blocks: List[str] = field(default_factory=list)       # sda, sda1 ...
    mounts: List[str] = field(default_factory=list)
    refused: str = ''      # '', 'system', 'd' or 'mounted'

    @property
    def ident(self) -> str:
        return f"{self.vendor}:{self.product}"

    @property
    def allowed(self) -> bool:
        return not self.refused


def _read(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read().strip()
    except OSError:
        return ''


def mounts_by_device(mountinfo: str) -> Dict[str, List[str]]:
    """'major:minor' -> mount points, from the text of /proc/self/mountinfo."""
    found: Dict[str, List[str]] = {}
    for line in mountinfo.splitlines():
        parts = line.split()
        if len(parts) > 4:
            found.setdefault(parts[2], []).append(parts[4].replace('\\040', ' '))
    return found


def is_system_mount(mountpoint: str) -> bool:
    return mountpoint in SYSTEM_MOUNTS or mountpoint.startswith(SYSTEM_PREFIXES)


def is_d_mount(mountpoint: str) -> bool:
    return any(mountpoint == d or mountpoint.startswith(d + '/') for d in D_MOUNTS)


def refusal(mounts: List[str]) -> str:
    """Why a device whose parts are mounted at `mounts` may not be offered ('' if it may)."""
    if any(is_d_mount(m) for m in mounts):
        return 'd'
    if any(is_system_mount(m) for m in mounts):
        return 'system'
    return 'mounted' if mounts else ''


def _block_devices(dev_dir: str) -> List[str]:
    """Names of the block devices (and their partitions) that sit under a USB device."""
    names: List[str] = []
    for root, dirs, _files in os.walk(dev_dir):
        if os.path.basename(root) == 'block':
            for disk in dirs:
                names.append(disk)
                for sub in os.listdir(os.path.join(root, disk)):
                    if sub.startswith(disk) and os.path.isdir(os.path.join(root, disk, sub)):
                        names.append(sub)
            dirs[:] = []
    return names


def list_devices(sysfs: str = '/sys', mountinfo: Optional[str] = None) -> List[UsbDevice]:
    """Every USB device that is not a hub, with the reason it is refused (if it is)."""
    if mountinfo is None:
        mountinfo = _read('/proc/self/mountinfo')
    mounted = mounts_by_device(mountinfo)
    base = os.path.join(sysfs, 'bus', 'usb', 'devices')
    devices: List[UsbDevice] = []
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return devices
    for entry in entries:
        if ':' in entry:                         # an interface, not a device
            continue
        path = os.path.realpath(os.path.join(base, entry))
        if _read(os.path.join(path, 'bDeviceClass')) == HUB_CLASS:
            continue
        vendor = _read(os.path.join(path, 'idVendor'))
        product = _read(os.path.join(path, 'idProduct'))
        try:
            busnum = int(_read(os.path.join(path, 'busnum')))
            devnum = int(_read(os.path.join(path, 'devnum')))
        except ValueError:
            continue
        if not vendor or not product:
            continue
        name = ' '.join(p for p in (_read(os.path.join(path, 'manufacturer')),
                                    _read(os.path.join(path, 'product'))) if p) \
            or f"{vendor}:{product}"
        device = UsbDevice(busnum, devnum, vendor, product, name)
        device.blocks = _block_devices(path)
        for block in device.blocks:
            numbers = _read(os.path.join(sysfs, 'class', 'block', block, 'dev'))
            device.mounts += mounted.get(numbers, [])
        device.refused = refusal(device.mounts)
        devices.append(device)
    return devices


def hostdev_xml(device: UsbDevice) -> str:
    return ("<hostdev mode='subsystem' type='usb' managed='yes'><source>"
            f"<vendor id='0x{device.vendor}'/><product id='0x{device.product}'/>"
            f"<address bus='{device.busnum}' device='{device.devnum}'/></source></hostdev>")
