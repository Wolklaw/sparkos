# Spark Notes

Read [README.md](README.md) first for the conventions every Spark app follows, and load the
`wolklaw-design` skill for the look (the mono variant, the SparkOS colours).

## Why

Meta+V opens Klipper, KDE's clipboard history, which sits inside the system tray and is one more
Plasma piece the owner did not choose. The owner wants a clipboard history that skips passwords and
can be paused, and a place for quick notes, without an account or a cloud.

## What it does

- Quick notes: plain text, light markdown (headings, lists, tick-able tasks, bold), search, pin,
  autosave to `~/.local/share/spark-notes`, one file per note.
- Clipboard history: the last N texts and images, search, click to copy again, pin, clear, a "don't
  keep" pause. It skips items marked `x-kde-passwordManagerHint`. Meta+V opens it as a small popup,
  and again closes it.
- A watcher (`spark-notes --watch`, a systemd user service) keeps recording when no window is open.
  When the program that copied something closes, Wayland drops the copy; the watcher puts the newest
  item back.

## Its own app

Same shape as Spark Emoji: GTK 4 through PyGObject, a unique `Gtk.Application` that lingers for a
minute, a popup entry (`dev.wolklaw.SparkNotes.Clipboard.desktop`) that carries `X-KDE-Shortcuts=Meta+V`
and is linked in `/usr/share/kglobalaccel`. Copy and paste go through `wl-clipboard` (`wl-paste
--watch`, `wl-copy`), which needs the data-control protocol that KWin offers. wl-clipboard is installed
by the image step and listed in THIRD-PARTY.md.

## Replacing Klipper

Klipper is not a file: it is the `org.kde.plasma.clipboard` entry of the system tray, inside
plasmashell, and Meta+V is its shortcut. So there is nothing to hide; it has to leave the tray.

- New profiles: the default layout (`org.kde.plasma.desktop-layout.js`) writes the tray's `extraItems`
  without it and `knownItems` with it.
- Existing profile (the owner's): a one-time update script
  (`contents/updates/sparkos-no-klipper.js`) removes the entry, edits the same lists and deletes
  Klipper's `show-on-mouse-pos` shortcut so Meta+V is free.
- `org.kde.klipper.desktop` is already `NoDisplay`.

The extra-items list in the layout is Plasma 6's defaults as copied from a profile and not checked
against Plasma's source; if it is wrong the tray keeps its defaults, Klipper stays, and Spark Notes
still works.

## Tests

- Unit tests (no display): notes, history, settings, the watcher against fake wl tools, the command
  line, English and French text.
- Window tests under Xvfb: popup, notes window, search, pin, tasks, the glitch.
- In the SparkOS image: the build step, `--self-test`, no other entry claims Meta+V, a per-user
  install and uninstall. The boot test runs `--self-test` and checks the Meta+V link, the enabled
  watcher and the update script are in the image.
- Tried on the owner's PC: the per-user install, the watcher recording real copies, a launch.

## Done when

CI passes on Fedora and in the SparkOS image, and the PR is open for the owner. Marked 0.1.0 until
Meta+V and the tray change are seen working on a booted SparkOS.
