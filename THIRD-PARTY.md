# Parts made by others

These files are not covered by SparkOS's [LICENSE](LICENSE). They keep the license their
authors gave them.

| What | From | License |
|---|---|---|
| `installer/` and `.github/workflows/installer-iso.yml` | Adapted from Bazzite's installer (github.com/ublue-os/bazzite) | Apache-2.0, text in [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt). SparkOS's changes to these files are under the same license. |
| `files/sparkos-theme/fonts/` (Chakra Petch) | Cadson Demak | SIL Open Font License 1.1, text in [files/sparkos-theme/fonts/OFL.txt](files/sparkos-theme/fonts/OFL.txt) |
| `files/device-rules/game-devices-udev/` (controller udev rules) | game-devices-udev 1.1 by Fabian Bornschein (codeberg.org/fabiscafe/game-devices-udev), unchanged | MIT, text in [files/device-rules/game-devices-udev/LICENSE](files/device-rules/game-devices-udev/LICENSE) |
| `files/device-rules/udev-joystick-blacklist/` | udev-joystick-blacklist by denilsonsa (github.com/denilsonsa/udev-joystick-blacklist), unchanged | Public domain |
| `files/device-rules/oversteer/` (Logitech wheel udev rule) | Oversteer by berarma (github.com/berarma/oversteer), unchanged | GPL-3.0, text in [files/device-rules/oversteer/LICENSE](files/device-rules/oversteer/LICENSE) |
| `files/ds-inhibit/` (DualShock 4/DualSense touchpad fix) | ds-inhibit by Valve (Vicki Pfau), from SteamOS, as packaged for Bazzite; unchanged | BSD-2-Clause, text in [files/ds-inhibit/LICENSE](files/ds-inhibit/LICENSE) |

## In the SparkOS image

The image is built on Fedora's atomic base image, `quay.io/fedora-ostree-desktops/base-atomic`
(until 2026-11-26 on Fedora Kinoite, until 2026-11-23 on [Bazzite](https://github.com/ublue-os/bazzite), Apache-2.0). It contains Linux, Mesa, Wine (in Spark Run's download) and many
other programs, each under its own license (GPL, LGPL, MIT and others). Their source is
available from Fedora, RPM Fusion, Terra and each project. SparkOS's license does not limit any right
those licenses give you.

Spark Terminal's terminal emulation (escape codes, Unicode, mouse, colours) is
[VTE](https://gitlab.gnome.org/GNOME/vte), the GNOME project's terminal library, from Fedora's
`vte291-gtk4` package. It is LGPL-3.0-or-later; Spark Terminal links to it as a library
through GObject introspection and does not modify it. Writing a terminal emulator from scratch
would break programs in ways VTE already handles, the same reason SparkOS uses Mesa and Linux
rather than its own.

Spark Emoji's emoji, symbol names and search words are the Unicode Consortium's data: the
Unicode emoji data files (`emoji-test.txt`, version 18.0) and the English and French annotations
from the Unicode CLDR project (`common/annotations` and `common/annotationsDerived`). They are
licensed under the Unicode License v3 (Unicode-3.0, https://www.unicode.org/license.txt), a
permissive licence that asks for the copyright notice and permission notice to be kept:
Copyright © 1991-present Unicode, Inc. `files/spark-emoji/tools/make_data.py` converts them to the
JSON files in `files/spark-emoji/sparkemoji/data/`; the data is not otherwise changed. The
colour emoji are drawn by the system's emoji font (Noto Color Emoji, `google-noto-color-emoji-fonts`
from Fedora, OFL-1.1), which Spark Emoji installs but does not modify.

Spark Notes' clipboard history runs `wl-paste --watch` and `wl-copy` from Fedora's `wl-clipboard`
package (GPL-3.0-or-later, https://github.com/bugaevc/wl-clipboard). It is called as a separate
command and is not linked into or modified by Spark Notes. The image step installs it
(`files/spark-notes/install.sh --deps`).

Spark Boxes runs virtual machines on libvirt and QEMU/KVM (Fedora's `libvirt-daemon-driver-qemu`,
`qemu-kvm`, `edk2-ovmf` and `swtpm`; LGPL-2.1-or-later, GPL-2.0-or-later, BSD-2-Clause and BSD-3-Clause
respectively; edk2 is BSD-2-Clause-Patent) through Fedora's `python3-libvirt` (LGPL-2.1-or-later), and shows a machine's screen with
`spice-gtk3` (LGPL-2.1-or-later). They are used as libraries and commands and are not modified. The
Windows driver disc (virtio-win) is not in the image: Spark Boxes downloads it on request, over https,
from Fedora's own download server (https://fedorapeople.org/groups/virt/virtio-win/), checks it against
a SHA-256 written in the source, and keeps it in the user's cache. Its drivers are by Red Hat and the
virtio-win project (mostly BSD-3-Clause; see the licence files on the disc).

SparkOS also builds kernel modules from other projects'
source while the image builds: zenergy, ryzen_smu, xone (xonedo), hid-fanatecff, new-lg4ff,
hid-tmff2 with hid-tminit (GPL-2.0) and vhba (GPL-2.0-or-later), plus v4l2loopback (GPL-2.0)
from RPM Fusion's akmod package. They are unchanged except that xone's version string is filled
in. Their license texts, and the exact source each was built from, are in
`/usr/share/licenses/sparkos-kmods/` in the image;
[docs/fedora-base.md](docs/fedora-base.md#kernel-modules) lists the pins. The Xbox wireless
dongle's firmware in that image is Microsoft's, extracted unchanged from its Windows Update
packages; it is not under an open-source license, and is redistributed the way the xone project
and other Linux distributions do.

The Fedora image also downloads, unchanged and checked by SHA-256 while it builds, the
`winetricks` script 20260125 (LGPL-2.1-or-later) and Nerd Fonts' Symbols Nerd Font 3.5.1 with
its fontconfig file (MIT). Their license texts are in `/usr/share/licenses/sparkos-parity/`.

Spark Games downloads three store programs the first time you use them, into
`~/.local/share/spark-games/runners/`, unchanged and checked by SHA-256 before they are ever
run. They are not in the image and Spark Games never imports their code; it starts each one as
a separate process and reads what it prints. All three are GPL-3.0; their source is in the
repository each link comes from.

| Program | For | Version | Download | SHA-256 |
|---|---|---|---|---|
| legendary | Epic Games Store | 0.21.1 | https://github.com/legendary-gl/legendary/releases/download/0.21.1/legendary_linux_x64 | dbed33bbe96031e65858233e4badf0a1d401bb6cb0cc995d1237cf3a0c826a45 |
| gogdl | GOG | 1.4.0 | https://github.com/Heroic-Games-Launcher/heroic-gogdl/releases/download/v1.4.0/gogdl_linux_x86_64 | 2aa2b59c83d3bfbe7b60ead91c6297b263b5d1e6c233a04b7409bafe26738f02 |
| nile | Amazon Games | 1.2.0 | https://github.com/imLinguin/nile/releases/download/v1.2.0/nile_linux_x86_64 | d73519514df9d52c50c6feec629373cc3a0d9504e087b6c7372a8ca8a95e7bfe |

Spark Games' "Add a launcher" downloads the Battle.net, EA app, Ubisoft Connect and Rockstar
installers from their companies' own sites when you ask, and runs them in their own Wine
folder. Those are the companies' programs under their own terms; nothing of them is bundled.

Soot and FreeSuite are separate Wolklaw projects with their own terms.
