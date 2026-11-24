"""Write a disk image (.iso, .img, and those packed as .gz, .xz or .bz2) to a USB stick or SD
card, then read it back and compare. udisks opens the device for us (a file descriptor), so this
runs as the user. The target goes through ops.image_target first: removable drives only, never
the system's or D:'s."""

import bz2
import gzip
import hashlib
import lzma
import os
import threading
from typing import Callable, IO, Optional

from .log import log
from .model import Node
from .ops import BadInput, Ops
from .udisks import Backend

CHUNK = 4 * 1024 * 1024
OPENERS = {'.gz': gzip.open, '.xz': lzma.open, '.bz2': bz2.open}

Progress = Callable[[str, int, int], None]      # phase ('write' or 'verify'), done, total (0 = unknown)


class Cancelled(Exception):
    pass


class VerifyFailed(Exception):
    def __init__(self, offset: int):
        super().__init__(f'differs at byte {offset}')
        self.offset = offset


def packed(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in OPENERS


def open_image(path: str) -> IO[bytes]:
    opener = OPENERS.get(os.path.splitext(path)[1].lower())
    return opener(path, 'rb') if opener else open(path, 'rb')    # type: ignore[operator]


def image_size(path: str) -> int:
    """The image's size in bytes, or 0 when it is packed (the size is not known before reading)."""
    return 0 if packed(path) else os.path.getsize(path)


def check_image(path: str) -> None:
    """Raise BadInput when the file can't be an image."""
    if not os.path.isfile(path):
        raise BadInput('bad.image_missing')
    if not packed(path) and os.path.getsize(path) == 0:
        raise BadInput('bad.image_empty')
    try:
        with open_image(path) as f:
            if not f.read(512):
                raise BadInput('bad.image_empty')
    except (OSError, EOFError, lzma.LZMAError):
        raise BadInput('bad.image_unreadable') from None


def _same_device(fd: int, path: str) -> bool:
    """The descriptor udisks handed back is the device we asked for (when /dev has it)."""
    try:
        return os.stat(path).st_rdev == os.fstat(fd).st_rdev
    except OSError:
        return True


def write_image(ops: Ops, backend: Backend, image: str, dev: str, progress: Progress,
                cancel: threading.Event, verify: bool = True) -> Node:
    """Write `image` to `dev`. Raises Refused (not allowed), BadInput, Cancelled, VerifyFailed,
    DiskError or OSError. Returns the target as it was."""
    target = ops.image_target(dev)
    check_image(image)
    size = image_size(image)
    if size and size > target.size:
        raise BadInput('bad.image_big', image=str(size), drive=str(target.size))
    ops._unmount_all(target)
    log.info('write %s to %s (%d bytes, verify=%s)', image, target.path, size, verify)
    fd = backend.open_device(target.path, 'w')
    try:
        if not _same_device(fd, target.path):
            raise OSError('the device udisks opened is not ' + target.path)
        done = 0
        digest = hashlib.sha256()
        with open_image(image) as source:
            while True:
                if cancel.is_set():
                    raise Cancelled()
                chunk = source.read(CHUNK)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                done += len(chunk)
                digest.update(chunk)
                progress('write', done, size)
        os.fsync(fd)
    finally:
        os.close(fd)
    if verify:
        _verify(backend, target.path, image, done, progress, cancel)
    log.info('wrote %d bytes to %s, sha256 %s', done, target.path, digest.hexdigest())
    return target


def _verify(backend: Backend, dev: str, image: str, length: int, progress: Progress,
            cancel: threading.Event) -> None:
    fd = backend.open_device(dev, 'r')
    try:
        offset = 0
        with open_image(image) as source, os.fdopen(fd, 'rb', closefd=False) as device:
            while offset < length:
                if cancel.is_set():
                    raise Cancelled()
                want = source.read(CHUNK)
                if not want:
                    break
                got = device.read(len(want))
                if got != want:
                    raise VerifyFailed(offset)
                offset += len(want)
                progress('verify', offset, length)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
