# Spark Settings without KDE's modules (1.1.0)

Stage 2 of [Replacing KDE](../PLAN.md), the Spark Settings part. Spark Settings covers every page
itself instead of opening KDE's System Settings modules. Code in
[files/spark-settings](../files/spark-settings); the app's own brief is
[spark-settings.md](spark-settings.md).

## What opened KDE before, and what replaces it

| Page | Opened | Now |
| --- | --- | --- |
| Appearance | kcm_lookandfeel, kcm_colors, kcm_wallpaper, kcm_cursortheme, kcm_fonts, kcm_icons, kcm_desktoptheme, kcm_kwin_effects, kcm_animations | Appearance page: colour scheme and accent, wallpaper, cursor, window animations and blur. Fonts open Spark Fonts when installed. Icons and Plasma themes are not offered |
| Mouse, keyboard and controllers | kcm_mouse, kcm_keyboard, kcm_touchpad, kcm_keys, kcm_gamecontroller, kcm_tablet | Mouse and keyboard page (KWin input devices over D-Bus, kxkbrc), Shortcuts page (kglobalaccel over D-Bus), controllers go to Spark Controller. Tablets and touchscreens: not set |
| Users | kcm_users | Users page over AccountsService. Passwords: `passwd` in Spark Terminal |
| Storage and games drive | kcm_device_automounter, kcm_baloofile | Storage page: lsblk volumes, file indexing switch, Spark Disks for mount and format |
| Power | kcm_powerdevilprofilesconfig (timers, power button) | Power page: logind and power-profiles-daemon over D-Bus, timers and button written for powerdevil |
| Date and time, language | timedatectl and localectl commands | timedated and localed over D-Bus, manual time, system language |
| Startup | autostart files, no add | add an installed app, remove your own entries |
| Notifications | kcm_notifications | Notifications page |
| More settings | every kcm | unchanged: still the one way into KDE's modules |

## Kept on KDE, behind one module

`sparksettings/plasma.py` is the only place that names KWin, kscreenlocker, powerdevil,
plasmashell or baloo. Each function is tagged in its docstring table. They stay while KWin stays.
Displays still use `kscreen-doctor` in `displays.py` (no KWin output-management client yet).
`kcms.open_module` and "More settings" are the only paths that open a KDE module.

Per-user settings are also written to `~/.config/spark/*.json` (locale, power, lock, appearance,
input, notifications, storage) so the Spark session can read them without Plasma.

## Tests

Parsers and writers against fakes. `tests/test_dbus.py` runs python-dbusmock services for
timedated, logind and power-profiles-daemon (templates) and localed, AccountsService, KWin input
and kglobalaccel (hand-written), on private buses. Window tests run under Xvfb in CI in English
and French. No test can reach the real buses: the test environment points them at nothing.

## Not tried

Nothing here has run against a live Plasma session or the real services: KWin input, kglobalaccel,
powerdevil, kscreenlocker, AccountsService changes and timedated writes are tested against fakes.
