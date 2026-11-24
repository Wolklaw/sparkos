"""The rules that keep a slip from costing the owner a drive. Pure functions, no text and no I/O:
a Verdict carries a key the window turns into a sentence (text.py), and ops.py asks again right
before it acts, so a bug in the window can't skip a rule.

  locked   D: and the drive it sits on: nothing but look (and read SMART)
  system   what the running system stands on: can't be unmounted, formatted, deleted or resized
  hard     Windows partitions, anything on the system disk, any other internal drive: the person
           types the device name before the button works
  ordinary removable drives: the dialog shows the facts, Cancel is the default
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import SWAP_AND_FRIENDS, Node, drive_of, is_system_mount, removable_drive

ACTIONS = ('mount', 'unmount', 'format', 'create', 'delete', 'resize', 'erase', 'eject',
           'write_image', 'smart')
DESTRUCTIVE = ('format', 'create', 'delete', 'resize', 'erase', 'write_image')


@dataclass
class Verdict:
    allowed: bool
    level: str = ''                           # '' (no confirmation), 'ordinary' or 'hard'
    key: str = ''                             # the reason, when refused (a text.py key)
    args: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)   # extra warnings for the dialog (keys)

    @property
    def hard(self) -> bool:
        return self.level == 'hard'


def _no(key: str, **args) -> Verdict:
    return Verdict(False, key=key, args=args)


def confirm_level(node: Node, disk: Node) -> str:
    """How hard the confirmation is for changing this row."""
    if node.windows or node.is_system or disk.is_system or not removable_drive(disk):
        return 'hard'
    return 'ordinary'


def check(action: str, node: Optional[Node], disks: List[Node]) -> Verdict:
    """May `action` happen to `node` (a drive, a partition or a free-space row)? `disks` is the
    fresh tree. For 'write_image' the node is the target drive."""
    if node is None:
        return _no('refuse.gone')
    disk = drive_of(disks, node)
    if disk is None:
        return _no('refuse.gone')
    if action not in ACTIONS:
        return _no('refuse.unknown', action=action)
    if action == 'smart':
        return Verdict(node.kind == 'disk', key='' if node.kind == 'disk' else 'refuse.not_drive')

    # D: and its drive are look-only, whatever the action
    if node.is_d or disk.is_d:
        return _no('refuse.d')
    if node.kind == 'other' or node.container:
        return _no('refuse.stacked' if node.kind == 'other' else 'refuse.container')
    if node.read_only and action in DESTRUCTIVE:
        return _no('refuse.read_only')

    if action == 'mount':
        if node.kind == 'free' or not node.fstype or node.fstype in SWAP_AND_FRIENDS:
            return _no('refuse.no_filesystem')
        if node.mounts:
            return _no('refuse.already_mounted')
        return Verdict(True)
    if action == 'unmount':
        if node.is_system or any(is_system_mount(m) for m in node.mounts):
            return _no('refuse.system', device=node.path)
        if not node.mounts or node.kind == 'free':
            return _no('refuse.not_mounted')
        return Verdict(True)
    if action == 'eject':
        if node.kind != 'disk' or not removable_drive(node):
            return _no('refuse.not_removable')
        if node.is_system:
            return _no('refuse.system', device=node.path)
        return Verdict(True)

    # everything below changes data
    if node.is_system:
        return _no('refuse.system_disk' if node.kind == 'disk' and action == 'erase'
                   else 'refuse.system', device=node.path)
    if action == 'write_image':
        if node.kind != 'disk':
            return _no('refuse.not_drive')
        if not removable_drive(node):
            return _no('refuse.not_removable')
        return Verdict(True, 'ordinary')
    level = confirm_level(node, disk)
    if action == 'create':
        if node.kind != 'free':
            return _no('refuse.not_free')
        if disk.pttype == 'dos' and sum(1 for c in disk.children if c.kind == 'part') >= 4:
            return _no('refuse.four_primary')
        return Verdict(True, level)
    if action == 'erase':
        if node.kind != 'disk':
            return _no('refuse.not_drive')
        return Verdict(True, level, notes=['note.all_lost'])
    if node.kind == 'free':
        return _no('refuse.is_free')
    if action == 'format':
        if node.kind == 'disk' and node.pttype:
            return _no('refuse.has_table')            # erase it (a new table) instead
        return Verdict(True, level, notes=['note.unmounted_first'] if node.mounts else [])
    if action in ('delete', 'resize'):
        if node.kind != 'part':
            return _no('refuse.not_partition')
        return Verdict(True, level, notes=['note.unmounted_first'] if node.mounts else [])
    return _no('refuse.unknown', action=action)


def tag_for(node: Node) -> str:
    """The short tag a row wears: D:, SYSTEM, WINDOWS, USB (key part of text.py)."""
    if node.is_d:
        return 'tag.d'
    if node.is_system:
        return 'tag.system'
    if node.windows:
        return 'tag.windows'
    if node.kind == 'disk' and removable_drive(node):
        return 'tag.usb'
    return ''
