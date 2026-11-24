"""Shared by the tests: made-up drives (as lsblk would print them) and a backend that only records
what it was asked. Nothing here touches a real disk: the paths are /dev/spark... names that don't
exist, and the fake backend never opens a device."""

import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for _var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(_var, tempfile.mkdtemp(prefix=f'spark-disks-{_var.lower()}-'))

from sparkdisks.model import Node, classify, parse_lsblk  # noqa: E402
from sparkdisks.udisks import Backend  # noqa: E402

GB = 10 ** 9
MIB = 1024 * 1024
BASIC_DATA = 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'


def part(name: str, size: int, start_mib: int, fstype: str = '', mounts=(), label: str = '',
         parttype: str = '', used: int = 0, ro: bool = False) -> Dict[str, Any]:
    return {'name': name, 'path': '/dev/' + name, 'type': 'part', 'size': size,
            'start': start_mib * MIB // 512, 'fstype': fstype or None, 'label': label or None,
            'mountpoints': list(mounts) or [None], 'rm': False, 'ro': ro, 'parttype': parttype or None,
            'fsused': used or None, 'partuuid': name + '-uuid'}


def disk(name: str, size: int, children, removable: bool = False, pttype: str = 'gpt',
         model: str = 'Test Drive', tran: str = '') -> Dict[str, Any]:
    return {'name': name, 'path': '/dev/' + name, 'type': 'disk', 'size': size, 'rm': removable,
            'hotplug': removable, 'ro': False, 'model': model, 'pttype': pttype,
            'tran': tran or ('usb' if removable else 'nvme'), 'children': children,
            'mountpoints': [None], 'serial': 'S-' + name}


def sample() -> Dict[str, Any]:
    """The owner's kind of PC: a system disk with Windows data on it, D: on its own drive, an
    internal data disk, and a USB stick with room left."""
    return {'blockdevices': [
        disk('sparkn0', 1000 * GB, [
            part('sparkn0p1', 500 * MIB, 1, 'vfat', ['/boot/efi'], parttype='c12a7328-f81f-11d2-ba4b-00a0c93ec93b'),
            part('sparkn0p2', 400 * GB, 501, 'ntfs', ['/var/mnt/e'], 'Games', BASIC_DATA, used=100 * GB),
            part('sparkn0p3', 500 * GB, 400 * 1000 + 501, 'btrfs', ['/sysroot', '/var', '/etc'])]),
        disk('sparksa', 250 * GB, [
            part('sparksa1', 250 * GB - 2 * MIB, 1, 'ntfs', ['/var/mnt/d'], 'Scrap', BASIC_DATA, ro=True)]),
        disk('sparksc', 500 * GB, [
            part('sparksc1', 200 * GB, 1, 'ext4', [], 'Data', used=50 * GB),
            part('sparksc2', 100 * GB, 200 * 1000 + 1, 'ntfs', [], 'Old', BASIC_DATA, used=10 * GB)]),
        disk('sparksb', 16 * GB, [
            part('sparksb1', 4 * GB, 1, 'ext4', ['/run/media/x/stick'], 'Stick', used=1 * GB),
            part('sparksb2', 2 * GB, 4000, 'vfat', [], 'Spare')], removable=True, model='Cruzer'),
        {'name': 'loop0', 'path': '/dev/loop0', 'type': 'loop', 'size': 100 * MIB, 'rm': False,
         'children': [], 'mountpoints': ['/run/media/x/loop']},
    ]}


def tree(data: Optional[Dict[str, Any]] = None, windows=None) -> List[Node]:
    return classify(parse_lsblk(json.dumps(data or sample())), windows)


def find(disks: List[Node], path: str) -> Node:
    for d in disks:
        for n in d.walk():
            if n.path == path:
                return n
    raise KeyError(path)


class FakeBackend(Backend):
    """Records every call. Never touches a device."""

    def __init__(self, formats=None, resize_mode: int = 22):
        self.calls: List[tuple] = []
        self._formats = formats or ['ext4', 'btrfs', 'xfs', 'vfat', 'exfat', 'ntfs']
        self.resize_mode = resize_mode
        self.fds: List[int] = []

    def _rec(self, *call):
        self.calls.append(call)

    def mount(self, dev): self._rec('mount', dev); return '/run/media/x/' + os.path.basename(dev)
    def unmount(self, dev): self._rec('unmount', dev)
    def format(self, dev, fstype, label='', zero=False, own=True): self._rec('format', dev, fstype, label, zero)
    def new_table(self, dev, table): self._rec('new_table', dev, table)
    def create_partition(self, disk, offset, size, fstype, label, table):
        self._rec('create', disk, offset, size, fstype, label, table)
    def delete_partition(self, dev): self._rec('delete', dev)
    def resize_partition(self, dev, size): self._rec('resize_partition', dev, size)
    def resize_filesystem(self, dev, size): self._rec('resize_fs', dev, size)
    def can_resize(self, fstype): self._rec('can_resize', fstype); return True, self.resize_mode, ''
    def formats(self): return list(self._formats)
    def eject(self, dev): self._rec('eject', dev)
    def open_device(self, dev, mode): self._rec('open', dev, mode); return self.fds.pop(0)
    def smart(self, dev): self._rec('smart', dev); return {'kind': 'none', 'props': {}, 'attributes': []}
    def smart_update(self, dev): self._rec('smart_update', dev)
    def smart_selftest(self, dev): self._rec('selftest', dev)

    def changed_anything(self) -> bool:
        """True when any call other than a question was made."""
        return any(c[0] not in ('can_resize', 'smart') for c in self.calls)
