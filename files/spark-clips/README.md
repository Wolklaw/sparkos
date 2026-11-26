# Spark Clips

Instant replay for games on SparkOS. Version 0.1.0. It is an optional Spark app: install it from Spark
Store, or per user with `install.sh --user`.

While the replay buffer is on, Spark Clips keeps the last 15, 30, 60, 120 or 300 seconds of one monitor,
encoded on the GPU. Press **Meta+Alt+G** and those seconds become a clip in `~/Videos/Clips/<Game>/`, with a
notification that has Open and Show in folder.

## What it does

- Replay buffer in `/dev/shm`, as 1 second MPEG-TS pieces that are deleted by age. Nothing is written to the
  disk until you save.
- System sound on by default. Microphone off by default; when on it is a second audio track, so you can mute
  it later without recording again.
- Encoding through VA-API (H.264 by default, HEVC if you pick it). Without a GPU encoder it falls back to
  openh264, then x264. No AV1.
- "Only while a game is running" (on by default). A game is a Steam game, a Wine or Proton process, a
  GameMode client, or a Lutris or Heroic game. Outside a game nothing is recorded.
- A clip library with thumbnails: play, trim (lossless, no re-encode), rename, copy the file, delete to the
  trash, open the folder.
- `spark-clips --save` saves a clip from a terminal or a script. `spark-clips --status` prints what the
  service is doing (`--json` for a script). Exit codes: 0 fine, 1 a problem, 2 the service is not running.
- English and French.

## How it works

A systemd user service (`spark-clips.service`) holds the buffer and listens on a control socket in
`$XDG_RUNTIME_DIR`. The window, `--save` and the shortcut all talk to it. The shortcut is the compositor's: it binds Super+Alt+G to `spark-clips --save` itself, and `bind Super+Alt+g none` in its config turns that off.

The screen comes from the desktop's screen-share portal (xdg-desktop-portal ScreenCast) and PipeWire. The
first time, the portal asks which screen to share: click it once. Spark Clips keeps the permission, so later
starts do not ask. A start that nobody is watching never opens that dialog; the window shows "Set up the
screen" until you do.

## Limits

- **HDR is not supported.** Record an SDR screen or turn HDR off for the game.
- The screen is the one you pick in the portal dialog. There is no setting for it in the window, and no
  "follow the game" yet.
- A trim keeps whole frames from the keyframe before your start point, so it can start up to about a second
  early. Spark Clips never re-encodes a clip.
- A save leaves out the newest second, the one still being written.
- The buffer lives in memory: 5 minutes at a high bit rate can take several gigabytes. The window shows the
  estimate and turns it gold when it would not fit, and the service then says so instead of starting.
- Capturing costs some frame rate. How much on a real game is not measured yet.

## What was tried, and how

CI and the test suite have no game, no screen share and no GPU, so `SPARK_CLIPS_FAKE=1` replaces the screen
and the sound with a test pattern and a test tone. With that, the real pieces run: the encoder, the MPEG-TS
buffer and its pruning, joining pieces into an MP4, the trim, thumbnails, the service and its socket, the
window, and the French text widths. The GPU encoder (`vah264enc`) and `openh264enc` were tried on the
owner's PC that way.

Not tried yet: the portal dialog with a real screen, a real game, the frame-rate cost, the key press on a
booted SparkOS, game detection against real processes, and the microphone track.

## Tests

```
cd files/spark-clips
python3 -m unittest discover -s tests -v
SPARK_LANG=fr python3 -m unittest discover -s tests -v
spark-clips --self-test
```

The window tests need a display (CI uses Xvfb) and skip without one. The service tests need GStreamer and an
H.264 encoder and skip without them.

## Install and remove

```
bash install.sh --user                 # no root
bash install.sh --user --uninstall
sudo bash install.sh --deps            # the whole system, on Fedora
```

Uninstalling stops the service. Your clips, settings (`~/.config/spark-clips`) and log
(`~/.local/state/spark-clips`) stay.
