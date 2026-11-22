# SparkOS &nbsp; [![build](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml/badge.svg)](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml)

A Linux desktop for gaming and everyday work, built on [Bazzite](https://bazzite.gg) from its own [Containerfile](Containerfile) ([how it's built](docs/building.md)).

Status: early. It runs on one real PC (AMD, dual boot next to Windows 11, since 21 Nov 2026), and every build is booted in a VM by CI ([boot-test](.github/workflows/boot-test.yml)), which checks the system name, the signed image, the preinstalled apps and the default apps. Expect rough edges, and keep Windows. See [PLAN.md](PLAN.md) for the roadmap.

## What's in it

SparkOS ships only its own apps. Everything else, Steam included, installs from the Store (Bazaar) in a click, or by double-clicking a downloaded `.exe`, `.AppImage` or `.rpm`.

| | |
|---|---|
| SparkOS apps | [Soot](https://github.com/Wolklaw/Soot), the default browser; [FreeSuite](https://github.com/Wolklaw/freesuite-releases) for mail, calendar, PDF and every Word, Excel, PowerPoint and OpenDocument format (both always their latest release); Spark Snip for screenshots, copying text off the screen (OCR) and recording ([source](files/spark-snip)); Spark Media for photos, videos and music, the default for all three ([source](files/spark-media)); Spark Welcome, which opens once at first login to offer game launchers and apps (on click only), copy your files from a Windows drive and check the PC ([source](files/spark-welcome)); Spark Games, one library of every installed game from Steam, Heroic and Lutris ([source](files/spark-games)); Spark Monitor, a task manager on Ctrl+Shift+Esc, Meta+Esc or Ctrl+Esc ([source](files/spark-monitor)); Spark Edit, the text and code editor, default for text files ([source](files/spark-edit)); Spark Calc, the calculator ([source](files/spark-calc)); Spark Archive for zip, 7z, tar, rar and iso, default for archives, with Extract/Compress in Dolphin ([source](files/spark-archive)); Spark Scan for scanning to PDF with OCR ([source](files/spark-scan)); Spark Run for Windows programs, downloading Wine on first use ([source](files/spark-run)); Spark Link, the phone link whose phone side is in Soot's app ([source](files/spark-link)); Spark Store, a store over Flathub next to Bazaar ([source](files/spark-store)); Spark Update, the update notification, window and rollback ([source](files/spark-update)) |
| Platform (from Bazzite and KDE) | KDE Plasma, Dolphin, Konsole, System Settings, Ark, KDE Connect, the Bazaar store, current Mesa drivers and a gaming-tuned kernel, CUPS driverless printing, SANE scanning, Bluetooth |
| Removed from Bazzite | Steam, Lutris, Waydroid, Firefox and Bazzite's other first-boot apps, Kate/KWrite, Filelight, Plasma System Monitor (Spark Monitor replaces it), Spectacle (Spark Snip replaces it), Tailscale and the Bazzite Portal. The apps are installable from the Store, and Tailscale as [the switching guide](docs/switching.md) says. |
| Compatibility SparkOS adds | Double-click installs for `.exe` and `.msi` (Spark Run), `.AppImage` (added to the menu by SparkOS itself), `.rpm` and `.deb`; Caps Lock turns on and off when you press it, like Windows, not when you release it ([source](files/sparkos-capslock)); VIA keyboard access; what Androidbox needs to install for a user; Claude Code one click away ([docs](docs/claude-code.md)); `sparkos-dev-setup` for Node, Python, GitHub CLI and JDK 17 |
| Look | Dark indigo with a mint accent, Inter and Chakra Petch, a slim top bar and a floating dock, the bot wallpaper, and a SparkOS boot splash, sign-in screen and sign-in splash |
| Identity | The SparkOS name, the bot logo and the zap startup sound |

Soot, FreeSuite and the Spark apps are new on Linux. The boot test checks them on every build and opens each one from the app menu on a real SparkOS desktop in a VM, with a screenshot, but none has been used by hand on a SparkOS desktop yet. To install it next to Windows, see [docs/install.md](docs/install.md). For what works, what's replaced and what doesn't run, see [docs/switching.md](docs/switching.md). For installing apps the Windows way (a store, or double-clicking a download), see [docs/installing-apps.md](docs/installing-apps.md).

Games with kernel-level anti-cheat (Valorant, Fortnite, recent Call of Duty, and others) don't run on Linux. Check your games on [ProtonDB](https://www.protondb.com) and [Are We Anti-Cheat Yet](https://areweanticheatyet.com).

## Install next to Windows

Download every file of the [installer release](https://github.com/Wolklaw/sparkos/releases/tag/installer) (the ISO comes in parts under 2 GB), join them with `join-iso.cmd` (Windows) or `join-iso.sh` (Linux), write the ISO to a USB stick, and follow [docs/install.md](docs/install.md). Windows stays; you pick the system at power-on.

CI builds the installer every Monday, boots it in a VM and installs it next to a Windows disk there ([installer-install-test](.github/workflows/installer-install-test.yml)). It has been installed on one real PC so far. The image is for AMD and Intel graphics; there is no NVIDIA build.

## Switching from Bazzite

1. Install [Bazzite](https://bazzite.gg) (KDE, AMD/Intel).
2. Switch to the unsigned SparkOS image first. This installs the SparkOS signing key:
   ```
   rpm-ostree rebase ostree-unverified-registry:ghcr.io/wolklaw/sparkos:latest
   systemctl reboot
   ```
3. Switch to the signed image:
   ```
   rpm-ostree rebase ostree-image-signed:docker://ghcr.io/wolklaw/sparkos:latest
   systemctl reboot
   ```

Updates arrive automatically. A new image is built every day from the latest Bazzite. If an update breaks something, choose the previous entry in the boot menu.

## Verify

Images are signed with [cosign](https://github.com/sigstore/cosign):

```
cosign verify --key cosign.pub ghcr.io/wolklaw/sparkos
```

## License

SparkOS is source-available, not open source: you can read the code here, and download, install and use the official SparkOS installer and images. Copying, modifying, redistributing or building your own versions needs written permission. See [LICENSE](LICENSE). Parts made by others keep their own licenses: see [THIRD-PARTY.md](THIRD-PARTY.md).
