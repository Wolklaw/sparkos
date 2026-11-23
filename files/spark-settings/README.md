# Spark Settings

SparkOS's own settings app, in place of KDE System Settings. Python 3 and Tk, no packages beyond
what the image has. The brief is [briefs/spark-settings.md](../../briefs/spark-settings.md).

## Pages

Done in Spark Settings (each reads the real state when opened and talks to the tool named):

| Page | Tool | Notes |
| --- | --- | --- |
| Displays | `kscreen-doctor` | monitors as boxes you drag, resolution, refresh rate, scale, rotation, VRR, HDR, primary, on/off. Every change asks "Keep these settings?" and goes back after 15 s, on Revert, or if the window closes |
| Sound | `wpctl` | output and input device, default, volume, mute, per-app volume, a test tone |
| Network | `nmcli` | Wi-Fi list and connect (asks for the password), wired status, VPN connections (import, up, down), proxy |
| Bluetooth | `bluetoothctl` | on/off, scan, pair, connect, disconnect, forget |
| Power | `powerprofilesctl`, or `busctl` to the same service | power profile. Screen-off and sleep timers and the power button open KDE's module |
| Default apps | `xdg-mime` | browser, mail, folders, text, media, archives, terminal |
| Date, time and language | `timedatectl`, `localectl` | time zone, automatic time, language, 24-hour clock (writes Plasma's locale file) |
| Printers | `lpstat`, `lpinfo`, `lpadmin`, `lp` | list, find on the network, add, remove, make default, test page |
| Startup | autostart files | apps that open at sign-in, on or off |
| Updates | Spark Update | opens it |
| About | `/etc/os-release`, `rpm-ostree`, `lspci` | version, image, hardware, "Copy system info" |

Open KDE's own modules from inside Spark Settings (the page says so):
Appearance, Mouse/keyboard/controllers, Users, Storage and games drive.

**More settings** lists every module `kcmshell6 --list` reports and opens it, so nothing in
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

Three-monitor layout drag and apply, the FiiO DAC and QuadCast in Sound, the Canon TR4700
printer, Bluetooth pairing, and Wi-Fi password prompts. The commands and parsing are tested
against recorded output, not the devices.

## Known limits

- Appearance, input devices, Users and Storage are KDE's modules for now.
- The 24-hour clock writes `plasma-localerc` (`LC_TIME`) rather than a dedicated setting.
- Screen-off, sleep and the power button stay in KDE's module.
- The proxy is saved to KDE's `kioslaverc`, so it applies to KDE apps; other apps follow their own.
