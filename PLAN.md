# SparkOS plan

SparkOS is a custom Linux image for gaming and everyday work. It is built on **Fedora Kinoite 45** (Fedora's atomic KDE image; Bazzite until 2026-11-23) from SparkOS's own **Containerfile** (BlueBuild until 2026-11-20; see [docs/building.md](docs/building.md)), which GitHub Actions turns into a signed OS image on every change and again each day when upstream updates.

We don't maintain a kernel or drivers: Fedora handles those. SparkOS adds the gaming layer Bazzite used to provide (kernel modules, device rules, tuning, gamescope/MangoHud/GameMode), the apps, defaults and branding. See [docs/fedora-base.md](docs/fedora-base.md).

## Status (2026-11-20)
- **Phase 0: done.** Repo `Wolklaw/sparkos` is public, the cosign key is in `SIGNING_SECRET` (a local copy is in the git-ignored `cosign.key`), and the first CI build passed in about 5 minutes. `ghcr.io/wolklaw/sparkos:latest` is public, and its signature verifies against `cosign.pub`.
- **Phase 1: done in CI.** The boot-test workflow boots every build in QEMU/KVM on GitHub. Local VirtualBox testing on this PC froze because Windows' Memory Integrity holds the CPU's virtualization. [docs/vm-test.md](docs/vm-test.md) stays as the manual path for a PC without that.
- Renamed from WolkOS to SparkOS on 2026-11-19: the repo is now `Wolklaw/sparkos` (GitHub redirects the old URL) and the image is `ghcr.io/wolklaw/sparkos`. The old `ghcr.io/wolklaw/wolkos` image is no longer updated. The local folder is still named `WolkOS`.
- **Base: Fedora Kinoite only since 2026-11-23.** The `sparkos-fedora` test image passed on the real PC (no failed units, faster boot than Bazzite, GPU video, Vulkan, every kernel module and Spark app self-test; [docs/fedora-base.md](docs/fedora-base.md)), so the Bazzite build was dropped and `ghcr.io/wolklaw/sparkos` is built from Fedora. Only the visible name is SparkOS: `ID=fedora` stays, because Fedora's own tools read it.

## Starting point (checked on this PC, 2026-11-19)

| | Found | What it means |
|---|---|---|
| GPU | AMD Radeon RX 6800 XT | Best case for Linux. Open drivers come in the kernel, so no NVIDIA variant is needed. |
| CPU / RAM | Ryzen 7 7800X3D, 32 GB | No constraints. |
| Disks | Two 1 TB NVMe drives (Windows; games) and a SATA SSD for scratch files (stays as is) | SparkOS shares the games drive: Windows shrank it and SparkOS uses the freed space (dual boot, installed 21 Nov 2026). |
| Board | ASUS PRIME X670-P WIFI | Should have three M.2 slots, two of them in use. Confirm in the manual before buying a drive. |
| Tools | git, gh (logged in), no WSL, no VM software | Images build on GitHub Actions, so nothing has to be installed locally for builds. A VM app is needed for testing. |

## Decisions (defaults I'd pick)

1. **Base image:** `quay.io/fedora/fedora-kinoite:45` (KDE Plasma) since 2026-11-23; `ghcr.io/ublue-os/bazzite:stable` before that (Release 3 below).
2. **Your own apps ship preinstalled:** **Soot** as the browser and **FreeSuite** as the office suite (mail, documents, sheets, slides, PDF). Both are Windows-only today, so each needs a Linux build first:
   - **Soot: in the image, always the latest release** (`files/scripts/soot.sh`). It installs to `/usr/lib/soot` and is the default browser. The installed release is recorded in `/usr/lib/soot/SOOT_RELEASE`.
   - **FreeSuite: in the image** (`files/scripts/freesuite.sh`, always the latest release, checked against that release's SHA256SUMS). It installs to `/usr/lib/opt/freesuite`, because `/opt` is in `/var` on Fedora Atomic. It's the default for mail, calendar, PDF and every Office format it opens, including .doc/.xls/.ppt, OpenDocument and RTF.
   - **Spark Snip 1.0.0: in the image**, built from this repo (`files/spark-snip`, installed by `files/scripts/spark-snip.sh`). It's the screenshot, OCR and screen recording tool and takes Print, Meta+Shift+S/T/R from Spectacle, which stays installed because Spark Snip reads the screen through it. It grew out of QuickOCR, whose Windows app is finished.
   - **Spark Media 1.0.0: in the image**, built from this repo (`files/spark-media`, installed by `files/scripts/spark-media.sh`). It opens photos, videos and music and is the default for all three, so a fresh SparkOS needs no extra app for them. Photos through Pillow (HEIC with pillow-heif), playback through GStreamer with FFmpeg's decoders; the build fails if H.264, H.265, AAC or MP3 can't play.
   - **Spark Welcome, Spark Games, Spark Monitor 1.0: in the image (owner's decision, 2026-11-20)**, built by separate sessions from [briefs/](briefs/README.md) and merged in PRs #3 to #5. Welcome opens once at first login; Games gathers Steam, Heroic and Lutris libraries; Monitor is the Ctrl+Shift+Esc task manager (1.1.0 adds Logs and System tabs). The boot test runs each one's self-test in the real image. Later Spark apps are optional, through a future Spark Portal.
   - **Androidbox: not in the image, but ready to install.** SparkOS ships what its Linux installer needs: `python3.13`, because Qt for Python has no packages for Fedora 45's Python 3.15, plus the Qt, SDL and emulator libraries. You install it for your user, with no root, from the latest release (see the switching guide). The boot test does exactly that on every build and starts it.
   - **Androidbox compatibility: parked (2026-11-20).** The owner will finish it later. The boot test no longer installs Androidbox as a user (that check was slow and kept failing). `python3.13` and the Qt/SDL libraries stay in the image, ready for when it's picked up.
   - **App policy (2026-11-20):** SparkOS ships only the owner's own apps: Soot, FreeSuite and the Spark apps (Snip, Media, Welcome, Games, Monitor, Edit, Calc, Archive, Scan, Run, Link, Store, Files, Terminal, Emoji, Notes, Update). Every other company's or project's app is removed, Bazzite's included (Steam, Lutris, Waydroid, Firefox and its other first-boot apps, Kate/KWrite, Filelight, the Portal), and is installable from the Store. ONLYOFFICE is gone too: old .doc/.xls/.ppt open in FreeSuite, which reads them partly. The platform stays: Plasma, Dolphin, Konsole (hidden since Spark Terminal), Spectacle, System Settings, Ark, KDE Connect and the Store.
   - **Updates:** publish a new release of Soot or FreeSuite, and the next image build (daily, or any push) includes it. The boot test then checks it.
3. **Install target (needed only in Phase 5; Phases 0–4 run in a VM):**
   - **Chosen: E:, after its games are uninstalled.** In Phase 5, uninstall the Windows games on E: (Steam, Epic, Battle.net and Xbox app), then shrink E: in Disk Management (run as admin) and install SparkOS into the freed space. Uninstall the Xbox app's games through the Xbox app itself. Their protected `WindowsApps`/`XboxGames` files are what usually block a shrink.
   - **How big:** E: is 954 GB. Keep enough NTFS space for `Personal Projects` plus room to grow, and give the rest (likely 600–800 GB) to SparkOS. Measure the size of `Personal Projects` at that point to decide.
   - **Keep on NTFS:** `Personal Projects` and any other files you share between the two systems. SparkOS can read and write NTFS for files like these. Only games need to sit on the Linux partition.
   - **Keep in Windows:** any game blocked by kernel anti-cheat. It can be reinstalled on C:, which has 196 GB free.
   - **Before shrinking:** back up `Personal Projects`. Shrinking is usually safe, but this is the one step where a mistake costs data.
   - **Fallback if E: won't shrink far enough:** a new NVMe SSD in the free M.2 slot.
   - **Never use:** D:, which holds downloads and temp files.
4. **Repo:** public GitHub repo `sparkos`. The image goes to GHCR. A public repo keeps image pulls free and authentication-free.
5. **Test VM:** VMware Workstation Pro (now free) or VirtualBox. Windows 11 Home has no Hyper-V Manager.

## Phases

### Phase 0: Prep (about an hour)
- Install VMware Workstation Pro or VirtualBox, and confirm SVM virtualization is on in the BIOS.
- Create the repo (from the BlueBuild template at first), generate a cosign signing key, and store it as the `SIGNING_SECRET` repo secret.
- **Done when:** the first CI build goes green and the image shows up in GHCR.

### Phase 1: Minimal image (one evening)
- The build file (`recipes/recipe.yml` then, the `Containerfile` since 2026-11-20): base Bazzite, with the image name and description set to SparkOS.
- Game launchers (Steam, Heroic, Lutris) install from the Store; none are preinstalled.
- Add the office suite (FreeSuite) and Soot.
- In the VM: install the stock Bazzite ISO, then `rpm-ostree rebase` onto `ghcr.io/wolklaw/sparkos:latest`.
- **Done when:** the VM boots SparkOS, `/etc/os-release` reports it, and the apps open.

### Phase 2: Defaults and first boot (a few evenings)
- A first-boot setup script: choose a games drive, sign in to launchers, pick an office suite.
- Custom `ujust` commands, for example `ujust sparkos-update` and `ujust sparkos-games-drive`.
- Sensible defaults: Steam Proton enabled for all titles, MangoHud preset, power profile, Flatpak permissions.
- **Done when:** a fresh install gets from login to a playable Steam game and an open document with no terminal use.

### Phase 3: Branding (a few evenings, in the house style)
**Built (2026-11-20), checked in the boot-test VM.** Colour scheme, fonts, Konsole profile, the SparkOS look-and-feel package (top bar and floating dock, sign-in splash), wallpaper on desktop, lock and sign-in screens, Plymouth boot splash in a rebuilt initramfs, logo in About/os-release/fastfetch (`files/scripts/sparkos-theme.sh`, `files/system`). The boot test signs in once and screenshots the real desktop.
- Plasma Login Manager has no themes by KDE's design, so the sign-in screen gets the SparkOS wallpaper, colours and fonts but keeps KDE's layout (its big clock is close to the mockup).
- **Not confirmed yet:** the boot splash on screen. The VM showed black then boot text; being looked into, and to check on real hardware in Phase 5.
- Still to do: the animated bot in the sign-in splash (today a still image). The dock's "S" and "F" tiles are Soot's and FreeSuite's own brand icons, already in the house style; the mockup's placeholder tiles needed no replacing.

**Your verdict on the stock look (2026-11-19):** it reads as "Windows on a black theme". SparkOS needs its own identity, not Bazzite's skin with a dark palette. The plan:
- Remove Bazzite's Portal autostart, announcements and wallpaper, in the live installer too.
- Rethink the taskbar layout rather than keep the Windows-style bar.
- Mock it up first (desktop, login, boot splash) and agree on it before building, because each image round takes about an hour.
- **Mockup approved (2026-11-20):** [SparkOS look](https://claude.ai/artifact/52XRMbG3ELXyz4K2FdYfHe). Build this:
  - **Desktop:** a floating, centred dock (not a full-width taskbar) with the bot as the launcher button, and a slim top bar with the SPARKOS wordmark, tray and clock.
  - **Wallpaper:** the dark field with the bot large and faint, and one slipped magenta/cyan scan line.
  - **App launcher:** search first, then pinned apps, recent files and the power buttons.
  - **Sign-in screen:** a big glitch clock and a sign-in card.
  - **Boot splash:** the bot hammering its anvil (a 2 s loop of one blow, on every screen), the spaced-out wordmark and a thin progress line.
  - **Logo:** the SparkOS bot (`branding/`), with its animation timed to the zap startup sound at sign-in.
  - **Accent:** mint by default.
  - **Still needed:** real app icons in place of the lettered tiles.

Base the palette on the wolklaw web tokens: `#0a0919` background, `#141233` surface, mint `#9be8b8` accent, 3px corners. The magenta/cyan slip (`#ff2e88` / `#22d8ff`) is the only decoration.
- KDE Plasma colour scheme, window decoration and Konsole profile. Fonts: Chakra Petch for headings, Inter for UI, Cascadia Code for mono.
- A SparkOS mark (to design), used everywhere below.
- Plymouth boot splash: the mark with a short channel-slip tear while loading.
- SDDM login screen: dark panel with a glitch heading, honoring reduced motion.
- Wallpaper: a plain dark field with the offset mark. No stock art.
- fastfetch logo and the name in About This System.
- **Done when:** every screen from power-on to desktop reads as SparkOS, checked against real screenshots from the VM.

### Phase 4: Own installer ISO (in progress)
- `installer/` and `.github/workflows/installer-iso.yml` build a SparkOS live installer, adapted from Bazzite's (Apache-2.0). It runs on demand and every Monday.
- The installer carries SparkOS itself. It can carry Flatpaks too (`installer/flatpaks`, copied onto the new system during install), but under the app policy that list is empty.
- After install, the system follows signed SparkOS updates (`bootc switch --enforce-container-sigpolicy`).
- **Uploaded** to the `installer` release in parts under 2 GiB (GitHub's limit per file), with `join-iso.cmd` and `join-iso.sh`, which join the parts and check the SHA-256. **Public since 2026-11-21:** the owner installed from it on their PC (dual boot) first, then published it; wolklaw.dev links to it.
- **CI checks:** the installer builds and the ISO boots in QEMU (screenshots kept for 7 days). It carries no third-party apps.
- **Tested:** a full install next to Windows in a VM on every installer build, and on the owner's PC (21 Nov 2026).
- **Done when:** a clean VM installs from the SparkOS ISO and first boots with all apps present.

### Phase 5: Real hardware and your games (ongoing)
- Uninstall the Windows games on E:, back up `Personal Projects`, shrink E:, and install SparkOS into the freed space (see decision 3). At startup, choose SparkOS or Windows from the boot menu.
- Reinstall the games inside SparkOS, onto its own partition. Secure Boot needs no key for the system (Fedora's signed kernel). SparkOS's extra kernel modules are signed in the image build once the `KMOD_SIGNING_KEY` secret and `secureboot/sparkos-kmods.der` are in place; then run `spark secureboot enroll` once per PC. Until then they don't load with Secure Boot on. **Status (2026-11-24):** signing, the cert path and `spark secureboot` are written but untested: no key made yet, no signed build, no enrollment tried on real firmware.
- Work through [docs/switching.md](docs/switching.md): every app and device on this PC, with its SparkOS answer. Settle the **Check** items first.
- Day-one hardware checks:
  - Print and scan a page on the Canon TR4700.
  - Set up the G502 in Piper.
  - Open the Keychron in VIA (Chrome).
  - Check that the QuadCast, FiiO DAC and C920 work in Discord and OBS.
  - Try OpenRGB on the motherboard and RAM.
  - Set up all three monitors, including refresh rates.
  - Chessbot (`E:\Personal Projects\CheatChessClaude`, not in the image): run `linux/install.sh --deps`, launch `chessbot`, and check its window and clipboard paste. Its Linux port was never run, because there was no Fedora system to test it on before real hardware. If it works, it can be added to the image like Soot.
- **Benchmark against Windows 11:**
  - Run 4–5 games you play, at the same settings and resolution on both systems.
  - Log average FPS and 1% lows (MangoHud on SparkOS, PresentMon/CapFrameX on Windows).
  - Time boot to desktop on both.
  - Put the results in `docs/benchmarks.md`.
  - Anything slower gets looked into before Windows goes.
- **Done when:** a normal week of work and games happens on SparkOS without reaching for Windows, except for the games and tools marked **No** in the switching guide.

### Phase 6: Upkeep (minutes a week)
- CI rebuilds daily against the latest Fedora Kinoite. Updates are atomic, and a bad update rolls back from the boot menu.
- When Fedora changes something, it's usually a one-line fix in the Containerfile or a build script. A new kernel can break a kernel module's build: the build stops, and the module's pinned source gets bumped (build_files/kmods.sh).

## Independence roadmap (owner's goal, 2026-11-20)
Rely on other people's products as little as possible by Release 2 or 3. Replace what a Spark app or a small change can own; keep what no one person can maintain. Work items have briefs in [briefs/](briefs/README.md).

**Release 2: easy wins**
| Today | SparkOS's own | Status |
|---|---|---|
| Chakra Petch downloaded from Google's GitHub at every build | The font kept in this repo (OFL allows it) | PR [#13](https://github.com/Wolklaw/sparkos/pull/13) ([brief](briefs/release2-cleanup.md)) |
| Plasma System Monitor | Spark Monitor, already shipping, also on Meta+Esc and Ctrl+Esc; KDE's removed | PR [#13](https://github.com/Wolklaw/sparkos/pull/13) |
| Gear Lever, fetched to open `.AppImage` files | A small Spark handler in `sparkos-open-package` | PR [#13](https://github.com/Wolklaw/sparkos/pull/13) |
| Tailscale, preinstalled by Bazzite | Removed (installable by anyone who wants it) | PR [#13](https://github.com/Wolklaw/sparkos/pull/13) |
| Fedora's usage counting and connectivity check, KDE's "Get New Stuff" | Usage counting off and Get New Stuff hidden in PR [#13](https://github.com/Wolklaw/sparkos/pull/13); the connectivity check is the owner's call (in the PR) |
| Spectacle, which Spark Snip uses to capture | Spark Snip captures through KWin directly | Done in the first release: Spectacle removed after the boot test's real-session capture passed |
| Bazzite/ublue update tools (`ujust`, their update service and rollback helper) | **Spark Update**: "SparkOS updated, restart?", what changed, one-click rollback | **Done 2026-11-20**: Spark Update downloads and stages updates itself (the boot test had it stage and start a real update); `uupd` and the Bazzite Updater are removed, and `ujust update` runs Spark Update. `ujust` went with the Fedora move (2026-11-23) |
| Homebrew's daily update timers, Universal Blue's akmods repository | Homebrew quiet until `sparkos-dev-setup --brew`; the repository off | **Done 2026-11-20** |

**Release 3: bigger moves**
| Today | SparkOS's own | Status |
|---|---|---|
| Bazaar, the store | **Spark Store**: SparkOS's own store over Flathub, with the Spark apps in it (the Spark Portal idea) | Brief: [spark-store](briefs/spark-store.md) |
| Bazzite as the base, and Universal Blue's tooling | Build on Fedora's own atomic KDE image with SparkOS's own gaming layer (Mesa, gamescope, MangoHud, kernel settings) | Prototype merged as a separate image, `sparkos-fedora` ([#16](https://github.com/Wolklaw/sparkos/pull/16)): it builds and boots, and 19 of 22 checks pass (missing: H.265, Bazaar, Homebrew). **Done 2026-11-23**: tried on the real PC for a day and passed, so it became the only image; the Bazzite build is gone and `ujust` with it (`spark` replaces it). Results in [docs/fedora-base.md](docs/fedora-base.md) |
| BlueBuild | A plain Containerfile and SparkOS's scripts | **Done 2026-11-20**: the real build uses SparkOS's own Containerfile ([#15](https://github.com/Wolklaw/sparkos/pull/15), [docs/building.md](docs/building.md)) |
| Bottles, fetched to open `.exe` files | Spark Run, on Wine/Proton | In the first release ([#17](https://github.com/Wolklaw/sparkos/pull/17)). The Wine it downloads is now built by SparkOS's own CI from WineHQ's signed source (release [wine-11.22-2](https://github.com/Wolklaw/sparkos/releases/tag/wine-11.22-2), reproducible), no longer Kron4ek's build |
| KDE System Settings | **Spark Settings**: displays, sound, network, Bluetooth, power, default apps, printers and more; KDE's modules open for the rest until covered | Brief: [spark-settings](briefs/spark-settings.md) (2026-11-22) |
| SignalRGB, Armoury Crate, NZXT CAM, Fan Xpert | **Spark Controller**: fan curves with smoothing, RGB lighting, game controller tester, fwupd firmware updates | Brief: [spark-controller](briefs/spark-controller.md) (2026-11-23) |
| firewall-config | **Spark Firewall**: on/off, a zone per network, plain-language rules (Steam Remote Play, Spark Link), ports; firewalld through a polkit helper | Brief: [spark-firewall](briefs/spark-firewall.md) (2026-11-23). Hidden firewall-config stays installed one release; not tried on a real firewall change yet |
| Backups: Timeshift, Pika Backup, Deja Dup (none installed) | **Spark Backup**: Btrfs snapshots of /home on a schedule, a copy on another drive (btrfs send, or rsync to NTFS), browse and restore a file, keep the last N. Version 0.1.2: tested with fakes, a throwaway loop image and a temp folder; on 2026-11-24 the real /home was found as a Btrfs subvolume and the real drives listed without root (D: is refused, being read-only). A real snapshot, copy and restore are not tried yet (they need a polkit click). Owner picks the drive, schedule and how many to keep | Brief: [spark-backup](briefs/spark-backup.md) (2026-11-23) |
| Heroic and Lutris | **Spark Games** signs in to Epic, GOG and Amazon itself (on legendary, gogdl and nile, the clients Heroic runs) and installs Battle.net, EA and Ubisoft with umu-run | Brief: [spark-games-stores](briefs/spark-games-stores.md) (2026-11-22) |
| GNOME Disks | **Spark Disks**: drives and partitions, mount, format, resize, SMART health, USB image writer, on udisks2; D: is look-only | Brief: [spark-disks](briefs/spark-disks.md) (2026-11-23) |
| (no clock app) | **Spark Clock** (optional): alarms, timers, stopwatch, world clocks, rung by a systemd user service with the window closed | Brief: [spark-clock](briefs/spark-clock.md) (2026-11-24). Wake from suspend (0.2.0, opt in) through a small root helper in the image; not yet tried on a booted SparkOS |
| Ark | Spark Archive | Brief: [spark-archive](briefs/spark-archive.md) |
| KDE Connect | Spark Link: the PC side in SparkOS, the phone side in Soot's Android app, no outside service | Briefs: [spark-link](briefs/spark-link.md), [protocol](docs/spark-link-protocol.md) |

**New Spark tools for gaps (no app at all today):** Spark Edit, a light text and code editor ([brief](briefs/spark-edit.md)); Spark Calc ([brief](briefs/spark-calc.md)); Spark Scan, for the Canon scanner ([brief](briefs/spark-scan.md)). Planned 2026-11-24: Spark Boxes, virtual machines ([brief](briefs/spark-boxes.md)), and Spark Fonts ([brief](briefs/spark-fonts.md)). Spark Clips, instant replay for games, is an optional app ([brief](briefs/spark-clips.md)).

**Owner's decision (2026-11-22): as little software from others as possible, Dolphin and Konsole included.** Spark Files replaces Dolphin ([brief](briefs/spark-files.md); built in [files/spark-files](files/spark-files), in the image as the default file manager with Dolphin hidden; 1.1.0 adds network places (sftp, smb) and Google Drive through KIO and kio-fuse, the last thing only Dolphin did, so Dolphin can go once the owner has used Spark Files daily; real sftp tried against a throwaway sshd, smb and Drive not yet tried), Spark Terminal replaces Konsole ([brief](briefs/spark-terminal.md), on the VTE library; built 2026-11-22, the default terminal from that build, Konsole hidden) and Spark Launcher replaces Plasma's Kickoff menu ([brief](briefs/spark-launcher.md)). Each old app stays installed but hidden for one release, then goes. Next in line once their Spark app covers them: Spectacle (Spark Snip), Ark (Spark Archive), KDE Connect (Spark Link) and Bazaar (Spark Store, already on the dock). **2026-11-23:** Ark, KDE Connect and Discover are hidden from the menu the same way (the owner uses Spark Link over Wi-Fi; Spark Archive was tried on real archives 2026-11-24: made and extracted zip, 7z and tar.zst identically, and listed real archives on C: and E:), and so are tools that don't need a menu entry: btop, nvtop, Microsoft Edit, Info Center, Journald Browser, Btrfs Assistant, the Menu Editor ([sparkos-cleanup.sh](files/scripts/sparkos-cleanup.sh)). GNOME Disks is hidden too (Spark Disks, 0.1.0: tried on loop devices and, read-only on 2026-11-24, on the real drives and their SMART health; not yet on a real USB stick). **Firewall:** firewall-config is hidden the same way now that Spark Firewall covers it ([brief](briefs/spark-firewall.md)). **Spark Emoji** ([brief](briefs/spark-emoji.md), [files/spark-emoji](files/spark-emoji), 0.1.0, built 2026-11-23) now covers the Emoji Selector: it takes Meta+. and the Emoji Selector is hidden. It is its own app, not part of Spark Launcher (a dock plasmoid). Copying works everywhere; pasting into the previous window goes through the desktop portal's keyboard permission, tested against a fake portal; on the booted SparkOS (2026-11-24) Meta+. belongs to Spark Emoji alone and the portal offers RemoteDesktop with a keyboard, so what is left is one real paste, which asks the owner once. **Spark Notes** ([brief](briefs/spark-notes.md), [files/spark-notes](files/spark-notes), 0.1.0, built 2026-11-24) replaces Klipper: quick notes plus a clipboard history on Meta+V, kept by a small per-user watcher service. Klipper has no file to hide (it is the Clipboard entry of the system tray inside plasmashell), so the default layout starts the tray without it and a one-time update script takes it out of the owner's existing profile and frees Meta+V. That removal is syntax-checked only until it runs on a booted SparkOS. **Spark Audio** ([brief](briefs/spark-audio.md), [files/spark-audio](files/spark-audio), 0.1.0, built 2026-11-24) is the sound mixer: outputs, microphones, per-app volume and routing, mic test, a five-band EQ (PipeWire filter-chain as a user service) and a Focusrite Scarlett page. It replaces Focusrite Control and a separate mixer; Plasma's volume applet stays in the tray (its "Configure Audio Devices..." still opens Plasma's Sound page, rewiring it would mean patching plasma-pa). The Scarlett page stays hidden (the owner no longer has a Scarlett, so it is not going to be tried); volume, mute and moving an app were tried live on the FiiO DAC-E10 on 2026-11-24. **Spark Camera** ([brief](briefs/spark-camera.md), [files/spark-camera](files/spark-camera), 0.1.0, optional through Spark Store): webcam preview, photos, video with sound and a voice recorder; engine tried with the owner's C920 and QuadCast, the window mostly on a test pattern.

**Kept on purpose:** the Linux kernel, Mesa, KDE Plasma, Wine/Proton, Soot's Firefox engine and FreeSuite's Chromium/Electron, Flathub as the source of other people's apps, libraries the Spark apps are built on (Tk, GTK, VTE, GStreamer), Sigstore signing and LVFS firmware updates. GitHub and GHCR stay for code, builds and downloads; a mirror on SparkOS's own server is the cheap insurance later.
Plasma is on this list as my suggestion, not the owner's rule; the next section is the path to replace it.

## Replacing KDE (planned 2026-11-24, not started)
**Where it stands.** The apps are mostly replaced; the desktop is not. Measured on the owner's PC on 2026-11-24: 173 KDE packages (81 of them KDE Frameworks libraries), about 1.3 GiB with Qt6.
- **Already replaced or hidden:** Dolphin, Konsole, Kickoff, Spectacle, Ark, KDE Connect, Discover, Klipper, Plasma System Monitor, the Emoji Selector, firewall-config, GNOME Disks.
- **Still KDE, the desktop:** KWin (window manager and compositor), plasmashell (panels, dock, tray, desktop, notifications), the lock screen (kscreenlocker), Plasma Login Manager, the KDE desktop portal, the polkit password prompt (polkit-kde), global shortcuts (kglobalacceld).
- **Still KDE, system pieces:** power (powerdevil), display setup (kscreen), the network, volume, Bluetooth and printer applets (plasma-nm, plasma-pa, bluedevil, plasma-print-manager), plus Thunderbolt, Vault, Disks and the Breeze theme.
- **Spark apps that lean on KDE today:** Spark Snip captures through KWin; spark-share runs on krdp; Spark Files network places run on KIO and kio-fuse, and Google Drive also needs kaccounts; Spark Settings opens KDE's settings pages for what it doesn't cover; Spark Launcher is a Plasma panel widget; Spark Emoji pastes through the KDE portal.

**What limits the speed.** Not writing the code: SparkOS and its apps were built in four days. The limit is testing the shell and compositor on the real PC. The CI boot test's VM has no real GPU, HDR, VRR or mixed-refresh monitors, and a broken shell or compositor means a black screen at login or stuttering games, not one broken app. Every step from stage 3 on needs rounds of the owner trying it and saying what broke.

**Safety rule.** The Spark shell, and later the compositor, ship as a **separate session picked on the login screen**, with Plasma kept as the fallback. Plasma leaves the image only after the owner has used the Spark session daily and not needed Plasma for a while.

**Stages, cheapest first**
1. **Remove the hidden apps** (about an hour). **Done in the PR `kde-stage1-remove-apps`, not yet tried on the owner's PC:** Konsole, Ark, KDE Connect, Discover (and its backends), kinfocenter, Journald Browser, GNOME Disks, Btrfs Assistant and firewall-config are out of the image (18 packages, about 44 MiB installed); Dolphin stays, and the Emoji Selector and Menu Editor stay hidden because plasma-desktop contains or requires them. What follows is the original plan. Dolphin, Konsole, Ark, Discover, KDE Connect, kinfocenter and the hidden tools, once their one-release grace is over; check nothing in the image still calls them, and that the boot test passes. Dolphin waits until the owner has used Spark Files network places daily.
2. **Settings and tray without KDE** (one or two days). Spark Settings covers its remaining pages itself instead of opening KDE's. **Spark Settings part: PR open [#102](https://github.com/Wolklaw/sparkos/pull/102), fakes only; Displays still use kscreen-doctor.** Spark versions of the network, Bluetooth, power and printer applets talk to NetworkManager, BlueZ, UPower/power-profiles-daemon and CUPS directly. The volume applet becomes Spark Audio's. Each one works inside Plasma's tray first, so it is used daily before stage 3.
3. **Spark shell** (a few days to build, then daily use). GTK4 with gtk4-layer-shell, in the house style: panel, dock (Spark Launcher moves out of its plasmoid), tray (StatusNotifierItem), notifications (org.freedesktop.Notifications), wallpaper and desktop, on-screen volume and brightness, lock screen (ext-session-lock), a login greeter, a polkit agent. It still runs on KWin. Spark Snip, spark-share, Spark Files and Spark Emoji get backends that don't need Plasma (screen capture and input through the portal, files without KIO where possible). Once the owner stops using the Plasma session, plasma-workspace, plasma-desktop, the Plasma add-ons, Breeze and most of KDE Frameworks can go; KWin and what it needs stay. **App side done in a PR (2026-11-25, [brief](briefs/spark-apps-without-plasma.md)):** in a headless KWin with no plasmashell, Snip, spark-share, Files (sftp through sshfs when kio-fuse is absent) and Emoji work and Update restarts through logind; smb, Google Drive and a real desktop are not tried. r, wallpaper, OSD) and the `Spark` login session are in [ **Built 2026-11-25 ([#104](https://github.com/Wolklaw/sparkos/pull/104), not default):** the shell (panel per monitor, tray, notifications, launcher, wallpaper, OSD) and the `Spark` login session are in [files/spark-shell](files/spark-shell/README.md) and the image; tested headless on 3 virtual outputs only, nothing tried on the real PC yet.
   *Stage 3 security pieces ([#107](https://github.com/Wolklaw/sparkos/pull/107)): a polkit agent and a greetd sign-in screen are built and tested in containers; the sign-in screen stays off until the owner runs `spark greeter enable`. No Spark lock screen yet: KWin 6.8.3 has no ext-session-lock, so kscreenlocker stays. See [briefs/spark-session.md](briefs/spark-session.md).*
4. **Spark compositor, optional** (days for a working one; how long it takes to match KWin depends on test rounds). On wlroots or Smithay. It has to cover what the owner uses today: HDR, VRR, the mixed-refresh monitors, game direct scanout, gamescope, Steam's overlay, screen capture for Snip and Share, fractional scaling. My recommendation is to stop after stage 3 and keep KWin alone, like Mesa or the kernel; this stage is the owner's call. **Started 2026-11-25:** a first wlroots compositor exists as the experimental `spark-wl` session ([files/spark-compositor](files/spark-compositor)); it passes headless tests with three virtual outputs, layer-shell, XWayland and screencopy, but has never run on a real GPU, and HDR, VRR, direct scanout and Steam's overlay are untried or missing.

**Next step when this is picked up:** stage 1, then a brief for the Spark shell in [briefs/](briefs/README.md).

## Remote care: connector app and GestionDirecte tablet OS (owner's goal, 2026-11-21)
Two new parts. Working names until the owner picks real ones: **Spark Connect** (the connector app) and **GD Tablet** (the tablet OS). Nothing is built yet; this section records the goal and the defaults I'd pick.

**What the owner wants**
1. **The connector app:** one place to see and troubleshoot every Linux machine that runs the owner's websites, and every GestionDirecte tablet.
2. **The tablet OS:** an Android-compatible system for tablets that opens only GestionDirecte, connects to the connector, and lets the owner see the tablet's screen and fix it remotely.

**Machines it covers today** (details in wolklaw.dev's local notes, kept out of this public repo): the OptiPlex (Caddy, Cloudflare tunnel, wolklaw.dev, the GestionDirecte portal and the owner's other services), the old laptop (failover standby with the watchdog and net monitor), and the venue laptop that runs GestionDirecte at the convention center (its OS not checked yet).

**First brief:** [spark-connect](briefs/spark-connect.md), the home servers over SSH.

**Defaults I'd pick**
- **Connection model: each machine and tablet dials out to a hub; nothing listens on the internet.** The hub runs on the OptiPlex behind the existing Cloudflare tunnel (or a WireGuard endpoint), so venue networks need no open ports and no outside service is involved (independence goal). Every device has its own key, enrolled once; the connector app authenticates to the hub with the owner's key. Losing a tablet means revoking one key.
- **Linux machines, first version: no agent, over SSH.** The OptiPlex and laptop already trust this PC's key. The connector shows, per machine: up/down, the systemd units that matter (`gestiondirecte-portal`, `cloudflared`, `caddy`, the failover units), each public URL's status, disk, memory, load, temperature, recent journal errors, and the failover/netmon state that already exists on the laptop. Actions: open a terminal, tail a log, restart one unit (always confirmed, never `cloudflared` or other services without saying which hostnames it affects). A small dial-out agent comes second, for machines outside the home network (the venue laptop).
- **Tablets: stock Android plus our own device-owner app first, not a custom ROM.** The app is set as device owner at setup (`dpm set-device-owner`, on a factory-reset tablet), runs in lock-task (kiosk) mode, shows the venue's GestionDirecte in a full-screen WebView, and blocks everything else (no status bar, no other apps, no settings). It reports battery, Wi-Fi, app version, last page load and errors to the hub, and can reload, clear cache, update itself and reboot on command. This works on most tablets with no per-model work.
- **Seeing the tablet's screen is the hard part.** A normal app needs a consent tap on the tablet every time it captures the screen (Android's rule), and remote taps need an accessibility service. Options, in order: (a) screen share that someone at the venue accepts, which is fine when a staff member is there; (b) keep wireless ADB on and reach it through the hub, the same way Androidbox drives phones (scrcpy-style view and control with no taps on the tablet); (c) a custom AOSP/LineageOS build where our app is a system app with silent capture rights. (c) is the only true "OS" and needs a build per tablet model, so it waits until one tablet model is chosen.
- **The tablet shows when it is being viewed.** A visible banner on the tablet whenever the screen is being watched or controlled, because these tablets sit in client venues with client data on screen.
- **The connector app runs on SparkOS and Windows,** built like the other Spark apps, in the house style. It's the owner's admin tool, so it's an optional Spark app (Spark Store or per-user install), not preinstalled for everyone. Owner's call.

**Owner's answers (2026-11-21)**
- **Tablets:** probably Samsung; model and count not chosen yet.
- **Where:** the convention center only, for now.
- **What they open:** the venue's own GestionDirecte install, not the portal.
- **Accounts:** each tablet signs in with its department's generic account. Department heads have their own private accounts, because they can edit and see more.
- **Screen access:** the full version, a live mirror with remote control.
- **Hub:** the OptiPlex is the central hub for GestionDirecte.

**What the answers change**
- **Sign-in on the tablet:** the tablet starts signed in as its department's generic account. A department head taps "Sign in as me", uses their own account, and the tablet signs them out after a few idle minutes and goes back to the generic account, so a head's edit rights never stay open on a shared screen. The generic account's password is set at enrollment and never shown on the tablet.
- **Samsung and full remote control:** no custom ROM. On Samsung, unlocking the bootloader trips Knox for good (Samsung Pay, Secure Folder and Knox features stop working) and many North American models can't be unlocked at all. So GD Tablet stays our device-owner app on Samsung's own Android, and the full mirror-with-control comes from one of these, to be tested on the first tablet:
  1. **Wireless ADB through the hub** (the Androidbox way: scrcpy-style view and control, no taps on the tablet). The thing to test: whether it stays on after a reboot on One UI, or needs re-enabling.
  2. **Samsung's Knox SDK** inside our app, which allows screen capture and remote input for an enrolled device-owner app without a tap each time. It runs on the tablet, but needs a free license key from Samsung, a tie to an outside company that the owner should approve first.
  3. **Fallback:** a staff member accepts the share once per session.
- **Buy one test tablet first** (a recent Galaxy Tab A or S on the latest One UI), prove kiosk mode, sign-in switching and remote control on it, then pick the model for the venue.
- **The venue's GestionDirecte install** runs on the venue laptop at the convention center. Its tablets and the laptop itself dial out to the hub on the OptiPlex, so the venue laptop is the first machine that needs the small agent instead of SSH.

**Desktops and the GD host's console (owner's ask, 2026-11-23):** Spark Connect can also see and control a SparkOS desktop, and show (and type into) the console of the GD host, which has no desktop (sudo password typed in a terminal, nothing installed on the server). For a desktop: the person at it accepts a prompt, or the owner skips the prompt with `sudo` on that machine; a banner shows while it is shared. Over SSH with KDE's own RDP server (krdp, already in the image), nothing listening on the network. The Ubuntu servers don't get it. Brief: [spark-connect-screen](briefs/spark-connect-screen.md).

**Order:** Spark Connect for the home Linux machines first (SSH, no new software on the servers), then the agent for the venue laptop, then the GD Tablet kiosk app with status and remote reload on one test tablet, then the full screen mirror with control.

## Live app updates (2026-11-24)
Spark app changes ship as signed releases of the app alone, and Spark Update installs them with no reboot and no image rebuild. Full write-up: [docs/app-updates.md](docs/app-updates.md); code in [files/spark-apps](files/spark-apps).

**Decisions and why**
- **Pilot: Spark Calc, Clock, Edit, Emoji, Notes, Space.** User-space only, no root helper, easy to roll back. Spark Update, Files, Terminal and anything with a daemon or pkexec helper stay image-only until the mechanism has run for a while.
- **Root code always comes from the image.** Live bundles hold the app's own files only. Each app has an integer `system_api`; a live bundle runs only if it equals the image's number, so a change to system parts (bump the number) falls back to the built-in copy until the image catches up.
- **One signed index, not one signature per bundle.** Serial that only goes up, issue date, 30 day expiry, a weekly re-sign. This stops rollback and freeze attacks; a bad bundle can't be swapped in because the index pins each sha256 and size.
- **Reuse the image's cosign key.** One key to guard, already baked into the image; a leaked key already controls the whole OS, so app updates add no new power. A separate key stays possible (the client reads one file).
- **GitHub Releases as the host** (tags `app-<slug>-<version>` and `apps-index`), HTTPS only, no new server.
- **Built-in copy stays in the image** as the fallback and the first-boot version.

**What still needs an image update:** new packages, root helpers, units, polkit and udev rules, menu entries and icons, launcher changes, and the first install of this mechanism. Bump `system_api` with any of them.

**Rollback:** Spark Update's App updates page (built-in, live, previous) or the `spark-apps-now@` units. The previous live version is kept.

**Trust chain:** `SIGNING_SECRET` signs the index (`cosign sign-blob`) -> `cosign.pub` baked into the image checks it with openssl on the PC -> the signed index pins each bundle's sha256 and size.

**Failure modes:** offline or a bad or expired index changes nothing; a damaged live copy fails the launcher checks and the built-in runs. Table in the doc.

**Not proven yet:** `cosign sign-blob` flags, systemd and polkit on a booted SparkOS, the image build with the new step, a first real release. Nothing is released until the owner sets `SIGNING_SECRET` and runs the `app-updates` workflow once.

## Risks, plainly
- **Kernel anti-cheat games** won't run, including League of Legends and Teamfight Tactics (Riot Vanguard) and GTA Online. Windows stays for those, on a small partition or as a VM.
- **Windows-only device tools:** 8BitDo firmware updates for models fwupd does not support (Spark Controller's Pads tab updates the ones it does, and says which) and Focusrite's own app. The devices themselves work, and replacements are listed in the switching guide.
- **Microsoft Office desktop and Adobe apps** don't run. FreeSuite and the web versions do.
- **GPU-heavy gaming can't be tested in a VM.** Real performance testing happens in Phase 5.
- **Dependence on Fedora, RPM Fusion and Terra.** Fedora does the hard parts; RPM Fusion supplies full video codecs and Terra two small packages. SparkOS now owns the gaming layer Bazzite used to provide, so keeping the kernel modules building on new kernels is SparkOS's job.
- **Battle.net** occasionally breaks for a few days after a client update.
