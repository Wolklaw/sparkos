"""The command line. --version, --self-test and --list never load Tk and never change anything."""

import argparse
import shutil
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test() -> int:
    from . import safety
    from .model import Node, classify, free_spaces, list_devices, parse_lsblk
    from .text import EN, FR

    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors="replace")      # a C locale can't print every sign
    except (AttributeError, ValueError):
        pass
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio  # noqa: F401
        print(f"PyGObject: {gi.__version__}")
        gio = True
    except (ImportError, ValueError) as exc:
        print(f"PyGObject: MISSING ({exc})")
        failures.append("PyGObject")
        gio = False
    for tool in ("lsblk", "smartctl"):
        found = shutil.which(tool)
        print(f"{tool + ':':10} {found or 'not installed'}")
        if tool == "lsblk" and not found:
            failures.append("lsblk")
    if gio:
        from .udisks import DiskError, Udisks
        try:
            formats = Udisks().formats()
            print(f"udisks2:   reachable, can make {', '.join(formats) or 'no file systems'}")
        except DiskError as exc:
            print(f"udisks2:   not reachable here ({exc.key})")      # fine in a container
        except Exception as exc:
            print(f"udisks2:   not reachable here ({exc})")
    try:
        disks = list_devices()
        print(f"drives:    {len(disks)} listed, "
              f"{sum(len([c for c in d.children if c.kind == 'part']) for d in disks)} partitions")
    except (OSError, ValueError) as exc:
        print(f"drives:    lsblk failed ({exc})")
        failures.append("lsblk output")
    # the rules, on made-up drives
    sample = ('{"blockdevices":[{"name":"sdz","path":"/dev/sdz","type":"disk","size":8000000000,'
              '"rm":true,"pttype":"gpt","children":[{"name":"sdz1","path":"/dev/sdz1",'
              '"type":"part","size":4000000000,"start":2048,"fstype":"ext4","mountpoints":[null]}]},'
              '{"name":"sdy","path":"/dev/sdy","type":"disk","size":8000000000,"rm":false,'
              '"children":[{"name":"sdy1","path":"/dev/sdy1","type":"part","size":4000000000,'
              '"start":2048,"fstype":"ntfs","mountpoints":["/var/mnt/d"]}]}]}')
    fake = classify(parse_lsblk(sample))
    stick, d_drive = fake[0], fake[1]
    ok = (safety.check("format", stick.children[0], fake).allowed
          and not safety.check("format", d_drive.children[0], fake).allowed
          and not safety.check("write_image", d_drive, fake).allowed
          and safety.check("write_image", stick, fake).allowed
          and bool(free_spaces(stick))
          and safety.check("create", free_spaces(stick)[0], fake).allowed
          and not safety.check("create", None, fake).allowed)
    print(f"safety:    {'rules hold on a made-up stick and D:' if ok else 'RULES BROKEN'}")
    if not ok:
        failures.append("safety")
    if set(EN) != set(FR):
        print("text:      English and French tables differ")
        failures.append("text")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def list_drives() -> int:
    """Print the drives and partitions (read only). The same tree the window shows."""
    from .lang import local_units
    from .model import human_size, list_devices
    from .safety import tag_for
    from .text import t

    try:
        disks = list_devices()
    except (OSError, ValueError) as exc:
        print(f"lsblk: {exc}", file=sys.stderr)
        return 1
    for disk in disks:
        tag = tag_for(disk)
        print(f"{disk.path}  {disk.title or '-'}  {local_units(human_size(disk.size))}"
              f"  {t(tag) if tag else ''}".rstrip())
        for part in disk.children:
            tag = tag_for(part)
            what = part.fstype or ("free" if part.kind == "free" else "-")
            where = ", ".join(part.mounts)
            print(f"    {part.path or '(free)':18} {what:10} "
                  f"{local_units(human_size(part.size)):>10}  {where}"
                  f"  {t(tag) if tag else ''}".rstrip())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: the PC's drives, "
                                     "partitions, health and USB images.")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--self-test", action="store_true", help="check what this PC offers")
    parser.add_argument("--list", action="store_true", help="print the drives and exit")
    parser.add_argument("--tab", choices=("drives", "health", "image"))
    args = parser.parse_args(argv)
    if args.version:
        print(f"{APP_SLUG} {VERSION}")
        return 0
    if args.self_test:
        return self_test()
    if args.list:
        return list_drives()

    from .log import setup_logging
    setup_logging(to_file=True)
    from .app import App
    App(tab=args.tab).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
