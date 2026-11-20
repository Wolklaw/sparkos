# Spark Scan

Scanning for SparkOS. It finds your scanner, previews the glass, lets you drag out the part to keep, scans page after page (or the whole feeder), and saves one PDF, searchable if you want, or an image per page to `Documents/Scans`. Everything runs on this computer; nothing is uploaded.

It is an optional Spark app: it installs for one user without root (`install.sh --user`), and has a build step ([files/scripts/spark-scan.sh](../scripts/spark-scan.sh)) in case the owner moves it into the image. It replaces the switching guide's advice to install Skanpage.

- **Scanner:** every scanner SANE finds, on USB and on the network (Canon printers through the `pixma` and `airscan` backends). The last one used is remembered and asked first, so it is usually ready before the full search finishes. When none is found it says what to check: power, USB or the network.
- **Source:** Glass, Feeder, and Both sides when the scanner has them. The feeder scans every sheet in it in one go; each page appears as soon as it is done.
- **Preview and crop:** Preview scans the whole glass at 75 dpi. Drag on it to mark the part to scan; drag inside the mark to move it, or a corner to resize it. A click, or the crop button next to the size, goes back to the whole glass. The scanner itself is told the area, so it scans less and faster; for a scanner that can't be told, the page is cropped after.
- **Resolution and colour:** 150, 300 or 600 dpi (the scanner's nearest, if it doesn't offer exactly that); colour, grey, or black and white. Black and white is scanned in grey and turned into black and white here (Otsu's threshold), so it looks the same on every scanner and stays small.
- **Pages:** scan as many as you like. Click a page to see it; move it up or down, or delete it. Clear removes them all (it asks if they aren't saved).
- **Save:** one PDF, or one PNG or JPG per page. Named by date, like `Scan 2026-11-20 14.32.pdf`, with ` (2)` added instead of ever overwriting. **Searchable text** runs tesseract over the pages (English, French, or both) and saves a PDF with the text laid invisibly over the pages, so you can search it and copy from it.
- **Slow things run in the background**, with progress and Cancel: finding scanners, scanning, saving and reading text. A cancelled feeder scan keeps the pages already done. Closing with unsaved pages asks first.

Shortcuts: Ctrl+P preview, Ctrl+Enter scan, Ctrl+S save, Escape cancels (or clears the crop), Delete deletes the selected page, Alt+Up and Alt+Down move it, Up and Down pick a page, Ctrl+W closes.

The interface is in English, and in French on a French desktop (`LANG=fr_*`); every sentence is in [sparkscan/text.py](sparkscan/text.py).

## How it works

- **SANE through `scanimage`.** python-sane isn't in the SparkOS image, and `scanimage` (sane-backends, in the image) is what every backend is tested with, so Spark Scan runs it: `scanimage -f …` lists scanners, `scanimage -d DEVICE -A` says what a scanner offers (modes, resolutions, glass size, sources), and each scan is one `scanimage` writing a PNM file, `--batch` for the feeder. Its progress output drives the progress bar; Cancel sends it SIGTERM, which makes it cancel the scan, then SIGKILL 6 seconds later if it is still there. Scanner errors (jammed, cover open, busy, feeder empty, connection lost) are turned into plain sentences.
- **Pages stay on disk**, in `~/.cache/spark-scan/session-…/`, not in memory, so a long document at 600 dpi doesn't fill the RAM. A page that needs no change is kept exactly as the scanner sent it. The folder is removed when the window closes (and any left by a crash, after a day).
- **The PDF is written here**, a page at a time ([sparkscan/document.py](sparkscan/document.py)): colour and grey pages as JPEG (quality 85), black and white as 1-bit (Flate), each page the real size of what was scanned. No PDF library is needed. Searchable PDFs are made by `tesseract pages.txt out pdf`, which puts the page JPEGs into the PDF without encoding them again.
- **Light.** Nothing polls while nothing is happening; the window checks for results only while something runs in the background. The window opens before any scanner is looked for.

Settings are in `~/.config/spark-scan/`, the log in `~/.local/state/spark-scan/`.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the build step runs)
spark-scan                                # the window
spark-scan --device airscan:e0:…          # start with this scanner
spark-scan --list                         # the scanners SANE finds
spark-scan --self-test                    # what it needs and what it finds; no display needed
spark-scan --scan-to ~/doc.pdf --pages 2 --dpi 300 --mode gray --ocr    # no window
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

`--user` needs only what the SparkOS image already has: Python 3 with tkinter and Pillow, SANE's `scanimage`, and tesseract with English and French for searchable PDFs (optional). It installs to `~/.local/lib/spark-scan/`, `~/.local/bin/spark-scan`, `~/.local/share/applications/` and `~/.local/share/icons/`, and lists every file it wrote in `~/.local/lib/spark-scan/installed-files` for `--uninstall`. Settings, the log and your scans are left in place.

`spark-app.json` describes the app for the Spark Portal (ID, name, summary, version, size, what it needs, how to install it).

**Without a scanner.** `tests/fake_scanimage.py` stands in for `scanimage` (a pixma-like scanner with a glass and a feeder, and errors on request): `SPARK_SCAN_SCANIMAGE="python3 tests/fake_scanimage.py" python3 spark_scan.py`. SANE also has its own test scanner: put `test` in a `dll.conf` in a folder, point `SANE_CONFIG_DIR` at it, and use device `test:0`.

The tests ([tests/test_spark_scan.py](tests/test_spark_scan.py)) cover the parsers (including what the test scanner and sane-airscan print), the PDF writer (every object where the cross-reference table says, checked by `pdfinfo` and `qpdf` too), file names, both text tables, and the window (preview, crop, scan, the feeder, reorder, delete, save, an error, Cancel, no scanner). Through the real `scanimage` and SANE's test scanner, they scan with a crop at 150, 300 and 600 dpi in colour, grey and black and white, empty the feeder (10 sheets), check that jammed, cover open, busy, I/O error and feeder empty each give the right sentence, cancel a slow scan, and save multi-page PDFs and PNGs. A searchable PDF made by tesseract is read back with `pdftotext`. CI ([workflow](../../.github/workflows/spark-scan.yml)) runs all of it in Fedora under Xvfb, and inside the published SparkOS image installs it with `--user` as a normal user, scans a searchable PDF with the test scanner, runs the tests on the image's Python and SANE, and uninstalls it.

## Known gaps

- **Not tried with a real scanner yet.** Everything above was tested with SANE's test scanner and the fake one; the owner's Canon TR4700 (Wi-Fi, so `airscan` and `pixma` will probably both list it) has not been scanned with. Whether its feeder is reported as a source, and how long it takes to show up, will be known on the first day.
- **One feeder side setting:** "Both sides" appears only if the backend offers a duplex source; the TR4700's feeder is one-sided.
- **No rotation, deskew, brightness or contrast.** Rotate in Spark Media or another editor for now.
- **Scanner search on SparkOS:** some of the image's SANE backends need D-Bus; in a desktop session that is always there. In a container or over SSH without one, `scanimage -L` can crash, and Spark Scan then says "Looking for scanners failed" rather than "No scanner found".
- **Opening speed:** building and drawing the window took 47 ms in CI (Fedora, Xvfb) and about 300 ms on a Windows development PC, Python's own start-up not included; the scanner search starts after the window is up. Not yet timed on the owner's PC.
