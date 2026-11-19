# WolkOS &nbsp; [![build](https://github.com/Wolklaw/wolkos/actions/workflows/build.yml/badge.svg)](https://github.com/Wolklaw/wolkos/actions/workflows/build.yml)

A Linux desktop for gaming and everyday work, built on [Bazzite](https://bazzite.gg) with [BlueBuild](https://blue-build.org).

Status: early and personal. It boots in a VM, but it hasn't been tested on real hardware yet. See [PLAN.md](PLAN.md) for the roadmap.

## What it adds to Bazzite

| | |
|---|---|
| From Bazzite | KDE Plasma, Steam, Lutris (for Battle.net and others), gamescope, MangoHud, Firefox, current Mesa drivers |
| Added by WolkOS | Heroic Games Launcher (Epic, GOG, Amazon), ONLYOFFICE (documents, spreadsheets, slides), WolkOS name |
| Planned | First-boot setup, WolkOS look (Plasma theme, login screen, boot splash), own installer ISO |

Games with kernel-level anti-cheat (Valorant, Fortnite, recent Call of Duty, and others) don't run on Linux. Check your games on [ProtonDB](https://www.protondb.com) and [Are We Anti-Cheat Yet](https://areweanticheatyet.com).

## Install (switching from Bazzite)

1. Install [Bazzite](https://bazzite.gg) (KDE, AMD/Intel).
2. Switch to the unsigned WolkOS image first. This installs the WolkOS signing key:
   ```
   rpm-ostree rebase ostree-unverified-registry:ghcr.io/wolklaw/wolkos:latest
   systemctl reboot
   ```
3. Switch to the signed image:
   ```
   rpm-ostree rebase ostree-image-signed:docker://ghcr.io/wolklaw/wolkos:latest
   systemctl reboot
   ```

Updates arrive automatically. A new image is built every day from the latest Bazzite. If an update breaks something, choose the previous entry in the boot menu.

## Verify

Images are signed with [cosign](https://github.com/sigstore/cosign):

```
cosign verify --key cosign.pub ghcr.io/wolklaw/wolkos
```
