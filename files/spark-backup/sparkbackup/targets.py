"""Drives a backup can be copied to: what is plugged in, which ones can hold a copy and how,
and mounting one temporarily when it isn't mounted. Reading the list needs no root."""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import RUN_DIR, TARGET_FOLDER
from .runner import Runner

GIB = 1024 ** 3
# filesystem -> how the copy is made
METHODS = {"btrfs": "btrfs", "ext4": "rsync", "ext3": "rsync", "ext2": "rsync", "xfs": "rsync",
           "f2fs": "rsync", "ntfs": "rsync"}
# filesystems a backup can't live on, and why (shown in Settings)
REFUSED = {"vfat": "refuse.fat", "exfat": "refuse.fat"}
LSBLK = ["lsblk", "-J", "-b", "-o",
         "PATH,LABEL,UUID,FSTYPE,SIZE,FSAVAIL,MOUNTPOINTS,RM,HOTPLUG,TYPE,MODEL"]


@dataclass
class Drive:
    path: str
    label: str
    uuid: str
    fstype: str
    size: int
    free: Optional[int]
    mountpoint: Optional[str]
    removable: bool
    model: str = ""
    method: str = ""            # "btrfs", "rsync", or "" when it can't be used
    reason: str = ""            # text key: why it can't be used

    @property
    def usable(self) -> bool:
        return bool(self.method)

    @property
    def name(self) -> str:
        return self.label or self.model or os.path.basename(self.path)


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _flag(value: Any) -> bool:
    return value in (True, 1, "1", "true")


def _walk(nodes: List[Dict[str, Any]], parent: Optional[Dict[str, Any]] = None):
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node, parent
        yield from _walk(node.get("children") or [], node)


def system_uuid(runner: Runner, source: str) -> str:
    """The filesystem id of the disk the backed-up folder is on."""
    res = runner.run(["findmnt", "-no", "UUID", "-T", source])
    return res.out.strip().splitlines()[0] if res.ok and res.out.strip() else ""


def parse_drives(text: str, source_uuid: str = "") -> List[Drive]:
    try:
        tree = json.loads(text)["blockdevices"]
    except (ValueError, KeyError, TypeError):
        return []
    out: List[Drive] = []
    for node, parent in _walk(tree):
        fstype = (node.get("fstype") or "").lower()
        uuid = node.get("uuid") or ""
        if not fstype or not uuid or node.get("type") in ("rom",):
            continue
        mounts = [m for m in (node.get("mountpoints") or []) if m]
        mount = next((m for m in mounts if m not in ("[SWAP]",)), None)
        size = _int(node.get("size")) or 0
        if fstype in REFUSED:
            if size < GIB or (mount or "").startswith(("/boot", "/efi")):
                continue                       # the EFI partition is not a place for backups
        elif fstype not in METHODS:
            continue                           # swap, LUKS, LVM and so on: not a backup place
        removable = _flag(node.get("rm")) or _flag(node.get("hotplug")) \
            or (parent is not None and (_flag(parent.get("rm")) or _flag(parent.get("hotplug"))))
        drive = Drive(path=node.get("path") or "", label=node.get("label") or "", uuid=uuid,
                      fstype=fstype, size=size, free=_int(node.get("fsavail")),
                      mountpoint=mount, removable=removable,
                      model=(parent or node).get("model") or "")
        if fstype in REFUSED:
            drive.reason = REFUSED[fstype]
        elif source_uuid and uuid == source_uuid:
            drive.reason = "refuse.system"
        elif mount in ("/", "/boot", "/usr") or (mount or "").startswith(("/sysroot", "/boot")):
            drive.reason = "refuse.system"
        else:
            drive.method = METHODS[fstype]
        out.append(drive)
    # one entry per filesystem (a btrfs with several subvolumes mounted shows up once)
    seen: Dict[str, Drive] = {}
    for drive in out:
        if drive.uuid not in seen or (drive.mountpoint and not seen[drive.uuid].mountpoint):
            seen[drive.uuid] = drive
    return sorted(seen.values(), key=lambda d: (not d.usable, d.name.lower()))


def list_drives(runner: Optional[Runner] = None, source: str = "/home") -> List[Drive]:
    runner = runner or Runner()
    res = runner.run(LSBLK)
    if not res.ok:                      # an older lsblk without the free-space column
        res = runner.run(LSBLK[:-1] + [LSBLK[-1].replace("FSAVAIL,", "")])
    return parse_drives(res.out, system_uuid(runner, source)) if res.ok else []


def find(drives: List[Drive], uuid: str) -> Optional[Drive]:
    return next((d for d in drives if d.uuid == uuid), None)


def host_name() -> str:
    import socket
    return re.sub(r"[^A-Za-z0-9._-]", "_", socket.gethostname().split(".")[0]) or "sparkos"


def backup_root(mountpoint: str, host: str = "") -> str:
    """The one folder this app uses on a drive."""
    return os.path.join(mountpoint, TARGET_FOLDER, host or host_name())


def mount_temporarily(drive: Drive, runner: Runner,
                      base: str = "") -> Tuple[Optional[str], bool, str]:
    """(mount point, mounted by us, error). A drive that is already mounted is used where it
    is. Otherwise it is mounted under /run/spark-backup/mnt by its UUID (never by device
    name, which can change) and the caller unmounts it afterwards."""
    if drive.mountpoint:
        return drive.mountpoint, False, ""
    base = base or os.path.join(RUN_DIR, "mnt")
    where = os.path.join(base, re.sub(r"[^0-9A-Za-z-]", "", drive.uuid))
    try:
        os.makedirs(where, mode=0o700, exist_ok=True)
    except OSError as exc:
        return None, False, str(exc)
    res = runner.run(["mount", "-o", "nosuid,nodev", f"UUID={drive.uuid}", where])
    if not res.ok:
        try:
            os.rmdir(where)
        except OSError:
            pass
        return None, False, res.message()
    return where, True, ""


def unmount(where: str, runner: Runner) -> None:
    if runner.run(["umount", where]).ok:
        try:
            os.rmdir(where)
        except OSError:
            pass


LiveDrives = Callable[[], List[Drive]]
