# Spark Camera

Read [README.md](README.md) first for the conventions every Spark app follows, and load the
`wolklaw-design` skill for the look (the mono variant, the SparkOS colours).

## Why

SparkOS has no app for the webcam or the microphone. The owner has a Logitech C920 PRO and a HyperX
QuadCast and wants to check the picture, take a photo, record a short video, and record a voice note,
without a third-party app or a browser tab. Spark Media already plays the results.

## What it does

- Camera tab: live preview, photos with an optional countdown (off, 3, 5, 10 s), video with sound, a choice
  of camera, size, microphone and format, a mirror switch (preview only), and a strip of the newest files.
- Voice tab: a voice recorder with a microphone choice, a level meter, record, pause and stop, Opus or FLAC,
  and a list of recordings that plays, renames and moves to the trash.
- Files go to `~/Pictures/Camera`, `~/Videos/Camera` and `~/Music/Recordings`.

## How

Python 3 with Tk for the window, as the other tool apps are, and GStreamer through PyGObject for the
pipelines. There is no GLib main loop: Tk timers poll the pipelines, the way Spark Media does.

- One camera pipeline feeds a `tee`: a small RGB branch for the preview, a full-size one for photos, and a
  recording branch that is added while the camera runs. The recorder is opened and warmed first (the microphone
  can take a second), then linked, with pad offsets so the file starts at 0. Stopping blocks the branch, sends
  end-of-stream, and waits for the file to close.
- The PipeWire camera source is used where it works, Video4Linux otherwise.
- Formats come from the installed elements: WebM VP9 and Opus, MP4 H.264 and AAC, WebM VP8 and Opus; voice as Opus or
  FLAC. Nothing is assumed.
- `SPARK_CAMERA_FAKE=1` swaps in a test pattern and a test tone. CI has no camera, so every test and the
  `--self-test` use it.

## Optional, through Spark Store

It ships as sources and installs by a click in Spark Store (no `files/scripts/spark-camera.sh`, so it is not
in the image). `install.sh --user` installs it for one person without root.

## What is known to be limited

- With the C920 the first usable video frame arrives about a second after the recording starts (the camera
  sends one old picture, which is dropped, then pauses). Sound and picture stay in step; WebM files begin with
  a short stretch of sound over no picture.
- Mirror affects only the preview.
- The window was run on the owner's desktop with the C920 and its microphone (photo, video, voice) and the
  QuadCast through the engine; the countdown, pause, rename, delete and French were only run on the test pattern
  and tone. No other cameras have been tried.

## Not in this version

Effects and filters, a still-photo burst mode, screen recording (a different job), choosing the save folders,
and streaming to other programs as a virtual camera.
