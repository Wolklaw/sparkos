# Spark Bench

An optional Spark app for measuring game performance on SparkOS and comparing it with Windows. It
reads the frame times MangoHud records, and the CSVs PresentMon records on Windows. It is not part of
the SparkOS image; it installs for one user, without root.

Source-available under the repository's view-only license.

## What it does

- **Setup.** Checks that MangoHud is on the PC, that the MangoHud layer for Flatpak Steam's runtime
  branch is installed, that `MANGOHUD=1` is set for Flatpak Steam, and that MangoHud's config has the
  recording values (hotkey `Control_L+F11`, 90 seconds, `no_display`, an output folder). **Fix** shows
  exactly which lines and files it will change before it changes anything; **Undo** puts back what
  was there before (the original bytes, kept in `~/.local/state/spark-bench/undo.json`). It changes
  nothing else. The layer itself installs from Flathub only when you press its button.
- **Alerts.** A sound and a notification when a recording starts and when it ends, while the window
  is open. "Also when closed" adds a small systemd user service (`spark-bench-watch.service`) that
  does the same with the window closed; turning it off removes the service file.
- **Recordings.** Runs grouped by game: average FPS, 1% and 0.1% lows, worst frame, duration, a
  per-second FPS strip, trimming seconds off the start and end, leaving a run out of the comparison,
  and renaming a game so two names join.
- **Compare.** Import Windows PresentMon CSVs, pick a baseline, and see a side-by-side table per
  game with the difference in %, then export it as CSV.

### How the lows are worked out

"1% low" here is the average FPS of the slowest 1% of frames (and 0.1% the slowest 0.1%). MangoHud's
own summary uses the 99th percentile frame time instead, which gives a higher number. Spark Bench
works out every run, MangoHud and PresentMon alike, from the raw frame times the same way, so the two
systems are compared on equal terms. The Compare tab says this under the table.

### Game names

MangoHud names a recording after the game's program, and PresentMon after its `.exe` (without the
`.exe`). They don't always match: Clair Obscur: Expedition 33 records as `SandFall-Win64-Shipping`.
Rename a game in the Recordings tab to put both under one name; the names are kept in
`~/.config/spark-bench/`.

## Install

```sh
bash install.sh --user              # just you, no root (the way on SparkOS)
bash install.sh --user --uninstall  # remove exactly what --user installed
sudo bash install.sh --deps         # system-wide on Fedora, with dnf for what's missing
spark-bench --self-test             # what it found and what's missing
```

It needs Python 3 with tkinter. MangoHud records the frame times (SparkOS has it). `notify-send` and
`pw-play` (or `paplay`, `canberra-gtk-play`) give the notification and the sound; without them the
alerts are skipped.

Where things live:

| What | Where |
|---|---|
| Settings, game names, run marks | `~/.config/spark-bench/` |
| Imported PresentMon CSVs (copies) | `~/.local/share/spark-bench/imported/` |
| Undo record | `~/.local/state/spark-bench/undo.json` |
| MangoHud recordings (Flatpak Steam) | `~/.var/app/com.valvesoftware.Steam/benchmark/` by default |

Uninstalling turns off the background watcher (only if Spark Bench wrote its unit) and leaves the
settings, imports and recordings. Press Undo before uninstalling if you want MangoHud's config back
as it was.

## Tests

```sh
xvfb-run -a python3 -m unittest discover -s tests -v
SPARK_LANG=fr xvfb-run -a python3 -m unittest discover -s tests -v
```

The tests run in a temporary HOME with stand-ins for `flatpak` and `systemctl`, so they never touch
your MangoHud config, Steam or Flatpak overrides. The French run also checks that no text is clipped.
CI (`.github/workflows/spark-bench.yml`) runs them on Fedora, and installs, self-tests and removes
the app as a normal user inside the published SparkOS image.

## Tested so far, and not yet

Tested: the frame math (checked against the owner's existing PowerShell summaries of real runs), the
MangoHud and PresentMon readers on real recordings, Fix and Undo on stand-in files (including exact
byte restore), the alert logic, the whole window in English and French under Xvfb, and the user and
system-wide installs in a Fedora container.

Not yet tried: a live game recording with the hotkey, the background watcher on a real systemd user
session, installing the MangoHud layer from Flathub, the real sound and notification on a desktop, and
the SparkOS CI job against the published image (it ran only in a Fedora container so far).
