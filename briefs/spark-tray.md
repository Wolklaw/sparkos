# Spark Tray: network, Bluetooth, power, printer and volume icons

Built into the image, live updates on. Replaces plasma-nm, bluedevil, powerdevil's battery
applet, plasma-print-manager and plasma-pa's volume applet, one step at a time. Part of stage 2 of
[Replacing KDE](../PLAN.md).

## What

One process, five StatusNotifierItem icons (network, Bluetooth, power, printers, volume). Each can
be turned off, has a menu, and has a small popup in the house style. Source in
[files/spark-tray](../files/spark-tray); its README has the details.

- Network: NetworkManager. Wi-Fi list, connect with a password prompt, secrets agent, disconnect,
  wired, VPN, airplane mode.
- Bluetooth: BlueZ. Power, scan, pair, trust, connect, disconnect, battery, pairing agent.
- Power: UPower, power profiles (tuned-ppd), logind. Battery (hidden with none), profile,
  sleep/restart/shutdown with a confirm.
- Printers: CUPS command line tools. List, queue, cancel a job, add printer opens Spark Settings.
- Volume: Spark Audio's backend. Scroll, middle click to mute.

## Decisions

- GTK 3, not Tk: popups beside the icon, no focus steal, one GLib loop with D-Bus, optional
  layer-shell. The README explains it.
- It starts only in the `spark` session (`OnlyShowIn=Spark;`). In Plasma it is off, so there are no
  doubled icons; `spark-tray --enable` turns it on.
- The power icon is hidden on a PC with no battery; `--power-without-battery on` shows it.
- Do not install power-profiles-daemon: tuned-ppd already provides the D-Bus name.

## Status

Built 2026-11-25. Tested with python-dbusmock fakes and, in CI, windows under Xvfb in English and
French. Not tried against the real NetworkManager, BlueZ, UPower, CUPS, a real tray host or
layer-shell. Spark Settings has no switch for it yet.
