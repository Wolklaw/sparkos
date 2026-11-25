# SparkOS &nbsp; [![build](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml/badge.svg)](https://github.com/Wolklaw/sparkos/actions/workflows/build.yml)

A Linux desktop for gaming and everyday work, built on [Fedora Kinoite](https://fedoraproject.org/atomic-desktops/kinoite/) from its own [Containerfile](Containerfile) ([how it's built](docs/building.md)).

Status: early. It is the daily system on one real PC (AMD, dual boot next to Windows 11, since 21 Nov 2026), and every build is booted in a VM by CI ([boot-test](.github/workflows/boot-test.yml)), which checks the system name, the signed image, the preinstalled apps and the default apps. Expect rough edges, and keep Windows. See [PLAN.md](PLAN.md) for the roadmap.

On that PC, Marvel's Spider-Man 2 runs **18% faster on SparkOS than on Windows 11** (92.4 vs 78.6 FPS on average, 1% lows 62.6 vs 48.4), with the same settings and HDR on in both. See [docs/benchmarks.md](docs/benchmarks.md) for the method and the limits.

## What's in it

SparkOS ships only its own apps: Soot, FreeSuite and 24 Spark apps come with the system and update with it, and 5 more Spark apps are optional, installed for your account from Spark Store in a click. Everything else, Steam included, installs from Spark Store, or by double-clicking a downloaded `.exe`, `.msi`, `.AppImage` or `.rpm`. Versions are today's; (new) means a first version from this week.

### Browser and office

| App | Version | What it does | |
|---|---|---|---|
| **Soot** | - | The default browser, on Firefox's engine, with ads and trackers blocked. Always its latest release. | [repo](https://github.com/Wolklaw/Soot) |
| **FreeSuite** | - | Mail, calendar, PDF, and Word, Excel, PowerPoint and OpenDocument files. Always its latest release. | [repo](https://github.com/Wolklaw/freesuite-releases) |

### The desktop

| App | Version | What it does | |
|---|---|---|---|
| **Spark Launcher** | - | The app menu, on the Meta key: search as you type, sums answered on the first line, pinned apps, recent files and power. | [source](files/spark-launcher) |
| **Spark Files** | 1.0.0 | The file manager: tabs and a split view, copies in the background, search, thumbnails, the Trash and your Windows drives. | [source](files/spark-files) |
| **Spark Terminal** | 1.1.0 | Tabs, split panes, search in the scrollback and clickable links, on Ctrl+Alt+T. | [source](files/spark-terminal) |
| **Spark Settings** | 1.0.0 | Displays, sound, network, Bluetooth, power, default apps, date and language, printers and startup, with KDE's pages for the rest. | [source](files/spark-settings) |
| **Spark Store** | 0.1.1 | The Spark apps, then every app on Flathub, with what each one can access in plain words. One click installs. | [source](files/spark-store) |
| **Spark Update** | 1.1.2 | Gets the next version ready in the background, says when a restart will start it, shows what changed and rolls back. | [source](files/spark-update) |
| **Spark Welcome** | 1.1.0 | Opens once at first login: the Spark app for each Windows program, your files, fonts and Steam games from Windows, apps to add, and a check of the PC. | [source](files/spark-welcome) |

### Everyday

| App | Version | What it does | |
|---|---|---|---|
| **Spark Snip** | - | Screenshots on Print with an annotate step (arrows, text, pixelate, crop), copying text off the screen (English and French) and screen recording. | [source](files/spark-snip) |
| **Spark Media** | - | Photos (camera RAW and HEIC too), videos with subtitles, and a music library with playlists and media keys. | [source](files/spark-media) |
| **Spark Edit** | 1.0.1 | Text and code: tabs, find and replace, syntax colours, files kept in their own encoding. Unsaved tabs come back. | [source](files/spark-edit) |
| **Spark Calc** | 1.0.1 | Exact sums (0.1 + 0.2 is 0.3), with scientific and programmer modes and a history. | [source](files/spark-calc) |
| **Spark Fonts** | 0.1.0 | See, install and remove fonts, with previews, characters and licence details. Finds the fonts on a Windows drive. Opens font files. | [source](files/spark-fonts) |
| **Spark Archive** | 1.2.0 | Opens and makes zip, 7z, tar, rar and iso, in several parts and with passwords. Extract and Compress on right-click. | [source](files/spark-archive) |
| **Spark Scan** | 1.1.0 | Scans from the glass or the feeder, straightens pages, and saves one PDF (searchable if you want) or an image per page. | [source](files/spark-scan) |
| **Spark Notes** | 0.1.0 (new) | Quick notes as plain files, and clipboard history on Meta+V with search, pins and a pause. No account. Replaces Klipper. | [source](files/spark-notes) |
| **Spark Emoji** | 0.1.0 (new) | Emoji and symbols on Meta+. (full stop): search in English or French, recents, skin tones, arrows, maths and accented letters. | [source](files/spark-emoji) |
| **Spark Boxes** | 0.1.0 (new) | Virtual machines: make one from an ISO, start it, see its screen, snapshots, USB. Sets up UEFI, Secure Boot and a TPM for Windows 11. On libvirt and KVM (`spark virt setup` first). Replaces Virtual Machine Manager. | [source](files/spark-boxes) |
| **Spark Audio** | 0.1.0 (new) | The sound mixer: outputs, microphones with a test, volume per app, a simple equalizer and Focusrite Scarlett controls. | [source](files/spark-audio) |

### Looking after the PC

| App | Version | What it does | |
|---|---|---|---|
| **Spark Monitor** | 1.1.0 | The task manager, on Ctrl+Shift+Esc: apps grouped by app, End task, live graphs, startup apps, the system log live, and a hardware summary to copy. | [source](files/spark-monitor) |
| **Spark Disks** | 0.1.0 (new) | Drives and partitions: mount, format, resize, drive health (SMART) and writing an image to a USB stick. | [source](files/spark-disks) |
| **Spark Backup** | 0.1.0 (new) | Snapshots of your home folder on a schedule, a copy on another drive, and restoring a file. Not tried on a real PC yet. | [source](files/spark-backup) |
| **Spark Firewall** | 0.1.2 (new) | The firewall in plain words: on or off, open what a game or app needs, and a zone for each network. Replaces firewall-config. | [source](files/spark-firewall) |

### Games, hardware and phone

| App | Version | What it does | |
|---|---|---|---|
| **Spark Games** | 0.3.3 | One library for every game: sign in to Epic, GOG and Amazon here, add Battle.net, EA, Ubisoft and Rockstar, and see Steam, Lutris, itch and more. Controller and big-screen modes. | [source](files/spark-games) |
| **Spark Controller** | 1.1.0 | Fan curves, RGB lighting on every part, game controllers with a live button tester, and firmware updates. | [source](files/spark-controller) |
| **Spark Run** | 1.0.1 | Runs Windows programs on Wine, or installs them as apps with their own menu entry. Wine downloads the first time. | [source](files/spark-run) |
| **Spark Link** | 1.0.1 | Your phone over the local network: links, files, notifications, battery, find my phone and an optional shared clipboard. Pairs with Soot for Android. | [source](files/spark-link) |

### Optional, from Spark Store

| App | Version | What it does | |
|---|---|---|---|
| **Spark Bench** | 0.1.0 | Game benchmarks: MangoHud recording set up in one click, a sound when a run starts and ends, FPS and lows per run, compared with Windows. | [source](files/spark-bench) |
| **Spark Space** | 1.0.0 | What takes the space on your drives: a map of every folder, the largest files, and safe moves to the Trash. | [source](files/spark-space) |
| **Spark Connect** | 0.2.0 | Home servers on one screen, fixed over SSH: services, health, tunnel, failover and websites. Also a desktop widget. | [source](files/spark-connect) |
| **Spark Clock** | 0.1.0 (new) | Alarms, timers, a stopwatch and world clocks. They ring with the window closed and after a restart. | [source](files/spark-clock) |
| **Spark Camera** | 0.1.0 (new) | Your webcam: preview, photos with a countdown, video with sound, and a voice recorder. | [source](files/spark-camera) |

## Every feature

**Updates and safety**

- The whole system updates as one image, built every day from the latest Fedora Kinoite.
- Every image is signed with cosign, and a SparkOS PC only accepts an update signed with SparkOS's key.
- Every build is installed and booted in a virtual machine on GitHub, which checks the system, the signature and opens every app.
- Updates download in the background and wait while a game runs, on a metered connection or on a low battery. The PC never restarts on its own.
- Roll back in one click in Spark Update, or pick the previous version in the boot menu. After three failed boots, it goes back by itself.
- Release notes in plain words, in English and French, for every change you will notice.

**Coming from Windows**

- Ctrl+Shift+Esc for the task manager, Print for a screenshot, Meta+V for clipboard history, Meta+. for emoji, Ctrl+Alt+T for a terminal.
- Caps Lock turns on when you press it, like Windows, not when you release it.
- Double-click a downloaded `.exe`, `.msi`, `.AppImage` or `.rpm` to install it. A `.deb` gets a plain explanation and a way to the Store.
- Spark Welcome copies your files, fonts and Steam games from a Windows drive, and your Windows drives show in Spark Files.
- Windows stays: SparkOS installs next to it and you pick one at power-on.

**Games**

- gamescope, MangoHud, GameMode and umu-launcher come with it.
- Drivers SparkOS builds for each kernel: Xbox wireless adapters, racing wheels, AMD CPU power sensors, virtual cameras and disc drives.
- Device rules for controllers and wheels, and game tuning: memory, network, zram, disk schedulers and a VRAM booster.
- Full video decoding and encoding on the graphics card, from RPM Fusion, for recording and streaming.
- Steam, Heroic and Lutris install from the Store in a click, and Spark Games puts their games in one library.

**The desktop**

- Its own look: dark indigo with a mint accent, a slim top bar, a floating dock, the bot wallpaper, its own icons, boot splash, sign-in screen and startup sound.
- KDE Plasma underneath, with KDE's tools replaced where a Spark app does the job: the file manager, terminal, app menu, task manager, screenshot tool, clipboard, emoji picker and firewall tool.
- No preinstalled apps from other companies. Fedora's apps are removed, and each one can come back from the Store.
- The on-screen keyboard stays off on a desktop PC, so it doesn't pop up over games.
- The Spark apps follow the system language, English or Quebec French.

**Everything else**

- Driverless printing, scanning and Bluetooth, from Fedora.
- Flathub for every other app, installed per user by the Store.
- For developers: Homebrew, `sparkos-dev-setup` for Node, Python, GitHub CLI and JDK 17, and Claude Code one click away ([docs](docs/claude-code.md)).
- VIA keyboard setup and Androidbox work without extra steps.
- The source can be read on GitHub: the build file, every script and every Spark app.

**Platform (from Fedora and KDE)**

- KDE Plasma, System Settings, Fedora's kernel and current Mesa drivers, CUPS driverless printing, SANE scanning, Bluetooth, and full video decoding and encoding from RPM Fusion.
- Dolphin is out of the menu, kept for one release behind Spark Files; Konsole is hidden, kept for one release behind Spark Terminal. Ark, KDE Connect and Discover stay installed but out of the menu (Spark Archive, Spark Link and Spark Store replace them).
- Removed from Fedora Kinoite: Firefox, Kate/KWrite, Filelight, Plasma System Monitor, Spectacle, Discover's tray notifier and KDE's other small apps. Each can be installed from the Store.

Soot, FreeSuite and the Spark apps are new on Linux. The boot test checks them on every build and opens each one from the app menu on a real SparkOS desktop in a VM, with a screenshot. On a real PC they have had only a few days of use, the new ones a few hours, and Spark Backup none yet. To install it next to Windows, see [docs/install.md](docs/install.md). For what works, what's replaced and what doesn't run, see [docs/switching.md](docs/switching.md). For installing apps the Windows way (a store, or double-clicking a download), see [docs/installing-apps.md](docs/installing-apps.md).

Games with kernel-level anti-cheat (Valorant, Fortnite, recent Call of Duty, and others) don't run on Linux. Check your games on [ProtonDB](https://www.protondb.com) and [Are We Anti-Cheat Yet](https://areweanticheatyet.com).

## Install next to Windows

Download every file of the [installer release](https://github.com/Wolklaw/sparkos/releases/tag/installer) (the ISO comes in parts under 2 GB), join them with `join-iso.cmd` (Windows) or `join-iso.sh` (Linux), write the ISO to a USB stick, and follow [docs/install.md](docs/install.md). Windows stays; you pick the system at power-on.

CI builds the installer every Monday, boots it in a VM and installs it next to a Windows disk there ([installer-install-test](.github/workflows/installer-install-test.yml)). It has been installed on one real PC so far. The image is for AMD and Intel graphics; an NVIDIA build is in progress and not released.

## Switching from another Fedora atomic desktop

SparkOS was built on [Bazzite](https://bazzite.gg) until 23 Nov 2026 and is now built on Fedora Kinoite ([why and what changed](docs/fedora-base.md)). From Bazzite, Kinoite or another Fedora atomic desktop:

1. Switch to the unsigned SparkOS image first. This installs the SparkOS signing key:
   ```
   rpm-ostree rebase ostree-unverified-registry:ghcr.io/wolklaw/sparkos:latest
   systemctl reboot
   ```
2. Switch to the signed image:
   ```
   rpm-ostree rebase ostree-image-signed:docker://ghcr.io/wolklaw/sparkos:latest
   systemctl reboot
   ```

Updates arrive automatically. A new image is built every day from the latest Fedora Kinoite. If an update breaks something, choose the previous entry in the boot menu.

## Verify

Images are signed with [cosign](https://github.com/sigstore/cosign):

```
cosign verify --key cosign.pub ghcr.io/wolklaw/sparkos
```

## License

SparkOS is source-available, not open source: you can read the code here, and download, install and use the official SparkOS installer and images. Copying, modifying, redistributing or building your own versions needs written permission. See [LICENSE](LICENSE). Parts made by others keep their own licenses: see [THIRD-PARTY.md](THIRD-PARTY.md).
