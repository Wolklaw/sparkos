# Spark Shell and the Spark session

SparkOS's desktop: the panel, tray, notifications, menu, wallpaper, lock screen and on-screen bars, as a GTK 4 program in the house style. See [PLAN.md](../../PLAN.md), "Replacing KDE", for how it came to be.

It runs in one session on the login screen: **Spark** (`spark-wl`), on the [Spark compositor](../spark-compositor), with no KDE, Plasma or KWin. It has been the owner's daily session since 25 Nov 2026 and is the only one in the image. The window list comes from `spark-wl-windows` (wlr-foreign-toplevel), and `spark-wl-startup` starts the session services. The older session that ran the same shell on KWin is gone, and so is its code.

## What is in it

| Part | What it does |
|---|---|
| Panel | One per monitor, with the launcher button, a task list (pinned apps first), a workspace switcher, a clock and, on the first monitor, the tray, the Spark Connect widget (off by default) and the notification bell. The clock opens a calendar and the next alarm; Spark Clock does the alarms. |
| Tray | A StatusNotifierWatcher and host: icons, left, right and middle click, scroll, and dbusmenu menus (checks, radios, submenus). `spark-xembed.service` (`spark-shell --xembed`) also owns the old X11 tray, so Wine and Proton apps (Battle.net) show their icon here instead of opening a small window of their own; their menus open where the icon was clicked. Icons can be dragged to a new place; the order is saved as `tray_order`. |
| Task list drag | Drag a task button to move it. Dropping a pinned app moves it within the pinned apps and saves `pinned`. An unpinned app dropped before the last pinned app becomes pinned there; dropped anywhere else it keeps a new place for the session only (not saved). An app with no desktop entry cannot be pinned, so it stays after the pinned ones. A click still clicks, and middle and right click are unchanged. |
| Workspaces | Shown on each panel when the compositor reports more than one workspace: numbered cells, the current one lit, occupied ones marked. Click a cell to switch, scroll to go next or previous, and the tile glyph toggles tiling. It talks to `$XDG_RUNTIME_DIR/spark-wl/ctl` (`watch`, `workspace N\|next\|prev`, `move-to-workspace`, `tile-toggle`), reconnects with a back-off (2, 5, 10, 30 s) and stays hidden while the compositor does not answer. Super+Ctrl+Left and Right also switch. |
| Spark Connect | With `connect_widget.enabled`, a dot and a problem count in the tray, fed by `spark-connect --status --json` every 60 s (one run at a time, killed after 45 s). Click for machines, problems, sites, the last check, "Check now" and "Open Spark Connect". Right-click: "Move to screen..." or "Remove from taskbar". It can be dragged to another screen's panel. Nothing shows when `spark-connect` is not installed (logged once), and it sends no notifications. |
| Notifications | `org.freedesktop.Notifications` 1.2: actions, urgency, replace-id, images, do not disturb, a history list that survives restarts. |
| Launcher | A Windows 7 style menu that opens above the SPARK button: apps ranked by the logic in `launcher_logic.py`, sums answered by Spark Calc, power buttons with a second click to confirm. The Meta key opens it. |
| Wallpaper | One background surface per monitor. No desktop icons. |
| Lock screen | ext-session-lock, with the password checked through PAM. In spark-wl, Super+L and the idle timer lock. |
| OSD | Volume (wpctl) with a bar on screen, from the compositor's volume keys. Brightness keys (bound by the compositor) move every backlight in `/sys/class/backlight` through logind's SetBrightness and show the brightness bar. External monitors without a backlight device are not changed. |
| Session | `spark-wl-session` starts the compositor, which runs `spark-wl-startup`: activation environment, the `spark-wl-workspace.target` user target, portal, polkit agent and the shell, restarted if it crashes. |

## Settings

`~/.config/spark/shell.json`, all keys optional:

```json
{ "wallpaper": "~/Pictures/wall.png", "wallpaper_mode": "fill",
  "panel_position": "bottom", "pinned": ["dev.wolklaw.SparkFiles.desktop"],
  "tray_order": ["nm-applet"], "connect_widget": { "enabled": false, "monitor": "" } }
```

`wallpaper_mode` is `fill`, `fit`, `stretch` or `center`; `panel_position` is `bottom` or `top`. The shell reads the file again when it changes. `tray_order` lists tray item ids, first to last; items not listed go last. `connect_widget.monitor` is a connector such as `DP-1`; empty means the first screen. Pinning, dragging and the widget's menu write their own keys and keep the others. Spark Settings (Appearance, Taskbar) edits `connect_widget` and the workspace count.

## How the pieces talk to the compositor

`spark-wl-windows` (built with the compositor, in `files/spark-compositor`) binds wlr-foreign-toplevel and reports windows to the shell; the shell's actions (activate, minimize, close) go back through it. The compositor binds the keys: Super runs `spark-shell --toggle`, and the volume and brightness keys call `Key` on `/Shell`.

## Install

```
sudo bash install.sh              # the image build does this; /usr/lib/spark-shell + the session
bash install.sh --user            # ~/.local only, no login entry
bash install.sh --stage DIR       # the system layout under DIR
bash install.sh --self-test
```

The image also needs `gtk4-layer-shell` (in `build_files/packages.sh`). Without it the shell still runs, with ordinary windows instead of a panel.

## Tests

- `tests/test_units.py`: config, tray menu parsing, the notification model, the window list, the OSD parsers, key cleaning (`tray_order`, `connect_widget`), the drag reorder functions (`ordering.py`), the compositor line parser and a fake ctl socket, and the Spark Connect JSON parser and summary text. No display.
- `tests/test_logic.py`: the launcher search (`launcher_logic.py`) against the cases in `tests/vectors.json`. No display.
- `tests/headless.sh 3 DIR`: boots the session on a headless Spark compositor with three outputs, inside the SparkOS image, and runs `tests/session_check.py` against it (panels, wallpapers, a fake tray item, notifications, a real window in the task list, the launcher). CI runs it in `.github/workflows/spark-shell.yml`.

## Not covered by any test

Real screens and GPU rendering, a real login from the login screen, the systemd path of `spark-session-run`, clicks and typing, tray menus opening, the Steam overlay, games, and dragging in a real compositor (task buttons, tray icons, the Connect widget between screens), the workspace switcher against the real compositor, what the panel and the toasts look like (the headless screenshots cover the wallpaper, the launcher and the OSD only).
