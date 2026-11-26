# Spark Media

The SparkOS app for photos, videos and music. Double-click a photo, video, song or playlist in the file manager and it opens here. Opened from the menu, it shows your Pictures, Videos or your music library.

- **Photos:** fit to the window, zoom around the pointer (wheel or + and -), drag to pan, rotate, slideshow, animated GIF and WebP, HEIC/HEIF and AVIF (what phones save), move to the Trash. Left and Right go through the folder.
- **Camera RAW:** CR2, CR3, NEF, ARW, DNG, RAF, ORF and RW2 (and PEF, SRW, NRW, CRW, 3FR, IIQ, RWL, X3F). A RAW opens at once on the JPEG the camera stored inside it; when that's smaller than the photo, the full picture is developed in the background and replaces it.
- **Edits:** rotate, crop (free, the photo's own shape, 1:1, 4:3, 3:2, 16:9) and auto-enhance. Saving makes a new file next to the original, `photo (edited).jpg`, unless you pick Replace. The date taken, camera, lens and exposure stay in the saved file.
- **Videos:** play, seek, volume, fullscreen (F or double-click), subtitles (embedded, or a `.srt`/`.ass`/`.vtt` file with the same name), a second audio track (A). Long videos pick up where you left off.
- **Music library:** your Music folder (and any folders you add) by Artists, Albums (a cover grid) and Songs, with search. Play an album or an artist, shuffle, add songs to the queue or play them next. The music keeps playing while you browse; the bar at the bottom shows what's on. "By folder" still browses the folders themselves.
- **Playlists:** opens `.m3u` and `.m3u8` files. Make playlists in the app, add songs from their right-click menu, reorder and remove them, or save the queue as one. They're saved as `.m3u8` files in `Music/Playlists`, with paths relative to the playlist, so other players and other computers open them too.
- **One window:** with Spark Media open, double-clicking another file hands it to the open window instead of starting a second one. A song or playlist goes into the queue and plays now; a photo or video opens in the window, which comes to the front.
- **Media keys and media controls:** the keyboard's play, pause, next and previous keys and anything else that speaks MPRIS2 (such as Spark Shell's media controls) control the music, with the title, artist, album and cover.
- **English and French:** French when the computer's language is French (`LC_ALL`, `LC_MESSAGES` or `LANG` starting with `fr`), English otherwise. `SPARK_LANG=en` or `SPARK_LANG=fr` overrides it.

Everything runs on the computer. Nothing is uploaded. Settings are in `~/.config/spark-media/`, the log in `~/.local/state/spark-media/`, the music index and album covers in `~/.cache/spark-media/`, and thumbnails go to the shared `~/.cache/thumbnails` (other file managers use it too).

| Key | Photos | Editing a photo | Videos and music |
|---|---|---|---|
| Left, Right | previous, next photo | | back, forward 5 s (Shift: 30 s) |
| Space | next photo | | play, pause |
| Page Up, Page Down | previous, next photo | | previous, next file |
| Up, Down | previous, next photo | | volume |
| + - 0 1 | zoom in, out, fit, 100% | | |
| R, S, Delete | rotate in view, slideshow, Trash | R, Shift+R: rotate right, left | |
| E | edit | auto-enhance on or off | |
| Enter, Ctrl+S | | save a copy | |
| M, A, S | | | mute, audio track, subtitles |
| F or F11, Esc | fullscreen, leave fullscreen or go back | Esc: cancel the edit | same |

In the music library: `/` or Ctrl+F searches, Enter plays, the Menu key or a right-click opens a song's menu, Backspace or Esc goes back up, Space plays or pauses.

## How it works

