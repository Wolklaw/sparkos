# Spark Media

The SparkOS app for photos, videos and music. Double-click a photo, video or song in the file manager and it opens here. Opened from the menu, it shows your Pictures, Videos or Music folder.

- **Photos:** fit to the window, zoom around the pointer (wheel or + and -), drag to pan, rotate in view (the file isn't changed), slideshow, animated GIF and WebP, move to the Trash. Left and Right go through the folder.
- **Videos:** play, seek, volume, fullscreen (F or double-click), subtitles (embedded, or a `.srt`/`.ass`/`.vtt` file with the same name), a second audio track (A). Long videos pick up where you left off.
- **Music:** plays the folder in order, with cover art from the file or a `cover.jpg` next to it, shuffle and repeat.

Everything runs on the computer. Nothing is uploaded. Settings are in `~/.config/spark-media/`, the log in `~/.local/state/spark-media/`, and thumbnails go to the shared `~/.cache/thumbnails` (Dolphin uses it too).

| Key | Photos | Videos and music |
|---|---|---|
| Left, Right | previous, next photo | back, forward 5 s (Shift: 30 s) |
| Space | next photo | play, pause |
| Page Up, Page Down | previous, next photo | previous, next file |
| Up, Down | previous, next photo | volume |
| + - 0 1 | zoom in, out, fit, 100% | |
| R, S, Delete | rotate, slideshow, Trash | |
| M, A, S | | mute, audio track, subtitles |
| F or F11, Esc | fullscreen, leave fullscreen or go back | same |

## How it works

- **Photos:** Pillow, with EXIF orientation applied. Only the part on screen is resized, so a 50-megapixel photo zooms as fast as a small one. HEIC and AVIF open when the `pillow-heif` plugin is installed (the SparkOS build installs it).
- **Videos and music:** GStreamer's playbin. The video draws straight into the window (glimagesink, then xvimagesink, then ximagesink), so frames never pass through Python. Formats depend on the system's decoders; SparkOS has the full FFmpeg set through gst-libav, and its build fails if H.264, H.265, AAC or MP3 can't play.
- **Interface:** Tk, in the Wolklaw app style: BotWatch palette, mono type, sharp corners, and the magenta/cyan channel slip. The common widgets are shared with [Spark Snip](../spark-snip).

## Run, install, test

```
python3 spark_media.py                    # the library
python3 spark_media.py photo.jpg          # open a file (its folder becomes the list)
python3 spark_media.py --music            # start in Music
python3 spark_media.py --self-test        # photo formats, decoders, playback; no display needed
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the image build runs)
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

The UI tests need a display. CI runs everything under Xvfb in a Fedora container ([workflow](../../.github/workflows/spark-media.yml)), and the SparkOS boot test runs `--self-test` inside the real image.

## Known gaps

- Not tried by hand on a SparkOS desktop yet. The photo viewer and library were checked on Windows; playback is covered by CI with test files and fake outputs, not on real screens and speakers.
- No editing beyond rotate-in-view: no crop, no filters, no saving.
- No music library by artist or album. Music is browsed by folder.
- Camera RAW photos (CR2, NEF, ARW, DNG) don't open.
- No playlists files (.m3u), no streaming, no casting.
