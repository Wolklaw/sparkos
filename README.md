# SparkOS &nbsp; [![build](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml/badge.svg)](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml)

A Linux desktop for gaming and everyday work, built on [Bazzite](https://bazzite.gg) with [BlueBuild](https://blue-build.org).

Status: early and personal. Every build is booted in a VM by CI ([boot-test](.github/workflows/boot-test.yml)), which checks the system name, the signed image, the preinstalled apps and the default apps. It hasn't run on real hardware yet. See [PLAN.md](PLAN.md) for the roadmap.

## What it adds to Bazzite

| | |
|---|---|
| From Bazzite | KDE Plasma, Steam, Lutris (for Battle.net and others), gamescope, MangoHud, Firefox, current Mesa drivers, CUPS driverless printing with KDE Printers settings, SANE scanning, Bluetooth, KDE Connect, Tailscale |
| Added by SparkOS | [Soot](https://github.com/Wolklaw/Soot) 0.2.0 as the default browser, [FreeSuite](https://github.com/Wolklaw/freesuite-releases) 0.4.1 for mail, calendar, PDF and every Word, Excel and PowerPoint format, old and new, plus OpenDocument (default for all of them), ONLYOFFICE kept under "Open with" for old files with pictures or charts |
| | Spark Snip, the screenshot tool: Print for a screenshot, Meta+Shift+T to copy text off the screen (OCR), Meta+Shift+R to record ([source](files/spark-snip)) |
| | Skanpage for scanning, Piper (Logitech mice), OpenRGB, Mission Center, qpwgraph, VIA keyboard access |
| | Heroic, Prism Launcher, RuneLite, Bolt, Chrome, Discord, Spotify, OBS, Blender, GIMP, Audacity, Kdenlive, Flameshot, VS Code, Unity Hub, Bottles |
| | Claude Code one click away (app menu, right-click a folder, `sparkos-claude`), with its sandbox tools and `sparkos-claude-import` for your Windows setup ([docs](docs/claude-code.md)) |
| | `sparkos-dev-setup` for Node, Python, GitHub CLI and JDK 17, and the SparkOS name |
| Planned | First-boot setup, SparkOS look (Plasma theme, login screen, boot splash), own installer ISO |

Soot, FreeSuite and Spark Snip's Linux versions are new. The boot test checks them on every build, but none has been used by hand on a SparkOS desktop yet. For what works, what's replaced and what doesn't run, see [docs/switching.md](docs/switching.md).

Games with kernel-level anti-cheat (Valorant, Fortnite, recent Call of Duty, and others) don't run on Linux. Check your games on [ProtonDB](https://www.protondb.com) and [Are We Anti-Cheat Yet](https://areweanticheatyet.com).

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
