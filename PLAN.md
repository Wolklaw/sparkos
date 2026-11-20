# SparkOS plan

SparkOS is a custom Linux image for gaming and everyday work. It is built on **Bazzite** (Fedora Atomic + Universal Blue) from SparkOS's own **Containerfile** (BlueBuild until 2026-11-20; see [docs/building.md](docs/building.md)), which GitHub Actions turns into a signed OS image on every change and again each day when upstream updates.

We don't maintain a kernel, drivers or the gaming stack. Bazzite handles those. SparkOS adds the apps, defaults and branding.

## Status (2026-11-20)
- **Phase 0: done.** Repo `Wolklaw/sparkos` is public, the cosign key is in `SIGNING_SECRET` (a local copy is in the git-ignored `cosign.key`), and the first CI build passed in about 5 minutes. `ghcr.io/wolklaw/sparkos:latest` is public, and its signature verifies against `cosign.pub`.
- **Phase 1: done in CI.** The boot-test workflow boots every build in QEMU/KVM on GitHub. Local VirtualBox testing on this PC froze because Windows' Memory Integrity holds the CPU's virtualization. [docs/vm-test.md](docs/vm-test.md) stays as the manual path for a PC without that.
- Renamed from WolkOS to SparkOS on 2026-11-19: the repo is now `Wolklaw/sparkos` (GitHub redirects the old URL) and the image is `ghcr.io/wolklaw/sparkos`. The old `ghcr.io/wolklaw/wolkos` image is no longer updated. The local folder is still named `WolkOS`.
- Note: only the visible name changes to SparkOS. `ID=bazzite` and Bazzite's `image-info.json` stay as they are, because Bazzite's own tools read them. Bazzite's rollback helper therefore offers stock Bazzite images, which is a fine way out if SparkOS ever breaks.

## Starting point (checked on this PC, 2026-11-19)

| | Found | What it means |
|---|---|---|
| GPU | AMD Radeon RX 6800 XT | Best case for Linux. Open drivers come in the kernel, so no NVIDIA variant is needed. |
| CPU / RAM | Ryzen 7 7800X3D, 32 GB | No constraints. |
| Disks | C: 1 TB NVMe (Windows, 196 GB free), E: 1 TB NVMe "Games" (289 GB free), D: 250 GB SATA "Scrap" (downloads, temp: stays as is) | No spare drive. SparkOS needs either a new SSD or space taken from E:. |
| Board | ASUS PRIME X670-P WIFI | Should have three M.2 slots, two of them in use. Confirm in the manual before buying a drive. |
| Tools | git, gh (logged in), no WSL, no VM software | Images build on GitHub Actions, so nothing has to be installed locally for builds. A VM app is needed for testing. |

## Decisions (defaults I'd pick)

