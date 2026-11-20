"""The command line. --version and --self-test never load Tk; a second launch hands over to
the open window before Tk is even imported, so Ctrl+Shift+Esc on an open monitor is instant."""

import argparse
import os
import sys
import time
from typing import List, Optional

T0 = time.monotonic()

from . import APP_NAME, APP_SLUG, SHORTCUT, VERSION  # noqa: E402
from .source import Source, read_line  # noqa: E402


def process_age() -> Optional[float]:
    """Seconds since this process started (Python's own start-up included), from /proc."""
    try:
        stat = read_line('/proc/self/stat')
        up = read_line('/proc/uptime')
        if not stat or not up:
            return None
        start = int(stat[stat.rfind(')') + 2:].split()[19])
        return float(up.split()[0]) - start / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, AttributeError, IndexError):
        return None


def shortcut_owner(src: Source) -> Optional[str]:
    """Which Plasma shortcut already uses Ctrl+Shift+Esc, from kglobalshortcutsrc, if any."""
    path = os.path.join(src.config_home, 'kglobalshortcutsrc')
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return None
    want = _norm_keys(SHORTCUT)
    group = ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            group = line
            continue
        if '=' not in line or 'SparkMonitor' in group:
            continue
        key, _, value = line.partition('=')
        active = value.split(',', 1)[0]
        if any(_norm_keys(k) == want for k in active.split('\t') if k and k != 'none'):
            return f"{group} {key}"
    return None


def _norm_keys(combo: str) -> frozenset:
    parts = [p.strip().lower() for p in combo.replace('\\t', '\t').split('+') if p.strip()]
    return frozenset('esc' if p == 'escape' else 'ctrl' if p == 'control' else p for p in parts)


def self_test(src: Source) -> int:
    """Read the live /proc and /sys and say what was found. No display needed."""
    from . import core, procs, startup, system
    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors='replace')     # a C locale can't print "°C"
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
    if not os.path.isfile(os.path.join(src.proc, 'stat')):
        print(f"/proc:     MISSING at {src.proc}")
        return 1

    sysm = system.SystemSampler(src)
    sysm.sample(time.monotonic())
    time.sleep(0.3)
    snap = sysm.sample(time.monotonic(), full=True)
    if not sysm.threads:
        failures.append("cpu")
    print(f"cpu:       {sysm.model}, {sysm.threads} threads, {core.pct(snap.cpu, 0)} busy, "
          f"clock {'yes' if snap.cpu_mhz else 'no'}, temperature "
          f"{core.temp(snap.cpu_temp) if sysm.cpu_temp_path else 'no'}")
    m = snap.mem
    if not m.total:
        failures.append("memory")
    zram = f", zram {core.size(m.zram_data)} -> {core.size(m.zram_compressed)}" \
        if m.zram_data is not None else ""
    print(f"memory:    {core.size(m.total)}, {core.size(m.available)} available, swap "
          f"{core.size(m.swap_total)}{zram}")
    if not sysm.gpus:
        print("gpu:       none found in /sys/class/drm")
    for g in sysm.gpus:
        readable = [name for name, value in (
            ('usage', g.busy), ('video memory', g.vram_total), ('clock', g.clock_mhz),
            ('temperature', g.temp), ('hotspot', g.temp_hot), ('power', g.power_w),
            ('fan', g.fan_rpm)) if value is not None]
        print(f"gpu:       {g.card} {g.name} [{g.vendor:04x}:{g.device:04x}]: readable: "
              f"{', '.join(readable) or 'nothing'}" + (f" ({g.note})" if g.note else ""))
    for d in sysm.disks:
        print(f"disk:      {d.name} {d.model} ({d.kind}, {core.size(d.size, 0)}): temperature "
              f"{'yes' if d.temp_path else 'no'}, {len(d.usage)} filesystem(s) mounted")
    for n in sysm.nics:
        print(f"network:   {n.name} ({n.kind}, {'up' if n.up else 'down'})")

    sampler = procs.ProcSampler(src, threads=sysm.threads or 1)
    sampler.sample(time.monotonic())
    time.sleep(0.2)
    sampler.sample(time.monotonic())
    count, kernel = sampler.totals()
    if count == 0:
        failures.append("processes")
    sections = {s: sum(1 for g in sampler.groups.values() if g.section == s)
                for s in procs.SECTIONS}
    me = sampler.procs.get(os.getpid())
    scoped = bool(me and me.cgroup and not me.group.startswith('pid:'))
    print(f"processes: {count} ({kernel} kernel threads), {len(sampler.groups)} rows: "
          f"{sections['app']} apps, {sections['background']} background, "
          f"{sections['system']} system")
    print("grouping:  " + ("by systemd scope (this process: " +
                            (me.cgroup if me else '?') + ")" if scoped else
                            "one row per process (not in a systemd session here)"))
    print(f"gpu/app:   {'yes' if sampler.gpu_readable else 'no GPU users seen'}")
    items = startup.all_items(src, [])
    print(f"startup:   {sum(1 for i in items if i.kind == startup.AUTOSTART)} autostart "
          f"entries, {sum(1 for i in items if i.kind == startup.SERVICE)} services")
    owner = shortcut_owner(src)
    if owner:
        print(f"shortcut:  {SHORTCUT} is already used by {owner} - tell the owner")
    elif os.path.isfile(os.path.join(src.config_home, 'kglobalshortcutsrc')):
        print(f"shortcut:  {SHORTCUT} is free in kglobalshortcutsrc")
    else:
        print("shortcut:  no kglobalshortcutsrc yet (no Plasma session for this user)")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0



def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS "
                                     "task manager.")
    parser.add_argument('--tab', choices=('apps', 'performance', 'startup', 'details'),
                        help="open on this tab")
    parser.add_argument('--self-test', action='store_true',
                        help="read /proc and /sys and report what is readable; no display "
                             "needed")
    parser.add_argument('--bench', type=float, metavar='SECONDS',
                        help="open, measure time to first paint and CPU use, then close")
    parser.add_argument('--fill', type=int, default=0, metavar='N',
                        help="with --bench: start sleeping processes until there are N")
    parser.add_argument('--root', help="read a fake /proc and /sys under this folder "
                                       "(tests and interface work)")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    src = Source(args.root)
    if args.self_test:
        return self_test(src)
    if not args.bench and not src.fake:
        from .instance import ask_running_to_show
        if ask_running_to_show():
            return 0
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    from .app import App, bench
    core.setup_logging()
    try:
        if args.bench:
            return bench(src, args.bench, args.fill, args.tab or 'apps')
        app = App(src, args.tab)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
