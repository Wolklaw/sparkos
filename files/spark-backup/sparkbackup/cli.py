"""The command line. --version, --self-test and --status never load Tk."""

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional

from . import APP_NAME, APP_SLUG, SOURCE, VERSION


def _rsync_check() -> Optional[str]:
    """Copy a small tree twice in a temporary folder: the second copy must share the unchanged
    file with the first (hard link) and a restore must not replace anything. Touches nothing
    outside the temporary folder, and never the real /home."""
    from . import browse
    from .engine import EXCLUDES, RSYNC_POSIX, to_remove

    with tempfile.TemporaryDirectory(prefix="spark-backup-test-") as tmp:
        src, dest = os.path.join(tmp, "src"), os.path.join(tmp, "dest")
        os.makedirs(os.path.join(src, "docs"))
        os.makedirs(dest)
        with open(os.path.join(src, "docs", "a.txt"), "w") as f:
            f.write("one")
        with open(os.path.join(src, "skip.cache"), "w") as f:
            f.write("x")
        os.makedirs(os.path.join(src, ".cache"))
        with open(os.path.join(src, ".cache", "junk"), "w") as f:
            f.write("x")
        first, second = "2026-01-01_020000", "2026-01-02_020000"
        for name, link in ((first, None), (second, first)):
            args = ["rsync"] + RSYNC_POSIX + [f"--exclude={p}" for p in EXCLUDES]
            if link:
                args.append("--link-dest=" + os.path.join(dest, link))
            os.makedirs(os.path.join(dest, name))
            done = subprocess.run(args + [src + "/", os.path.join(dest, name) + "/"],
                                  capture_output=True, text=True, timeout=60)
            if done.returncode not in (0, 24):
                return f"rsync failed: {done.stderr.strip()[:200]}"
        one = os.stat(os.path.join(dest, first, "docs", "a.txt"))
        two = os.stat(os.path.join(dest, second, "docs", "a.txt"))
        if (one.st_ino, one.st_dev) != (two.st_ino, two.st_dev):
            return "an unchanged file was not shared with the previous copy"
        if os.path.exists(os.path.join(dest, second, ".cache")):
            return "an excluded folder was copied"
        live = os.path.join(tmp, "live")
        os.makedirs(live)
        with open(os.path.join(live, "a.txt"), "w") as f:
            f.write("newer")
        when = browse.parse_name(second)
        got = browse.restore(os.path.join(dest, second), "docs/a.txt", live, when, beside=True)
        with open(os.path.join(live, "a.txt")) as f:
            if f.read() != "newer":
                return "a restore replaced a file"
        if not os.path.exists(got.path):
            return "a restore did not copy the file"
        try:
            browse.inside(os.path.join(dest, second), "../x")
            browse.clean_rel("../x")
            return "a path with .. was accepted"
        except browse.BrowseError:
            pass
        names = [f"2026-01-0{d}_020000" for d in range(1, 6)]
        if to_remove(names, 2, protect=[names[0]]) != names[1:3]:
            return "the keep rule removed the wrong snapshots"
    return None


def self_test() -> int:
    from . import config, state, targets
    from .btrfs import Btrfs
    from .runner import Runner
    from .text import EN, FR

    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    for tool in ("btrfs", "rsync", "lsblk", "findmnt", "mount", "umount"):
        path = shutil.which(tool)
        print(f"{tool + ':':10} {path or 'MISSING'}")
        if not path:
            failures.append(tool)
    runner = Runner()
    # read only: where /home lives and whether it can be snapshotted
    print(f"/home:     {'a Btrfs subvolume' if Btrfs(runner).is_subvolume(os.path.realpath(SOURCE)) else 'not a subvolume (a plain image or another layout)'}")
    print(f"drives:    {len(targets.list_drives(runner, SOURCE))} found")
    try:
        config.load()
        print(f"config:    {config.config_path()} {'ok' if os.path.exists(config.config_path()) else 'not saved yet'}")
    except config.ConfigError as exc:
        print(f"config:    {config.config_path()} BROKEN: {exc}")
        failures.append("config")
    print(f"history:   {len(state.load_history()['runs'])} run(s)")
    if set(EN) != set(FR):
        print("text:      English and French tables differ")
        failures.append("text")
    if shutil.which("rsync"):
        problem = _rsync_check()
        print(f"copy test: {problem or 'ok (temporary folder)'}")
        if problem:
            failures.append("copy test")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def status() -> int:
    from . import config, state, targets
    from .app import next_text
    from .btrfs import Btrfs
    from .runner import Runner
    from .text import t

    try:
        cfg = config.load()
    except config.ConfigError as exc:
        print(f"{config.config_path()}: {exc}", file=sys.stderr)
        return 1
    last = state.last_run()
    runner = Runner()
    names = Btrfs(runner).names(os.path.join(os.path.realpath(SOURCE), ".spark-backup", "snapshots"))
    print(t("cli.last", value=(last or {}).get("time") or t("tile.never")))
    print(t("cli.next", value=next_text(cfg, dt.datetime.now())))
    print(t("cli.snapshots", n=len(names)))
    target = cfg.get("target")
    if target:
        found = targets.find(targets.list_drives(runner, SOURCE), target["uuid"])
        print(t("cli.drive", value=found.name if found else t("tile.unplugged")))
    else:
        print(t("cli.drive", value=t("tile.no_drive")))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: snapshots of "
                                     "/home, a copy on another drive, and restore.")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--self-test", action="store_true",
                        help="check what this PC offers (changes nothing)")
    parser.add_argument("--status", action="store_true", help="print the state and exit")
    parser.add_argument("--tab", choices=("backups", "browse", "settings"))
    args = parser.parse_args(argv)
    if args.version:
        print(f"{APP_SLUG} {VERSION}")
        return 0
    if args.self_test:
        return self_test()
    if args.status:
        return status()

    from .log import setup_logging
    setup_logging(to_file=True)
    from .app import App
    App(tab=args.tab).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
