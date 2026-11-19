# SparkOS &nbsp; [![build](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml/badge.svg)](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml)

A Linux desktop for gaming and everyday work, built on [Bazzite](https://bazzite.gg) with [BlueBuild](https://blue-build.org).

Status: early and personal. Every build is booted in a VM by CI ([boot-test](.github/workflows/boot-test.yml)), which checks the system name, the signed image, the preinstalled apps and the default apps. It hasn't run on real hardware yet. See [PLAN.md](PLAN.md) for the roadmap.

## What it adds to Bazzite

| | |
|---|---|
| From Bazzite | KDE Plasma, Steam, Lutris (for Battle.net and others), gamescope, MangoHud, Firefox, current Mesa drivers, CUPS driverless printing with KDE Printers settings, SANE scanning, Bluetooth, KDE Connect, Tailscale |
| Added by SparkOS | [Soot](https://github.com/Wolklaw/Soot) as the default browser and [FreeSuite](https://github.com/Wolklaw/freesuite-releases) (both always their latest release) for mail, calendar, PDF and every Word, Excel and PowerPoint format, old and new, plus OpenDocument (default for all of them), ONLYOFFICE kept under "Open with" for old files with pictures or charts |
| | [Androidbox](https://github.com/Wolklaw/Androidbox), the ad-free Android emulator (Google Play, game controls, macros), using KVM. It downloads Android the first time you open it |
| | Spark Snip, the screenshot tool: Print for a screenshot, Meta+Shift+T to copy text off the screen (OCR), Meta+Shift+R to record ([source](files/spark-snip)) |
| | Skanpage for scanning, Piper (Logitech mice), OpenRGB, Mission Center, qpwgraph, VIA keyboard access |
| | Heroic, Prism Launcher, RuneLite, Bolt, Chrome, Discord, Spotify, OBS, Blender, GIMP, Audacity, Kdenlive, Flameshot, VS Code, Unity Hub, Bottles |
| | Claude Code one click away (app menu, right-click a folder, `sparkos-claude`), with its sandbox tools and `sparkos-claude-import` for your Windows setup ([docs](docs/claude-code.md)) |
| | `sparkos-dev-setup` for Node, Python, GitHub CLI and JDK 17, and the SparkOS name |
| Planned | First-boot setup, SparkOS look (Plasma theme, login screen, boot splash), own installer ISO |

Soot, FreeSuite, Spark Snip and Androidbox's Linux versions are new. The boot test checks them on every build, but none has been used by hand on a SparkOS desktop yet, and no Android has been booted in Androidbox on Linux. For what works, what's replaced and what doesn't run, see [docs/switching.md](docs/switching.md).

Games with kernel-level anti-cheat (Valorant, Fortnite, recent Call of Duty, and others) don't run on Linux. Check your games on [ProtonDB](https://www.protondb.com) and [Are We Anti-Cheat Yet](https://areweanticheatyet.com).

## Install from the SparkOS installer

The [installer release](https://github.com/Wolklaw/sparkos/releases/tag/installer) holds a live USB image with every app inside. The apps are copied onto the new system during install, so they're there on the first start, even offline. It's rebuilt every Monday with the latest image and the latest apps from Flathub.

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
