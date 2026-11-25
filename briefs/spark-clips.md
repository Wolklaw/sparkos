# Spark Clips: instant replay for games

Optional Spark app, through Spark Store (`install.sh --user`, no root). Live updates on.

## Why

Spark Snip records the screen from the moment you press the key. A gamer wants the other thing:
something cool just happened, press a key, and the last 30 seconds are saved. On Windows that is
Xbox Game Bar's "Record that" (Win+Alt+G), NVIDIA ShadowPlay or AMD ReLive. SparkOS has nothing
for it, and the common Linux answer (gpu-screen-recorder) is someone else's app.

## What

- **Replay buffer.** While it is on, the last N seconds (15, 30, 60, 120, 300; default 30) of one
  monitor are kept, encoded on the GPU. **Meta+Alt+G** saves them as a clip. A notification says
  "Clip saved (30 s)" with Open and Show in folder.
- **Sound.** System sound on by default (the default output's monitor). Microphone off by
  default, as a second audio track when on, so it can be muted later without re-recording.
- **Which monitor.** The one picked in settings, default the primary one (on the owner's PC, the
  2560×1440 DP-1). "Follow the game" (the monitor with the focused full-screen window) is a later
  version.
- **When it runs.** A toggle "Keep a replay" in the window and in the tray icon, plus a setting
  "Only while a game is running" (default on): the buffer starts when a game process appears and
  stops when it ends, so it costs nothing on the desktop. Game detection: a process started by
  Steam (`reaper`/`SteamLaunch` in its parents), by Spark Games, or by umu/Proton/Wine, or one
  that gamemode reports. Detection lives in one module with tests, so it is easy to fix.
- **Clip library.** A grid of clips in `~/Videos/Clips/<Game name>/` with thumbnails, length, size
  and date. Play (opens Spark Media), trim (start and end handles, a lossless cut at keyframes,
  a re-encode only if the owner asks for a frame-exact cut), rename, delete to the trash, copy the
  file, open the folder. The game name comes from the detection (Steam app name, or the window
  title), else "Desktop".
- **`spark-clips --save`** saves from a terminal or another app's shortcut, and `--status` prints
  whether the buffer runs, its length, encoder and memory use.

Non-goals for 0.1: streaming (OBS's job), uploading anywhere, a video editor beyond trim,
recording with a key press (Spark Snip does that), webcam overlay.

## How

- **A user service records; the window only shows and edits.** `spark-clips --daemon` as a
  systemd user unit (`spark-clips.service`, `Restart=on-failure`), enabled by `install.sh --user`,
  single instance (flock), same split as Spark Clock. The window and the CLI talk to it over a
  small Unix socket in `$XDG_RUNTIME_DIR/spark-clips/` (save, start, stop, status).
- **Capture:** the desktop's ScreenCast portal, like Spark Snip's recording, with
  `persist_mode = 2` and the restore token saved, so Plasma's share dialog shows once and never
  again. Cursor embedded. PipeWire stream into GStreamer (`pipewiresrc`). Copy what is useful from
  Spark Snip's portal client rather than importing it: apps stay self-contained.
- **Encode:** VA-API on the GPU. The owner's RX 6800 XT (Navi 21) has `vah264enc` and `vah265enc`
  and **no AV1 encoder**; it is checked on this PC. Default H.264 for "plays everywhere", HEVC as
  an option for half the size. Fallbacks when there is no VA encoder: `openh264enc`, then x264 if
  present. Constant quality with a bitrate cap (default about 40 Mbit/s at 1440p60), one keyframe
  every second so the buffer can be cut on a second boundary. Frame rate: the monitor's, capped
  at 60 by default (setting: 30, 60, 120, native).
- **The buffer is in RAM, not on the SSD.** Hours of gaming at 40 Mbit/s would write tens of GB a
  day to the SSD for nothing. `splitmuxsink` writes one-second MPEG-TS pieces to
  `/dev/shm/spark-clips-<uid>/` (tmpfs, 16 GB on this PC; 30 GB of RAM), and the daemon deletes
  pieces older than the buffer length. Two minutes at 40 Mbit/s is about 600 MB. The settings
  show the expected memory use for the chosen length and quality, and refuse a length that would
  use more than a quarter of the free `/dev/shm`.
- **Saving:** take the pieces that cover the last N seconds, join them (MPEG-TS joins by
  concatenation), and remux to MP4 (`tsdemux ! h264parse ! mp4mux`, no re-encode) in
  `~/Videos/Clips/`. The buffer keeps recording while it saves. Saving twice in a row gives two
  clips that overlap; that is fine.
- **Performance target:** under 3 % average FPS loss in a GPU-bound game, measured with
  Spark Bench (MangoHud) with the buffer on and off. Write the numbers in the PR. If it misses,
  try lower resolution scaling (`vapostproc`) before anything else.
- **Settings** in `~/.config/spark-clips/config.json`, log in `~/.local/state/spark-clips/`.
- **The shortcut:** register Meta+Alt+G the same way Spark Snip registers its shortcuts
  (a `.desktop` action with `X-KDE-Shortcuts`, read by kglobalaccel); the action runs
  `spark-clips --save`. If Meta+Alt+G is taken, say so in the window instead of stealing it.
- **Look:** the house style (`wolklaw-design` skill): dark, sharp 3px corners, magenta/cyan
  channel slip as the only decoration, mono font. Tk like the other Spark apps, English and
  French with the text-fit check.

## Decisions

- **Own pipeline on GStreamer and the portal, not gpu-screen-recorder.** It is what Spark Snip
  already uses and ships in the image; nothing new from others.
- **Optional, through Spark Store.** Not everyone games; the image stays lean. Owner can promote it
  into the image later.
- **No HDR in 0.1.** HDR games get captured as the portal gives them (SDR). Say so in the README.
- **No root part,** so `system_api` 1 and live updates on.

## Tests

CI has no GPU, no portal and no PipeWire session:

- Unit: game detection on fake process trees (Steam, Spark Games, Proton, plain desktop), piece
  pruning by age, the "which pieces cover N seconds" choice, memory estimate, settings, the
  socket protocol.
- Pipeline with `SPARK_CLIPS_FAKE=1`: `videotestsrc` and `audiotestsrc` instead of the portal,
  software encoder. Run the buffer for 10 s, save the last 5, check with `gst-discoverer-1.0`
  that the MP4 is about 5 s long, has video and audio, and plays. Check pruning keeps memory flat.
- Trim: lossless cut gives the expected length within a second.
- The window under Xvfb in English and French with the text-fit check, like Spark Camera.
- The `sparkos` job: install as a normal user inside the published image, self-test, unit tests,
  uninstall leaves nothing.
- Not covered by CI, say so in the PR: the real portal, VA-API encoding, the FPS cost, the global
  shortcut. Try what can be tried on the owner's PC (VA-API encode of a test source, the portal
  once with the owner's click) and mark the rest.

## Files

`files/spark-clips/` like Spark Camera: `spark_clips.py`, `sparkclips/` package, `install.sh`
(`--user`, `--uninstall`, `--deps`, `--stage`), `spark-app.json`, `dev.wolklaw.SparkClips.desktop`,
icons from `make_icons.py` in the house style, `tests/`, README.md, and
`.github/workflows/spark-clips.yml` (copy spark-camera.yml's shape; quote any step name that has
`: ` in it). Add the Store source like the other optional apps, the row in
[README.md](README.md), and a ShareX/ShadowPlay row in [docs/switching.md](../docs/switching.md).

## Status

Brief written 2026-11-24. Not built yet.
