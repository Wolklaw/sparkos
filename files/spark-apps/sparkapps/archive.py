"""Safe extraction of an app bundle (a .tar.gz).

The bundle is already pinned by a signed sha256, but it is still unpacked as if it were hostile:
only plain files and folders; no absolute paths, no "..", no links, devices or fifos; no repeated
names; limits on entries, depth and unpacked size. Nothing from the archive's own owner, group or
mode is used: folders end up 0755 and files 0644, owned by whoever runs this (root).
Files are written by this code, never by tarfile's extractall.
"""

import os
import shutil
import tarfile

from . import MAX_ENTRIES, MAX_PATH_DEPTH, MAX_UNPACKED_BYTES


class ArchiveError(Exception):
    pass


def _clean(name: str) -> str:
    if not name or '\0' in name or '\\' in name or len(name) > 240:
        raise ArchiveError(f"bad name in the bundle: {name!r}")
    if name.startswith('/'):
        raise ArchiveError(f"absolute path in the bundle: {name!r}")
    parts = name.split('/')
    if parts and parts[-1] == '':          # a folder may end with a slash
        parts.pop()
    if not parts or any(p in ('', '.', '..') for p in parts) or len(parts) > MAX_PATH_DEPTH:
        raise ArchiveError(f"bad path in the bundle: {name!r}")
    return '/'.join(parts)


def extract(archive: str, dest: str, max_unpacked: int = MAX_UNPACKED_BYTES) -> int:
    """Unpack `archive` into the new, empty folder `dest` (created here, 0755). Returns the
    number of files. On any problem the half-written folder is removed and ArchiveError raised."""
    os.makedirs(dest, mode=0o755)
    seen = set()
    files = total = entries = 0
    try:
        try:
            tar = tarfile.open(archive, 'r:gz')
        except (tarfile.TarError, OSError, EOFError) as exc:
            raise ArchiveError(f"can't read the bundle: {exc}") from None
        with tar:
            for member in tar:
                entries += 1
                if entries > MAX_ENTRIES:
                    raise ArchiveError("too many files in the bundle")
                rel = _clean(member.name)
                if rel in seen:
                    raise ArchiveError(f"{rel} appears twice in the bundle")
                seen.add(rel)
                target = os.path.join(dest, *rel.split('/'))
                if member.isdir():
                    try:
                        os.mkdir(target, 0o755)
                    except FileExistsError:
                        if not os.path.isdir(target) or os.path.islink(target):
                            raise ArchiveError(f"{rel} clashes with another entry") from None
                    except OSError as exc:
                        raise ArchiveError(f"can't create {rel}: {exc}") from None
                    os.chmod(target, 0o755)
                elif member.isreg():
                    total += member.size
                    if total > max_unpacked:
                        raise ArchiveError("the bundle unpacks to more than the limit")
                    parent = os.path.dirname(target)
                    try:
                        os.makedirs(parent, mode=0o755, exist_ok=True)
                        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                     | os.O_NOFOLLOW, 0o644)
                    except OSError as exc:
                        raise ArchiveError(f"can't create {rel}: {exc}") from None
                    source = tar.extractfile(member)
                    if source is None:
                        os.close(fd)
                        raise ArchiveError(f"can't read {rel}")
                    written = 0
                    with os.fdopen(fd, 'wb') as out, source:
                        while True:
                            block = source.read(65536)
                            if not block:
                                break
                            written += len(block)
                            if written > member.size:
                                raise ArchiveError(f"{rel} is bigger than it says")
                            out.write(block)
                    os.chmod(target, 0o644)
                    files += 1
                else:
                    raise ArchiveError(f"{rel} is a link or a special file: not allowed")
    except (ArchiveError, tarfile.TarError, EOFError, OSError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        if isinstance(exc, ArchiveError):
            raise
        raise ArchiveError(f"can't unpack the bundle: {exc}") from None
    if not files:
        shutil.rmtree(dest, ignore_errors=True)
        raise ArchiveError("the bundle is empty")
    return files
