# Spark Notes

The SparkOS quick notes and clipboard history. It is bound to Meta+V (Windows key and
V). Version 0.1.0. No account, no cloud: everything stays in your home folder.

## Using it

**Notes.** Open Spark Notes from the app menu. A list of plain-text notes on the left, the note on
the right, a search box on top. Light markdown: `# headings`, `- lists`, `- [ ]` tasks you can tick,
`**bold**`. Pin a note to keep it at the top. Notes save as you type, one file each, in
`~/.local/share/spark-notes`. Nothing to open, save or sync.

**Clipboard history.** Meta+V opens a small popup with the last texts and images you copied.

| | |
|---|---|
| Meta+V | open the popup (again while it is open: close it) |
| type | search the history |
| click or Enter | copy that item again |
| pin | keep an item; pinned items are never dropped or cleared |
| Clear | remove everything that isn't pinned |
| Don't keep | pause: nothing you copy is kept until you turn it back on |
| Esc | close |

What it skips: anything the program marks as sensitive (`x-kde-passwordManagerHint`, which KeePassXC,
Bitwarden and others set), and everything while paused. The history keeps the last 50 items by
default (5 to 500, in the settings).

## The watcher

A small background process (`spark-notes --watch`, a systemd user service started at login) listens
to the clipboard and records what you copy, so the history is there even when no window is open.
Closing the popup does not stop it. When the program you copied from closes, Wayland normally drops the
copy; the watcher puts the newest item back (setting `keep_alive`, on by default).

It needs `wl-clipboard` (`wl-paste`, `wl-copy`), a Fedora package that SparkOS's image step installs.

## The command line

```
spark-notes                  open the notes
spark-notes --clipboard      open the clipboard popup (again: close it)
spark-notes --watch          the background service
spark-notes --list [QUERY]   print the history, or what matches QUERY
spark-notes --pause          stop keeping what you copy
spark-notes --resume         keep it again
spark-notes --version
spark-notes --self-test      check what it needs, without a window
```

Language follows `LC_ALL`, `LC_MESSAGES`, `LANG` (English or Quebec French); `SPARK_LANG=en|fr` wins.

## Installing

On SparkOS it is in the image (`files/scripts/spark-notes.sh`). The image step installs the app and
`wl-clipboard`, enables the watcher for every login and gives the popup Meta+V.

Elsewhere:

```
bash install.sh --user              just you, no root (into ~/.local); starts the watcher
bash install.sh --user --uninstall  remove exactly what --user installed
sudo bash install.sh --deps         system-wide, installing dependencies with dnf first
```

Per user there is no Meta+V (the desktop reads shortcuts from /usr/share); start the popup from
the app menu (right-click Spark Notes, Clipboard) or run `spark-notes --clipboard`. Uninstalling
keeps your notes, history and settings (`~/.local/share/spark-notes`, `~/.config/spark-notes`,
`~/.local/state/spark-notes`).

## Honest limits

- Wayland with a compositor that has the data-control protocol (the Spark compositor does). Without it the
  history stays empty and the notes still work. X11 is untested.
- Meta+V is a built-in bind of the Spark compositor; there is no Klipper in the image. It is tested only as files and CI, not on hardware.

## Tests

```
python3 -m unittest tests.test_core -v      no display; the watcher runs against a fake wl-paste and wl-copy
dbus-run-session -- xvfb-run -a python3 -m unittest tests.test_ui -v     windows (GDK_DEBUG=no-portals in a sandbox)
bash tests/image_check.sh                   inside the SparkOS image, as root (what CI does)
```

CI (`.github/workflows/spark-notes.yml`) runs them on Fedora and inside the published SparkOS image.
`SPARK_SHOT_DIR=folder` saves screenshots from the window tests. `make_icons.py` redraws the icons.