- **Photos:** Pillow, with EXIF orientation applied. Only the part on screen is resized, so a 50-megapixel photo zooms as fast as a small one.
- **HEIC/HEIF and AVIF:** libheif's C library (`libheif.so.1`, through ctypes). SparkOS's libheif (1.23.7) decodes HEVC with libde265 and AV1 with dav1d or libaom. libheif turns the photo upright itself; the date taken and camera come from its EXIF; the grid uses the thumbnail stored in the file when there is one. Edits are saved as a JPEG copy. Without a decoder for a file's format, the viewer says which one is missing.
- **Camera RAW:** the embedded JPEG is found by reading the file (no extra program), and the camera, date and settings come from the RAW's TIFF tags through Pillow. The full decode uses LibRaw's C library (`libraw_r`, through Python's ctypes) with the camera's white balance, in a background thread. SparkOS's image carries LibRaw; without it, RAWs still open on their preview.
- **Edits:** Pillow. Edit mode works on a copy at most 2400 px wide, so it stays quick; the save applies the edit to the full photo (the developed one for a RAW). Auto-enhance stretches the tones to the full range, ignoring the darkest and brightest half percent, keeps the colours' hue, and adds a little colour. JPEG, PNG, WebP and TIFF are saved in their own format; anything else (RAW, HEIC, GIF, ...) as a JPEG copy, and Replace is offered only for formats that can be written back.
- **Music tags:** TagLib's C library (`libtag_c`, TagLib 2, through ctypes), cover art included. In CI it reads a song's tags in about 0.1 ms (small test files, already in the disk cache; on a real first scan, reading the files from disk takes longer). Without TagLib, GStreamer's Discoverer reads the same tags, about 15 times slower.
- **Music library:** a background thread walks the folders, reads tags only for files that are new or changed since the last scan, and keeps the index (`music.json`) and one 320 px cover per album. It runs when the library opens (not again within 30 s) and when you change the folders. Nothing runs between scans: no file watching, no timers. Lists and the cover grid draw only the rows on screen, so 10 000 songs scroll like 10. In CI, grouping and sorting 10 000 songs takes about 0.03 s, loading the index 0.05 s, and a rescan of 10 000 unchanged files 0.05 s.
- **Videos and music:** GStreamer's playbin. The video draws straight into the window (glimagesink, then xvimagesink, then ximagesink), so frames never pass through Python. Music has its own player, owned by the app rather than a screen, so it keeps playing in the library. Formats depend on the system's decoders; SparkOS has the full FFmpeg set through gst-libav, and its build fails if H.264, H.265, AAC or MP3 can't play.
- **One window:** the open window listens on a socket in `$XDG_RUNTIME_DIR/spark-media/` (only you can reach it). A second `spark-media FILE` sends its files there and exits before it makes a window. A socket left behind by a crash answers nobody, so the next start removes it and listens in its place. `SPARK_MEDIA_NEW_INSTANCE=1` starts a separate window anyway.
- **MPRIS2:** `org.mpris.MediaPlayer2.SparkMedia` on the session bus, through GLib's Gio (PyGObject, already there for GStreamer). It starts with the music and runs in its own thread with its own GLib loop; a call from outside is handed to the window through a pipe the window watches, so nothing polls. Play, Pause, PlayPause, Next, Previous, Stop, Seek, SetPosition, OpenUri, Raise and Quit; Metadata (title, artist, album, album artist, track, length, a `file://` cover), PlaybackStatus, Volume, Shuffle and LoopStatus, with PropertiesChanged and Seeked signals.
- **Interface:** Tk, in the Wolklaw app style: BotWatch palette, mono type, sharp corners, and the magenta/cyan channel slip. The common widgets are shared with [Spark Snip](../spark-snip). Every word is in `sparkmedia/strings.py`, in English and French.

## Run, install, test

```
python3 spark_media.py                    # the library
python3 spark_media.py photo.jpg          # open a file (its folder becomes the list)
python3 spark_media.py mix.m3u8           # play a playlist
python3 spark_media.py --music            # start in Music
SPARK_LANG=fr python3 spark_media.py      # in French
python3 spark_media.py --self-test        # photo formats, decoders, playback; no display needed
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the image build runs)
python3 -m unittest discover -s tests -v
python3 tests/screenshots.py OUT fr       # pictures of the new screens, with invented music
python3 make_icons.py                     # redraw icons/ after changing the mark
```

The tests make their own test files: songs encoded with GStreamer and tagged (with a cover) in Python, and a small DNG written by hand. The three small HEIC and AVIF files in `tests/fixtures/` were made with pillow-heif (`tests/make_heif_fixtures.py` says how), because neither Fedora nor SparkOS has an HEVC encoder. The UI tests need a display; the MPRIS tests need a session bus and call Spark Media from outside with `gdbus`. CI runs everything under Xvfb and `dbus-run-session` in a Fedora container, then the self-test and the unit tests again inside the published SparkOS image, on its own TagLib, LibRaw, libheif, GStreamer and D-Bus ([workflow](../../.github/workflows/spark-media.yml)). The SparkOS boot test runs `--self-test` inside the real image.

## Known gaps

- Not tried by hand on a SparkOS desktop yet. Playback, the library, playlists, RAW and edits are covered by CI with generated files and fake outputs, not on real screens and speakers. The real RAW formats are tested through their embedded preview and a generated DNG, not with files from real cameras.
- Whether the compositor lets the window come to the front when a second double-click hands it a photo is not checked; the file always opens, but the window may only flash in the taskbar. Media keys and the hand-off are tested in CI against a real session bus and real second starts, not yet on hardware.
- Album artists and compilations are guessed from the tags: without an album artist, an album is grouped by its name and folder.
- No filters beyond auto-enhance, no straightening, no undo after saving (the original stays unless you picked Replace).
- No streaming or internet radio (web addresses in playlists are skipped), no casting.
