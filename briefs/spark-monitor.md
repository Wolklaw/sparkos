# Spark Monitor

Read [README.md](README.md) first for the conventions every Spark app follows.

## Why

Windows users press Ctrl+Shift+Esc when something hangs and expect Task Manager: a list of apps, an
"End task" button, and graphs of what the PC is doing. Spark Monitor is that for SparkOS, faster and
cleaner, and aware of gaming hardware (the owner's PC: Ryzen 7 7800X3D, Radeon RX 6800 XT).

## What it does

Ctrl+Shift+Esc opens it from anywhere. Tabs, in this order:

1. **Apps.** Like Windows' Processes tab. Two groups: **Apps** (things with windows or a desktop
   entry) and **Background**. Group processes by app, not one row per process: Plasma 6 starts each
   app in its own systemd scope, so read `/proc/<pid>/cgroup` and group by
   `app-<desktop-id>@….scope` / `app-flatpak-<id>-….scope`, then name and icon the group from that
   desktop entry. Columns: name, CPU %, memory, GPU % where readable, disk and network rate.
   Click a column to sort. Select and press Delete or **End task**: send SIGTERM to the group, then
   SIGKILL after 5 seconds if it's still alive, and say what happened. Never let the user end
   Plasma, KWin, the login session or systemd from the simple view; put those in a "System" group
   with a warning.
2. **Performance.** Live graphs (last 60 s) with the current number large:
   - CPU: total and per thread (16 on the owner's CPU), clock speed, temperature (`hwmon`: `k10temp`).
   - Memory: used, cached, available, swap/zram.
   - GPU (AMD, from `/sys/class/drm/card*/device/`): busy % (`gpu_busy_percent`), VRAM used and
     total (`mem_info_vram_used`/`_total`), clock, temperature, power draw and fan from its `hwmon`.
     Intel and NVIDIA: show what's readable, and say when something isn't.
   - Disks: read/write rate and usage per drive (`/proc/diskstats`), NVMe temperature.
   - Network: down/up per interface (`/proc/net/dev`).
3. **Startup.** Apps that start at login, with an on/off switch each: `~/.config/autostart/` and
   `/etc/xdg/autostart/` entries (turning off a system one writes a `Hidden=true` override to the
   user's autostart folder; never edit `/etc`), and enabled `systemd --user` services, shown with
   their description. Spark Welcome's and the startup sound's entries appear here too, which is fine.
4. **Details** (for advanced users): the flat process list with PID, user, command line, state and
   nice; End process and End process tree.

Read everything from `/proc` and `/sys` directly. No `ps`, `top` or other tools spawned every second.
`psutil` is fine if it's in Fedora (`python3-psutil`), but check its cost against direct reads.

## The shortcut

Give the desktop entry `X-KDE-Shortcuts=Ctrl+Shift+Esc` and check Plasma registers it (kglobalaccel),
on a fresh user, for both a `--user` install (`~/.local/share/applications/`) and a system-wide one.
If Plasma doesn't pick it up from the user's folder, register it on install and remove it on
`--uninstall`. Ctrl+Esc opens Plasma's own System Monitor today; leave that alone. If Ctrl+Shift+Esc
is taken by something else in Plasma 6.8, report it to the owner rather than silently stealing it.

Plasma System Monitor stays in the image for now (the recipe keeps it as part of the platform).
Whether Spark Monitor replaces it is the owner's call once it's done; ask.

## Speed

This app watches the PC, so it must not be what slows it down.

- Sample once per second while the window is visible; stop sampling when it's minimized or hidden.
- Target: under 1% of one CPU core while open on the Apps tab with ~400 processes, and under
  0.5 s to first paint. Measure both and put the numbers in the README.
- Draw graphs on one Tk canvas per graph, updating the line coordinates, not recreating items.

## Tests

- Unit: parsers against a fake `/proc` and `/sys` tree in `tests/fixtures/` (stat, meminfo,
  per-process stat/status/cgroup/cmdline, diskstats, net/dev, an AMD card with hwmon), CPU %
  from two samples, grouping by cgroup scope (regular and Flatpak apps), the End task sequence
  against a real child process the test starts, the autostart override writer.
- UI under Xvfb: every tab renders; sorting works; End task on a test process removes its row.
- `--self-test`: reads the live `/proc` and `/sys`, prints what it found (CPU threads, memory, GPU and
  which sensors are readable). No display needed.
- CI, inside the SparkOS image: `install.sh --user`, `--self-test`, `--uninstall` as a normal user.

## Done when

CI passes in Fedora and inside the SparkOS image, the app installs and uninstalls for one user with no
root, the speed targets are measured, and the PR is open for the owner. The owner confirms
Ctrl+Shift+Esc on hardware. It is optional (future Spark Portal), so it is not added to the recipe.

## Logs and System tabs (1.1.0)

Two tabs added after the first release. Behaviour and limits are in
[files/spark-monitor/README.md](../files/spark-monitor/README.md).

- **Logs:** `journalctl -o json -f` for this or the previous boot at three levels, filtered by
  app or unit and by text; a plain-language sentence per entry with the full entry and Copy entry
  one click away; a crashes view from `coredumpctl --json=short` with Copy report (clipboard only,
  nothing uploaded, machine ID, host name and user name removed); failed units and an unclean
  previous shutdown on top. Loaded only when the tab opens, stopped when it closes, 2000 entries
  at most. A new error or crash while the tab is open is an event: the heading tears.
- **System:** SparkOS version and digest, kernel, processor, GPUs with kernel driver and Mesa
  version, memory size and speed (from udev, no root), motherboard and BIOS from
  `/sys/class/dmi/id`, disks, displays, uptime, and Copy all without serial numbers by default.
- **Decisions for the owner:** none blocking. The unclean-shutdown notice is a guess from the log
  and says so. Whether the System tab should also read BIOS fields that need root (it can't,
  without a helper) is open.
