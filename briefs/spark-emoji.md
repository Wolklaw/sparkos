# Spark Emoji

Read [README.md](README.md) first for the conventions every Spark app follows, and load the
`wolklaw-design` skill for the look (the mono variant, the SparkOS colours).

## Why

Meta+. opens Plasma's Emoji Selector, which is KDE's, English-first, and the one Plasma app left in
the menu that no Spark app covers. The owner types in English and French and wants to find a character
by either name, and to get accented letters, arrows, currency and maths signs from the same place.

## What it does

- Meta+. opens a small popup. Type to search at once, in English and French together; accents and case
  don't matter ("coeur" finds the heart, "etoile" finds the star). `U+1F44D` finds a code point, and a
  typed character finds itself.
- Recently used first, then the categories (smileys, people, nature, food, travel, activities, objects,
  symbols, flags), then a Symbols tab: arrows, maths, currency, accented letters and other signs.
- Skin tones: right-click a hand or a person for the five tones, or set one tone for everything.
- Enter picks the first result, the arrow keys move around the grid, Esc closes, a click picks. Meta+.
  again closes it.
- A pick is copied to the clipboard and the old window is put back in front. If the person has allowed
  it, Spark Emoji also presses Ctrl+V there. If not, it says "copied, press Ctrl+V" in a notification.
  It never claims to have pasted when it only copied.

## Its own app, not part of Spark Launcher

Spark Launcher is a Plasma widget (QML) that lives on the dock and answers the Meta key. The picker
needs its own 1900-entry data set, a window that opens in a fraction of a second, per-user recents and
settings, and the paste logic below. None of that belongs in a plasmoid, and the two would be
released and tested together for no reason. The launcher keeps the Meta key; Spark Emoji takes
Meta+. only, through its desktop entry (`X-KDE-Shortcuts`), the way Spark Terminal takes Ctrl+Alt+T.

## Pasting on Wayland, honestly

Wayland lets no program type into another program's window. The only supported way is the XDG desktop
portal's RemoteDesktop interface, a keyboard-only session the person allows once (the desktop asks, and
remembers it with a restore token). Spark Emoji asks for that when the person clicks "Turn on pasting"
in the footer, and never before. What is certain: copying always works (Klipper keeps it after the
app exits). What is tested: the portal calls (create, select keyboard, start, then Ctrl+V; Ctrl+Shift+V
for terminals is in the code but not used yet) against a fake portal in CI. What is not tested: KDE's real portal and
the real permission dialog. That needs a booted SparkOS.

## Data and licence

Emoji and names come from Unicode's `emoji-test.txt` (v18.0) and the CLDR annotations in English and
French (licence Unicode-3.0, noted in THIRD-PARTY.md). `tools/make_data.py` turns them into two JSON
files that are committed, so the image build needs no network. Symbols (arrows, maths, currency, letters)
use the same CLDR names where they exist; accented letters are named from their parts, and a short
hand-written French list fills the rest.

## How

Python 3 with GTK 4 through PyGObject. GTK renders colour emoji (Pango with Noto Color Emoji), which Tk
can't. A unique `Gtk.Application`: the second Meta+. closes the picker, and the process lingers for a
minute so the clipboard is handed to Klipper and a second pick starts at once.

## Replacing Plasma's Emoji Selector

`files/scripts/spark-emoji.sh` installs the app, links its entry in `/usr/share/kglobalaccel`, and takes
`Meta+.` out of `org.kde.plasma.emojier`. `sparkos-cleanup.sh` hides the Emoji Selector from the menu.
It stays installed for one release.

## Tests

- Unit tests (no display): data, search in both languages, accents, ranking, recents, settings, the
  command line.
- Window tests under Xvfb: tabs, search, Enter and click pick, skin tones, recents.
- Portal tests against a fake portal on a private D-Bus (no activation, so the real portal can't answer).
- In the SparkOS image: the build step, `--self-test`, no other entry claims Meta+., a per-user
  install and uninstall. The boot test runs `--self-test` and checks the Emoji Selector is hidden.

## Done when

CI passes on Fedora and in the SparkOS image, Meta+. is Spark Emoji's in a test build, and the PR is
open for the owner. Marked 0.1.0 until pasting is seen working on a real KDE session.
