"""Every change to a drive goes through here. Each method looks the device up again in a fresh
tree, asks safety.check, and refuses on its own (Refused) before the backend is touched; for
the hard cases it also needs the device's name typed exactly. The window checks the same rules
to switch its buttons off, but it is this layer that keeps a window bug from reaching a disk."""

import os
from typing import Callable, List, Optional, Tuple

from . import safety
from .log import log
from .model import MIB, Node, drive_of, find, find_free, list_devices
from .udisks import OFFLINE_GROW, OFFLINE_SHRINK, ONLINE_GROW, ONLINE_SHRINK, Backend, DiskError

# longest label each file system takes (bytes)
LABEL_MAX = {'ext2': 16, 'ext3': 16, 'ext4': 16, 'xfs': 12, 'btrfs': 255, 'ntfs': 128,
             'exfat': 15, 'vfat': 11, 'swap': 15, 'f2fs': 512, 'udf': 126, 'nilfs2': 80}
FAT_BAD = set('"*+,./:;<=>?[\\]|')
TABLES = ('gpt', 'dos')


class Refused(Exception):
    """A rule said no. `verdict.key` is a text.py key, `verdict.args` fills it in."""

    def __init__(self, verdict: safety.Verdict):
        super().__init__(verdict.key)
        self.verdict = verdict


class BadInput(Exception):
    """The person asked for something that can't work (a label too long, a size too big)."""

    def __init__(self, key: str, **args):
        super().__init__(key)
        self.key, self.args = key, args


def check_label(fstype: str, label: str) -> None:
    limit = LABEL_MAX.get(fstype)
    if label and limit is not None and len(label.encode('utf-8')) > limit:
        raise BadInput('bad.label_long', n=str(limit))
    if fstype == 'vfat' and any(c in FAT_BAD for c in label):
        raise BadInput('bad.label_chars')
    if '\n' in label or '\x00' in label:
        raise BadInput('bad.label_chars')


def resize_modes(mode: int, mounted: bool, grow: bool) -> Tuple[bool, bool]:
    """(possible, must_unmount) for a resize, from libblockdev's capability bits."""
    offline = OFFLINE_GROW if grow else OFFLINE_SHRINK
    online = ONLINE_GROW if grow else ONLINE_SHRINK
    if mounted:
        if mode & online:
            return True, False
        return bool(mode & offline), True
    return bool(mode & offline or mode & online), False


