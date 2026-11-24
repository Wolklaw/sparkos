"""Shared by the tests. Nothing here touches the real /home or a real disk: snapshots are plain
folders in a temporary directory, and every command goes through a fake runner."""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for _var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(_var, tempfile.mkdtemp(prefix=f'spark-backup-{_var.lower()}-'))

from sparkbackup.btrfs import Btrfs  # noqa: E402
from sparkbackup.runner import Result, Runner  # noqa: E402
from sparkbackup.targets import Drive  # noqa: E402


class FakeRunner(Runner):
    """Records every command. `answers` maps the first word(s) of a command to a Result; a
    command it doesn't know succeeds with no output. `real` lets rsync through."""

    def __init__(self, answers=None, real=()):
        self.calls = []
        self.answers = answers or {}
        self.real = set(real)

    def run(self, argv, input=None, timeout=None):
        argv = list(argv)
        self.calls.append(argv)
        if argv[0] in self.real:
            return Runner.run(self, argv, input, timeout)
        for key, result in self.answers.items():
            if " ".join(argv).startswith(key):
                return result(argv) if callable(result) else result
        return Result(0, "", "")

    def pipe(self, first, second):
        self.calls.append(list(first) + ["|"] + list(second))
        for key, result in self.answers.items():
            if key == "pipe":
                return result
        return Result(0), Result(0)

    def commands(self, word):
        return [c for c in self.calls if c[0] == word]


class FakeBtrfs(Btrfs):
    """A 'subvolume' is any real folder; a snapshot is a copy of the folder. The tests never
    run `btrfs`."""

    def __init__(self, runner=None, unfinished=()):
        super().__init__(runner or FakeRunner())
        self.unfinished = set(unfinished)
        self.deleted = []

    def is_subvolume(self, path):
        return os.path.isdir(path) and not os.path.islink(path)

    def is_readonly(self, path):
        return os.path.basename(path) not in self.unfinished

    def snapshot(self, source, dest):
        shutil.copytree(source, dest, symlinks=True,
                        ignore=shutil.ignore_patterns(".spark-backup"))
        return Result(0)

    def delete(self, path):
        self.deleted.append(path)
        shutil.rmtree(path, ignore_errors=True)
        return Result(0)

    def send_receive(self, snapshot, dest_dir, parent=None):
        self.runner.calls.append(["send", snapshot, parent or "", dest_dir])
        if not getattr(self, "fail_receive", False):
            shutil.copytree(snapshot, os.path.join(dest_dir, os.path.basename(snapshot)),
                            symlinks=True)
            return Result(0), Result(0)
        os.makedirs(os.path.join(dest_dir, os.path.basename(snapshot)))
        return Result(0), Result(1, "", "ERROR: cannot receive")


def drive(uuid="AAAA-1111", fstype="ext4", mountpoint=None, method="rsync", reason="", **kw):
    return Drive(path="/dev/fake1", label=kw.pop("label", "Backup"), uuid=uuid, fstype=fstype,
                 size=500 * 1024 ** 3, free=300 * 1024 ** 3, mountpoint=mountpoint,
                 removable=True, method=method, reason=reason, **kw)


def make_home(root):
    """A little /home with a user, a file, a folder, and the app's own snapshot folder."""
    home = os.path.join(root, "home")
    os.makedirs(os.path.join(home, "alex", "docs"))
    with open(os.path.join(home, "alex", "docs", "note.txt"), "w") as f:
        f.write("hello")
    with open(os.path.join(home, "alex", "top.txt"), "w") as f:
        f.write("top")
    return home
