"""Storage: the mounted drives with free space (lsblk), file indexing on or off, and a way into
Spark Disks, which mounts, formats and checks drives. Spark Settings doesn't mount or format."""

import json
from typing import List, Optional

from . import core, plasma
from .core import have, run, spawn

SKIP_MOUNTS = ('/boot', '/boot/efi', '/sysroot', '/etc', '/usr', '/var', '/run', '[SWAP]')


class Volume:
    def __init__(self, name: str, label: str, mount: str, fstype: str, size: int, free: int,
                 removable: bool):
        self.name, self.label, self.mount, self.fstype = name, label, mount, fstype
        self.size, self.free, self.removable = size, free, removable

    @property
    def title(self) -> str:
        return self.label or self.name


def parse_lsblk(text: str) -> List[Volume]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    found: List[Volume] = []

    def walk(node: dict, removable: bool) -> None:
        rm = removable or bool(node.get('rm'))
        mount = node.get('mountpoint')
        if mount and node.get('fstype') and mount not in SKIP_MOUNTS and \
                not str(mount).startswith(('/boot', '/sysroot', '/var/lib', '/run/', '/etc/')):
            size = int(node.get('size') or 0)
            free = node.get('fsavail')
            found.append(Volume(node.get('name', ''), node.get('label') or '', mount,
                                node.get('fstype') or '', size, int(free) if free else 0, rm))
        for child in node.get('children') or []:
            walk(child, rm)

    for dev in data.get('blockdevices', []):
        walk(dev, False)
    return found


def volumes() -> List[Volume]:
    rc, text, _ = run(['lsblk', '-J', '-b', '-o', 'NAME,LABEL,SIZE,FSTYPE,MOUNTPOINT,RM,FSAVAIL'])
    return parse_lsblk(text) if rc == 0 else []


def indexing() -> Optional[bool]:
    saved = core.spark_load('storage').get('indexing')
    return saved if isinstance(saved, bool) else plasma.baloo_enabled()


def set_indexing(on: bool) -> bool:
    ok = core.spark_save('storage', indexing=on)
    return plasma.baloo_set(on) and ok


def open_disks() -> bool:
    return have('spark-disks') and spawn(['spark-disks'])


def open_folder(path: str) -> bool:
    return spawn(['spark-files', path] if have('spark-files') else ['xdg-open', path])