class Ops:
    def __init__(self, backend: Backend, lister: Callable[[], List[Node]] = list_devices):
        self.backend, self.lister = backend, lister

    # --- the gate
    def _gate(self, action: str, path: str, confirm: str = '') -> Tuple[Node, Node, List[Node]]:
        disks = self.lister()
        node = find(disks, path)
        verdict = safety.check(action, node, disks)
        if not verdict.allowed:
            log.warning('refused %s %s: %s', action, path, verdict.key)
            raise Refused(verdict)
        assert node is not None
        disk = drive_of(disks, node)
        assert disk is not None
        if verdict.hard and confirm != os.path.basename(node.path):
            log.warning('refused %s %s: the device name was not typed', action, path)
            raise Refused(safety.Verdict(False, key='refuse.typed', args={'name': node.name}))
        return node, disk, disks

    def _unmount_all(self, node: Node) -> None:
        for sub in node.walk():
            if sub.kind in ('part', 'disk') and sub.mounts and sub.path:
                log.info('unmount %s first', sub.path)
                self.backend.unmount(sub.path)

    # --- the actions
    def mount(self, path: str) -> str:
        node, _disk, _all = self._gate('mount', path)
        log.info('mount %s', node.path)
        return self.backend.mount(node.path)

    def unmount(self, path: str) -> None:
        node, _disk, _all = self._gate('unmount', path)
        log.info('unmount %s', node.path)
        self.backend.unmount(node.path)

    def format(self, path: str, fstype: str, label: str = '', zero: bool = False,
               confirm: str = '') -> None:
        node, _disk, _all = self._gate('format', path, confirm)
        if fstype not in self.backend.formats():
            raise BadInput('bad.fs_unavailable', fs=fstype)
        check_label(fstype, label)
        self._unmount_all(node)
        log.info('format %s as %s label=%r zero=%s', node.path, fstype, label, zero)
        self.backend.format(node.path, fstype, label, zero)

    def create(self, disk_path: str, start: int, size: int, fstype: str, label: str = '',
               confirm: str = '') -> None:
        disks = self.lister()
        free = find_free(disks, disk_path, start)
        verdict = safety.check('create', free, disks)
        if not verdict.allowed:
            log.warning('refused create on %s: %s', disk_path, verdict.key)
            raise Refused(verdict)
        disk = find(disks, disk_path)
        assert free is not None and disk is not None
        if verdict.hard and confirm != os.path.basename(disk.path):
            raise Refused(safety.Verdict(False, key='refuse.typed', args={'name': disk.name}))
        if size < MIB or size > free.size or size % MIB or start % MIB:
            raise BadInput('bad.size', max=str(free.size))
        if fstype != 'empty' and fstype not in self.backend.formats():
            raise BadInput('bad.fs_unavailable', fs=fstype)
        check_label(fstype, label)
        log.info('create %s at %d size %d as %s label=%r', disk.path, start, size, fstype, label)
        self.backend.create_partition(disk.path, start, size, fstype, label, disk.pttype)

    def delete(self, path: str, confirm: str = '') -> None:
        node, _disk, _all = self._gate('delete', path, confirm)
        self._unmount_all(node)
        log.info('delete partition %s', node.path)
        self.backend.delete_partition(node.path)

    def max_resize(self, node: Node, disks: List[Node]) -> int:
        """The most a partition can grow to: its size plus the free space right after it."""
        disk = drive_of(disks, node)
        room = 0
        if disk is not None:
            for free in disk.children:
                if free.kind == 'free' and free.start <= node.end + MIB and free.end > node.end:
                    room = free.end - node.end
        return node.size + room

    def resize(self, path: str, new_size: int, confirm: str = '') -> None:
        node, _disk, disks = self._gate('resize', path, confirm)
        if new_size == node.size:
            raise BadInput('bad.size', max=str(self.max_resize(node, disks)))
        if new_size % MIB:
            new_size = (new_size // MIB) * MIB
        grow = new_size > node.size
        if new_size < MIB:
            raise BadInput('bad.size', max=str(self.max_resize(node, disks)))
        if grow and new_size > self.max_resize(node, disks):
            raise BadInput('bad.size', max=str(self.max_resize(node, disks)))
        if not grow and node.fsused and new_size < int(node.fsused * 1.05):
            raise BadInput('bad.too_small')
        has_fs = bool(node.fstype) and node.fstype not in ('swap',)
        if has_fs:
            ok, mode, tool = self.backend.can_resize(node.fstype)
            if not ok:
                raise BadInput('bad.cant_resize', fs=node.fstype, tool=tool or '?')
            possible, must_unmount = resize_modes(mode, bool(node.mounts), grow)
            if not possible:
                raise BadInput('bad.cant_resize', fs=node.fstype, tool=tool or '?')
            if must_unmount:
                self._unmount_all(node)
        else:
            self._unmount_all(node)
        log.info('resize %s %s -> %d', node.path, node.size, new_size)
        if grow:                                # the table first, then what is in it
            self.backend.resize_partition(node.path, new_size)
            if has_fs:
                self.backend.resize_filesystem(node.path, new_size)
        else:                                   # the file system first: if it refuses, nothing moved
            if has_fs:
                self.backend.resize_filesystem(node.path, new_size)
            self.backend.resize_partition(node.path, new_size)

    def erase(self, path: str, table: str, confirm: str = '') -> None:
        node, _disk, _all = self._gate('erase', path, confirm)
        if table not in TABLES:
            raise BadInput('bad.table')
        self._unmount_all(node)
        log.info('new %s table on %s', table, node.path)
        self.backend.new_table(node.path, table)

    def eject(self, path: str) -> None:
        node, _disk, _all = self._gate('eject', path)
        self._unmount_all(node)
        log.info('eject %s', node.path)
        self.backend.eject(node.path)

    # --- SMART (read only, allowed on every drive)
    def smart(self, path: str):
        node, _d, _a = self._gate('smart', path)
        return self.backend.smart(node.path)

    def smart_update(self, path: str) -> None:
        node, _d, _a = self._gate('smart', path)
        self.backend.smart_update(node.path)

    def smart_selftest(self, path: str) -> None:
        node, _d, _a = self._gate('smart', path)
        log.info('SMART short self-test on %s', node.path)
        self.backend.smart_selftest(node.path)

    # --- the image writer's gate
    def image_target(self, path: str) -> Node:
        """The drive a bootable image may be written to, or Refused."""
        node, _d, _a = self._gate('write_image', path)
        return node
