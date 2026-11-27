# Spark compositor (experimental)

A Wayland compositor on wlroots 0.20, written in C. It runs the Spark session,
"Spark (experimental compositor)" (`spark-wl`) on the login screen, with Spark Shell. It has
been the owner's daily session since 25 Nov 2026 and is the only session in the image
(greetd with Spark Greeter starts it). Read the "Missing" list before you log in to it.

`spark-wl-windows/` is a small helper that gives Spark Shell the window list (foreign-toplevel) for
its task list. `spark-wl-windows --ext-list` prints the ext-foreign-toplevel-list windows once as a JSON
array (`[{"identifier","title","app_id"}]`) and exits.

## Build and run

    make                      # needs wlroots-devel (0.20), wayland-protocols-devel, wlr-protocols-devel,
                              # libxkbcommon-devel, libinput-devel, pixman-devel, libdrm-devel,
                              # cairo-devel, pango-devel, librsvg2-devel
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

Other lines (Spark Settings writes them too):

    keyboard layout=ca variant=fr options=caps:none repeat_rate=30 repeat_delay=400
    mouse accel=0 profile=flat natural=off left_handed=off
    touchpad tap=on natural=on dwt=on
    idle lock=300 screen_off=600 suspend=0
    cursor theme=SparkOS-cursors size=24
    workspaces count=4

Actions: `exec CMD`, `close`, `quit`, `focus-next`, `fullscreen`, `maximize`, `output-next`, `reload`,
`snap-left`, `snap-right`, `restore-down`, `show-desktop`, `workspace-next`, `workspace-prev`, `workspace N`,
`move-to-workspace-next`, `move-to-workspace-prev`, `move-to-workspace N`, `tile-toggle`, `tile-master`, and `none`, which turns a default off and lets the key reach the app (`bind Super+e none`). A later
line for the same key wins. Spark Settings > Shortcuts writes its own block in this file.

Defaults:
- Windows: Super+q and Alt+F4 (close), Alt+Tab and Super+Tab (focus next), Super+f (fullscreen),
  Super+Up (maximize), Super+Left/Right (snap to a half; again moves on to the next screen),
  Super+Down (restore, then minimize), Super+d (show the desktop, again brings the windows back),
  Super+o (next output). Super+drag moves a window, Super+right-drag resizes it.
- Workspaces: global across all monitors, `workspaces count=N` in compositor.conf (default 4, 1 to 9).
  Super+Ctrl+Left/Right switch, Super+Ctrl+Shift+Left/Right move the focused window and follow it
  (the workspace switches to where the window went), Super+Ctrl+1..9 go to workspace N. New windows open on the
  current workspace; a dialog opens on its parent's. Windows on other workspaces are hidden and take no
  focus; Alt+Tab and Super+d only see the current workspace. Layer-shell surfaces, the lock screen and
  X11 override-redirect windows are on every workspace. An app that activates itself (xdg-activation or
  foreign-toplevel activate) on another workspace switches to that workspace. The wlr foreign-toplevel
  handle of a window is destroyed while it is on another workspace and created again (title, app_id, state,
  output) when it comes back; ext-foreign-toplevel-list handles stay for every window.
- Tiling: off by default, on per workspace. Super+Ctrl+t toggles it, Super+Ctrl+Return makes the focused
  window the master. Master on the left half, the rest stacked on the right, 6 px gaps, inside the
  usable area of the window's output. Fixed-size, minimized, fullscreen and child windows are left
  alone. Dragging a tiled window or snapping it makes it float; maximize still works. Turning tiling off
  puts each window back where it was.
- Always floating: `spark-screen-pick` (the screen-share picker) is hard-coded to float, centred on the
  focused output like a dialog. There is no general per-app rule mechanism.
- Drag and drop: the compositor starts data-device drags (pointer only, with the drag icon). Touch is
  not supported by the compositor, so touch drags are not either.
