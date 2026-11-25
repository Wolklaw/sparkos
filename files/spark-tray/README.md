# Spark Tray 0.1.0

The SparkOS tray icons: network, Bluetooth, power, printers and volume. One process, five
StatusNotifierItem icons. Each icon can be turned off, has a menu, and opens a small popup in the
SparkOS house style (dark, 3px corners, mono type, a magenta and cyan channel slip as the only
decoration). Built into the image; live updates on. Stage 2 of "Replacing KDE" in
[PLAN.md](../../PLAN.md).

It replaces, one step at a time, plasma-nm, bluedevil, powerdevil's battery applet,
plasma-print-manager and plasma-pa's volume applet. Those stay installed and keep running in the
Plasma session; Spark Tray starts at login only in the `spark` session.

## The icons

| Icon | Talks to | What it does |
|---|---|---|
| Network | NetworkManager | Wi-Fi list, connect (asks for the password), disconnect, wired status, VPN switches, airplane mode. Also runs the secrets agent, so saved and new passwords reach NetworkManager. |
| Bluetooth | BlueZ | Power, scan, pair, trust, connect, disconnect, battery level. Runs the pairing agent (confirm, PIN, passkey). |
| Power | UPower, power-profiles (tuned-ppd), logind | Battery level and time left, profile switch, sleep, restart and shutdown with a confirm step. Hidden on a PC with no battery. |
| Printers | CUPS (`lpstat`, `cancel`, `cupsenable`, `cupsdisable`) | Printers, their queue, cancel a job, pause or resume. "Add printer" opens Spark Settings' printers page, else system-config-printer. Hidden when there are no printers or CUPS is not running. |
| Volume | Spark Audio's backend (PipeWire) | Scroll changes the volume, middle click mutes, the popup has a slider and the output list. |

## GTK, not Tk

Spark's other apps use Tk. This one uses GTK 3 through PyGObject, for three reasons:

- The tray protocol is D-Bus. GTK's main loop is GLib's, the same loop Gio's D-Bus code runs on, so
  the icons, the agents and the popups share one loop with no threads.
- A tray popup has to open beside its icon, without taking focus away and without a title bar. Tk
  can't place a window on Wayland, and it can't use layer-shell. GTK can, and `gtk-layer-shell`
  (optional here, guarded and untested) is the way to do it on Wayland.
- Tk draws a Tk look and doesn't follow the screen scale. GTK does both.

The image already has GTK 3 and PyGObject (Plasma and the Spark apps use them), so this adds no
big dependency. The StatusNotifierItem and `com.canonical.dbusmenu` sides are written by hand on
Gio. Each icon has its own D-Bus connection and its own `org.kde.StatusNotifierItem-<pid>-<n>`
name, because every item answers at `/StatusNotifierItem`.

## Settings and command line

```
spark-tray                         run the tray
spark-tray --status                what is on
spark-tray --item printers off     turn an icon off (on to turn it back on)
spark-tray --power-without-battery on   show the power icon on a PC with no battery
spark-tray --enable | --disable | --reset   autostart
spark-tray --self-test             check the pieces and the services (no display needed)
```

Choices are in `~/.config/spark-tray/`. The log is in `~/.local/state/spark-tray/`.

Spark Settings has no switch for these yet; the command line is the only control.

## Autostart

- The image ships `/etc/xdg/autostart/dev.wolklaw.SparkTray.desktop` with `OnlyShowIn=Spark;`, so it
  starts in the Spark session and not in Plasma.
- `spark-tray --enable` writes a per-user autostart file with no `OnlyShowIn`, so it starts in
  Plasma too. `--disable` writes `Hidden=true`. `--reset` removes the file, back to the default.
- If you run it in Plasma next to Plasma's own applets, you get two icons for each. Turn the Plasma
  ones off in Plasma's tray settings first.

## Install

On SparkOS it is in the image. For one user, without root:

```
bash install.sh --user            # to ~/.local
bash install.sh --user --uninstall
```

System-wide (root, image build): `bash install.sh --deps` installs python3, python3-gobject, gtk3
and cups-client with dnf, then the app. Do not install `power-profiles-daemon`: SparkOS uses
`tuned-ppd`, which provides the same `net.hadess.PowerProfiles` D-Bus name.

## Tests

```
python3 -m unittest discover -s tests -v
```

- The services are python-dbusmock fakes on private `dbus-daemon` buses (`tests/harness.py`), CUPS is
  a fake runner, volume is Spark Audio's saved test data. Nothing talks to the real network,
  Bluetooth, power or printers.
- `tests/test_windows.py` opens the popups and needs a display. It is skipped without one. CI runs
  it under Xvfb, in English and with `SPARK_LANG=fr`.
- Install `python3-dbusmock` and `dbus-daemon` to run them.

## Status

Written 2026-11-25. Honest state:

- Tested against fakes: all five backends, the StatusNotifierItem and menu protocol, settings, the
  per-user install and uninstall.
- Not tried against real NetworkManager, BlueZ, UPower or CUPS, with a real Plasma or Spark tray
  host, on real Wayland, or with gtk-layer-shell.
- Airplane mode covers NetworkManager's Wi-Fi and BlueZ's power; it does not touch other radios.
