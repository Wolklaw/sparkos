# SparkOS &nbsp; [![build](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml/badge.svg)](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml)

A Linux desktop for gaming and everyday work, built on [Bazzite](https://bazzite.gg) with [BlueBuild](https://blue-build.org).

Status: early and personal. Every build is booted in a VM by CI ([boot-test](.github/workflows/boot-test.yml)), which checks the system name, the signed image, the preinstalled apps and the default apps. It hasn't run on real hardware yet. See [PLAN.md](PLAN.md) for the roadmap.

## What's in it

SparkOS ships only its own apps. Everything else, Steam included, installs from the Store (Bazaar) in a click, or by double-clicking a downloaded `.exe`, `.AppImage` or `.rpm`.

| | |
|---|---|
| SparkOS apps | [Soot](https://github.com/Wolklaw/Soot), the default browser; [FreeSuite](https://github.com/Wolklaw/freesuite-releases) for mail, calendar, PDF and every Word, Excel, PowerPoint and OpenDocument format (both always their latest release); Spark Snip for screenshots, copying text off the screen (OCR) and recording ([source](files/spark-snip)); Spark Media for photos, videos and music, the default for all three ([source](files/spark-media)); Spark Welcome, which opens once at first login to offer game launchers and apps (on click only), copy your files from a Windows drive and check the PC ([source](files/spark-welcome)); Spark Games, one library of every installed game from Steam, Heroic and Lutris ([source](files/spark-games)); Spark Monitor, a task manager on Ctrl+Shift+Esc, Meta+Esc or Ctrl+Esc ([source](files/spark-monitor)) |
| Platform (from Bazzite and KDE) | KDE Plasma, Dolphin, Konsole, Spectacle, System Settings, Ark, KDE Connect, the Bazaar store, current Mesa drivers and a gaming-tuned kernel, CUPS driverless printing, SANE scanning, Bluetooth, Tailscale |
| Removed from Bazzite | Steam, Lutris, Waydroid, Firefox and Bazzite's other first-boot apps, Kate/KWrite, Filelight, Plasma System Monitor (Spark Monitor replaces it, on Ctrl+Shift+Esc, Meta+Esc and Ctrl+Esc) and the Bazzite Portal. All are installable from the Store. |
| Compatibility SparkOS adds | Double-click installs for `.exe` (Bottles, fetched on first use), `.AppImage` (added to the menu by SparkOS itself), `.rpm` and `.deb`; VIA keyboard access; what Androidbox needs to install for a user; Claude Code one click away ([docs](docs/claude-code.md)); `sparkos-dev-setup` for Node, Python, GitHub CLI and JDK 17 |
| Look | Dark indigo with a mint accent, Inter and Chakra Petch, a slim top bar and a floating dock, the bot wallpaper, and a SparkOS boot splash, sign-in screen and sign-in splash |
| Identity | The SparkOS name, the bot logo and the zap startup sound |

Soot, FreeSuite and all five Spark apps are new on Linux. The boot test checks them on every build, but none has been used by hand on a SparkOS desktop yet. For what works, what's replaced and what doesn't run, see [docs/switching.md](docs/switching.md). For installing apps the Windows way (a store, or double-clicking a download), see [docs/installing-apps.md](docs/installing-apps.md).

Games with kernel-level anti-cheat (Valorant, Fortnite, recent Call of Duty, and others) don't run on Linux. Check your games on [ProtonDB](https://www.protondb.com) and [Are We Anti-Cheat Yet](https://areweanticheatyet.com).

## Install from the SparkOS installer

The [installer release](https://github.com/Wolklaw/sparkos/releases/tag/installer) holds a live USB image of SparkOS. It's rebuilt every Monday from the latest image.

1. Download **all** the files in the release. The ISO comes in parts because GitHub limits each release file to 2 GiB.
2. Run `join-iso.cmd` (Windows) or `join-iso.sh` (Linux). It joins the parts into `SparkOS-installer.iso` and checks its SHA-256.
3. Write the ISO to a USB stick of 16 GB or more with [Fedora Media Writer](https://fedoraproject.org/workstation/download) (choose *Custom image*) or Rufus (DD mode).
4. Boot from the stick (UEFI mode) and choose **Install SparkOS**. If Secure Boot is on, the next start shows a blue key-enrollment screen: choose *Enroll MOK*, then *Continue*, and type `universalblue`.

Status: the installer is new. CI builds it and boots it once in a VM, but no one has installed from it yet.

## Install (switching from Bazzite)

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