- Cursor: theme `SparkOS-cursors` by default; the `XCURSOR_THEME` environment variable wins over it.
- Window switcher: `focus-next` bound with a modifier (Alt+Tab, Super+Tab) opens a panel of the
  open windows, most recent first, while the modifier is held. Tab or the arrows move along,
  Shift+Tab goes back (Alt+Shift+Tab also opens it at the far end), letting go switches, Escape
  stays put. Icons come from each app's .desktop file and the SparkOS icon theme.
- Session: Super alone (Spark menu), Super+l (lock), Super+Shift+e (quit), Super+Ctrl+Shift+r
  (reload this file).
- Apps: Super+Return and Ctrl+Alt+t (terminal), Ctrl+Shift+Esc, Super+Esc and Ctrl+Esc (Spark
  Monitor), Super+e (Spark Files), Super+i (Spark Settings), Super+. (Spark Emoji), Super+v
  (clipboard history), Super+Alt+g (save a Spark Clips clip), Calculator key (Spark Calc). The compositor binds them
  itself (`set_default_binds`); the apps' desktop entries carry no shortcut lines.
- Title bars: the compositor draws them (title, minimize, maximize, close)
  on Wayland apps that ask for server-side decorations and on X11 windows that don't draw their
  own. X11 apps that draw their own bar (Battle.net) get none; dragging one by its own bar while
  maximized restores it.
- Spark Snip: Print and Super+Shift+s (area), Super+Shift+t (text), Super+Shift+r (recording).
- Volume and brightness keys go to the Spark shell's on-screen display; play/pause, next, previous and stop go to
  the playing MPRIS player through the shell.
- Apps that ask `org.freedesktop.ScreenSaver` to keep the screen on (Steam, Chrome, Discord) are
  answered by the shell, which keeps `$XDG_RUNTIME_DIR/spark-wl/idle-inhibit` while they do; the
  idle timer treats it like a Wayland idle inhibitor.

Control socket: `$XDG_RUNTIME_DIR/spark-wl/ctl` (directory 0700, socket 0600), a Unix stream socket with
one command per line and one reply line each, `ok` or `error <message>`. Commands: `workspace N|next|prev`,
`move-to-workspace N|next|prev` (the focused window), `tile-toggle`, `watch`. Anything else gets
`error unknown command`. Nothing from the socket is executed as a program. After `watch` the compositor sends
the current state and then a line on every change: `workspace <cur> <count> <occupied>` (1-based, occupied a
comma list or `-`, e.g. `workspace 2 4 1,2`), `tiling on|off`, `focus <pid> <app_id>` (`focus 0 ` when
nothing is focused). A client that sends a line over 255 bytes is dropped.

`wlr-randr` and any wlr-output-management client can change outputs at runtime; those changes are not saved.

## Protocols

xdg-shell, xdg-decoration (server side, drawn with cairo), layer-shell, ext-session-lock, ext and wlr
foreign-toplevel, idle-notify, idle-inhibit, xdg-activation, fractional-scale, viewporter, cursor-shape,
wlr-output-management, wlr-output-power, primary-selection, wlr-data-control, ext-data-control,
wlr-screencopy, ext-image-copy-capture, export-dmabuf, gamma-control, tearing-control,
pointer-constraints, relative-pointer, virtual keyboard and pointer, presentation-time,
single-pixel-buffer, content-type, alpha-modifier, linux-dmabuf, ext-image-capture-source for windows
(`ext_foreign_toplevel_image_capture_source_manager_v1`, next to the output capture source; sharing a hidden or
minimized window is untested, its scene node is disabled), data-device drag and drop. XWayland starts on demand.

## Missing

HDR is in (the owner runs hdr=on on DP-1 daily). VRR, tearing and direct scanout are written but still
untested on a GPU. Mixed-refresh handling beyond what wlroots does per output. A proven Steam overlay and
Steam Input. Per-app rules beyond the screen-share picker. Night light. NVIDIA work. Gamescope nested has
not been tried. Touch input.
