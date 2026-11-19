# Spark Snip

The SparkOS tool for screenshots, copying text off the screen, and screen recording. It grew out of [QuickOCR](https://github.com/Wolklaw/QuickOCR), whose Windows app is finished.

| Key | Does |
|---|---|
| Print, Meta+Shift+S | Screenshot an area. It goes on the clipboard. Read its text or save it from the window that follows. |
| Meta+Shift+T | Copy the text in an area (OCR, English and French). |
| Meta+Shift+R | Record an area or a whole screen. Press again, or STOP, to finish. |

The screen freezes, you drag a box (or click once for the whole monitor), and the chip at the top switches between TEXT, IMAGE and VIDEO (T, I and V also work). Esc or a right-click cancels. Recordings go to `~/Videos/Screencasts` and saved screenshots to `~/Pictures/Screenshots`. Settings are in `~/.config/spark-snip/config.json` and the log in `~/.local/state/spark-snip/`.

Everything runs on the computer. Nothing is uploaded.

## How it works

- **Screenshots:** on Plasma, Spectacle reads the screen in the background (KWin only lets trusted programs do that). grim and gnome-screenshot are used on other Wayland desktops, and Pillow on X11. Spark Snip then shows that frozen frame full screen, so what you pick is exactly what you saw.
- **Text:** Tesseract, with the same preprocessing as QuickOCR: three variants, and the most confident read wins.
- **Recording:** the desktop's ScreenCast portal shares one monitor as a PipeWire stream, and GStreamer crops it to the area and encodes it. It tries the GPU (VA-API H.264) first, then x264, OpenH264, and finally VP8 in WebM. The first recording on each monitor shows Plasma's share dialog. The answer is remembered after that. System sound is on by default and the microphone is off. Switch them in the main window, or with M and S in the overlay.
- **Interface:** Tk, in the Wolklaw app style: BotWatch palette, mono type, sharp corners, and the magenta/cyan channel slip.

## Run, install, test

```
python3 spark_snip.py                 # the window
python3 spark_snip.py text            # straight to a capture: text, image or video
python3 spark_snip.py --self-test     # OCR samples and a test encode, no display needed
sudo bash install.sh --deps           # system-wide, with Fedora packages (what the image build runs)
python3 -m unittest discover -s tests -v
python3 make_icons.py                 # redraw icons/ after changing the mark
```

The tests that open windows need a display. CI runs them under Xvfb in a Fedora container ([workflow](../../.github/workflows/spark-snip.yml)), and the SparkOS image build runs `--self-test` inside the real image.

## Known gaps

- Not tried by hand on a SparkOS desktop yet. CI covers install, OCR, encoding and the overlay under X11. The Plasma Wayland paths (Spectacle capture, the share portal, global shortcuts, scaling) have only been checked against their documentation.
- A selection stays on one monitor. Mixed scaling across monitors may misplace the recorded area.
- On an existing install, Plasma keeps the shortcuts it already has saved. If Print still opens Spectacle, set it in System Settings > Shortcuts > Spark Snip.
- No annotation or upload. Flameshot is in the image for that.
