# Spark Bench

Read [README.md](README.md) first for the conventions every Spark app follows.

## Why

The owner benchmarks games on SparkOS against Windows. Today that takes MangoHud set up by hand (the
host package, the Flatpak layer for Steam's runtime, `MANGOHUD=1`, config lines), a shell script that
beeps when a recording starts and stops, and a PowerShell script to summarize the CSVs. Spark Bench
puts that in one optional app.

## What it does

- Setup check with one Fix and one Undo: MangoHud on the host, the Flatpak layer for Steam's runtime
  branch, `MANGOHUD=1` in Steam's override, and the config values (hotkey `Control_L+F11`, 90 s,
  `no_display`, `output_folder`). Fix shows exactly what it will change; Undo restores the original
  bytes. Nothing else is touched.
- A sound and a notification when a recording starts and ends, and an optional systemd user service
  that does the same with the window closed.
- Recordings grouped by game: average FPS, 1% and 0.1% lows (average of the slowest frames), worst
  frame, a per-second strip, trim, and leave a run out.
- Compare: import Windows PresentMon CSVs, side-by-side table with the difference in %, export CSV.

Optional, per user, not in the image. Code in [files/spark-bench](../files/spark-bench).

## Status

Built 2026-11-22, PR open. Tested on the owner's real recordings (the averages match his PowerShell
summaries), under Xvfb in English and French, and installed and removed in a Fedora container. Not yet
tried with a live game, the background service on a real session, the Flathub layer install, or the
real sound and notification. Open for the owner: the lows definition (average of the slowest frames
vs. MangoHud's 99th percentile), whether to ship known game names (Expedition 33 records as
`SandFall-Win64-Shipping`), and whether `--deps` should pull MangoHud.
