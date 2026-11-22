# Spark Terminal

Read [README.md](README.md) first for the conventions every Spark app follows, and load the
`wolklaw-design` skill for the look (the mono variant: Cascadia Code, the SparkOS colours).

## Why

Konsole is KDE's. The owner wants as little software from others as possible, and uses the terminal
daily (Claude Code runs in it).

## What it does

- Tabs (Ctrl+Shift+T), split panes (side by side and stacked), close with a confirmation when something is
  still running.
- Copy/paste (Ctrl+Shift+C/V, and select-to-copy, middle-click paste), clickable links and file paths,
  search in the scrollback (Ctrl+Shift+F), scrollback of 10,000 lines by default.
- Font size zoom (Ctrl+plus/minus), the SparkOS colour scheme, and a profile setting for the shell and the
  starting folder.
- "Open terminal here" from Spark Files, and `spark-terminal --workdir DIR -e CMD` like Konsole's options, so
  Nova, Spark Run and the SparkOS scripts that start Konsole today can switch to it.
- Full-screen programs work properly: vim, htop, less, Claude Code's own interface, mouse support, true
  colour, Unicode and wide characters.

## How

Terminal emulation is the hard part, and getting it wrong breaks every program that runs inside. So the
terminal itself comes from **VTE**, the terminal library GNOME's terminals use: a library, not an app, the
same way SparkOS keeps Mesa or the kernel. The app around it (tabs, splits, settings, look) is SparkOS's own.

- Python 3 with GTK 4 and VTE through PyGObject. GTK 4 is already in the image; add `vte291-gtk4` to the
  image (it's in Fedora's own repos). Style the GTK window with CSS to match the house style.
- Write the reason for VTE in THIRD-PARTY.md (LGPL, linked as a library, not modified).
- If VTE turns out not to fit, say why in the PR before trying anything else; don't write a terminal
  emulator from scratch without the owner agreeing.

## Replacing Konsole

Ship it in the image and on the dock, make it the default terminal (`TerminalApplication` in kdeglobals, and
the `x-scheme-handler/terminal`-style defaults Plasma uses), switch every place SparkOS starts `konsole`
(scripts, Spark apps, the Claude Code desktop entry, Nova's hooks) to `spark-terminal`, and hide Konsole. Keep
Konsole installed for one release as a fallback; removing it is a separate PR.

## Tests

Unit tests for the profile/settings and the command-line options; under Xvfb: a tab opens, runs `echo`,
the output appears, splits and tabs open and close, `--workdir` and `-e` work; in the SparkOS image:
`install.sh`, `--self-test`, and `vim`/`less` start and quit cleanly inside it.

## Done when

CI passes on Fedora and inside the SparkOS image, Spark Terminal is the default terminal in a test build,
and the PR is open for the owner.
