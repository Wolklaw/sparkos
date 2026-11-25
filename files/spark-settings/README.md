# Spark Settings

SparkOS's own settings app, in place of KDE System Settings. Python 3 and Tk, no packages beyond
what the image has. The brief is [briefs/spark-settings.md](../../briefs/spark-settings.md).

## Pages

Done in Spark Settings (each reads the real state when opened and talks to the tool named):

| Page | Tool | Notes |
| --- | --- | --- |
| Displays | `kscreen-doctor` | monitors as boxes you drag, resolution, refresh rate, scale, rotation, VRR, HDR, primary, on/off. Every change asks "Keep these settings?" and goes back after 15 s, on Revert, or if the window closes |
| Sound | `wpctl`, `pw-metadata` | output and input device, default, volume, mute, per-app volume, a test tone, output sample rate (follow the track, or a fixed rate your DAC lists in `/proc/asound/card*/stream0`, saved in `~/.config/pipewire/pipewire.conf.d/50-sample-rates.conf` and applied at once with `pw-metadata`) |
| Network | `nmcli` | Wi-Fi list and connect (asks for the password), wired status, VPN connections (import, up, down), proxy |
| Bluetooth | `bluetoothctl` | on/off, scan, pair, connect, disconnect, forget |
| Power | `busctl` (power-profiles-daemon, logind), `kwriteconfig6` | power profile, screen off and sleep after N minutes, power button, lock screen (also saved in `~/.config/spark/power.json` and `lock.json`) |
| Default apps | `xdg-mime` | browser, mail, folders, text, media, archives, terminal |
| Date, time and language | `busctl` (timedated, localed) | time zone, automatic time, set the time by hand, language (yours, or the whole computer's), 24-hour clock |
| Appearance | `plasma-apply-*`, `kwriteconfig6`, KWin | colour scheme, accent colour, wallpaper, cursor, window animations and blur; opens Spark Fonts for fonts |
| Mouse and keyboard | KWin input devices over D-Bus, `kcminputrc`, `kxkbrc` | pointer speed, acceleration, natural scrolling, left-handed, tap to click, key repeat, layouts |
| Shortcuts | kglobalaccel over D-Bus | list, change, reset, conflict check |
| Notifications | `plasmanotifyrc`, `~/.config/spark/notifications.json` | how long, where, mute sounds |
| Users | AccountsService over D-Bus | add, remove, rename, standard or administrator; passwords through `passwd` in Spark Terminal |
| Storage | `lsblk`, Spark Disks | mounted drives and free space, file indexing on or off |
| Printers | `lpstat`, `lpinfo`, `lpadmin`, `lp` | list, find on the network, add, remove, make default, test page |
| Startup | autostart files | apps that open at sign-in: on, off, add an installed app, remove |
| Updates | Spark Update | opens it |
| About | `/etc/os-release`, `rpm-ostree`, `lspci` | version, image, hardware, "Copy system info" |

Spark Settings no longer opens KDE's System Settings for any of its pages. The KDE-specific
writes (colour scheme, wallpaper, cursor, KWin effects and input, powerdevil, kscreenlocker,
plasma-localerc, baloo) are in one module, `sparksettings/plasma.py`, with a table of what each
function talks to. Settings that belong to the user are also saved in `~/.config/spark/*.json`,
so the Spark session can read them without Plasma.

**More settings** is the one way into KDE's modules: it lists every module `kcmshell6 --list` reports and opens it, so nothing in
System Settings is out of reach. Search matches English and French names and keywords, and those
modules too.

## Replacing System Settings

`files/scripts/spark-settings.sh` (the image build step):

- moves the real `/usr/bin/systemsettings` and `/usr/bin/kcmshell6` to
  `/usr/libexec/sparkos/kde-settings/` and puts a small stand-in in each place. Plasma opens
  settings by running those names (the desktop's "Configure Display Settings" runs
  `systemsettings kcm_kscreen`), so the stand-in runs `spark-settings --route`: modules that have
  a page here (`ROUTES` in `sparksettings/kcms.py`) open that page, everything else goes to the
  real tool unchanged
- hides the System Settings menu entries (`NoDisplay=true`); the package stays installed
- `spark-settings --kde [module]` opens KDE's System Settings (or one module) directly

Spark Settings is pinned on the dock. Spark Welcome's links already run `systemsettings kcm_...`,
so they land on the matching page here with no change to Welcome.

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

Everything that changes the real system or the live Plasma session (timedated, localed, AccountsService, KWin input, kglobalaccel, powerdevil, kscreenlocker) is tested against fakes only, not a live session. Three-monitor layout drag and apply, the FiiO DAC and QuadCast in Sound, the Canon TR4700
printer, Bluetooth pairing, and Wi-Fi password prompts. The commands and parsing are tested
against recorded output, not the devices.

## Known limits

- Displays still go through `kscreen-doctor` (`displays.py` is the one module to swap for a KWin output-management client).
- Input: pointer and touchpad settings go live over KWin's D-Bus; button mapping, calibration, tablets and touchscreens are not set here. Keyboard layouts are written to `kxkbrc` and apply through KWin.
- Appearance, KWin effects, powerdevil timers and the lock screen are written to Plasma's files today (`plasma.py`); they need KWin and Plasma running to take effect.
- Users: no passwords here, and no picture upload beyond choosing a file.
- The 24-hour clock writes `plasma-localerc` (`LC_TIME`) rather than a dedicated setting.
- The proxy is saved to KDE's `kioslaverc`, so it applies to KDE apps; other apps follow their own.
