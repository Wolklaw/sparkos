# Spark Shell and the Spark session

Stage 3 of "Replacing KDE" in [PLAN.md](../PLAN.md). Source and README: [files/spark-shell](../files/spark-shell/README.md).

## What was built

A GTK 4 + gtk4-layer-shell program (Python, PyGObject) in the house style, and a second login session, `Spark`, that runs it on KWin instead of plasmashell. Plasma is still the default session and nothing about it changed.

- **Panel** per monitor: launcher button, task list with pinned apps, clock (calendar, next alarm from Spark Clock), tray and notification bell on the first monitor.
- **Tray**: StatusNotifierWatcher and host, SNI icons, dbusmenu menus.
- **Notification server**: actions, urgency, replace-id, images, do not disturb, history.
- **Launcher**: search with the Spark Launcher widget's ranking (shared `launcher_logic.py`, one `vectors.json` both copies must pass), sums through Spark Calc, power buttons.
- **Wallpaper** layer per monitor, no desktop icons; **OSD** for volume and brightness.
- **Session**: `/usr/share/wayland-sessions/spark.desktop` -> `spark-session` (KWin) -> `spark-session-run` (activation environment, `spark-workspace.target`, KDE daemon, portal, polkit agent, then the shell in a restart loop). `XDG_CURRENT_DESKTOP=Spark:KDE`, so the KDE portal and Qt theme still apply.

## Config contract (`~/.config/spark/shell.json`)

Keys, all optional: `wallpaper` (path), `wallpaper_mode` (`fill` `fit` `stretch` `center`), `panel_position` (`bottom` `top`), `pinned` (list of desktop file ids). The Settings session writes it; the shell watches the file. Unknown keys are kept.

## Changes from the first plan

- **The dock is the pinned part of the panel**, not a separate surface. One bar per monitor is simpler for three monitors; a floating dock can come later if the owner wants one.
- **Python**, not C or Rust: every other Spark app is, and a shell that crashes is restarted by the session script.
- **The shell owns `org.kde.plasmashell`** as a small shim, so the Meta key (kglobalaccel -> `activateLauncherMenu`) opens its launcher with no other change.
- **The tray uses KDE's watcher** when kded already owns the name, and registers its own otherwise.
- **Window list through a KWin script**, because KWin only gives the plasma window management protocol to plasmashell. It was checked on a headless KWin.
- **Panel and toast screenshots are missing** from the CI artifact: the headless capture renders the shell's own windows, and container widgets (the panel, the toasts) came back empty. KWin's ScreenShot2 crashed the software-rendered KWin, so it is not used. The wallpaper, launcher and OSD are in the artifact.
- No pinned-apps editor beyond the task list's right-click menu (pin, unpin).
- The polkit agent is a placeholder that starts `spark-polkit-agent` when it exists and KDE's agent otherwise; the lock screen, polkit and greeter belong to another session.

## Tried, and not

Tried (CI and a rootless container on the author's PC, virtual KWin with 3 outputs): the shell comes up, owns the notification, tray and plasmashell names, one panel and wallpaper per output, a fake tray item shows, notifications replace and stack, a real window shows in the task list and leaves it, the launcher opens, unit tests, the shared launcher vectors on both copies, the install layout.

Not tried by anyone: logging in from the login screen, real monitors (2560x1440, 1080p, portrait), the real GPU, games, the Steam overlay, tray apps (Steam, Discord, Nova, Spark Tray), clicks and keys, tray menus opening, the Meta key, volume and brightness keys, the systemd path of `spark-session-run`, what the panel and toasts look like.
