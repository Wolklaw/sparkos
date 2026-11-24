"""One backup run: snapshot, copy to the drive, remove what is past the limit. Runs as root from
the systemd service. Every command goes through the Runner and every Btrfs call through Btrfs, so
the tests drive it with fakes and a temporary folder, never a real disk."""

import contextlib
import datetime as dt
import fcntl
import os
import shutil
import stat
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set

from . import SNAP_FOLDER, SOURCE, state, targets
from .btrfs import Btrfs, is_name, snapshot_name
from .log import log
from .runner import Runner

# What is not copied to a drive that holds plain folders (rsync). A Btrfs drive gets the whole
# snapshot, because a send stream can't leave things out. Anchored with a leading slash means
# "at the top of /home".
EXCLUDES = ("/.spark-backup/", "/lost+found/", ".cache/", ".local/share/Trash/",
            "steamapps/common/", "steamapps/shadercache/", "steamapps/downloading/",
            "steamapps/temp/", ".var/app/*/cache/")
RSYNC_POSIX = ["-aH", "--numeric-ids", "--acls", "--xattrs"]
RSYNC_NTFS = ["-rlt", "--no-perms", "--no-owner", "--no-group", "--modify-window=1"]
RSYNC_OK = (0, 24)               # 24: a file vanished while it was read
RSYNC_PARTIAL = 23               # some files could not be copied; the rest is there


class BackupError(Exception):
    pass


def to_remove(names: Iterable[str], keep: int, protect: Iterable[str] = ()) -> List[str]:
    """The names past the limit, oldest first. The newest `keep` stay, the newest of all stays
    whatever `keep` says, and so does anything in `protect`."""
    ordered = sorted(names)
    stay: Set[str] = set(ordered[-max(1, keep):]) | {p for p in protect if p in ordered}
    return [n for n in ordered if n not in stay]


@contextlib.contextmanager
def exclusive(path: str) -> Iterator[None]:
    """Only one run at a time: the timer and 'Back up now' can't overlap."""
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    handle = open(path, "a+")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BackupError("busy") from exc
        yield
    finally:
        handle.close()


def _rmtree(path: str) -> None:
    def fix(func, p, _info):
        try:
            os.chmod(os.path.dirname(p), stat.S_IRWXU)
            os.chmod(p, stat.S_IRWXU)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=fix)


def _open_dir(name: str, dir_fd: int) -> int:
    """Open a folder by name under `dir_fd`, never following a symlink in the last step."""
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                   dir_fd=dir_fd)


