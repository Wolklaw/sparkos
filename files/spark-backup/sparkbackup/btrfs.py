"""Btrfs, and the names snapshots carry. Only this file builds btrfs command lines."""

import datetime as dt
import os
import re
from typing import List, Optional, Tuple

from .runner import Result, Runner

NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
SUBVOLUME_INODE = 256        # the root directory of every Btrfs subvolume has this inode


def snapshot_name(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%d_%H%M%S")


def parse_name(name: str) -> Optional[dt.datetime]:
    if not NAME_RE.match(name):
        return None
    try:
        return dt.datetime.strptime(name, "%Y-%m-%d_%H%M%S")
    except ValueError:
        return None


def is_name(name: str) -> bool:
    return parse_name(name) is not None


class Btrfs:
    def __init__(self, runner: Optional[Runner] = None):
        self.runner = runner or Runner()

    def is_subvolume(self, path: str) -> bool:
        """A Btrfs subvolume's root directory always has inode 256 (a plain folder can't)."""
        try:
            info = os.stat(path)
        except OSError:
            return False
        return os.path.isdir(path) and not os.path.islink(path) and info.st_ino == SUBVOLUME_INODE

    def is_readonly(self, path: str) -> bool:
        """A copy that `btrfs receive` finished is read only; one that was cut short is not."""
        res = self.runner.run(["btrfs", "property", "get", "-ts", path, "ro"])
        return res.ok and "ro=true" in res.out

    def snapshot(self, source: str, dest: str) -> Result:
        return self.runner.run(["btrfs", "subvolume", "snapshot", "-r", source, dest])

    def delete(self, path: str) -> Result:
        return self.runner.run(["btrfs", "subvolume", "delete", path])

    def send_receive(self, snapshot: str, dest_dir: str,
                     parent: Optional[str] = None) -> Tuple[Result, Result]:
        send = ["btrfs", "send"] + (["-p", parent] if parent else []) + [snapshot]
        return self.runner.pipe(send, ["btrfs", "receive", dest_dir])

    def names(self, folder: str) -> List[str]:
        """The snapshots in a folder, oldest first: only names we made, only subvolumes."""
        try:
            found = os.listdir(folder)
        except OSError:
            return []
        return sorted(n for n in found if is_name(n) and self.is_subvolume(os.path.join(folder, n)))