1. **Base image:** `ghcr.io/ublue-os/bazzite:stable` (KDE Plasma, AMD/Intel). It already includes Steam, gamescope, Lutris and current Mesa.
2. **Your own apps ship preinstalled:** **Soot** as the browser and **FreeSuite** as the office suite (mail, documents, sheets, slides, PDF). Both are Windows-only today, so each needs a Linux build first:
   - **Soot: in the image, always the latest release** (`files/scripts/soot.sh`). It installs to `/usr/lib/soot` and is the default browser. The installed release is recorded in `/usr/lib/soot/SOOT_RELEASE`.
   - **FreeSuite: in the image** (`files/scripts/freesuite.sh`, always the latest release, checked against that release's SHA256SUMS). It installs to `/usr/lib/opt/freesuite`, because `/opt` is in `/var` on Fedora Atomic. It's the default for mail, calendar, PDF and every Office format it opens, including .doc/.xls/.ppt, OpenDocument and RTF.
   - **Spark Snip 1.0.0: in the image**, built from this repo (`files/spark-snip`, installed by `files/scripts/spark-snip.sh`). It's the screenshot, OCR and screen recording tool and takes Print, Meta+Shift+S/T/R from Spectacle, which stays installed because Spark Snip reads the screen through it. It grew out of QuickOCR, whose Windows app is finished.
   - **Spark Media 1.0.0: in the image**, built from this repo (`files/spark-media`, installed by `files/scripts/spark-media.sh`). It opens photos, videos and music and is the default for all three, so a fresh SparkOS needs no extra app for them. Photos through Pillow (HEIC with pillow-heif), playback through GStreamer with FFmpeg's decoders; the build fails if H.264, H.265, AAC or MP3 can't play.
   - **Spark Welcome, Spark Games, Spark Monitor 1.0: in the image (owner's decision, 2026-11-20)**, built by separate sessions from [briefs/](briefs/README.md) and merged in PRs #3 to #5. Welcome opens once at first login; Games gathers Steam, Heroic and Lutris libraries; Monitor is the Ctrl+Shift+Esc task manager. The boot test runs each one's self-test in the real image. Later Spark apps are optional, through a future Spark Portal.
   - **Androidbox: not in the image, but ready to install.** SparkOS ships what its Linux installer needs: `python3.13`, because Qt for Python has no packages for Fedora 45's Python 3.15, plus the Qt, SDL and emulator libraries. You install it for your user, with no root, from the latest release (see the switching guide). The boot test does exactly that on every build and starts it.
   - **Androidbox compatibility: parked (2026-11-20).** The owner will finish it later. The boot test no longer installs Androidbox as a user (that check was slow and kept failing). `python3.13` and the Qt/SDL libraries stay in the image, ready for when it's picked up.
   - **App policy (2026-11-20):** SparkOS ships only the owner's own apps: Soot, FreeSuite and the Spark apps (Snip, Media, Welcome, Games, Monitor, Edit, Calc, Archive, Scan, Run, Link, Store, Update). Every other company's or project's app is removed, Bazzite's included (Steam, Lutris, Waydroid, Firefox and its other first-boot apps, Kate/KWrite, Filelight, the Portal), and is installable from the Store. ONLYOFFICE is gone too: old .doc/.xls/.ppt open in FreeSuite, which reads them partly. The platform stays: Plasma, Dolphin, Konsole, Spectacle, System Settings, Ark, KDE Connect and the Store.
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
  - **Boot splash:** the bot, the spaced-out wordmark and a thin progress line.
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
- **Published** to the `installer` release in parts under 2 GiB (GitHub's limit per file), with `join-iso.cmd` and `join-iso.sh`, which join the parts and check the SHA-256.
- **CI checks:** the installer builds and the ISO boots in QEMU (screenshots kept for 7 days). It carries no third-party apps.
- **Not yet tested:** a full install from the ISO, in a VM or on hardware.
- **Done when:** a clean VM installs from the SparkOS ISO and first boots with all apps present.

### Phase 5: Real hardware and your games (ongoing)
- Uninstall the Windows games on E:, back up `Personal Projects`, shrink E:, and install SparkOS into the freed space (see decision 3). At startup, choose SparkOS or Windows from the boot menu.
- Reinstall the games inside SparkOS, onto its own partition. If Secure Boot is on, enroll the Universal Blue key once, using the steps Bazzite provides.
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
- CI rebuilds daily against the latest Bazzite. Updates are atomic, and a bad update rolls back from the boot menu.
- When Bazzite changes something, it's usually a one-line fix in the Containerfile or a build script.

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
| Bazzite/ublue update tools (`ujust`, their update service and rollback helper) | **Spark Update**: "SparkOS updated, restart?", what changed, one-click rollback | **Done 2026-11-20**: Spark Update downloads and stages updates itself (the boot test had it stage and start a real update); `uupd` and the Bazzite Updater are removed, and `ujust update` runs Spark Update. `ujust` itself stays until the Fedora move (Bazzite's own tools call it) |
| Homebrew's daily update timers, Universal Blue's akmods repository | Homebrew quiet until `sparkos-dev-setup --brew`; the repository off | **Done 2026-11-20** |

**Release 3: bigger moves**
| Today | SparkOS's own | Status |
|---|---|---|
| Bazaar, the store | **Spark Store**: SparkOS's own store over Flathub, with the Spark apps in it (the Spark Portal idea) | Brief: [spark-store](briefs/spark-store.md) |
| Bazzite as the base, and Universal Blue's tooling | Build on Fedora's own atomic KDE image with SparkOS's own gaming layer (Mesa, gamescope, MangoHud, kernel settings) | Prototype merged as a separate image, `sparkos-fedora` ([#16](https://github.com/Wolklaw/sparkos/pull/16)): it builds and boots, and 19 of 22 checks pass (missing: H.265, Bazaar, Homebrew). Results in [docs/fedora-base.md](docs/fedora-base.md) |
| BlueBuild | A plain Containerfile and SparkOS's scripts | **Done 2026-11-20**: the real build uses SparkOS's own Containerfile ([#15](https://github.com/Wolklaw/sparkos/pull/15), [docs/building.md](docs/building.md)) |
| Bottles, fetched to open `.exe` files | Spark Run, on Wine/Proton | In the first release ([#17](https://github.com/Wolklaw/sparkos/pull/17)). The Wine it downloads is now built by SparkOS's own CI from WineHQ's signed source (release [wine-11.22-2](https://github.com/Wolklaw/sparkos/releases/tag/wine-11.22-2), reproducible), no longer Kron4ek's build |
| Ark | Spark Archive | Brief: [spark-archive](briefs/spark-archive.md) |
| KDE Connect | Spark Link: the PC side in SparkOS, the phone side in Soot's Android app, no outside service | Briefs: [spark-link](briefs/spark-link.md), [protocol](docs/spark-link-protocol.md) |

**New Spark tools for gaps (no app at all today):** Spark Edit, a light text and code editor ([brief](briefs/spark-edit.md)); Spark Calc ([brief](briefs/spark-calc.md)); Spark Scan, for the Canon scanner ([brief](briefs/spark-scan.md)).

**Kept on purpose:** the Linux kernel, Mesa, KDE Plasma, Wine/Proton, Soot's Firefox engine and FreeSuite's Chromium/Electron, Flathub as the source of other people's apps, Dolphin and Konsole, Sigstore signing and LVFS firmware updates. GitHub and GHCR stay for code, builds and downloads; a mirror on SparkOS's own server is the cheap insurance later.

## Risks, plainly
- **Kernel anti-cheat games** won't run, including League of Legends and Teamfight Tactics (Riot Vanguard) and GTA Online. Windows stays for those, on a small partition or as a VM.
- **Windows-only device tools:** 8BitDo firmware updates and Focusrite's own app. The devices themselves work, and replacements are listed in the switching guide.
- **Microsoft Office desktop and Adobe apps** don't run. FreeSuite and the web versions do.
- **GPU-heavy gaming can't be tested in a VM.** Real performance testing happens in Phase 5.
- **Dependence on Bazzite and Universal Blue.** They do the hard parts today. The independence roadmap moves SparkOS to plain Fedora Atomic in Release 3, which also covers the case where they stop.
- **Battle.net** occasionally breaks for a few days after a client update.