@contextlib.contextmanager
def anchored_root(mountpoint: str, host: str) -> Iterator[str]:
    """The backup folder on a drive, as a path that stays on the folder we checked.

    The service runs as root, but a Windows drive is mounted as the user, so the user (or any
    program running as them) can swap SparkBackup/ or SparkBackup/<host>/ for a symlink. Each
    level is created or opened by name with O_NOFOLLOW|O_DIRECTORY, relative to the fd of the
    level above, so a symlink is refused and a swap after the check can't redirect us. The
    path given back is /proc/<pid>/fd/N of the final folder: it names that very inode."""
    fds: List[int] = []
    try:
        try:
            fd = os.open(mountpoint, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            fds.append(fd)
            for part in targets.backup_parts(host):
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
                fd = _open_dir(part, fd)
                fds.append(fd)
        except OSError as exc:
            raise BackupError(f"{mountpoint} has a backup folder that is not a plain folder "
                              f"({exc.strerror or exc}); not writing to it") from exc
        yield f"/proc/{os.getpid()}/fd/{fd}"
    finally:
        for f in fds:
            os.close(f)


class Backup:
    def __init__(self, cfg: Dict[str, Any], runner: Optional[Runner] = None,
                 fs: Optional[Btrfs] = None, source: str = "",
                 drives: Optional[Callable[[], List[targets.Drive]]] = None,
                 now: Optional[Callable[[], dt.datetime]] = None,
                 progress: Optional[Callable[[str, str], None]] = None,
                 mount_base: str = "", host: str = ""):
        self.cfg = cfg
        self.runner = runner or Runner()
        self.fs = fs or Btrfs(self.runner)
        # /home is a link to /var/home on this system: work on the real folder
        self.source = os.path.realpath(source or os.environ.get("SPARK_BACKUP_SOURCE") or SOURCE)
        self._drives = drives or (lambda: targets.list_drives(self.runner, self.source))
        self.now = now or dt.datetime.now
        self.progress = progress or state.write_progress
        self.mount_base = mount_base
        self.host = host or targets.host_name()

    @property
    def snap_dir(self) -> str:
        return os.path.join(self.source, SNAP_FOLDER)

    def lock_path(self) -> str:
        return os.path.join(state.run_dir(), "lock")

    def local(self) -> List[str]:
        return self.fs.names(self.snap_dir)

    # — removing —
    def remove_local(self, name: str) -> None:
        """Delete one snapshot of ours. Only a name we would have made, only a subvolume in
        our own folder."""
        if not is_name(name):
            raise BackupError(f"not a snapshot name: {name!r}")
        path = os.path.join(self.snap_dir, name)
        if os.path.dirname(os.path.realpath(path)) != os.path.realpath(self.snap_dir) \
                or not self.fs.is_subvolume(path):
            raise BackupError(f"not a snapshot: {name}")
        res = self.fs.delete(path)
        if not res.ok:
            raise BackupError(res.message())

    def _remove_copy(self, root: str, name: str, method: str) -> None:
        if not is_name(name):
            raise BackupError(f"not a copy name: {name!r}")
        path = os.path.join(root, name)
        if os.path.islink(path) or os.path.dirname(os.path.realpath(path)) != os.path.realpath(root):
            raise BackupError(f"not a copy: {name}")
        if method == "btrfs":
            if not self.fs.is_subvolume(path):
                raise BackupError(f"not a copy: {name}")
            res = self.fs.delete(path)
            if not res.ok:
                raise BackupError(res.message())
        elif os.path.isdir(path):
            _rmtree(path)

    def copy_names(self, root: str, method: str, check: bool = True) -> List[str]:
        """The finished copies in a backup folder on a drive, oldest first. `check` asks Btrfs
        whether each one is complete (root only); the window skips it and lists what is there."""
        if method == "btrfs":
            return [n for n in self.fs.names(root)
                    if not check or self.fs.is_readonly(os.path.join(root, n))]
        try:
            found = os.listdir(root)
        except OSError:
            return []
        return sorted(n for n in found if is_name(n)
                      and os.path.isdir(os.path.join(root, n))
                      and not os.path.islink(os.path.join(root, n)))

    # — copying —
    def _copy_btrfs(self, name: str, root: str) -> int:
        have = self.copy_names(root, "btrfs")
        if name in have:
            return 0
        common = [n for n in have if n in self.local()]
        parent = os.path.join(self.snap_dir, common[-1]) if common else None
        dest = os.path.join(root, name)
        sent, received = self.fs.send_receive(os.path.join(self.snap_dir, name), root, parent)
        if sent.ok and received.ok:
            return 0
        if os.path.isdir(dest) and not os.path.islink(dest) and name not in have \
                and self.fs.is_subvolume(dest):
            self.fs.delete(dest)           # only the half-received copy we just started
        raise BackupError((received if not received.ok else sent).message())

    def _copy_rsync(self, name: str, root: str, fstype: str) -> int:
        final = os.path.join(root, name)
        partial = final + ".partial"
        if os.path.isdir(partial) and not os.path.islink(partial):
            _rmtree(partial)                # left by an interrupted run
        have = [n for n in self.copy_names(root, "rsync") if n != name]
        args = ["rsync"] + (RSYNC_NTFS if fstype == "ntfs" else RSYNC_POSIX)
        args += [f"--exclude={p}" for p in EXCLUDES]
        if have:
            args.append("--link-dest=" + os.path.join(root, have[-1]))
        # `root` is fd-anchored. Make the partial folder fresh, open it without following
        # links and hand rsync that fd's path, so it can't be swapped for a symlink mid-run.
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            try:
                os.mkdir(name + ".partial", 0o755, dir_fd=root_fd)
            except FileExistsError:
                pass
            try:
                part_fd = _open_dir(name + ".partial", root_fd)
            except OSError as exc:
                raise BackupError(f"{name}.partial is not a plain folder ({exc.strerror})") from exc
            try:
                res = self.runner.run(args + [os.path.join(self.snap_dir, name) + "/",
                                              f"/proc/{os.getpid()}/fd/{part_fd}/"])
            finally:
                os.close(part_fd)
            if res.code in RSYNC_OK or res.code == RSYNC_PARTIAL:
                os.rename(name + ".partial", name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        finally:
            os.close(root_fd)
        if res.code in RSYNC_OK or res.code == RSYNC_PARTIAL:
            if res.code == RSYNC_PARTIAL:
                return sum(1 for line in res.err.splitlines() if line.startswith("rsync:"))
            return 0
        _rmtree(partial)
        raise BackupError(res.message())

    def _copy(self, name: str, report: Dict[str, Any]) -> None:
        target = self.cfg.get("target")
        if not target:
            report["copy"] = "none"
            return
        drive = targets.find(self._drives(), target["uuid"])
        if drive is None:
            report["copy"] = "unplugged"
            return
        if not drive.usable:
            report["copy"] = "failed"
            report["error"] = f"{drive.name} can't hold backups ({drive.reason})"
            return
        where, ours, err = targets.mount_temporarily(drive, self.runner, self.mount_base)
        if where is None:
            report["copy"] = "failed"
            report["error"] = f"can't mount {drive.name}: {err}"
            return
        try:
            with anchored_root(where, self.host) as root:
                self.progress("copy", drive.name)
                if drive.method == "btrfs":
                    report["warnings"] = self._copy_btrfs(name, root)
                else:
                    report["warnings"] = self._copy_rsync(name, root, drive.fstype)
                report["copy"] = drive.method
                report["copied"] = name
                self.progress("prune", drive.name)
                keep = int(self.cfg["keep_target"])
                for old in to_remove(self.copy_names(root, drive.method), keep):
                    self._remove_copy(root, old, drive.method)
                    report["removed_copies"] += 1
        except (BackupError, OSError) as exc:
            log.warning("copy to %s failed: %s", drive.name, exc)
            report["copy"] = "failed"
            report["error"] = str(exc)
        finally:
            if ours:
                targets.unmount(where, self.runner)

    # — the run —
    def run(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "time": self.now().strftime("%Y-%m-%d %H:%M:%S"), "ok": False, "snapshot": "",
            "copy": "none", "copied": "", "warnings": 0, "removed": 0, "removed_copies": 0,
            "error": ""}
        with exclusive(self.lock_path()):
            try:
                self._run(report)
            except (BackupError, OSError) as exc:
                log.error("backup failed: %s", exc)
                report["error"] = report["error"] or str(exc)
            finally:
                report["ok"] = bool(report["snapshot"]) and report["copy"] != "failed" \
                    and not report["error"]
                state.add_run({k: v for k, v in report.items() if k != "copied"},
                              copied=report["copied"])
                state.clear_progress()
        return report

    def _run(self, report: Dict[str, Any]) -> None:
        if not self.fs.is_subvolume(self.source):
            raise BackupError(f"{self.source} is not a Btrfs subvolume, so it can't be "
                              "snapshotted")
        os.makedirs(self.snap_dir, mode=0o755, exist_ok=True)
        name = snapshot_name(self.now())
        path = os.path.join(self.snap_dir, name)
        if os.path.lexists(path):
            raise BackupError(f"{name} already exists (two runs in the same second)")
        self.progress("snapshot", name)
        res = self.fs.snapshot(self.source, path)
        if not res.ok:
            raise BackupError(res.message())
        report["snapshot"] = name
        self._copy(name, report)
        self.progress("prune", "")
        history = state.load_history()
        protect = {history["last_copied"], report["copied"], name}
        for old in to_remove(self.local(), int(self.cfg["keep_local"]), protect):
            try:
                self.remove_local(old)
                report["removed"] += 1
            except BackupError as exc:
                log.warning("could not remove %s: %s", old, exc)
