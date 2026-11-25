# Spark compositor (experimental)

A small Wayland compositor on wlroots 0.19, written in C (one file). It runs as its own login session,
"Spark (experimental compositor)" (`spark-wl`), never the default. The Plasma session and KWin are
untouched. Read the "Missing" list before you log in to it.

## Build and run

    make                      # needs wlroots0.19-devel, wayland-protocols-devel, wlr-protocols-devel,
                              # libxkbcommon-devel, libinput-devel, pixman-devel, libdrm-devel
    ./spark-compositor -s foot

Test mode: `SPARK_HEADLESS_OUTPUTS=3 ./spark-compositor` runs on virtual outputs with a software
renderer and puts nothing on a screen. CI uses it (`.github/scripts/spark-compositor/test.py`).

## Config

Files in `~/.config/spark/compositor/` (`SPARK_COMPOSITOR_CONFIG_DIR` overrides the folder). Spark Settings
has no output-layout key yet, so these two files are the source of truth.

`outputs.conf`:

    output DP-1 mode=2560x1440@144 scale=1 pos=0,0
    output HDMI-A-1 mode=1920x1080@60 scale=1.5 pos=2560,0 vrr=off
    output DP-2 mode=1920x1080@60 transform=90 pos=4480,0
    output eDP-1 enabled=off

`transform` is 0, 90, 180, 270 or flipped, flipped-90, flipped-180, flipped-270. Outputs without a line
are placed to the right of the others, at their preferred mode.

`compositor.conf`:

    bind Super+Return exec spark-terminal
    bind Super+t exec foot

Actions: `exec CMD`, `close`, `quit`, `focus-next`, `fullscreen`, `maximize`, `output-next`, `reload`,
`snap-left`, `snap-right`, `restore-down`, `show-desktop`, and `none`, which turns a default off and lets the key reach the app (`bind Super+e none`). A later
line for the same key wins. Spark Settings > Shortcuts writes its own block in this file.

Defaults:
- Windows: Super+q and Alt+F4 (close), Alt+Tab and Super+Tab (focus next), Super+f (fullscreen),
  Super+Up (maximize), Super+Left/Right (snap to a half; again moves on to the next screen),
  Super+Down (restore, then minimize), Super+d (show the desktop, again brings the windows back),
  Super+o (next output). Super+drag moves a window, Super+right-drag resizes it.
- Window switcher: `focus-next` bound with a modifier (Alt+Tab, Super+Tab) opens a panel of the
  open windows, most recent first, while the modifier is held. Tab or the arrows move along,
  Shift+Tab goes back (Alt+Shift+Tab also opens it at the far end), letting go switches, Escape
  stays put. Icons come from each app's .desktop file and the SparkOS icon theme.
- Session: Super alone (Spark menu), Super+l (lock), Super+Shift+e (quit), Super+Ctrl+Shift+r
  (reload this file).
- Apps: Super+Return and Ctrl+Alt+t (terminal), Ctrl+Shift+Esc, Super+Esc and Ctrl+Esc (Spark
  Monitor), Super+e (Spark Files), Super+i (Spark Settings), Super+. (Spark Emoji), Super+v
  (clipboard history), Calculator key (Spark Calc). These are the same keys the apps register
  in Plasma.
- Spark Snip: Print and Super+Shift+s (area), Super+Shift+t (text), Super+Shift+r (recording).
- Volume keys go to the Spark shell's on-screen display; play/pause, next, previous and stop go to
  the playing MPRIS player through the shell.
- Apps that ask `org.freedesktop.ScreenSaver` to keep the screen on (Steam, Chrome, Discord) are
  answered by the shell, which keeps `$XDG_RUNTIME_DIR/spark-wl/idle-inhibit` while they do; the
  idle timer treats it like a Wayland idle inhibitor.

`wlr-randr` and any wlr-output-management client can change outputs at runtime; those changes are not saved.

## Protocols

xdg-shell, xdg-decoration (server side, nothing drawn), layer-shell, ext-session-lock, ext and wlr
foreign-toplevel, idle-notify, idle-inhibit, xdg-activation, fractional-scale, viewporter, cursor-shape,
wlr-output-management, wlr-output-power, primary-selection, wlr-data-control, ext-data-control,
wlr-screencopy, ext-image-copy-capture, export-dmabuf, gamma-control, tearing-control,
pointer-constraints, relative-pointer, virtual keyboard and pointer, presentation-time,
single-pixel-buffer, content-type, alpha-modifier, linux-dmabuf. XWayland starts on demand.

## Missing against KWin

HDR. Tested VRR, tearing and direct scanout (written, never run on a GPU). Mixed-refresh handling
beyond what wlroots does per output. A proven Steam overlay and Steam Input. Window decorations,
workspaces, tiling, per-app rules. Keyboard layout and pointer settings (only `XKB_DEFAULT_*`
variables). A screen-share picker. NVIDIA work. Gamescope nested has not been tried.
