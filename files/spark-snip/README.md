# Spark Snip

The SparkOS tool for screenshots, copying text off the screen, and screen recording. It grew out of [QuickOCR](https://github.com/Wolklaw/QuickOCR), whose Windows app is finished.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

| Key | Does |
|---|---|
| Print, Meta+Shift+S | Screenshot an area. It goes on the clipboard. Read its text or save it from the window that follows. |
| Meta+Shift+T | Copy the text in an area (OCR, English and French). |
| Meta+Shift+R | Record an area or a whole screen. Press again, or STOP, to finish. |

The screen freezes, you drag a box (or click once for the whole monitor), and the chip at the top switches between TEXT, IMAGE and VIDEO (T, I and V also work). Esc or a right-click cancels. Recordings go to `~/Videos/Screencasts` and saved screenshots to `~/Pictures/Screenshots`. The last screenshot is also kept as `~/.cache/spark-snip/latest.png`, replaced by the next one, for Spark Link's Send screenshot. Settings are in `~/.config/spark-snip/config.json` and the log in `~/.local/state/spark-snip/`.

Everything runs on the computer. Nothing is uploaded.

## How it works

- **Screenshots:** on Plasma, Spark Snip asks KWin for the whole desktop over D-Bus (`org.kde.KWin.ScreenShot2`, `CaptureWorkspace`, at the screens' native resolution). KWin writes the pixels into a pipe; there is no helper program and no file on disk. If KWin refuses or isn't there, it uses Spectacle while Spectacle is still installed, then asks the XDG Desktop Portal for a screenshot. grim and gnome-screenshot are used on other Wayland desktops, and Pillow on X11. Spark Snip then shows that frozen frame full screen, so what you pick is exactly what you saw. Spark Snip never needs Spectacle.
- **Text:** Tesseract, with the same preprocessing as QuickOCR: three variants, and the most confident read wins.
- **Recording:** the desktop's ScreenCast portal shares one monitor as a PipeWire stream, and GStreamer crops it to the area and encodes it. It tries the GPU (VA-API H.264) first, then x264, OpenH264, and finally VP8 in WebM. The first recording on each monitor shows Plasma's share dialog. The answer is remembered after that. System sound is on by default and the microphone is off. Switch them in the main window, or with M and S in the overlay.
- **Interface:** Tk, in the Wolklaw app style: BotWatch palette, mono type, sharp corners, and the magenta/cyan channel slip.

## Run, install, test

```
python3 spark_snip.py                 # the window
python3 spark_snip.py text            # straight to a capture: text, image or video
python3 spark_snip.py --self-test     # OCR samples, capture setup, a test encode; no display needed
python3 spark_snip.py --capture-test /tmp/snip.png  # in a Plasma session: one screenshot through KWin only; exit 1 if it fails
python3 spark_snip.py --capture-check # on a desktop: try every capture path, save the results
sudo bash install.sh --deps           # system-wide, with Fedora packages (what the image build runs)
python3 -m unittest discover -s tests -v
python3 make_icons.py                 # redraw icons/ after changing the mark
```

The tests that open windows need a display. The D-Bus capture tests need `dbus-daemon` and run the real client against a stand-in KWin and portal ([tests/fake_desktop.py](tests/fake_desktop.py)) on a private bus. CI runs everything under Xvfb in a Fedora container and again inside the published SparkOS image with Spectacle removed ([workflow](../../.github/workflows/spark-snip.yml)), and the SparkOS image build runs `--self-test` inside the real image.

## Known gaps

- Opened on a real SparkOS desktop in CI, not used by hand yet. The boot test opens its window from the app menu in a Plasma 6.8 session in a VM, in English and in French, keeps a screenshot and fails on a Python traceback; it also takes a real screenshot through KWin (`--capture-test`). CI covers install, OCR, encoding, the overlay under X11, and the KWin and portal screenshot client against stand-ins. The real KWin and portal on Plasma Wayland, the share portal for recording, global shortcuts and scaling have only been checked against KWin's source and the portal documentation. `spark-snip --capture-check` on a Plasma session tries each capture path and saves what it got to `~/.cache/spark-snip/capture-check/`.
- KWin's screenshot interface answers any program from Plasma 6.8 on (SparkOS has 6.8). Older Plasma only answers programs whose desktop entry declares it, matched by the running executable, which for Spark Snip is Python, so there it will likely fall back to the portal.
- A selection stays on one monitor. Mixed scaling across monitors may misplace the recorded area.
- On an existing install, Plasma keeps the shortcuts it already has saved. If Print does nothing or opens something else, set it in System Settings > Shortcuts > Spark Snip.
- No annotation or upload. For those, install Flameshot from the Store (it isn't in the image).
