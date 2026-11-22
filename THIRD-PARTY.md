# Parts made by others

These files are not covered by SparkOS's [LICENSE](LICENSE). They keep the license their
authors gave them.

| What | From | License |
|---|---|---|
| `installer/` and `.github/workflows/installer-iso.yml` | Adapted from Bazzite's installer (github.com/ublue-os/bazzite) | Apache-2.0, text in [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt). SparkOS's changes to these files are under the same license. |
| `files/sparkos-theme/fonts/` (Chakra Petch) | Cadson Demak | SIL Open Font License 1.1, text in [files/sparkos-theme/fonts/OFL.txt](files/sparkos-theme/fonts/OFL.txt) |
| `files/device-rules/game-devices-udev/` (controller udev rules, Fedora image only) | game-devices-udev 1.1 by Fabian Bornschein (codeberg.org/fabiscafe/game-devices-udev), unchanged | MIT, text in [files/device-rules/game-devices-udev/LICENSE](files/device-rules/game-devices-udev/LICENSE) |
| `files/device-rules/udev-joystick-blacklist/` (Fedora image only) | udev-joystick-blacklist by denilsonsa (github.com/denilsonsa/udev-joystick-blacklist), unchanged | Public domain |
| `files/device-rules/oversteer/` (Logitech wheel udev rule, Fedora image only) | Oversteer by berarma (github.com/berarma/oversteer), unchanged | GPL-3.0, text in [files/device-rules/oversteer/LICENSE](files/device-rules/oversteer/LICENSE) |

## In the SparkOS image

The image is built on [Bazzite](https://github.com/ublue-os/bazzite) (Apache-2.0), which is
built on Fedora. It contains Linux, KDE Plasma, Mesa, Wine (in Spark Run's download) and many
other programs, each under its own license (GPL, LGPL, MIT and others). Their source is
available from Fedora, Bazzite and each project. SparkOS's license does not limit any right
those licenses give you.

Spark Terminal's terminal emulation (escape codes, Unicode, mouse, colours) is
[VTE](https://gitlab.gnome.org/GNOME/vte), the GNOME project's terminal library, from Fedora's
`vte291-gtk4` package. It is LGPL-3.0-or-later; Spark Terminal links to it as a library
through GObject introspection and does not modify it. Writing a terminal emulator from scratch
would break programs in ways VTE already handles, the same reason SparkOS uses Mesa and Linux
rather than its own.

Soot and FreeSuite are separate Wolklaw projects with their own terms.
