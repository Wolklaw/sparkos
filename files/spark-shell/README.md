# Spark Shell and the Spark session

Stage 3 of replacing KDE (see [PLAN.md](../../PLAN.md), "Replacing KDE"). The desktop part of Plasma, redone as a GTK 4 program in the house style, and a login session that starts it on KWin. **Plasma stays the default session.** Spark is a second entry on the login screen, for trying.

## What is in it

| Part | What it does |
|---|---|
| Panel | One per monitor, with the launcher button, a task list (pinned apps first), a clock and, on the first monitor, the tray and the notification bell. The clock opens a calendar and the next alarm; Spark Clock does the alarms. |
| Tray | A StatusNotifierWatcher and host: icons, left, right and middle click, scroll, and dbusmenu menus (checks, radios, submenus). If KDE's daemon already owns the watcher name, the shell uses that one. In the Spark compositor session, `spark-xembed.service` (`spark-shell --xembed`) also owns the old X11 tray, so Wine and Proton apps (Battle.net) show their icon here instead of opening a small window of their own; their menus open where the icon was clicked. |
| Notifications | `org.freedesktop.Notifications` 1.2: actions, urgency, replace-id, images, do not disturb, a history list that survives restarts. Only in this session. |
| Launcher | Full-screen search card: apps ranked by the same logic as the Spark Launcher widget (`launcher_logic.py`), sums answered by Spark Calc, power buttons with a second click to confirm. The Meta key opens it. |
| Wallpaper | One background surface per monitor. No desktop icons. |
| OSD | Volume (wpctl) with a bar on screen. Brightness is powerdevil's: it takes the keys, drives every monitor and reports to `org.kde.plasmashell /org/kde/osdService`, which the shell answers with the same bar. |
| Session | `spark-session` starts KWin, then `spark-session-run` brings up what Plasma's startup does (activation environment, the `spark-workspace.target` user target, KDE daemon, portal, polkit agent) and runs the shell, restarting it if it crashes. |

## Settings

`~/.config/spark/shell.json`, all keys optional:

```json
{ "wallpaper": "~/Pictures/wall.png", "wallpaper_mode": "fill",
  "panel_position": "bottom", "pinned": ["dev.wolklaw.SparkFiles.desktop"] }
```

`wallpaper_mode` is `fill`, `fit`, `stretch` or `center`; `panel_position` is `bottom` or `top`. The shell reads the file again when it changes. Pinning from the task list's right-click menu writes `pinned` and keeps the other keys. A Settings page that edits this file belongs to the Settings session.

## How the pieces talk to KWin

KWin only gives its window list to plasmashell, so the shell loads a small KWin script through `org.kde.KWin /Scripting`. The script reports windows to the shell and carries the shell's actions (activate, minimize, close) and the volume keys back. The shell also owns the name `org.kde.plasmashell` so that the Meta key (`activateLauncherMenu`) reaches it.

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
- `../spark-launcher/tests/test_logic.py` and `check_js.mjs`: the launcher search on the Python copy and on the widget's JavaScript, from one `vectors.json`.
- `tests/headless.sh 3 DIR`: boots the whole session on a virtual KWin with three outputs and runs `tests/session_check.py` against it (panels, wallpapers, a fake tray item, notifications, a real window in the task list, the launcher). Needs the SparkOS image (or Fedora with KWin and gtk4-layer-shell) and `--cap-add=SYS_NICE` in a container. CI runs it in `.github/workflows/spark-shell.yml`.

## Not covered by any test

Real screens and GPU rendering, a real login from the login screen, the systemd path of `spark-session-run`, clicks and typing, tray menus opening, the Steam overlay, games, and what the panel and the toasts look like (the headless screenshots cover the wallpaper, the launcher and the OSD only).
