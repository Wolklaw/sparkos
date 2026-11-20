# Spark Scan

Scanning for SparkOS. It finds your scanner, previews the glass, lets you drag out the part to keep, scans page after page (or the whole feeder), lets you turn, straighten and lighten each page, and saves one PDF, searchable if you want, or an image per page to `Documents/Scans`. Everything runs on this computer; nothing is uploaded.

It is an optional Spark app: it installs for one user without root (`install.sh --user`), and has a build step ([files/scripts/spark-scan.sh](../scripts/spark-scan.sh)) in case the owner moves it into the image. It replaces the switching guide's advice to install Skanpage.

- **Scanner:** every scanner SANE finds, on USB and on the network (Canon printers through the `pixma` and `airscan` backends). The last one used is remembered and asked first, so it is usually ready before the full search finishes. When none is found it says what to check: power, USB or the network.
- **Source:** Glass, Feeder, and Both sides when the scanner has them. The feeder scans every sheet in it in one go; each page appears as soon as it is done.
- **Preview and crop:** Preview scans the whole glass at 75 dpi. Drag on it to mark the part to scan; drag inside the mark to move it, or a corner to resize it. A click, or the crop button next to the size, goes back to the whole glass. The scanner itself is told the area, so it scans less and faster; for a scanner that can't be told, the page is cropped after.
- **Resolution and colour:** 150, 300 or 600 dpi (the scanner's nearest, if it doesn't offer exactly that); colour, grey, or black and white. Black and white is scanned in grey and turned into black and white here (Otsu's threshold), so it looks the same on every scanner and stays small.
- **Pages:** scan as many as you like. Click a page to see it; move it up or down, or delete it. Clear removes them all (it asks if they aren't saved). The button at the bottom right of the page list turns every page a quarter turn right (twice for a feeder load that came out upside down).
- **Fix a page after the scan:** under the page shown, turn it left, right or 180°; **Straighten** a page scanned at a slant (it measures the angle of the lines of text, up to 10° either way, and turns the page back; the corners that come in are white); **Whiten paper** for documents (grey or yellowed paper becomes white and the ink darker; each colour is evened out separately, so tinted paper comes out white too); **Brightness** and **Contrast** sliders, with the page following the slider as you drag. Reset puts the page back as scanned. Straighten and Whiten paper stay on for the pages you scan next, until you turn them off. Black and white pages turn and straighten, but have no brightness or contrast.
- **Edits are applied when saving.** The scan in the cache is never changed; the PDF, the PNGs and JPGs, and the text tesseract reads are made from the page with its edits, so OCR reads the straightened page.
- **Save:** one PDF, or one PNG or JPG per page. Named by date, like `Scan 2026-11-20 14.32.pdf`, with ` (2)` added instead of ever overwriting. **Searchable text** runs tesseract over the pages (English, French, or both) and saves a PDF with the text laid invisibly over the pages, so you can search it and copy from it.
- **Slow things run in the background**, with progress and Cancel: finding scanners, scanning, saving and reading text. A cancelled feeder scan keeps the pages already done. Closing with unsaved pages asks first.

Shortcuts: Ctrl+P preview, Ctrl+Enter scan, Ctrl+S save, Escape cancels (or clears the crop), Delete deletes the selected page, Alt+Up and Alt+Down move it, Up and Down pick a page, Ctrl+R and Ctrl+L turn it right and left, Ctrl+Shift+R turns every page, Ctrl+W closes. On a slider: Left and Right step by 5, Home or a double-click goes back to 0.

The interface is in English, and in French when the desktop's language is French (the first of `LC_ALL`, `LC_MESSAGES` and `LANG` that is set starts with `fr`). `SPARK_LANG=en` or `SPARK_LANG=fr` picks one. Every sentence is in [sparkscan/text.py](sparkscan/text.py).

## How it works

- **SANE through `scanimage`.** python-sane isn't in the SparkOS image, and `scanimage` (sane-backends, in the image) is what every backend is tested with, so Spark Scan runs it: `scanimage -f …` lists scanners, `scanimage -d DEVICE -A` says what a scanner offers (modes, resolutions, glass size, sources), and each scan is one `scanimage` writing a PNM file, `--batch` for the feeder. Its progress output drives the progress bar; Cancel sends it SIGTERM, which makes it cancel the scan, then SIGKILL 6 seconds later if it is still there. Scanner errors (jammed, cover open, busy, feeder empty, connection lost) are turned into plain sentences.
- **Pages stay on disk**, in `~/.cache/spark-scan/session-…/`, not in memory, so a long document at 600 dpi doesn't fill the RAM. A page that needs no change is kept exactly as the scanner sent it. The folder is removed when the window closes (and any left by a crash, after a day).
- **The PDF is written here**, a page at a time ([sparkscan/document.py](sparkscan/document.py)): colour and grey pages as JPEG (quality 85), black and white as 1-bit (Flate), each page the real size of what was scanned. No PDF library is needed. Searchable PDFs are made by `tesseract pages.txt out pdf`, which puts the page JPEGs into the PDF without encoding them again.
- **Page edits** ([sparkscan/adjust.py](sparkscan/adjust.py)) use Pillow only, which Spark Scan already needs (no numpy, no ImageMagick). Each page carries its edits; they are applied in a fixed order (turn, straighten, then one lookup table for Whiten paper, contrast and brightness) when the page is opened for saving or OCR. The window shows them on the page's screen-sized copy, and a slider only redoes the lookup table on the copy already scaled to the view: redrawing after a turn or straightening takes about 35 ms for a 300 dpi A4 page, and a slider step about 1 ms (Windows development PC; the tests check both stay under 100 ms). Applying the edits to the whole 300 dpi page for saving takes about 0.4 s.
- **Straightening** binarises a copy about 1100 pixels long (Otsu's threshold), keeps only where ink starts and stops going down the page, and turns that by 1° steps from −11° to 11°, then 0.1° steps around the best; the angle where those edges pile up in the fewest rows wins. It does this across and down the page, so a page scanned sideways works too. Going by edges rather than ink also handles grids and tables. With no clear best angle (a blank page, a photo) it says so and leaves the page alone. About 0.2 s, in the background.
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
spark-scan --scan-to ~/doc.pdf --source feeder --straighten --whiten --rotate 180
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

`--user` needs only what the SparkOS image already has: Python 3 with tkinter and Pillow, SANE's `scanimage`, and tesseract with English and French for searchable PDFs (optional). It installs to `~/.local/lib/spark-scan/`, `~/.local/bin/spark-scan`, `~/.local/share/applications/` and `~/.local/share/icons/`, and lists every file it wrote in `~/.local/lib/spark-scan/installed-files` for `--uninstall`. Settings, the log and your scans are left in place.

`spark-app.json` describes the app for the Spark Portal (ID, name, summary, version, size, what it needs, how to install it).

**Without a scanner.** `tests/fake_scanimage.py` stands in for `scanimage` (a pixma-like scanner with a glass and a feeder, and errors on request): `SPARK_SCAN_SCANIMAGE="python3 tests/fake_scanimage.py" python3 spark_scan.py`. SANE also has its own test scanner: put `test` in a `dll.conf` in a folder, point `SANE_CONFIG_DIR` at it, and use device `test:0`.

The tests ([tests/test_spark_scan.py](tests/test_spark_scan.py)) cover the parsers (including what the test scanner and sane-airscan print), the PDF writer (every object where the cross-reference table says, checked by `pdfinfo` and `qpdf` too), file names, both text tables (every English sentence has its French with the same blanks; the language comes from `LC_ALL`, `LC_MESSAGES`, `LANG` and `SPARK_LANG`), and the window (preview, crop, scan, the feeder, reorder, delete, save, an error, Cancel, no scanner, and every page edit followed by a save). Page edits are tested on generated A4 pages of text tilted by known angles from −9.6° to 10°, in colour, grey and black and white, sideways, and with sparse lines (each must be measured within 0.5°; they come out within 0.1°), on checkerboards like the test scanner's, on blank pages and noise (left alone), and for the turns, the tone, saving with edits, and the under-100 ms redraw. Through the real `scanimage` and SANE's test scanner, they scan with a crop at 150, 300 and 600 dpi in colour, grey and black and white, empty the feeder (10 sheets), check that jammed, cover open, busy, I/O error and feeder empty each give the right sentence, cancel a slow scan, and save multi-page PDFs and PNGs. A searchable PDF made by tesseract is read back with `pdftotext`, and so is one made from a page tilted 7° and straightened. The test scanner's grid is scanned, measured as straight, measured within 0.5° when tilted, turned and saved; `--scan-to` with `--rotate 90 --straighten --whiten` saves a turned page. CI ([workflow](../../.github/workflows/spark-scan.yml)) runs all of it in Fedora under Xvfb, and inside the published SparkOS image installs it with `--user` as a normal user, scans a searchable PDF with the test scanner, runs the tests on the image's Python and SANE, and uninstalls it.

## Known gaps

- **Not tried with a real scanner yet.** Everything above was tested with SANE's test scanner and the fake one; the owner's Canon TR4700 (Wi-Fi, so `airscan` and `pixma` will probably both list it) has not been scanned with. Whether its feeder is reported as a source, and how long it takes to show up, will be known on the first day.
- **One feeder side setting:** "Both sides" appears only if the backend offers a duplex source; the TR4700's feeder is one-sided.
- **Straighten, Whiten paper and the sliders have only met generated pages and the test scanner.** A real scan has shadows at the edges, the edge of the sheet on the glass, and photos mixed with text; how well the angle is found on those, and whether Whiten paper is too strong on a coloured page, will be known after the first real scans. Straightening keeps the page's size, so a page tilted 10° with text right into its corners loses a little at the corners.
- **No crop after the scan.** The crop is the part of the glass to scan (drag on the preview); a page already scanned can be turned and straightened, not cut down.
- **No drag and drop in the page list.** Pages move with the up and down buttons, or Alt+Up and Alt+Down.
- **Scanner search on SparkOS:** some of the image's SANE backends need D-Bus; in a desktop session that is always there. In a container or over SSH without one, `scanimage -L` can crash, and Spark Scan then says "Looking for scanners failed" rather than "No scanner found".
- **Opening speed:** building and drawing the window took 47 ms in CI (Fedora, Xvfb) and about 300 ms on a Windows development PC, Python's own start-up not included; the scanner search starts after the window is up. Not yet timed on the owner's PC.
