# Spark Fonts: see, install and remove fonts

Built into the image, live updates on. Replaces KDE's font page (`kcm_fontinst`) and font viewer
(`kfontview`). Part of stage 2 of [Replacing KDE](../PLAN.md).

## Why

Fonts are something everyone installs sooner or later (a design download, a font for a game mod
or a document from Windows). Today that means KDE's Font Management page, which looks nothing like
SparkOS, and double-clicking a `.ttf` opens KDE's viewer.

## What

- **All fonts, grouped by family:** search by name, filters (All, Mine, System; Sans, Serif, Mono,
  Display, Script by fontconfig's style hints where it has them; "Supports French", "Supports
  Japanese" and the like by `:lang=`), a count.
- **Preview:** a sample line you can type over, a size slider (8 to 96), every style of the family
  (Regular, Italic, Bold...), the character set as a grid with a search by character. Light text
  on dark by default, a switch for dark on light.
- **Details:** family, style, version, designer and foundry, licence text when the font has one,
  file path and format, languages covered, whether it is a variable font and its axes.
- **Install:** drop font files or a `.zip` of them on the window, or "Install..." with a file
  picker, or double-click a `.ttf`/`.otf`/`.ttc` in Spark Files (opens a preview with INSTALL).
  Installs for the current user into `~/.local/share/fonts/` (one folder per family), then runs
  `fc-cache` on that folder. Says when the font is already installed (same family and style),
  and offers to replace it.
- **Remove:** user fonts only, to the trash (so a mistake is undone in Spark Files). System fonts
  show a lock and the reason: they come with SparkOS and the system is read-only.
- **Import from Windows:** a button that lists the fonts in a Windows drive's `Windows\Fonts`
  (and `AppData\Local\Microsoft\Windows\Fonts` for each Windows user) that are not installed
  here, with checkboxes. Copies only; never writes to the Windows drive. Reuse how Spark Welcome
  finds the Windows drive rather than writing a new search. Note in the window that Windows' own
  fonts are licensed with Windows.
- **Broken fonts:** a file fontconfig can't read is listed apart with "Remove" instead of
  disappearing silently.
- `spark-fonts FILE...` opens the preview; `spark-fonts --install FILE...` installs without the
  window.

Non-goals for 0.1: installing for all users (the system font folder is read-only on SparkOS;
`/usr/local/share/fonts` would need a root helper, maybe later), font editing, Google Fonts
download (an outside service; maybe later through Spark Store), choosing the desktop's UI fonts
(that stays in Spark Settings, which gets a "Manage fonts..." button to open Spark Fonts).

## How

- **Tk app** like most Spark apps, house style (`wolklaw-design` skill: dark, sharp 3px corners,
  magenta/cyan channel slip only, mono font for the UI), English and French with the text-fit
  check.
- **Font data from fontconfig's tools:** `fc-list` with a `--format` that gives file, family,
  style, weight, slant, spacing, lang, fontformat, variable; `fc-query` for one file not
  installed. No fontTools dependency unless the licence text needs it (the `name` table's licence
  string can be read in a few lines of `struct`; do that).
- **Previews with Pillow** (`ImageFont.truetype` with the face index for `.ttc` and the named
  instance for variable fonts), drawn to images in the window. Tk can only draw installed fonts by
  family name, and preview has to work for files that are not installed, so use Pillow for all
  previews. Render in a background thread and cache per (file, size, text); the list must stay
  smooth with the thousand-plus faces a normal system has.
- **Install** copies the file (never moves the user's original), checks it opens with Pillow first,
  refuses anything that isn't a font by content (not by extension), and unpacks `.zip` files
  safely (no absolute paths, no `..`, no links, size limit).
- **Default app:** Spark Fonts becomes the handler for `font/ttf`, `font/otf`, `font/collection`,
  `font/woff`, `font/woff2` (view only for WOFF, install for TTF/OTF/TTC; FreeType reads WOFF,
  installing it is pointless), set the way the other defaults are set in the image. Hide
  `kcm_fontinst` and `kfontview` from the menu the way
  [sparkos-cleanup.sh](../files/scripts/sparkos-cleanup.sh) hides the others (they stay
  installed one release).
- **Spark Settings:** add the "Manage fonts..." button on its fonts page if it has one; if it
  opens KDE's page for fonts today, point that at Spark Fonts.

## Decisions

- **Per-user installs only** in 0.1: no root part, `system_api` 1, live updates on.
- **Pillow for every preview,** for the reason above. Pillow is already in the image (Spark
  Camera, Spark Snip).

## Tests

- Unit: parsing `fc-list`/`fc-query` output (fixtures), the family grouping, the filters, the
  licence reader on a test font, install and remove in a temp `$HOME` with a real `fc-cache`
  (DejaVu from the runner as the test font; also a `.ttc` and a variable font if the runner has
  them, else skip with a reason), the zip unpacker against hostile zips, the Windows import on a
  fake Windows tree, "not a font" refused.
- The window under Xvfb in English and French with the text-fit check; a list scroll test with
  a few hundred faces must stay under a time budget.
- The `sparkos` job: inside the published image, install a test font as a normal user, see it in
  `fc-list`, remove it.
- Boot test: opens from the menu in English and French like the other built-in apps.

## Files

`files/spark-fonts/` like the other built-in apps (`spark_fonts.py`, `sparkfonts/`, `install.sh`,
`spark-app.json` with `live_update` true and `system_api` 1, desktop file with the MIME types,
icons from `make_icons.py`, `tests/`, README.md), `.github/workflows/spark-fonts.yml`, the image
wiring the other built-in apps use, the cleanup script, Spark Settings' button, and the row in
[README.md](README.md).

## Status

PR open (2026-11-24): Spark Fonts 0.1.0, source in files/spark-fonts.
