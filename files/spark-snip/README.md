# Spark Snip

The SparkOS tool for screenshots, copying text off the screen, and screen recording. It grew out of [QuickOCR](https://github.com/Wolklaw/QuickOCR), whose Windows app is finished.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

| Key | Does |
|---|---|
| Print, Meta+Shift+S | Screenshot an area. It goes on the clipboard. Read its text or save it from the window that follows. |
| Meta+Shift+T | Copy the text in an area (OCR, English and French). |
| Meta+Shift+R | Record an area or a whole screen. Press again, or STOP, to finish. |

The screen freezes, you drag a box (or click once for the whole monitor), and the chip at the top switches between TEXT, IMAGE and VIDEO (T, I and V also work). Esc or a right-click cancels. Recordings go to `~/Videos/Screencasts` and saved screenshots to `~/Pictures/Screenshots`. The last screenshot is also kept as `~/.cache/spark-snip/latest.png`, replaced by the next one, for Spark Link's Send screenshot. Settings are in `~/.config/spark-snip/config.json` and the log in `~/.local/state/spark-snip/`.

After a screenshot, the result window has an **Annotate** button (or press E). The annotate window has an arrow, box, ellipse, pen, highlighter, text, numbered step markers, pixelate (hides what is under it, such as a password or a face) and crop. Pick a colour from the presets or the `…` picker, set the size with the slider, undo and redo with Ctrl+Z and Ctrl+Y, and finish with **Copy** (Ctrl+C) or **Save** (Ctrl+S, same file name and folder as the plain Save image). Esc throws the marks away (it asks first if you drew something). Either button puts the annotated picture on the clipboard and makes it the last screenshot (`latest.png`), so Spark Link's Send screenshot sends the annotated one, and returns to the result window. Text is one line per click: type, then Enter.

Everything runs on the computer. Nothing is uploaded.

## How it works

- **Screenshots:** in the Spark session, Spark Snip runs `grim` (the compositor's wlr-screencopy), which captures the whole desktop at the screens' native resolution, and falls back to the XDG Desktop Portal. Other wlroots compositors work the same way, gnome-screenshot is used on GNOME, and Pillow on X11. Spark Snip then shows that frozen frame full screen, so what you pick is exactly what you saw. The keys (Print, Super+Shift+S, T and R) are bound by spark-compositor, not by Spark Snip's desktop entry.
- **Text:** Tesseract, with the same preprocessing as QuickOCR: three variants, and the most confident read wins.
- **Recording:** the desktop's ScreenCast portal shares one monitor as a PipeWire stream, and GStreamer crops it to the area and encodes it. It tries the GPU (VA-API H.264) first, then x264, OpenH264, and finally VP8 in WebM. The first recording on each monitor shows the share dialog of the desktop's portal (on the Spark session, the wlroots portal, which has no picker yet). Where the portal remembers the answer, later recordings skip it. The answer is remembered after that. System sound is on by default and the microphone is off. Switch them in the main window, or with M and S in the overlay.
- **Annotation:** `sparksnip/annotate.py` holds the marks (frozen items, so undo is cheap) and draws them with Pillow, anti-aliased, at the screenshot's own resolution; `sparksnip/editor.py` is the Tk window, which scales the picture to fit the screen and converts mouse positions back to picture pixels, so a 4K shot on a scaled desktop is annotated at 4K. Crop moves the marks with the pixels.
- **Interface:** Tk, in the Wolklaw app style: BotWatch palette, mono type, sharp corners, and the magenta/cyan channel slip.

## Run, install, test

```
python3 spark_snip.py                 # the window
python3 spark_snip.py text            # straight to a capture: text, image or video
python3 spark_snip.py --self-test     # OCR samples, capture setup, a test encode; no display needed
python3 spark_snip.py --capture-test /tmp/snip.png  # in the Spark session: one screenshot through grim only; exit 1 if it fails
python3 spark_snip.py --capture-check # on a desktop: try every capture path, save the results
sudo bash install.sh --deps           # system-wide, with Fedora packages (what the image build runs)
python3 -m unittest discover -s tests -v
python3 make_icons.py                 # redraw icons/ after changing the mark
```

The tests that open windows need a display. The D-Bus capture tests need `dbus-daemon` and run the real client against a stand-in portal ([tests/fake_desktop.py](tests/fake_desktop.py)) on a private bus. grim is faked in the tests, so no compositor is needed. CI runs everything under Xvfb in a Fedora container and again inside the published SparkOS image ([workflow](../../.github/workflows/spark-snip.yml)), and the SparkOS image build runs `--self-test` inside the real image.

## Known gaps

- Opened on a real SparkOS desktop in CI, not used by hand yet. The boot test opens its window from the app menu in a VM, in English and in French, keeps a screenshot and fails on a Python traceback. CI covers install, OCR, encoding, the overlay under X11, and the portal screenshot client against a stand-in (grim is faked). The `grim` path in the Spark session, the wlroots share portal for recording, the compositor's Print and Super+Shift+S binds and scaling have not been checked on real hardware. `spark-snip --capture-check` on a desktop tries each capture path and saves what it got to `~/.cache/spark-snip/capture-check/`.
- A selection stays on one monitor. Mixed scaling across monitors may misplace the recorded area.
- The shortcuts are the compositor's (Print and Super+Shift+S for a screenshot, Super+Shift+T for text, Super+Shift+R for a recording). If one does nothing or opens something else, change it in Spark Settings > Shortcuts.
- Annotation has not been tried by hand on a SparkOS desktop (CI drives it under Xvfb and the tests draw onto generated images). Text is a single line per click and uses DejaVu Sans Bold (or Pillow's built-in font if it's missing). Pixelate is the only blur: it can't be undone from the saved file, which is the point. Annotating is for screenshots only, not for a picture opened from disk.
- No upload. Spark Snip never sends anything; for sharing to a site, use Flameshot from the Store (it isn't in the image).
