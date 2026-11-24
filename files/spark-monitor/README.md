# Spark Monitor

The SparkOS task manager, for people who press Ctrl+Shift+Esc when something hangs. It lists what is running grouped by app, ends the ones that stopped responding, graphs what the PC is doing, and switches startup apps on and off.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

Spark Monitor ships in the SparkOS image ([build step](../scripts/spark-monitor.sh)). It also installs for one user without root (`install.sh --user`), the way optional Spark apps will through the future Spark Portal. Plasma System Monitor stays in the image next to it for now.

- **Apps:** one row per app, not per process, in three groups: **Apps**, **Background** and **System**. Columns: CPU, memory, GPU (where the driver publishes it) and disk, with the totals in the headings. Click a heading to sort; open a row to see its processes. Select a row and press Delete or **End task**: the app is asked to close (SIGTERM), and if it is still running 5 seconds later it is forced to stop (SIGKILL). The status line says which happened. Steam games get their own row, named from Steam's library, so you can end a game without ending Steam.
- **Performance:** the last 60 seconds of CPU (total and each thread, clock, temperature), memory (in use, available, cached, swap and zram), each GPU (usage, video memory, clock, temperature, hotspot, power, fan), each disk (active time, read and write, temperature for NVMe, how full it is) and each network adapter (send and receive).
- **Startup:** autostart entries and `systemd --user` services, each with a switch.
- **Details:** every process with PID, user, state, CPU, memory, nice and command line; End process and End process tree.
- **Logs:** the systemd journal, live. Pick this boot or the previous one, errors only, warnings and errors, or everything, then filter by app or unit and search the text. Each row has a plain sentence ("blender was ended because the PC ran out of memory"); select it for the full entry and a Copy entry button. A second view lists crashes from `coredumpctl` (app, time, signal) with the details and a Copy report button that puts a report on the clipboard and sends nothing anywhere; the machine ID, host name and user name are left out. Failed units and a previous boot that didn't shut down cleanly show at the top.
- **System:** what this PC is, for a support request: SparkOS version and image digest, kernel, processor, each GPU with its kernel driver and Mesa version, memory (size, type and speed), motherboard and BIOS, disks, displays and uptime. **Copy all** puts it on the clipboard without serial numbers; the Serial numbers switch adds them to the screen and the copy.

Ctrl+1 to Ctrl+6 switch tabs, F5 refreshes now, Ctrl+W closes. Pressing Ctrl+Shift+Esc while it is open brings the open window forward instead of starting a second one.

## How it works

- **Grouping.** Plasma 6 starts every app in its own systemd scope, so `/proc/<pid>/cgroup` says which app a process belongs to: `app-<desktop-id>@….scope`, or `app-flatpak-<id>-….scope` for Flatpak apps. The row takes its name and icon from that desktop entry. Plasma, KWin, the login session, PipeWire, D-Bus, portals and system services go in **System**: the Apps tab won't end those (it can log you out or freeze the screen); Details can, after a warning. Processes outside any systemd session (containers) get one row each.
- **Numbers.** Everything is read straight from `/proc` and `/sys`: no `ps`, `top`, `nvidia-smi` or other program is started every second, and psutil isn't used. Per process: `stat` and `statm` every second, `io` for your own processes; owner, cgroup and command line once, when the process appears. Kernel threads are looked at again only every 10 seconds. GPU use per app comes from the `drm-engine-*` counters in `/proc/<pid>/fdinfo` (AMD and Intel); finding which processes have the GPU open is spread over several seconds so it never causes a spike.
- **AMD GPUs** (`/sys/class/drm/card*/device/`): `gpu_busy_percent`, `mem_info_vram_used`/`_total`, and the card's hwmon for clock (`freq1`, sclk), edge and junction temperature, power (`power1_average` or `power1_input`) and fan. The dedicated card is listed first. Names come from hwdata's PCI ID list.
- **Light.** It samples once a second while the window is visible and stops while it is minimized or on another desktop; only the open tab is updated. Each graph is one canvas whose line is moved, never redrawn from scratch. Tabs are built the first time you open them.
- **Startup.** Turning off an entry from `/etc/xdg/autostart` writes a copy with `Hidden=true` to `~/.config/autostart` (marked `X-Spark-Monitor-Override=true`); turning it back on removes that copy. `/etc` is never written. Your own services are switched with `systemctl --user enable/disable`; services the system enables for every user are listed but can't be switched here.
- **End task** uses pidfds, so a process ID reused by a new process while waiting is never signalled. It never signals itself, and with test data (`--root`) it sends nothing.

Settings are in `~/.config/spark-monitor/`, the log in `~/.local/state/spark-monitor/`.

## Speed

Targets from the brief: under 1% of one CPU core while open on the Apps tab with about 400 processes, and under 0.5 s to first paint.

Measured by CI on 2026-11-20 (GitHub runner: 4 vCPUs of an Intel Xeon 6975P-C, Fedora, Python 3.15, Tk 9.0, Xvfb), with 400 processes running, 30 seconds per tab:

| Tab | First paint | CPU (one core = 100%) | Per sample: system / processes / table |
|---|---|---|---|
| Apps | 0.18 s | 0.87% | 0.35 / 4.21 / 0.83 ms |
| Details | 0.18 s | 1.03% | 0.35 / 4.23 / 1.34 ms |
| Performance | 0.17 s | 0.37% | 0.53 / — / 0.84 ms |

