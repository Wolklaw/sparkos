# Spark Terminal

The SparkOS terminal. It replaces Konsole: tabs, split panes, search in the scrollback,
clickable links and file paths, in the SparkOS colours. The terminal emulation itself comes from
[VTE](https://gitlab.gnome.org/GNOME/vte), the library GNOME's terminals use, so full-screen
programs (vim, htop, less, Claude Code), mouse support, true colour, Unicode and wide characters
work the way they do everywhere else. Everything around it is Spark Terminal's own: Python, GTK 4
and VTE through PyGObject.

## Using it

| Keys | |
|---|---|
| Ctrl+Alt+T | open Spark Terminal (from anywhere on the desktop) |
| Ctrl+Shift+T / Ctrl+Shift+N | new tab / new window |
| Ctrl+Shift+R / Ctrl+Shift+D | split side by side / stacked |
| Ctrl+Shift+W | close the pane (or the tab, when it has one pane) |
| Alt+Arrows | move between panes |
| Ctrl+PgUp / Ctrl+PgDn, Alt+1 … 9 | previous / next tab, go to a tab |
| Ctrl+C / Ctrl+V | copy the selection / paste. With nothing selected, Ctrl+C stops the running program as usual; copying clears the selection, so the next Ctrl+C does too. Off in Settings (`ctrl_c_v`) for programs that need ^V |
| Ctrl+Shift+C / Ctrl+Shift+V, Shift+Insert | copy / paste |
| Ctrl+Shift+F | find in the scrollback (Enter: older match, Shift+Enter: newer, Esc closes) |
| Ctrl+Plus / Minus / 0 | zoom in / out / actual size |
| Ctrl+Shift+K | clear and reset |
| Ctrl+Shift+, | settings |
| Ctrl+click | open a link or a file path (`/etc/fstab`, `~/notes.txt`, `src/main.c:12:4`) |
| Right click | menu; Shift+right click goes to programs that use the mouse |

Selecting text copies it (a setting), and middle click pastes the selection. Closing a tab, pane
or window where a program is still running asks first (a setting). New tabs and splits start in
the folder the current pane is in.

**Settings** (Ctrl+Shift+, or the ≡ menu): the shell (empty: your login shell), the folder new
windows start in (empty: the folder it was started from), font and size, scrollback (10,000
lines by default), cursor, bell (flash, sound or off), copy on select, the close question, and
the glitch effect. They're saved in `~/.config/spark-terminal/settings.json`; the log is in
`~/.local/state/spark-terminal/`.

## The command line

Konsole's options, so scripts that started Konsole can switch:

```
spark-terminal [--workdir DIR] [--hold] [--title TITLE] [-e COMMAND [ARGS...]]
```

- Everything after `-e` (or `-x`, or `--`) is the command. One `-e` argument with spaces in it
  (`-e 'ls -l'`) is split like a shell would, as Konsole does.
- `--hold` keeps the tab open after the command ends and shows its exit code.
- Each `spark-terminal` is its own process and returns when its window closes, so a script can
  wait for what it started. `--nofork`, `--new-tab` and `--separate` are accepted for that
  reason and change nothing.
- `--version`, `--self-test` (checks GTK 4 and VTE, starts a shell on a VTE pty and reads its
  output back, the font, the folders; no window needed).

`--working-directory` and `--noclose` work too, and the desktop entry has the `X-TerminalArg*`
keys, so `xdg-terminal-exec` starts it correctly.

## In SparkOS

The image build step is [files/scripts/spark-terminal.sh](../scripts/spark-terminal.sh). It
adds `vte291-gtk4` from Fedora, installs Spark Terminal in `/usr/lib/spark-terminal`, and makes
it the terminal everywhere:

- the `TerminalApplication` and `TerminalService` keys in `/etc/xdg/kdeglobals`, which Spark Files and
  other KDE-aware apps read: "Open Terminal Here" and apps with `Terminal=true` start it
- `xdg-terminal-exec`'s default (`/etc/xdg/kde-xdg-terminals.list`, `xdg-terminals.list`)
- Ctrl+Alt+T, which the Spark compositor binds to it
- the dock, the Claude Code menu entry and the Spark Files action, the `.rpm` installer window, and Spark
  Connect's "Open terminal"

Konsole is not in the image. A person who still has an old dock layout can right-click the dock to swap it for Spark Terminal.

## Install by hand

```
sudo bash install.sh --deps        # system-wide, Fedora: installs VTE for GTK 4 with dnf
bash install.sh --user             # just you, into ~/.local (needs VTE for GTK 4 already there)
bash install.sh --user --uninstall
```

## Tests

```
python3 -m unittest discover -s tests                      # settings, command line, helpers
xvfb-run -a python3 -m unittest discover -s tests -v       # and the window tests
```

The window tests open real windows with real shells: a tab runs `echo` and the output appears,
tabs and splits open and close, `--workdir`, `-e` and `--hold`, the close question when `sleep`
runs, search in 300 lines of scrollback, copy on select, zoom, links, Unicode and true colour,
and vim and less starting and quitting cleanly. `SPARK_SHOT_DIR=folder` saves screenshots.
`GSK_RENDERER=cairo` helps under Xvfb without GL. CI
([spark-terminal.yml](../../.github/workflows/spark-terminal.yml)) runs them on Fedora in English
and French, and again inside the published SparkOS image after running the image build step
there ([tests/image_check.sh](tests/image_check.sh)).

## Files

`spark_terminal.py` starts it. In `sparkterminal/`: `app.py` (the application, `--self-test`),
`cli.py` (the command line), `core.py` (settings, shell, folders, colour scheme, link patterns,
what's running; no GTK), `window.py` (tabs, splits, search, menus, closing), `pane.py` (one VTE
terminal), `settings_ui.py`, `style.py` (the CSS and the glitch), `text.py` (English and French),
`lang.py` (shared by every Spark app). `make_icons.py` draws `icons/`.
