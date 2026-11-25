# Spark Fonts

See, install and remove fonts. Replaces KDE's Font Management page and font viewer.

- Lists every font on the system and in your own folder, grouped by family, with search and filters.
- Preview, characters and details tabs: sample text, glyph grid, licence, designer, variable axes.
- Install from files, a folder or a zip (drag and drop works). Installs go to `~/.local/share/fonts`, for you only.
- Remove works on the fonts you installed, by family. System fonts are shown with a lock and can't be removed.
- Finds the fonts on a Windows drive (read only) and installs the ones you pick.
- Opens font files from the file manager: `spark-fonts FILE...` previews them, and offers to install.
- WOFF and WOFF2 can be viewed but not installed.
- English and French.

Command line: `spark-fonts --install FILE...`, `--version`, `--self-test`.

## Install

    bash install.sh --user          # for you, no root
    sudo bash install.sh            # system-wide
    bash install.sh --user --uninstall

Needs python3, Tk, Pillow (draws the previews) and fontconfig. `--deps` installs them on Fedora.
Uninstalling the app keeps the fonts you installed, and keeps settings and logs in
`~/.config/spark-fonts` and `~/.local/state/spark-fonts`.

## Tests

    python3 -m unittest discover -s tests          # needs a display (Xvfb in CI)
    SPARK_LANG=fr python3 -m unittest discover -s tests

Tests run in a temporary HOME and never touch your real fonts.
