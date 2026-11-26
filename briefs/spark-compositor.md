# Spark compositor (stage 4 of replacing KDE, experimental)

Status: first version built on branch `spark-compositor`. It is a separate login session, `spark-wl`
("Spark (experimental compositor)"), now the login screen's default (25 Nov 2026). KWin and the `spark` session are not touched.

## What exists

- [files/spark-compositor](../files/spark-compositor): wlroots 0.19, C, one file, about 1700 lines. Its
  README has the config grammar, default keys, protocols and what is missing.
- Multi-output with per-output mode, scale, transform and position from `~/.config/spark/compositor`.
- xdg-shell windows (move, resize, focus, fullscreen, maximize, keys), XWayland, layer-shell,
  ext-session-lock, foreign-toplevel (ext and wlr), idle-notify, xdg-activation, fractional-scale,
  cursor-shape, output management, primary selection, data control, screencopy, tearing-control.
- Session: `/usr/share/wayland-sessions/spark-wl.desktop`, `spark-wl-session`, `spark-wl-startup`
  (runs `spark-shell` when it exists, else a terminal). Portal config for xdg-desktop-portal-wlr.
- Image: a `compositor-build` stage in the Containerfile, plus wlroots0.19, xdg-desktop-portal-wlr,
  grim and wlr-randr in packages.sh. About 2 to 3 MB estimated; not measured.
- CI: `.github/workflows/spark-compositor.yml` builds it on Fedora 45 and runs
  `.github/scripts/spark-compositor/test.py` headless with 3 virtual outputs (2560x1440, 1080p at 1.5,
  1080p rotated): sizes and transforms, about 25 globals, swaybg (layer-shell), foot (xdg-shell), xterm
  (XWayland), clipboard and primary selection, a key bind through wtype, grim screenshots through
  screencopy (kept as an artifact), swaylock lock and unlock.

## What was never tried

Real DRM and libinput backends, any GPU, VRR, tearing, direct scanout, gamescope nested, Steam overlay
and Steam Input, a real login through the display manager, xdg-desktop-portal-wlr running,
ext-image-copy-capture with a real client, the foreign-toplevel clients, idle-notify and xdg-activation
with a real client.

## Missing against KWin

HDR (not started), VRR, mixed-refresh monitors, Steam overlay, direct scanout (all unproven), window
decorations, workspaces, per-app rules, keyboard and pointer settings, a screen-share picker, Spark
Settings integration (no output-layout key exists; outputs.conf is its own file).

## What the owner must try

Log in to "Spark (experimental compositor)" from the login screen with the three monitors (2560x1440,
1080p, portrait), then try a game, VRR, screen capture through Spark Snip or a browser, and Steam. If
anything breaks, log out and use the Plasma session.

## Next

The Spark shell on layer-shell, then rounds of the owner's tests. HDR needs the color-management
protocol and a wlroots with HDR output support; not before the basics work on hardware.
