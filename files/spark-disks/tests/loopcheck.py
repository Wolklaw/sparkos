#!/usr/bin/env python3
"""Manual check of the real udisks calls, on a loop device made from a file in /tmp. Run it by
hand: python3 tests/loopcheck.py. It is not part of the unit tests or CI.

It only ever touches the loop device it makes itself. Every call is guarded: the device must be
that loop device or one of its partitions, and the loop must be backed by our image file."""

import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparkdisks.udisks import Udisks  # noqa: E402

MIB = 1024 * 1024
steps = []


def step(name, fn):
    try:
        value = fn()
        steps.append((name, True, ''))
        print(f'  ok    {name}')
        return value
    except Exception as exc:  # noqa: BLE001
        steps.append((name, False, f'{type(exc).__name__}: {exc}'))
        print(f'  FAIL  {name}: {type(exc).__name__}: {exc}')
        return None


def main() -> int:
    work = tempfile.mkdtemp(prefix='spark-disks-loop-')
    image = os.path.join(work, 'disk.img')
    with open(image, 'wb') as f:
        f.truncate(512 * MIB)
    out = subprocess.run(['udisksctl', 'loop-setup', '-f', image], capture_output=True, text=True)
    match = re.search(r'(/dev/loop\d+)', out.stdout)
    if not match:
        print('could not make a loop device:', out.stdout, out.stderr)
        return 2
    loop = match.group(1)
    backing = subprocess.run(['losetup', '-nO', 'BACK-FILE', loop], capture_output=True,
                             text=True).stdout.strip()
    if os.path.realpath(backing) != os.path.realpath(image):
        print(f'{loop} is not backed by {image} ({backing!r}): stopping, nothing was touched')
        return 2
    print(f'working on {loop}, backed by {image}')

    def guard(dev):
        if not re.fullmatch(re.escape(loop) + r'(p\d+)?', dev):
            raise SystemExit(f'refusing to touch {dev}: not {loop}')
        return dev

    class Guarded(Udisks):
        pass

    for name in ('mount', 'unmount', 'format', 'new_table', 'delete_partition', 'resize_partition',
                 'resize_filesystem', 'open_device'):
        original = getattr(Udisks, name)
        setattr(Guarded, name, (lambda o: lambda self, dev, *a, **k: o(self, guard(dev), *a, **k))(original))
    original = Udisks.create_partition
    Guarded.create_partition = lambda self, disk, *a, **k: original(self, guard(disk), *a, **k)

    be = Guarded()
    part = loop + 'p1'
    try:
        step('make a GPT table', lambda: be.new_table(loop, 'gpt'))
        time.sleep(1)
        step('create a 200 MiB ext4 partition',
             lambda: be.create_partition(loop, MIB, 200 * MIB, 'ext4', 'Check', 'gpt'))
        time.sleep(1)
        where = step('mount it', lambda: be.mount(part))
        print('        mounted at', where)
        step('unmount it', lambda: be.unmount(part))
        step('format it as exfat', lambda: be.format(part, 'exfat', 'Check2'))
        step('format it as ext4', lambda: be.format(part, 'ext4', 'Check3'))
        step('can_resize ext4', lambda: be.can_resize('ext4'))
        step('grow the partition', lambda: be.resize_partition(part, 300 * MIB))
        step('grow the file system', lambda: be.resize_filesystem(part, 300 * MIB))
        step('shrink the file system', lambda: be.resize_filesystem(part, 150 * MIB))
        step('shrink the partition', lambda: be.resize_partition(part, 150 * MIB))
        step('delete the partition', lambda: be.delete_partition(part))

        def write_back():
            fd = be.open_device(loop, 'w')
            try:
                os.write(fd, b'SPARK' * 1000)
                os.fsync(fd)
            finally:
                os.close(fd)
            fd = be.open_device(loop, 'r')
            try:
                if os.read(fd, 5000) != b'SPARK' * 1000:
                    raise OSError('read back differs')
            finally:
                os.close(fd)
        if '--open' in sys.argv:        # polkit asks for the admin password: needs someone at the PC
            step('write to the device and read it back', write_back)
        else:
            print('  skip  write to the device (run with --open to try it; it asks for a password)')
        step('wipe the table again', lambda: be.new_table(loop, 'dos'))
    finally:
        subprocess.run(['udisksctl', 'loop-delete', '-b', loop], capture_output=True)
        try:
            os.remove(image)
            os.rmdir(work)
        except OSError:
            pass
    failed = [s for s in steps if not s[1]]
    print(f'\n{len(steps) - len(failed)} of {len(steps)} steps passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
