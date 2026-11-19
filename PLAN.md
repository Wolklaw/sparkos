# SparkOS plan

SparkOS is a custom Linux image for gaming and everyday work. It is built on **Bazzite** (Fedora Atomic + Universal Blue) using **BlueBuild**: a short recipe file in a GitHub repo, which GitHub Actions turns into a signed OS image on every change and again each day when upstream updates.

We don't maintain a kernel, drivers or the gaming stack. Bazzite handles those. SparkOS adds the apps, defaults and branding.

## Status (2026-11-19)
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
   - **Androidbox: not in the image, but ready to install.** SparkOS ships what its Linux installer needs: `python3.13`, because Qt for Python has no packages for Fedora 45's Python 3.15, plus the Qt, SDL and emulator libraries. You install it for your user, with no root, from the latest release (see the switching guide). The boot test does exactly that on every build and starts it.
   - **ONLYOFFICE stays installed but isn't the default.** FreeSuite reads the old binary formats only partly: no pictures or formatting from .doc, only text from .ppt, and no charts or merged cells from .xls. ONLYOFFICE is under "Open with" for those files. Remove it whenever you like.
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
- Create the repo from the BlueBuild template, generate a cosign signing key, and store it as the `SIGNING_SECRET` repo secret.
- **Done when:** the first CI build goes green and the image shows up in GHCR.

### Phase 1: Minimal image (one evening)
- `recipes/recipe.yml`: base Bazzite, with the image name and description set to SparkOS.
- Add the launchers as Flatpaks: Heroic (Epic + GOG + Amazon), and Battle.net through Lutris (already in Bazzite).
- Add the office suite (FreeSuite) and Soot.
- In the VM: install the stock Bazzite ISO, then `rpm-ostree rebase` onto `ghcr.io/wolklaw/sparkos:latest`.
- **Done when:** the VM boots SparkOS, `/etc/os-release` reports it, and the apps open.

### Phase 2: Defaults and first boot (a few evenings)
- A first-boot setup script: choose a games drive, sign in to launchers, pick an office suite.
- Custom `ujust` commands, for example `ujust sparkos-update` and `ujust sparkos-games-drive`.
- Sensible defaults: Steam Proton enabled for all titles, MangoHud preset, power profile, Flatpak permissions.
- **Done when:** a fresh install gets from login to a playable Steam game and an open document with no terminal use.

### Phase 3: Branding (a few evenings, in the house style)
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
- **Every app is inside:** at ISO build time, Bazzite's first-boot apps and every system Flatpak in the recipe are installed from Flathub at their latest versions. They're copied onto the new system during install, so first start needs no download.
- After install, the system follows signed SparkOS updates (`bootc switch --enforce-container-sigpolicy`).
- **Published** to the `installer` release in parts under 2 GiB (GitHub's limit per file), with `join-iso.cmd` and `join-iso.sh`, which join the parts and check the SHA-256.
- **CI checks:** every app is in the installer image, and the ISO boots in QEMU (screenshots kept for 7 days).
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
- When Bazzite changes something, it's usually a one-line recipe fix.

## Risks, plainly
- **Kernel anti-cheat games** won't run, including League of Legends and Teamfight Tactics (Riot Vanguard) and GTA Online. Windows stays for those, on a small partition or as a VM.
- **Windows-only device tools:** 8BitDo firmware updates and Focusrite's own app. The devices themselves work, and replacements are listed in the switching guide.
- **Microsoft Office desktop and Adobe apps** don't run. FreeSuite, ONLYOFFICE and the web versions do.
- **GPU-heavy gaming can't be tested in a VM.** Real performance testing happens in Phase 5.
- **Dependence on Bazzite and Universal Blue.** That dependence is the point: they do the hard parts. If they stopped, the recipe could be moved to plain Fedora Atomic.
- **Battle.net** occasionally breaks for a few days after a client update.
