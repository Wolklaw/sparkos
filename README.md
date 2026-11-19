# SparkOS &nbsp; [![build](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml/badge.svg)](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml)

A Linux desktop for gaming and everyday work, built on [Bazzite](https://bazzite.gg) with [BlueBuild](https://blue-build.org).

Status: early and personal. The image builds, but it hasn't been tested in a VM or on real hardware yet. See [PLAN.md](PLAN.md) for the roadmap.

## What it adds to Bazzite

| | |
|---|---|
| From Bazzite | KDE Plasma, Steam, Lutris (for Battle.net and others), gamescope, MangoHud, Firefox, current Mesa drivers |
| Added by SparkOS | Heroic Games Launcher (Epic, GOG, Amazon), ONLYOFFICE (documents, spreadsheets, slides), SparkOS name |
| Planned | [Soot](https://github.com/Wolklaw/Soot) browser and [FreeSuite](https://github.com/Wolklaw/freesuite-releases) preinstalled (both need Linux builds first), first-boot setup, SparkOS look (Plasma theme, login screen, boot splash), own installer ISO |

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
