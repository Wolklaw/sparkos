# Spark Settings

SparkOS's own settings app. It replaced KDE System Settings. Python 3 and Tk, no packages beyond
what the image has. The brief is [briefs/spark-settings.md](../../briefs/spark-settings.md).

## Pages

Done in Spark Settings (each reads the real state when opened and talks to the tool named):

| Page | Tool | Notes |
| --- | --- | --- |
| Displays | `wlr-randr` | monitors as boxes you drag, resolution, refresh rate, scale, rotation, VRR, HDR, primary, on/off. Every change asks "Keep these settings?" and goes back after 15 s, on Revert, or if the window closes |
| Sound | `wpctl`, `pw-metadata` | output and input device, default, volume, mute, per-app volume, a test tone, output sample rate (follow the track, or a fixed rate your DAC lists in `/proc/asound/card*/stream0`, saved in `~/.config/pipewire/pipewire.conf.d/50-sample-rates.conf` and applied at once with `pw-metadata`) |
| Network | `nmcli` | Wi-Fi list and connect (asks for the password), wired status, VPN connections (import, up, down), proxy |
| Bluetooth | `bluetoothctl` | on/off, scan, pair, connect, disconnect, forget |
| Power | `busctl` (power-profiles-daemon, logind) | power profile, screen off and sleep after N minutes, power button, lock screen (saved in `~/.config/spark/power.json` and `lock.json`, which the compositor and shell read) |
| Default apps | `xdg-mime` | browser, mail, folders, text, media, archives, terminal |
| Date, time and language | `busctl` (timedated, localed) | time zone, automatic time, set the time by hand, language (yours, or the whole computer's), 24-hour clock |
| Appearance | `~/.config/spark/*.json`, compositor config | colour scheme, accent colour, wallpaper (the shell redraws every screen), cursor (a line in the compositor config, then a reload), window animations and blur; opens Spark Fonts for fonts |
| Mouse and keyboard | the compositor config (`~/.config/spark/compositor/compositor.conf`) | pointer speed, acceleration, natural scrolling, left-handed, tap to click, key repeat, layouts |
| Shortcuts | the compositor config | list, change, reset, conflict check; the compositor rereads the file on a reload signal |
| Notifications | `~/.config/spark/notifications.json` | how long, where, mute sounds |
| Users | AccountsService over D-Bus | add, remove, rename, standard or administrator; passwords through `passwd` in Spark Terminal |
| Storage | `lsblk`, Spark Disks | mounted drives and free space, file indexing on or off |
| Printers | `lpstat`, `lpinfo`, `lpadmin`, `lp` | list, find on the network, add, remove, make default, test page |
| Startup | autostart files | apps that open at sign-in: on, off, add an installed app, remove |
| Updates | Spark Update | opens it |
| About | `/etc/os-release`, `rpm-ostree`, `lspci` | version, image, hardware, "Copy system info" |

Spark Settings does not open KDE's System Settings: it is not installed. Settings that belong to
the user are saved in `~/.config/spark/*.json` (and the compositor config), which the Spark
compositor and Spark Shell read. `sparksettings/plasma.py` still holds the old writes for KDE's rc
files (colour scheme, KWin effects, powerdevil, kscreenlocker, plasma-localerc, baloo). In the
Spark session every one of them does nothing and reports success, so a page saves only to
Spark's own files.

The **More settings** page (KDE's control modules through `kcmshell6 --list`) is not shown in the
Spark session, because there are no KDE modules to list. Search matches English and French names
and keywords.

## Names KDE's apps used to call

`files/scripts/spark-settings.sh` (the image build step) moved KDE's `systemsettings` and
`kcmshell6` aside and put a stand-in at each name that runs `spark-settings --route`, so links
such as `systemsettings kcm_kscreen` land on the matching page (`ROUTES` in `sparksettings/kcms.py`).
The last build step ([sparkos-no-kde.sh](../scripts/sparkos-no-kde.sh)) deletes the stand-ins and
the moved originals along with KDE, so `--route` and `spark-settings --kde` have nothing to call
on the image. They still work on a machine that has KDE.

Spark Settings is pinned on the dock. Spark Welcome opens it on one page with the old module name
(`kcm_printer_manager` and the like), through Spark Settings' own route table.

## Install

```
bash install.sh --user [--no-test]      # you, no root, into ~/.local
bash install.sh --user --uninstall
sudo bash install.sh --deps             # system-wide (the image build uses this)
spark-settings --self-test [--strict]   # --strict fails when a page's tool is missing
```

## Tests

`python3 -m unittest discover -s tests -v`. Every tool is a fake in `tests/fixtures/bin` that logs
its arguments, so no real setting is changed. The window tests need a display (Xvfb in CI) and
set `SPARK_LANG=fr` to run in French. A test fails on any English string with no French.

## Not tried yet on real hardware

Everything that changes the real system or the live session (timedated, localed, AccountsService, the compositor config for input and shortcuts, power timers) is tested against fakes only, not a live session. In the Spark session, VRR is the only display option written to the compositor; primary monitor and HDR have no effect there yet. Three-monitor layout drag and apply, the FiiO DAC and QuadCast in Sound, the Canon TR4700
printer, Bluetooth pairing, and Wi-Fi password prompts. The commands and parsing are tested
against recorded output, not the devices.

## Known limits

- Displays go through `wlr-randr` in the Spark session (`displays.py`); `kscreen-doctor` is only used where it exists.
- Input: pointer and touchpad settings are written to the compositor config and reloaded; button mapping, calibration, tablets and touchscreens are not set here. The keyboard layout reads `kxkbrc` as its fallback when no Spark setting exists.
- The Plasma-file writes in `plasma.py` (KWin effects, powerdevil timers, kscreenlocker) do nothing in the Spark session; the Spark settings in `~/.config/spark/*.json` are what takes effect.
- Users: no passwords here, and no picture upload beyond choosing a file.
- The 24-hour clock is saved in the Spark locale setting; `plasma-localerc` is only also written for KDE machines.
- The proxy is saved to `kioslaverc`, which only KDE apps read; other apps follow their own.