Both targets are met on the Apps tab. Details, which lists every process, is just over 1%. This is the worst case: the runner's container has no systemd session, so each of the 400 processes is its own row; on a Plasma desktop processes are grouped by app, so there are far fewer rows to update. It hasn't been measured on the owner's Ryzen 7 7800X3D yet; run the line below there.

`spark-monitor --bench 30 --fill 400` measures the same on any PC: it opens the window, reports the time to first paint (from the moment the process started, Python's own start-up included), starts sleeping processes until there are 400, and reports the CPU the monitor itself used over 30 seconds.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the image build runs)
spark-monitor                             # or Ctrl+Shift+Esc
spark-monitor --tab performance           # open on a tab
spark-monitor --self-test                 # what it can read on this PC; no display needed
spark-monitor --root tests/fixtures/root  # the window, with the test data instead of this PC
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

`--user` needs only what the SparkOS image already has (Python 3 with tkinter). It installs to `~/.local/lib/spark-monitor/`, `~/.local/bin/spark-monitor`, `~/.local/share/applications/`, `~/.local/share/icons/` and `~/.local/share/kglobalaccel/` (that link is how Plasma picks up the shortcut), and lists every file it wrote in `~/.local/lib/spark-monitor/installed-files` for `--uninstall`. Settings and the log are left in place by `--uninstall`.

`spark-app.json` describes the app for the Spark Portal (ID, name, summary, version, size, what it needs, how to install it).

The tests use a fake `/proc` and `/sys` in `tests/fixtures/root`: a Ryzen 7 7800X3D with 16 threads, an RX 6800 XT plus the CPU's own graphics with their hwmon sensors, an NVMe drive behind LUKS, Plasma 6 app scopes, a Flatpak Steam running a game. End task is tested against real processes the tests start (Linux only). CI ([workflow](../../.github/workflows/spark-monitor.yml)) runs the image build step and everything else under Xvfb in Fedora, measures the speed, and inside the published SparkOS image installs it with `--user` as a normal user, runs the self-test and the unit tests, and uninstalls it.

## Logs and System: how they work

- **Nothing runs until you open the tab.** The Logs tab starts `journalctl -o json -f` when it opens and stops it when you leave; the System tab reads its programs once, on a thread. Spark Monitor still runs nothing in the background.
- **The journal is capped.** The newest 2000 entries are kept, long messages are cut, and the table shows what matches your filters among those. Boot and level are chosen in `journalctl`, so a quiet level reaches back further; the app and text filters look only at what is loaded.
- **Read as your user.** The journal needs your account to be in `wheel` or `systemd-journal` (the SparkOS default account is); if it isn't, the tab says so. Memory size and speed come from the udev database (`udevadm info -p /devices/virtual/dmi/id`), which holds what the firmware reported at boot and needs no root. Motherboard fields come from `/sys/class/dmi/id`; fields only root can read (serial numbers on some boards) are shown as not readable.
- **Programs used, all optional:** `journalctl`, `coredumpctl`, `systemctl --failed`, `rpm-ostree status --json`, `udevadm`, `vulkaninfo` (GPU driver and Mesa version, `glxinfo` as a fallback), `kscreen-doctor`. If one is missing, its rows say so instead of failing. Tests use fixture files in `tests/fixtures/root/commands` instead of the real programs.
- **Unclean shutdown is a guess.** The previous boot is called unclean when its last 300 lines contain none of the shutdown steps. A log cut short for another reason reads the same.
- **Times** are in the PC's time zone, with the zone shown in copies.
- **Tried on the real PC:** the owner's all-AMD desktop (Ryzen 7 7800X3D, RX 6800 XT, ASUS PRIME X670-P WIFI) showed the right processor, graphics driver and Mesa version, two memory modules with their rated and running speeds, the board and BIOS, three disks and three displays. The Logs tab loaded this and the previous boot, the crash list and a crash's details. Screenshots could not be taken in that session, so the look was checked in the widget tree and by the width test, not by eye.

## Known gaps

- **Opened on a real SparkOS desktop in CI, not used by hand yet.** The boot test opens it from the app menu in a Plasma 6.8 session in a VM, in English and in French, waits for its window, keeps a screenshot and fails on a Python traceback. Nobody has pressed Ctrl+Shift+Esc on real Plasma 6.8 yet, so it is not confirmed that Plasma registers it, or that nothing else in 6.8 uses it. `--self-test` reports it if anything in `kglobalshortcutsrc` already uses Ctrl+Shift+Esc. Ctrl+Esc (Plasma's System Monitor) is left alone. A `--user` install may need a log out and back in before Plasma picks up the shortcut.
- **No network column per app.** Linux only counts traffic per process with root-level tools (eBPF), so the Apps tab shows network totals on the Performance tab only.
- **GPU per app** needs a driver that publishes fdinfo counters (AMD, Intel). NVIDIA's driver publishes nothing in `/sys`, so its usage, memory and temperature show as not readable.
- Bringing the open window forward on Ctrl+Shift+Esc may only flash it in the taskbar, depending on KWin's focus-stealing setting.
- English and Quebec French, picked from the PC's language (`SPARK_LANG=en|fr` overrides it), app names included; every sentence is in `sparkmonitor/text.py`.
- App icons are PNG only (Tk can't draw SVG): apps whose icon theme has only SVG get a coloured tile.
