# Spark Shell and the Spark session

SparkOS's desktop: the panel, tray, notifications, menu, wallpaper, lock screen and on-screen bars, as a GTK 4 program in the house style. It took over from Plasma (see [PLAN.md](../../PLAN.md), "Replacing KDE").

It runs in one session on the login screen: **Spark** (`spark-wl`), on the [Spark compositor](../spark-compositor), with no KDE, Plasma or KWin. It has been the owner's daily session since 25 Nov 2026 and is the only one in the image. The window list comes from `spark-wl-windows` (wlr-foreign-toplevel), and `spark-wl-startup` starts the session services. The older session that ran the same shell on KWin is gone, and so is its code.

## What is in it

| Part | What it does |
|---|---|
| Panel | One per monitor, with the launcher button, a task list (pinned apps first), a clock and, on the first monitor, the tray and the notification bell. The clock opens a calendar and the next alarm; Spark Clock does the alarms. |
| Tray | A StatusNotifierWatcher and host: icons, left, right and middle click, scroll, and dbusmenu menus (checks, radios, submenus). `spark-xembed.service` (`spark-shell --xembed`) also owns the old X11 tray, so Wine and Proton apps (Battle.net) show their icon here instead of opening a small window of their own; their menus open where the icon was clicked. |
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
  "panel_position": "bottom", "pinned": ["dev.wolklaw.SparkFiles.desktop"] }
```

`wallpaper_mode` is `fill`, `fit`, `stretch` or `center`; `panel_position` is `bottom` or `top`. The shell reads the file again when it changes. Pinning from the task list's right-click menu writes `pinned` and keeps the other keys. A Settings page that edits this file belongs to the Settings session.

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

- `tests/test_units.py`: config, tray menu parsing, the notification model, the window list, the OSD parsers. No display.
- `tests/test_logic.py`: the launcher search (`launcher_logic.py`) against the cases in `tests/vectors.json`. No display.
- `tests/headless.sh 3 DIR`: boots the session on a headless Spark compositor with three outputs, inside the SparkOS image, and runs `tests/session_check.py` against it (panels, wallpapers, a fake tray item, notifications, a real window in the task list, the launcher). CI runs it in `.github/workflows/spark-shell.yml`.

## Not covered by any test

Real screens and GPU rendering, a real login from the login screen, the systemd path of `spark-session-run`, clicks and typing, tray menus opening, the Steam overlay, games, and what the panel and the toasts look like (the headless screenshots cover the wallpaper, the launcher and the OSD only).
