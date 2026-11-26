# Spark Camera

The SparkOS webcam app and voice recorder. Version 0.1.0. It is an optional Spark app: install it from
Spark Store, or per user with `install.sh --user`.

## What it does

**Camera tab**

- A live preview of your webcam.
- Photos (JPEG) with an optional countdown of 3, 5 or 10 seconds. A second press cancels the countdown.
- Video with sound. A video starts at 0 and the sound stays in step with the picture.
- A choice of camera, size, microphone and video format, and Sound and Mirror switches.
- Photos go to `~/Pictures/Camera`, videos to `~/Videos/Camera`. A strip of the newest ones sits under
  the preview; a click opens one (in Spark Media if it is the default, otherwise whatever `xdg-open` picks).

**Voice tab**

- A voice recorder with a microphone choice and a level meter that moves while you are not recording too.
- Record, pause and stop. Opus (small) or FLAC (lossless).
- Recordings go to `~/Music/Recordings`. The list plays, renames and deletes them. Delete asks first and
  moves the file to the trash; Spark Camera never deletes for good.

Keys: Ctrl+1 camera, Ctrl+2 voice, F5 look for devices again, Ctrl+Q or Ctrl+W close.

## Formats

Spark Camera checks which encoders GStreamer has instead of assuming them, and offers these, best first:

| Video | Needs |
|---|---|
| WebM, VP9 and Opus | `vp9enc`, `opusenc`, `webmmux` (gst-plugins-good and -base) |
| MP4, H.264 and AAC | an H.264 encoder (`vah264enc`, or `openh264enc`) and an AAC encoder (gst-libav) |
| WebM, VP8 and Opus | `vp8enc`, `opusenc`, `webmmux` |

Voice: Opus (`opusenc`, `oggmux`) and FLAC (`flacenc`). The PipeWire camera source is used where it
works, otherwise Video4Linux (`v4l2src`).

## Things to know

- **Mirror is for the preview only.** The preview looks like a mirror because that is easier to frame.
  Saved photos and videos are not flipped, so text in them reads the right way.
- **The first moment of a video can be without picture on some cameras.** Tried with a Logitech C920 PRO:
  the camera sends one old picture, then pauses for about a second. Spark Camera drops that old picture
  (the VP9 encoder sometimes refused the frame after it), so a WebM video begins with a short stretch of sound
  over no picture. Sound and picture stay in step after that.
- **A stop in the first third of a second is held until 0.3 s**, so a double click still ends in a valid file.
- Closing the window while recording stops the recording and saves the file.
- The camera and the microphone are let go when you leave a tab, so other programs can use them.

## Command line

```
spark-camera                 open the camera tab
spark-camera --tab voice     open the voice tab
spark-camera --self-test     check the install on a test pattern and a test tone
spark-camera --version
```

`--self-test` needs no display, camera or microphone. It lists the real devices for information, then
records a second of test pattern and test tone in every format, into a temporary folder it removes.

## Settings and files

`~/.config/spark-camera/settings.json` (camera, size, microphone, format, sound, mirror, countdown) and
the log in `~/.local/state/spark-camera`. `SPARK_LANG=fr` or `en` overrides the language; otherwise `LANG`
decides. `SPARK_CAMERA_FAKE=1` swaps the real devices for a test pattern and a test tone (this is what
the tests use). `SPARK_CAMERA_REDUCED_MOTION=1` stops the glitch effect; a zero `AnimationDurationFactor` in `~/.config/kdeglobals` (KDE's animation setting) is also
followed; the Spark session does not write that file, so use the variable.

## Installing

```
bash install.sh --user              just you, into ~/.local; no root
bash install.sh --user --uninstall
sudo bash install.sh --deps         the whole system
```

It needs Python 3 with tkinter and Pillow (with ImageTk), PyGObject, and GStreamer with the base and good
plugins. On SparkOS they come with the image; `--deps` installs them on Fedora.

## Tests

`python3 -m unittest discover -s tests` from this folder, under a display (`xvfb-run`), once with
`SPARK_LANG=en` and once with `SPARK_LANG=fr`. They run on the fake devices and write only to temporary folders
(HOME is a temporary folder too), so no camera is needed and none of your files are touched. CI does
the same on Fedora and in the published SparkOS image.

**What has been tried on real hardware (the owner's PC, 2026-11-24):** the window installed with
`install.sh --user` and driven with a Logitech C920 PRO and its microphone: preview, a 1280x720 photo, a
3 second VP9 video with sound, and a voice recording; plus the engine alone with the HyperX QuadCast, VP9, H.264
and VP8. The room was dark, so the photo came out nearly black: its size and format were checked, not how it looks.
**What has only been tried on the test pattern and test tone:** the countdown, pause, rename and delete, and the
French window.
