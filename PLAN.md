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
   - **Soot 0.2.0: in the image** (`files/scripts/soot.sh`, pinned to commit `24150cf`). It installs to `/usr/lib/soot` and is the default browser.
   - **FreeSuite 0.4.0: in the image** (`files/scripts/freesuite.sh`, pinned by SHA-256). It installs to `/usr/lib/opt/freesuite`, because `/opt` is in `/var` on Fedora Atomic. It's the default for mail, calendar, .docx/.xlsx/.csv/.pptx and PDF.
   - **ONLYOFFICE stays** for .doc, .xls, .ppt and OpenDocument files, which FreeSuite doesn't open. Remove it whenever you like.
   - **To update either app:** bump the version and commit (or SHA-256) in its script.
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
- Add the office suite (ONLYOFFICE for now) and Soot once its Linux build is merged.
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

### Phase 4: Own installer ISO (one or two evenings)
- A GitHub Actions job builds a SparkOS ISO from the image (BlueBuild ISO / bootc-image-builder), so installs no longer start from the Bazzite ISO.
- **Done when:** a clean VM installs straight from the SparkOS ISO.

### Phase 5: Real hardware and your games (ongoing)
- Uninstall the Windows games on E:, back up `Personal Projects`, shrink E:, and install SparkOS into the freed space (see decision 3). At startup, choose SparkOS or Windows from the boot menu.
- Reinstall the games inside SparkOS, onto its own partition. If Secure Boot is on, enroll the Universal Blue key once, using the steps Bazzite provides.
- Go through your library with ProtonDB and Are We Anti-Cheat Yet, and keep a list in `docs/games.md`.
- **Done when:** your daily games and work apps run, and anything blocked is known and handled through Windows.

### Phase 6: Upkeep (minutes a week)
- CI rebuilds daily against the latest Bazzite. Updates are atomic, and a bad update rolls back from the boot menu.
- When Bazzite changes something, it's usually a one-line recipe fix.

## Risks, plainly
- **Kernel anti-cheat games** (Valorant, Fortnite, CoD, and others) won't run. Windows stays for those.
- **Microsoft Office desktop and Adobe apps** don't run. ONLYOFFICE, LibreOffice and the web versions do.
- **GPU-heavy gaming can't be tested in a VM.** Real performance testing happens in Phase 5.
- **Dependence on Bazzite and Universal Blue.** That dependence is the point: they do the hard parts. If they stopped, the recipe could be moved to plain Fedora Atomic.
- **Battle.net** occasionally breaks for a few days after a client update.
