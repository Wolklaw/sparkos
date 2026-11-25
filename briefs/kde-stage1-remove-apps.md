# KDE stage 1: remove the hidden apps

Stage 1 of "Replacing KDE" in [PLAN.md](../PLAN.md). The apps that a Spark app replaced were hidden
from the menu for one release; now they leave the image.

## Removed (files/scripts/sparkos-apps.sh)
Konsole and konsole-part, Ark and ark-libs, KDE Connect (kde-connect, kde-connect-libs, kdeconnectd),
Discover (plasma-discover and its flatpak, rpm-ostree and kns backends and libs), kinfocenter,
Journald Browser (kjournald), GNOME Disks (and libhandy), Btrfs Assistant, firewall-config.
Spectacle, Plasma System Monitor and Discover's notifier were already out.
`ark`, `kde-connect`, `btrfs-assistant` and `gnome-disk-utility` are no longer installed in
build_files/packages.sh. Checks that they are gone: sparkos-apps.sh, sparkos-cleanup.sh and the boot test.

## Kept on purpose
- Dolphin: waits until Spark Files network places have been used daily.
- Emoji Selector (inside plasma-desktop), Menu Editor (plasma-desktop requires kmenuedit), Klipper
  (inside plasma-workspace): still hidden or out of the tray.
- kio-gdrive, kaccounts, kio-fuse, krdp, the portal, firewalld, snapper (command line).

## Left alone, for the owner to know
- Spark Firewall still lists a "KDE Connect" switch (firewalld ships that service itself); the
  SparkOS zone no longer opens it. Removing the switch needs a Spark Firewall release.
- Spark Files and Spark Games still try `konsole` / `plasma-discover` if present (guarded by `which`).
  Dead code now; removing it needs per-app releases.
- Spark Snip's Spectacle fallback is the same.

## Measured (Fedora Kinoite 45 container, 2026-11-25)
18 packages, 44.2 MiB installed: konsole 7.0, gnome-disk-utility 6.7, konsole-part 3.6, kde-connect 4.6,
ark 3.5, kinfocenter 3.4, plasma-discover-libs 3.6, kde-connect-libs 2.9, plasma-discover 2.3, ark-libs 1.9,
libhandy 1.4, firewall-config 1.0, plasma-discover-flatpak 0.7, btrfs-assistant 0.6, kjournald 0.5,
plasma-discover-rpm-ostree 0.3, plasma-discover-kns 0.2, kdeconnectd 0.1.
