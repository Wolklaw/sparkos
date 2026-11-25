# SparkOS on Fedora Kinoite

**Since 2026-11-23, SparkOS is built only on Fedora Kinoite 45.** The Bazzite build is gone:
one image, `ghcr.io/wolklaw/sparkos`, from the [Containerfile](../Containerfile)
([building.md](building.md)). The test image `ghcr.io/wolklaw/sparkos-fedora` is no longer built;
PCs that followed it move to `ghcr.io/wolklaw/sparkos` (Spark Update still recognises the old name
until they do). The scripts that were Fedora-only took the plain names: `fedora-identity.sh` is now
`sparkos-identity.sh` and `fedora-apps.sh` is now `sparkos-apps.sh`.

## On the real PC (2026-11-23)

The owner's PC (Radeon RX 6800 XT, Ryzen 7 7800X3D, dual boot with Windows 11, Secure Boot off)
ran the Fedora image, kernel 7.3.4-300.fc45, compared with its last Bazzite boot (kernel 7.3.4-ogc10.1):

| | Bazzite | Fedora |
|---|---|---|
| Failed system or user units | none | none |
| Boot, userspace (`systemd-analyze`) | 12.5 s | 9.1 s (14.8 s on the first boot, which built the man page index once) |
| Errors in the boot log | UDisks2, Avahi and BlueZ activation errors, plus Bluetooth L2CAP | Bluetooth L2CAP only (the same on both) |
| GPU video (`vainfo`, Mesa 26.2.7 radeonsi) | not measured that day | H.264, HEVC and HEVC Main10 decode and encode, VP9 and AV1 decode. A real H.265 file decoded with GStreamer's `vah265dec`, and FFmpeg decoded and encoded HEVC on the GPU |
| Vulkan (RADV), OpenGL (radeonsi), `vkcube` with MangoHud | worked in daily use | works |
| Kernel modules | Universal Blue's | SparkOS's own, all loaded: zenergy (CPU power reads), ryzen_smu, v4l2loopback, vhba, hid_fanatec, hid_logitech_new, hid_tmff_new, ntsync, uinput |
| Device rules (not-a-joystick list, OpenRGB, Steam Input, SteamVR, vhba, Fanatec) | from Bazzite's packages | there |
| Audio (USB DAC, USB mic, webcam mic, HDMI), wired network, Flatpak Steam, Heroic, Lutris, Discord | worked in daily use | work |
| Self-tests of the 15 Spark apps (Snip, Media with H.264, H.265, AAC and MP3, Welcome, Games, Monitor, Files, Edit, Calc, Archive, Scan, Run, Link, Store, Terminal, Update) | not run that day | pass |

Two things seen on Fedora that weren't on Bazzite, neither a regression:

- **GameMode** (`gamemoded -t`) passes everything except switching the CPU governor, which stays
  on powersave when run from a terminal. Bazzite had no GameMode at all. Not yet looked into.
- **Secure Boot.** Fedora's kernel is signed by Fedora, so Secure Boot needs no key enrollment and
  the installer no longer asks for one. The kernel modules SparkOS builds aren't signed yet: with
  Secure Boot on they don't load until their key is enrolled (the system still boots). The image
  build signs them when it has the key; `spark secureboot enroll` does the enrollment. See
  [Secure Boot](#kernel-modules) under Kernel modules.

The rest of this page is the prototype record from before the switch, kept as it was written; file
names in it are the old ones.

## Prototype results (2026-11-20 to 2026-11-22)

**Since 2026-11-22 it's built from the same Containerfile as SparkOS** (see
[building.md](building.md)), every time main's image builds and
every day, and booted with the same boot test. Before that it had its own BlueBuild recipe and its
own copy of the checks, which fell behind main (it missed the icon theme, the Caps Lock fix, the new
boot splash and the sign-in screen change). Two of the gaps below are fixed by that change:
**H.265** (RPM Fusion free's FFmpeg and Mesa video decode are now in the image) and **Spark
Update's image name** (it knows `sparkos-fedora`). Bazzite's device rules (controllers, RGB,
wheels, ntsync) were added the same day; see [Device rules](#device-rules). Also since then, **`ujust`** is replaced by
SparkOS's own `spark` command and **Homebrew** installs with `spark brew` ([spark-cli.md](spark-cli.md)).
The measurements below are from the prototype
runs of 2026-11-20 and haven't been redone.

**Closed after that (2026-11-22), not yet measured in a built image:**

- **Homebrew in the shell.** A PC that moves from Bazzite keeps its Homebrew (`/home` is a link
  to `/var/home`, which an image change keeps) but would lose Bazzite's shell setup, which no
  package owns. [files/scripts/fedora-homebrew.sh](../files/scripts/fedora-homebrew.sh) installs
  SparkOS's own: `/etc/profile.d/brew.sh` (PATH with Homebrew last, MANPATH, INFOPATH, zsh
  completion), `/etc/profile.d/brew-bash-completion.sh` and fish's `sparkos-brew.fish`
  (sources in [files/homebrew](../files/homebrew)). They keep Bazzite's names so they replace its
  copies, and do nothing without Homebrew. Homebrew itself isn't in the image: on a new install
  `sparkos-dev-setup --brew` points to Homebrew's installer. Since 2026-11-23 Homebrew's update
  timers are there too, under Bazzite's names (`brew-update.timer`, `brew-upgrade.timer`), off
  until `sparkos-dev-setup --brew`; a PC that had them on under Bazzite keeps them on.
- **Tools Bazzite had:** `distrobox`, `btop`, `lm_sensors`, `tmux`, `fzf`, `cabextract` from
  Fedora (67 packages with their dependencies, +37 MiB), and **`umu-run`** for Spark Games'
  Windows games: `umu-launcher` isn't in Fedora, so it comes from Terra for that one package
  (Terra's key checked by fingerprint, the repository not left on the system).
- **Store wording:** `sparkos-open-package` and the docs say Spark Store, not "the Store
  (Bazaar)". The Bazaar fallback stays for the Bazzite base.

Measured on 2026-11-20 with Kinoite 45, Bazzite `stable` (F45.20261117) and
`ghcr.io/wolklaw/sparkos:latest` built from main at 53f54a8, which has all 13 Spark apps and the
Release 2 cleanup. Both images were rebuilt and measured in the afternoon (run 4); the morning runs
(1 to 3, before main's new apps) found the same gaps. Every number below comes from a CI run
listed at the end.

**Short answer:** SparkOS runs on plain Fedora. All 13 Spark apps, Soot and FreeSuite, the look,
the sign-in, signed updates, Spark Update and the gaming tools work. The image is about 1.2 GB
smaller to download and 3.8 GB smaller on disk. One thing SparkOS requires today doesn't work with Fedora's own packages: **H.265 video**
(and H.264/H.265 decoding on the GPU). H.264, AAC and MP3 decode with Fedora's own packages plus
Cisco's OpenH264. Fixing H.265 takes one outside package source (RPM Fusion: one 16 MiB swap,
measured), a smaller tie than the five or so Bazzite brings. Details and the
recommendation are at the end.

## What was built

The same [Containerfile](../Containerfile) as SparkOS, with `SPARKOS_BASE=fedora` (until 2026-11-22
a separate BlueBuild recipe, `recipes/recipe-fedora.yml`). What differs from the Bazzite build:

| File | What it does |
|---|---|
| [build_files/packages.sh](../build_files/packages.sh) | On Fedora: what Bazzite brought that SparkOS uses (printing, scanning, ImageMagick, gamescope, MangoHud, GameMode), RPM Fusion free's FFmpeg and `mesa-va-drivers-freeworld`, and Cisco's real OpenH264 in place of Kinoite's empty `noopenh264` stand-in. Then the same list as on Bazzite. |
| [files/scripts/fedora-identity.sh](../files/scripts/fedora-identity.sh) | "SparkOS" as the system name and boot entry. Replaces `sparkos-identity.sh`, which checks for `ID=bazzite`. |
| [files/scripts/fedora-apps.sh](../files/scripts/fedora-apps.sh) | The app policy on Kinoite: removes Firefox, KWrite, Filelight and the other apps Kinoite installs as RPMs, Spectacle and Plasma System Monitor (as on Bazzite), plus Fedora's first-boot wizard, crash reporter and third-party repository switch. Replaces `sparkos-apps.sh`, which empties Bazzite's lists. |
| [files/scripts/fedora-gaming.sh](../files/scripts/fedora-gaming.sh) | The device rules Fedora doesn't package, from [files/device-rules](../files/device-rules) (see [Device rules](#device-rules)), `uinput` at boot, and Bazzite's gaming kernel settings. |
| [files/scripts/fedora-homebrew.sh](../files/scripts/fedora-homebrew.sh) | Homebrew on PATH and its completion in bash, zsh and fish, when Homebrew is installed (on Bazzite, Universal Blue's files do this). |
| [build_files/signing.sh](../build_files/signing.sh) | Shared. On Fedora it also writes `20-sparkos.toml`, the install setting that makes a fresh install check signatures (Bazzite has its own). |
| [.github/workflows/build-fedora.yml](../.github/workflows/build-fedora.yml) | Runs build.yml with `base: fedora`, then boot-test.yml on the result. By hand, with "compare", it also compares the three images, looks inside the built image, and boots both images twice to compare boot time. |

## Size

| | Fedora Kinoite 45 | Bazzite stable | SparkOS (Bazzite) | SparkOS on Fedora |
|---|---|---|---|---|
| Download (compressed, amd64) | 3.32 GB | 4.45 GB | 5.43 GB | **4.25 GB** |
| On disk (uncompressed image) | 7.34 GB | 11.00 GB | 13.18 GB | **9.41 GB** |
| `/usr` | 6,810 MB | 10,760 MB | 11,621 MB | **7,500 MB** |
| RPM packages | 1,736 | 2,408 (+237 more, mostly 32-bit library copies) | 2,397 (+237 more, mostly 32-bit library copies) | **1,744** |
| Kernel | 7.3.4-300.fc45 (Fedora) | 7.3.4-ogc8.1 (OGC) | 7.3.4-ogc8.1 (OGC) | 7.3.4-300.fc45 (Fedora) |

SparkOS's own layer costs about the same on either base (+1 GB download). The difference is the
base: Bazzite adds 714 packages and 2.7 GB (installed size) on top of Kinoite. Main's eight new
Spark apps changed neither image's size much: they reuse what Spark Snip and Spark Media already
pull in, and Spectacle and Plasma System Monitor went out at the same time.

## Boot and idle

| Test VM, run 4, one boot each | SparkOS (Bazzite, 53f54a8) | SparkOS on Fedora |
|---|---|---|
| First power-on until SSH answers | 122 s (includes an automatic restart at 92 s by `bazzite-hardware-setup`) | **21 s** (no reboot) |
| First boot, `systemd-analyze` | 18.8 s (the boot after that restart) | 19.4 s, of which 8.7 s is a one-time man-page index (`fedora-atomic-desktop-mandb-update`) |
| Later boot, `systemd-analyze` | 12.5 s (1.0 kernel + 2.6 initrd + 8.9 userspace) | **9.5 s** (0.9 kernel + 2.5 initrd + 6.1 userspace) |
| Reboot until SSH answers | 26 s | 16 s |
| Memory used at the sign-in screen, later boot | 1,174 MB | **1,127 MB** |
| Running services | 32 | 32 |
| Space used after install (`/sysroot`) | 14 GB | **6.5 GB** |
| Test disk image (qcow2) | 6.49 GB | **4.75 GB** |

The real boot test (`boot-test.yml`, run 44731730758 on 53f54a8) measures SparkOS after its
checks, on the boot after Bazzite's automatic reboot: **14.2 s** (1.0 + 2.5 + 10.7), **1,241 MB**
used, 34 services. The prototype's `boot` job measures at the same point, on its first and only
boot: 18.7 s, of which 8.2 s is the one-time man-page index, and **1,203 MB** used.

In run 4 the prototype's later boot was 3.0 s faster and its reboot 10 s faster. In run 2 (before
main's new apps) it was the other way round: 2.1 s slower to boot and 11 s slower to reboot. With
one sample per image per run, the two boot in about the same time once first-boot work is done.
What differs every time is the first power-on: Bazzite's hardware setup restarts the PC once (at
57 s in run 2, 92 s in run 4), and Fedora doesn't.

These are test-VM numbers (QEMU on a GitHub runner, 4 cores, 8 GB, no GPU), not the 7800X3D's.
They compare the two images under the same conditions.

## The same checks as the real boot test

From the `boot` job (run 4), the same checks as `boot-test.yml` on 53f54a8, adapted where they
name Bazzite things. 19 pass and 3 fail, the same three as in the morning runs. Since 2026-11-22
the image runs `boot-test.yml` itself; it skips only the checks about Bazzite's own parts (`ujust`,
Bazaar) and expects `.flatpakref` files to open in Spark Store.

| Check | Result |
|---|---|
| System name, signing policy | pass |
| Updates signature-checked (`ostree-image-signed:docker://ghcr.io/wolklaw/sparkos-fedora`) | pass (failed in run 1, before `20-sparkos.toml`) |
| Soot and FreeSuite, Soot's smoke test, default apps | pass |
| Printing, scanning, devices | pass |
| Startup sound | pass |
| Claude Code installed and runs | pass |
| Spark Snip self-test (OCR, H.264 and VP8 recording), its shortcuts, Spectacle gone | pass |
| Spark Snip captures the desktop through KWin in a signed-in Plasma session | pass (136 ms, 1280x800) |
| Spark Welcome, Games, Monitor self-tests | pass |
| Spark Edit, Calc, Archive, Scan, Run, Link and Store self-tests; Dolphin's Extract/Compress; text and archives open in Spark Edit and Spark Archive | pass |
| Spark Update | pass, with one expected warning: Fedora has no `uupd`, so `spark-update.sh` switched to Spark Update's own timer (enabled, active; the notification timer is on for every user). Its self-test fails only on the image name: Spark Update has `ghcr.io/wolklaw/sparkos` built in and this test image is `sparkos-fedora`. That goes away if the real image switches base and keeps its name. |
| Release 2 cleanup: Plasma System Monitor gone and its keys on Spark Monitor; no Tailscale; usage counting off; KDE's Get New Stuff hidden | pass |
| AppImages: added to the menu, run through FUSE, removed; the double-click questions | pass |
| Spark Media with H.264, H.265, AAC, MP3 | **fail: no H.265 decoder.** H.264, AAC, MP3 decode for real |
| No third-party apps; only Flathub configured; all 15 SparkOS apps present | pass |
| Gaming layer (uinput, Steam rules, sysctls, gamescope, MangoHud, GameMode) | pass |
| Installing apps the Windows way: `.exe`/`.msi` to Spark Run, AppImage, `.rpm` and `.deb` to `sparkos-open-package` | pass. `.flatpakref` opens in **Spark Store** here, because Bazaar (the default `sparkos-defaults.sh` sets) isn't installed |
| SparkOS look, sign-in screen, desktop layout (screenshots) | pass |
| The Store (Bazaar) | **fail: not in Fedora.** Spark Store and Discover are installed. Since 2026-11-22 Spark Store is the store on both bases; the boot test checks it on Fedora |
| Homebrew for `sparkos-dev-setup --brew` | **fail: not set up.** Since 2026-11-22 the shell setup is in the image (see the top); Homebrew itself is installed with Homebrew's installer |

## What Bazzite adds that SparkOS relies on

Bazzite starts from Kinoite too. Over Kinoite it adds 714 packages: 567 are Fedora's own
(1,956 MiB: LLVM and ROCm libraries, GCC, WebKit, CJK fonts, Oxygen themes, Kate, Lutris, fish and so on), and 147
come from other sources. It also replaces 16 of Fedora's packages with other builds. Where they
come from (from `rpm -qa` vendor fields in the images):

| Source | Packages | What |
|---|---|---|
| Terra (Fyra Labs' repository) | 60 | Mesa (replaces Fedora's), gamescope, MangoHud, Steam, Universal Blue's updater `uupd`, controller rules (`game-devices-udev`), wheel and fan drivers, BlueZ, WirePlumber, Xwayland |
| negativo17.org | 34 | Full FFmpeg (replaces Fedora's `ffmpeg-free`), H.264/H.265 libraries (x264, x265, libde265, OpenH264), Intel media drivers |
| Universal Blue (COPR, packages, akmods) | 15 + 5 + 20 | Bazaar, ujust, signing keys, media automount, Steam Deck presets, 20 out-of-tree kernel modules (xone, openrazer, v4l2loopback, ...) |
| Open Gaming Collective | kernel | `7.3.4-ogc8.1` (replaces Fedora's `7.3.4-300`) |
| RPM Fusion, other COPRs, Tailscale, Sigstore | 9 | broadcom-wl, v4l2loopback, nerd-fonts, system76, kvmfr, vhba, Tailscale, cosign |

And it runs its own services: `bazzite-hardware-setup` (kernel arguments per device, mostly for
handhelds and Framework laptops; the general ones it checks are `amdgpu.ppfeaturemask`, an AMD
IOMMU setting, Bluetooth's `disable_ertm` and `tsc=directsync`. It changed kernel arguments on the
test VM and **rebooted it once on first boot**, at 57 s), `bazzite-flatpak-manager` (Flathub on, Fedora's Flatpak
remote off, Flatpak overrides for themes and controllers), `bazzite-user-setup` (per-device user
fixes, template files), `uupd` (updates, daily at 04:00), `brew-setup` (Homebrew).

### Piece by piece

| Piece | On SparkOS today (Bazzite) | On the prototype (Fedora) | What it costs to own | Whose packages it still needs |
|---|---|---|---|---|
| **Kernel** | OGC kernel 7.3.4, signed with Universal Blue's key (Secure Boot needs the key enrolled once) | Fedora's 7.3.4, signed by Fedora: Secure Boot works with no enrollment | Nothing. Same upstream version. The RX 6800 XT and 7800X3D are fully supported by stock kernels. | Fedora |
| **Out-of-tree kernel modules** | 20 from Universal Blue's akmods, prebuilt for the OGC kernel (xone, zenergy, ryzen_smu, v4l2loopback, the wheel drivers, vhba, kvmfr, openrazer, ...) | Built by SparkOS while the image builds: zenergy, ryzen_smu, v4l2loopback, xone, hid-fanatecff, new-lg4ff, hid-tmff2 and vhba (see [Kernel modules](#kernel-modules)). xpad, hid-playstation, hid-nintendo and hid-steam are in Fedora's kernel. | About 1 to 2 minutes per build, and 254 MB of kernel-devel in a build stage that isn't kept. A source pin to bump when a module breaks on a new kernel. Signing for Secure Boot (a key in a GitHub secret, one enrollment per PC). | The modules' own projects (pinned sources), RPM Fusion's akmod-v4l2loopback, Microsoft's xone firmware |
| **Mesa (OpenGL, Vulkan)** | Terra's build of Mesa 26.2.7 | Fedora's Mesa 26.2.7, same version | Nothing for games: RADV and RadeonSI are the same code. | Fedora |
| **Hardware video decode (VA-API)** | Terra's Mesa decodes H.264 and H.265 on the GPU | Fedora builds Mesa with Mesa's default, patent-free codecs only: no H.264/H.265 on the GPU. Software decoding of H.264 still works (OpenH264). | Not measurable in the VM (no AMD GPU). RPM Fusion has a `mesa-va-drivers-freeworld` package that adds them; see the RPM Fusion results below. | RPM Fusion (or Terra) |
| **FFmpeg and codecs** | negativo17's full FFmpeg | Fedora's `ffmpeg-free` + Cisco's OpenH264 (from Fedora's `fedora-cisco-openh264` repo, swapped in for Kinoite's empty `noopenh264`). Measured by encoding and decoding: **H.264, AAC and MP3 decode; H.265 does not.** | One swap: `dnf swap ffmpeg-free ffmpeg` from RPM Fusion. Measured below. | RPM Fusion (or negativo17) |
| **gamescope, MangoHud, GameMode** | Terra's gamescope 3.17.0 and MangoHud 0.8.4; no GameMode | Fedora's gamescope 3.16.31, MangoHud 0.8.3~rc1, GameMode 1.8.2 | Nothing; Fedora's are one release behind Terra's. | Fedora |
| **Steam controller and VR rules** | `steam-devices` (Fedora's package), Valve commit 22ec85e | Fedora's `steam-devices` package, the same files (since 2026-11-22; before that fetched from Valve's repository at the same commit) | Nothing. | Fedora |
| **More device rules** | `game-devices-udev`, `udev-joystick-blacklist-rm` (Terra), `oversteer-udev` (Universal Blue), `openrgb-udev-rules`, `solaar-udev` (Fedora) | All of them since 2026-11-22; see [Device rules](#device-rules) | Small: three upstream rule sets kept in `files/device-rules`, to refresh now and then. | Fedora, and those projects' files |
| **ntsync** (Wine and Proton's NT sync driver) | `ntsync-autoload` (Fedora's package) loads it at boot | The same package since 2026-11-22; Fedora's kernel has the module (`ntsync.ko`) | Nothing. | Fedora |
| **Gaming kernel settings** | `kernel.split_lock_mitigate=0`, `vm.max_map_count=2147483642`, inotify limits | The same values in `/usr/lib/sysctl.d/70-sparkos-gaming.conf` | Nothing; 4 lines. | None |
| **Hardware setup service** | `bazzite-hardware-setup` (328 lines), which reboots the PC once on first boot | None | For a desktop AMD PC, a few kernel arguments at most (listed above); none was needed to boot and pass the checks in the VM. The rest is for handhelds and laptops SparkOS doesn't target. | None |
| **Firmware** | Fedora's `linux-firmware` (449 MB) plus a few extras | Fedora's `linux-firmware` 20261019 (438 MB), `amd-gpu-firmware`, `amd-ucode-firmware` | Nothing for this PC. | Fedora |
| **Flathub** | Bazzite's flatpak manager adds Flathub, turns Fedora's remote off, sets overrides | BlueBuild's `default-flatpaks` module adds Flathub (system and user); Kinoite 45 ships no Fedora remote in the image. Measured: only Flathub is configured. | Nothing extra. | Flathub; BlueBuild's module |
| **Signing** | BlueBuild's signing module + `sparkos-signing-fix.sh`; Bazzite's `/usr/lib/bootc/install/20-bazzite.toml` makes installs deploy as `ostree-image-signed` | The same signing module and fix, and SparkOS's own `20-sparkos.toml` with the same setting | Nothing: one file. Without it (first prototype run) the test install deployed as `ostree-unverified-registry`, which never checks signatures. | BlueBuild's module |
| **Updates** | `uupd` (Universal Blue) downloads, daily at 04:00; Spark Update adds the notification, the window and roll back | Spark Update does it all: with no `uupd` in the image, `spark-update.sh` turns on its own timer (every 6 hours, stages the new image, updates Flatpak apps). Measured: enabled and active, no other updater on. Staging a newer image, restarting into it and rolling back work (tried in a VM on 2026-11-22, see [Spark Update staging a newer image](#spark-update-staging-a-newer-image)). | Nothing new: Spark Update already ships. Its built-in image name would need changing only for a separately named image like this one. | None |
| **The Store** | Bazaar (Universal Blue COPR), with Spark Store installed next to it | Bazaar isn't available in Fedora. Spark Store is installed and `.flatpakref` files already open in it (measured); Kinoite's Discover is there too. | Done (2026-11-22): the dock, `.flatpakref` files and `sparkos-open-package` all use Spark Store. | None |
| **Homebrew** (`sparkos-dev-setup --brew`) | Bazzite ships a Homebrew tarball and a first-boot service | Not present: `sparkos-dev-setup --brew` says Homebrew isn't ready | Shell setup owned since 2026-11-22 (three small files; an existing `/var/home/linuxbrew` keeps working). `spark brew` installs Homebrew on request (Homebrew's installer pinned to one commit, SHA-256 checked). Update timers owned since 2026-11-23: SparkOS's own `brew-update`/`brew-upgrade` units with Bazzite's names and schedule, run as the user who owns Homebrew (Bazzite's run as UID 1000), off until `sparkos-dev-setup --brew`. Claude Code itself installs fine (`sparkos-dev-setup --claude` passed). | Homebrew's installer |
| **ujust, rollback helper, motd** | Universal Blue | Gone. **Since 2026-11-22 SparkOS has its own `spark` command** ([spark-cli.md](spark-cli.md)), on both bases: update, rollback, pin, kernel arguments, initramfs, boot menu, services, SSH, cleaning, logs and a bug-report bundle, Homebrew and containers. | Nothing SparkOS's own files use them. Rollback is in the boot menu either way; Spark Update covers the rest. The handheld, Nvidia/Intel and app-installer recipes aren't carried over (list in spark-cli.md). | None |
| **Fedora's first-boot wizard** | Not in Bazzite | `plasma-setup` opened "Welcome to Plasma Desktop, Begin Setup" before the SparkOS sign-in on the first test boot, though a user existed. `fedora-apps.sh` now removes it. | Nothing. | None |

### Video with RPM Fusion

Measured in a throwaway container from the prototype image (run 3):

- `dnf swap ffmpeg-free ffmpeg` with RPM Fusion's free repository: **16 MiB download, +30 MiB on
  disk**, 7 packages from RPM Fusion (ffmpeg, ffmpeg-libs, libavdevice, x264-libs, x265-libs,
  vvenc-libs, plus Fedora's vmaf-models). After it, H.264 and H.265 clips made with that ffmpeg
  **decode through GStreamer**, and Spark Media's own check (`--require h264,h265,aac,mp3`) passes.
- `mesa-va-drivers-freeworld` (GPU decoding of H.264/H.265 on AMD) installs as **one package,
  14 MiB download, +53 MiB**, with nothing removed (dry run). Whether the GPU then decodes can only
  be checked on real AMD hardware.

## Device rules

Added 2026-11-22. udev rules decide which devices the signed-in user may open without root
(controllers for Steam, RGB controllers for OpenRGB, a wheel's settings). Bazzite ships them as
eight packages; this is what the Fedora image does for each, checked against the owner's devices
(Keychron V5, Logitech G502 SE HERO, HyperX QuadCast, FiiO E10, Logitech C920, ASUS AURA and NZXT
RGB controllers, AMD GPU):

| Bazzite's package | On the Fedora image | Why |
|---|---|---|
| `steam-devices` | Fedora's package | Steam and Steam Input on controllers and VR headsets. Same Valve files as before (commit 22ec85e, same SHA-256), so the download in `fedora-gaming.sh` is gone. |
| `openrgb-udev-rules` | Fedora's package | Lists the owner's ASUS AURA (0b05:19af) and NZXT (1e71:2012) controllers, so OpenRGB works without root. |
| `solaar-udev` | Fedora's package | Logitech receivers and devices, the G502 included, for Solaar. |
| `ntsync-autoload` | Fedora's package | Loads `ntsync` at boot (Fedora's kernel has it; `/dev/ntsync` is open to all users). Wine and Proton use it for faster Windows sync. |
| `game-devices-udev` (Terra) | Copied into `files/device-rules/game-devices-udev` (1.1, MIT) | Not in Fedora or RPM Fusion. Gives Steam and browsers raw access to many controllers (8BitDo, PowerA, Hori, Nacon, PDP, Thrustmaster, ...). Its `uinput` modules file is left out (`fedora-gaming.sh` already loads it). |
| `udev-joystick-blacklist-rm` (Terra) | Copied into `files/device-rules/udev-joystick-blacklist` (public domain) | Not in Fedora or RPM Fusion. The kernel reports some keyboards and mice as joysticks; this hides those. **The owner's Keychron V5 (3434:0351) is on the list**: without it, games and Steam can see the keyboard as a controller. |
| `oversteer-udev` (Universal Blue COPR) | Only the Logitech wheel file, in `files/device-rules/oversteer` (GPL-3.0) | Not in Fedora. Lets Oversteer (Flathub) change a Logitech wheel's range and force feedback. Its Thrustmaster and Fanatec files are left out: the Fanatec driver's own rules come with it (see [Kernel modules](#kernel-modules)), and Oversteer's Thrustmaster file isn't added yet. |
| `ublue-os-media-automount-udev` | **Not added** | Not device rules: a service that mounts internal ext4 and btrfs partitions at boot. On this PC it mounts nothing (its log: every other drive is NTFS or FAT, or in fstab), and SparkOS doesn't need it. |

The copied files are unchanged from their projects; each folder's `SOURCE` says where from, at
which version and under which licence, and both go to `/usr/share/licenses/sparkos-device-rules`.
The QuadCast, E10 and C920 are standard USB audio and video devices and need no rules.

## Kernel modules

Bazzite ships about 20 kernel modules that aren't in Linux itself, prebuilt by Universal Blue for
its own kernel. Fedora's kernel has none of them. On the Fedora base, SparkOS builds the ones the
owner uses while the image builds ([build_files/kmods.sh](../build_files/kmods.sh), steps 0b and
4b of the [Containerfile](../Containerfile)). On Bazzite both steps do nothing.

| Module | What it's for | Source (pinned) | License |
|---|---|---|---|
| `zenergy` | CPU power for any user (see below) | BoukeHaarsma23/zenergy `2a40d24` | GPL-2.0 |
| `ryzen_smu` | Access to the Ryzen SMU for `ryzenadj`, `ryzen_monitor` and similar tools | amkillam/ryzen_smu `d298366` (v0.1.7) | GPL-2.0 |
| `v4l2loopback` | Virtual camera (OBS) | RPM Fusion's `akmod-v4l2loopback` 0.15.4, built with akmods | GPL-2.0 |
| `xone_*` | Xbox wireless dongle, and Xbox controllers over USB | OpenGamingCollective/xonedo `982cbcb` | GPL-2.0 |
| `hid-fanatec` | Fanatec wheels and pedals | gotzl/hid-fanatecff `136cb2d` | GPL-2.0 |
| `hid-logitech-new` | Logitech wheels (G25 to G923) with full force feedback | berarma/new-lg4ff `2092db1` | GPL-2.0 |
| `hid-tmff-new`, `hid-tminit-new`, `usb-tminit-new` | Thrustmaster wheels (T300, T248, TX, TS-XW, ...) | Kimplul/hid-tmff2 `7a1274d` with hid-tminit `8c45472` | GPL-2.0 |
| `vhba` | Virtual CD/DVD drives (CDEmu) | cdemu vhba-module 20260313 | GPL-2.0-or-later |

These are the commits Bazzite's current image uses, except xone: Bazzite's build names a commit
that isn't public, so SparkOS uses xonedo's `master` at `982cbcb` (xonedo is the maintained fork;
the original dlundqvist/xone is no longer maintained).

**How it's built.** A separate build stage installs `kernel-devel` for the exact kernel in the
base image, downloads each source, checks its SHA-256 and builds it with the kernel's own build
system (`make -C /usr/src/kernels/<kernel> M=...`); v4l2loopback goes through akmods into a kmod
RPM. The compiler and kernel headers stay in that stage; only the modules reach the image. There
they go to `/usr/lib/modules/<kernel>/extra/`, compressed like Fedora's own, then `depmod` runs.
The build stops with an error if:

- the kernel-devel version isn't the base's kernel, or its symbol list differs from the kernel's;
- a download's checksum doesn't match;
- a module's `vermagic` isn't the base's kernel, or `modinfo` can't find it after `depmod`;
- a module (v4l2loopback's included) has a `.BTF` section. Fedora's kernel refuses a module whose
  BTF type info doesn't match its own, and matching it needs the kernel's `vmlinux` and the exact
  `pahole` it was built with. The modules are built without BTF instead (kernel-devel has no
  `vmlinux`, so kbuild skips it; the build's "pahole version differs" warning is harmless).
  Measured 2026-11-22: all of them load on Fedora's 7.3.4-300 kernel booted in a VM;
- the image's kernel changed between the two stages.

So a module that stops compiling on a new Fedora kernel fails the build instead of shipping a
system without it. The fix is then to bump that module's pin.

**Also installed:** the xone dongle's firmware (extracted from Microsoft's Windows Update
packages, checked by SHA-256), the fanatec udev rules with `linuxconsoletools` (for
`evdev-joystick`), the vhba rule that lets the signed-in user open `/dev/vhba_ctl`, and the same
module options as Bazzite: `hid_logitech` and `mt76x2u` blacklisted so the new drivers take the
devices, and v4l2loopback named "OBS Virtual Camera" with `exclusive_caps=1`. `ryzen_smu`, `vhba`,
`v4l2loopback` and the three wheel drivers load at boot, as on Bazzite; `zenergy` and xone load
when their hardware is there. The license texts and the exact sources are in
`/usr/share/licenses/sparkos-kmods/`, and `/usr/share/sparkos/fedora-base/kmods.txt` lists what
was built.

**Who needs zenergy and ryzen_smu.** No Spark app reads CPU power: Spark Monitor shows CPU
temperature (k10temp) and GPU power, and Spark Bench reads only frame times. What uses them:

- **MangoHud's CPU power** (`cpu_power`). Without zenergy the only source is the kernel's RAPL
  counter, `/sys/class/powercap/intel-rapl:0/energy_uj`, which Fedora makes readable by root
  only, so MangoHud shows no CPU watts. zenergy gives the same counters through hwmon, readable by
  any user. The owner's MangoHud config doesn't turn `cpu_power` on today.
- **ryzen_smu**: `ryzenadj`, `ryzen_monitor` and other tuning tools. Nothing breaks without it
  unless one of them is used.

**Not built**, and why:

- `kvmfr`, `system76`, `system76-io`, `gcadapter_oc`: loaded on the owner's PC only because
  Bazzite's own list loads them on every PC. kvmfr is for Looking Glass GPU passthrough,
  system76 for System76 computers, gcadapter_oc for overclocking a GameCube controller adapter;
  none is used.
- `openrazer`, `evdi` (DisplayLink), `nct6687d`, `wl` (Broadcom Wi-Fi), `ayaneo-platform`,
  `sc0710`, `t150`, `logitech-trueforce`: hardware the owner doesn't have. Each can be added to
  `kmods.sh` the same way if needed.

**Cost.** The module stage adds about 1 to 2 minutes to a build (measured: about 1 minute for
the stage, including the kernel-devel download, 254 MB installed, which isn't kept). The image
grows by under 1 MB of modules and firmware, plus `linuxconsoletools`.

**Secure Boot.** With it on, Fedora's kernel locks down and refuses any module not signed by a
key it trusts: unsigned modules fail to load (the system still boots). SparkOS signs them:

- The image build signs every module `kmods.sh` produces (the ones built from source and
  v4l2loopback's) with the kernel's `sign-file` (sha256), in the install step (4b), using a private
  key passed as the `kmod_signing_key` build secret (the `KMOD_SIGNING_KEY` GitHub Actions
  secret). The secret is mounted for that one step and isn't in any layer. It then checks every
  module with `modinfo -F signer`, and that the key matches the certificate.
- Without the secret (pull requests from forks, Dependabot, local builds) the build still
  succeeds, logs `NOT SIGNING`, and leaves the modules unsigned.
- The public certificate is `secureboot/sparkos-kmods.der` in the repo, shipped as
  `/usr/share/sparkos/secureboot/sparkos-kmods.der`. If the file isn't committed yet, the image has
  no certificate and `spark secureboot enroll` says so.
- Each PC enrolls it once: `spark secureboot enroll` runs `mokutil --import` with a one-time
  password, and the blue MOK manager at the next restart finishes it. `spark secureboot` shows
  the Secure Boot state, whether the key is enrolled, and each module's loaded state and signer.
- Making the key and adding the secret: [building.md](building.md#module-signing-secure-boot).

Not tested: no signed build has been made yet and no PC has enrolled the key. Which of these
works first time on real firmware (the signature on `.ko.xz` modules, the certificate's key usage
fields being accepted by shim's MOK list) is unknown until it's tried with Secure Boot on.

## Performance and tuning

Added 2026-11-22. Bazzite tunes the system with packages and loose config files that plain
Kinoite doesn't have. Each one was checked on the owner's PC (Bazzite, read only: `rpm -qf`, the
active values in `/proc` and `/sys`, the services' state) and against the Fedora image. On the
Fedora base, [files/scripts/fedora-tuning.sh](../files/scripts/fedora-tuning.sh) (step 5) writes
SparkOS's own config, and [build_files/packages.sh](../build_files/packages.sh) installs the
packages. Nothing changes on the Bazzite base.

| Bazzite item | On the Fedora image | Why |
|---|---|---|
| `kernel.split_lock_mitigate=0`, `vm.max_map_count`, inotify limits | Already in `fedora-gaming.sh` | Same values. |
| Network sysctls (`75-networking.conf`: BBR, `tcp_mtu_probing=1`, IPv6 privacy addresses) | `/usr/lib/sysctl.d/75-sparkos-network.conf`, and `tcp_bbr` loads at boot | Fedora's default is CUBIC; Fedora builds BBR as a module. |
| zram (`/etc/systemd/zram-generator.conf`: zstd, half the RAM up to 16 GiB) | `/usr/lib/systemd/zram-generator.conf.d/50-sparkos.conf`, same values | Fedora's default is lzo-rle and at most 8 GiB; the owner's PC has 32 GiB, so 16 GiB of zram as today. Swappiness stays at 60 on both. |
| I/O schedulers (`60-schedulers.rules`) | `/usr/lib/udev/rules.d/60-sparkos-io-scheduler.rules`: kyber for SSDs and NVMe, BFQ for hard drives and SD cards | Fedora's own rule gives every `sd*` disk BFQ (SSDs too) and leaves NVMe on `none`. The owner's two NVMe drives and SATA SSD run kyber today. Bazzite's SD-card line matched partitions, which have no scheduler; SparkOS's matches the disk. |
| CPU governor and EPP, Bazzite's `*-bazzite` tuned profiles, `ppd.conf` | Nothing to add: Fedora's `tuned` and `tuned-ppd` are already on, with Fedora's profiles | Bazzite's profiles are Fedora's plus a sched_ext mode switch (does nothing while `scx_loader` is off) and Wi-Fi/USB power saving in "power saver". On a desktop the result is the same: amd-pstate `active`, `powersave` governor, EPP `balance_performance`, boost on. |
| Transparent huge pages | Nothing to add | Fedora's kernel defaults (`madvise`, defrag `madvise`, shmem `never`) are the values on the owner's PC. |
| Kernel argument `bluetooth.disable_ertm=1` (`bazzite-hardware-setup`) | `options bluetooth disable_ertm=1` in `/usr/lib/modprobe.d/sparkos-bluetooth.conf` | For Xbox controllers over Bluetooth. Fedora builds Bluetooth as a module, so a module option does it without touching the kernel command line. No other Bazzite kernel argument is set on this PC. |
| Stop timeout 15 s (`/etc/systemd/{system,user}.conf.d/timeout.conf`) | `/usr/lib/systemd/{system,user}.conf.d/50-sparkos-timeout.conf` | Fedora waits 45 s for a stuck service at shutdown. |
| `memlock` 2 GiB (`/etc/security/limits.d/memlock.conf`) | `/etc/security/limits.d/90-sparkos-memlock.conf` | Fedora's limit is 8 MiB; emulators (RPCS3) and some VR and anti-cheat software need more. |
| btrfs reclaim (`btrfs-reclaim.conf`) | `/usr/lib/tmpfiles.d/sparkos-btrfs-reclaim.conf` | The root disk is btrfs; reclaiming half-empty data chunks avoids "disk full" while space is free. |
| fstrim drop-in (`workaround-no-root-trim.conf`) | `/usr/lib/systemd/system/fstrim.service.d/50-sparkos-mounted.conf` | `/` is read-only in `/etc/fstab` on an image system; trim what's mounted instead (Fedora Atomic tracker issue 81). |
| `dmemcg-booster`, `plasma-foreground-booster-dmemcg`, `kcgroups-dmemcg` | **From Terra** (build time only, like `umu-launcher`), `dmemcg-booster-system` and `-user` enabled | Running on the owner's PC today: when VRAM is full, the focused app keeps its video memory and background apps are moved out first (and get less CPU). Fedora's kernel supports it as is: `CONFIG_CGROUP_DMEM=y`, amdgpu registers its VRAM and TTM has the protection code. Fedora doesn't package the two programs; writing SparkOS's own would mean a D-Bus/cgroup daemon plus a KWin window tracker, so Terra's packages (1 MiB) are used. Fedora's `plasma-workspace.target` already starts the foreground booster. |
| `ds-inhibit` (Universal Blue COPR) | Copied into `files/ds-inhibit` (Valve, BSD-2-Clause), `ds-inhibit.service` enabled | While Steam has a DualShock 4 or DualSense open, the touchpad stops moving the mouse pointer. A 170-line Python script; `python3-pyinotify` is Fedora's. |
| `vkBasalt` | Fedora's package | 1.8 MiB, off unless `ENABLE_VKBASALT=1`. Reaches games started from Spark Games (`umu-run` on the system); Flatpak Steam, Heroic and Lutris use Flathub's VulkanLayer extensions instead. |
| `obs-studio-plugin-vkcapture` (hook libraries) | **Skipped** | In Fedora, but its weak dependencies pull in OBS, CEF and WebKit (about 500 MiB); OBS isn't installed, and Flatpak games use Flathub's OBS capture layer. |
| sched_ext (`scx-scheds`, `scx-tools`, `scx_loader`) | **Skipped** | Shipped but off on Bazzite: `scx_loader` is disabled and `/sys/kernel/sched_ext/state` is `disabled`, so the PC runs the normal kernel scheduler. Fedora's kernel can run it (`CONFIG_SCHED_CLASS_EXT=y`, BTF on); Fedora's own `scx_rusty`/`scx_layered`/`scx_rustland` are 2024 builds, and `scx_lavd`/`scx_bpfland` are only in Terra. Can be added later if wanted. |
| `bpftune` | **Skipped** | Shipped but disabled on Bazzite; not in Fedora. |
| `vulkan-low-latency-layer` | **Skipped** | Terra only, version 0.2, off unless `LOW_LATENCY_LAYER=1`; Bazzite doesn't turn it on. |
| `ryzenadj` | **Skipped** | Not in Fedora (Universal Blue COPR). Made for laptop APUs; a desktop 7800X3D is tuned in the BIOS. The `ryzen_smu` module it uses is built (see Kernel modules). |
| ScopeBuddy | **Skipped** | A gamescope launch wrapper from Terra; nothing in SparkOS or the owner's setup uses it. gamescope itself is installed. |
| `ublue-os-selinux-workarounds` | **Skipped** | One SELinux rule (`kernel_t` execmem on composefs). The Fedora image's VM boot test had no failure from it; look for `execmem` denials on the real PC. |
| `80-gpu-reset.rules` | **Skipped** | Matches `RESET=1` uevents from a SteamOS kernel patch. Neither the OGC kernel (no `drm_sysfs_reset_event`) nor Fedora's sends them, so the rule does nothing on Bazzite either; KWin recovers from GPU resets on its own. |
| NetworkManager | Nothing to add | Bazzite adds no NetworkManager config for this PC (only broadcom-wl's); Wi-Fi uses NetworkManager with wpa_supplicant on both. |
| Other Bazzite files (`mt7921` ASPM, Framework charge control, Valve LEDs, CEC, coredump 5 days, journald persistent, incus/libvirt) | **Skipped** | Hardware the PC doesn't have (the Wi-Fi is a Realtek RTL8852BE), not performance, or already Fedora's default (journald keeps logs because `/var/log/journal` exists). |

**Boot: the sign-in screen doesn't wait for the network** (added 2026-11-24, not a Bazzite item).
Fedora enables `nfs-client.target`. Its `rpc-statd-notify.service` waits for
`network-online.target`, which holds back `remote-fs.target`, `systemd-user-sessions` and the
sign-in screen until NetworkManager has a connection. A benchmark on the owner's PC found the
sign-in screen starting at 10.5 s of userspace time, 6.0 s of it in `NetworkManager-wait-online`;
`rpc-statd-notify` started 24 ms after the network came up. SparkOS has no NFS mounts, so
`fedora-tuning.sh` disables the target (and `10-sparkos.preset` keeps it off). Mounting an NFS share
by hand still works: `mount.nfs` starts `rpc-statd` when it needs it.

`/usr/share/sparkos/fedora-base/tuning-layer.txt` in the image records the packages and values,
and the build stops if a package, file, kernel option or enabled service is missing.

**Checked in containers of `sparkos-fedora`** (not yet in a built image): the packages resolve
(Terra limited to its four packages, nothing else from it); `fedora-tuning.sh` runs to the end;
`systemd-analyze verify` passes for `ds-inhibit`, `dmemcg-booster-system` and `fstrim`;
`udevadm verify` passes and the rule sorts after Fedora's; the manager reads
`DefaultTimeoutStopSec=15s` for system and user; the zram generator makes 16000 MB on 32 GiB of
RAM and stops at 16384 MB on 64 GiB; the tmpfiles lines parse; `bluetooth` has the
`disable_ertm` option; `ds-inhibit` starts.

**Needs the real PC:** that kyber is active on the NVMe and SATA drives, `/dev/zram0` is 16 GiB
zstd, `sysctl net.ipv4.tcp_congestion_control` says `bbr`, `dmemcg-booster` and the foreground
booster run and `/sys/fs/cgroup/dmem.capacity` lists the GPU's VRAM, a DualSense's touchpad
stops moving the pointer while Steam is open, and that no SELinux `execmem` denials show up.

## Package parity

Added 2026-11-22. The owner's rule for the move: anything Bazzite gives today, the Fedora image
gives too. Method: `rpm -qa` on the owner's PC (SparkOS on Bazzite) against the Fedora image with
everything above already in it: 598 package names missing. Most are libraries that come with
something else, or the same thing under another name (negativo17 splits FFmpeg into
`libavcodec`, `libavformat`, ...; RPM Fusion's `ffmpeg-libs` holds them). The rest is below.
[build_files/packages.sh](../build_files/packages.sh) installs the Fedora packages (step 4);
[files/scripts/fedora-parity.sh](../files/scripts/fedora-parity.sh) (step 5) adds what Fedora
doesn't package. Nothing changes on the Bazzite base.

**Size:** +676 MiB installed (206 MiB download), measured with dnf in a container of the Fedora
image; 221 MiB of it is the C/C++ compiler and 146 MiB ROCm's OpenCL. The files from
`fedora-parity.sh` add 6 MiB. The Fedora image stays well under Bazzite's (9.4 GB against 12.5 GB
before this).

| Bazzite has | On the Fedora image | Why |
|---|---|---|
| nvtop, fish, just, vim-enhanced, squashfs-tools, duf, glow, gum, f3, evtest, lshw, powerstat, stress-ng, usbip, v4l-utils, wmctrl, xdotool, ydotool, xwininfo, wlr-randr, tcpdump, traceroute, ncurses-term, lzip, icoutils, mtools, symlinks, msedit, libinput-utils, libimobiledevice-utils, libbluray-utils, sbsigntools, grub2-tools-extra, udica, python3-pip | Fedora's packages | Command-line tools someone may already use. 169 MiB with yad and zenity. |
| yad, zenity | Fedora's packages | The dialogs winetricks, Proton tools and scripts open. |
| `rar` (negativo17) | RARLAB's `unrar` 7 from RPM Fusion nonfree (that repository used for this package only and not left on the system), and `7zip-standalone` (`7za`) | Spark Archive opens plain RAR through libarchive and hands password-protected RAR to `unrar`. Fedora's own `unrar` is unrar-free 0.3, which can't decrypt (found 2026-11-23: a password-protected RAR 5 failed on the image; Fedora's 7-Zip has no RAR codec either). Creating RAR needs RARLAB's paid program. |
| `winetricks` (a loose file) | Upstream's script 20260125, SHA-256 checked, the same file as Bazzite's | Fedora's package requires Wine itself (1.6 GiB with its Windows libraries); Proton and umu bring their own Wine. |
| gcc, gcc-c++, make (there with `kernel-devel`) | Fedora's packages, 221 MiB | A C/C++ compiler for Rust (cargo links with `cc`), pip and npm packages with native code, and Claude Code's builds. `kernel-devel` is left out: the kernel modules are built in their own stage. |
| snapper, btrfs-assistant, btrfsmaintenance, bees | Fedora's packages, off as on Bazzite | On the owner's PC snapper has no configuration and the btrfs timers are off; they are there to turn on. |
| gnome-disk-utility | Fedora's package | Disks: formatting, SMART data, disk images. |
| greenboot, greenboot-default-health-checks | Fedora's packages, with Bazzite's settings (`files/fedora-parity/greenboot.conf`); both services on | Running on the owner's PC: after an update, three failed boots in a row go back to the previous system. The DNS and update-server checks are off, as on Bazzite, so a PC that boots offline isn't a failed boot. |
| cockpit-system, -files, -networkmanager, -podman, -storaged | Fedora's packages | Cockpit's web admin pages, used through Cockpit's client or container. No web server is installed, as on Bazzite. |
| pam-u2f, pamu2fcfg, pam_yubico, yubikey-manager | Fedora's packages | Sign in or `sudo` with a YubiKey or another U2F key. |
| xdg-native-messaging-proxy, flatpak-spawn, dbus-x11, gvfs, wsdd, openxr, libFAudio, libnsl, libxcrypt-compat, bluez-cups (`terra-bluez-cups`) | Fedora's packages | Browser extensions that talk to apps (Flatpak browsers), `dbus-launch`, trash and network folders in GTK apps, Windows network discovery, the OpenXR loader for VR, older games and Linux programs, Bluetooth printers. |
| alsa-firmware, alsa-tools-firmware (with fxload) | Fedora's packages | Firmware for sound cards that load it. `alsa-sof-firmware` (Intel SOF) was already in Kinoite. |
| pipewire-module-filter-chain-sofa, ladspa-caps-plugins | Fedora's packages | Spatial audio filter, EasyEffects' and filter chains' plugins. |
| pipewire-libs-extra (negativo17: aptX, LC3plus) | RPM Fusion's `pipewire-codec-aptx` | aptX for Bluetooth headphones. LC3plus isn't packaged anywhere else; plain LC3 is in Fedora's PipeWire. |
| libheif with HEVC (negativo17: libde265 and others) | RPM Fusion's `libheif-freeworld` | HEIC photos (iPhone pictures). Fedora's libheif can't decode them. |
| mozilla-openh264 | Fedora's Cisco repository, marked as installed on purpose | H.264 video calls in Soot (Firefox's engine), through `MOZ_GMP_PATH` in `/etc/profile.d/gmpopenh264.sh`. Until 2026-11-23 removing Firefox took it out again as Firefox's leftover dependency, so the image built from 29b9cdc doesn't have it; `fedora-apps.sh` now fails the build if it goes. |
| rocm-opencl, rocm-runtime, rocm-comgr, rocm-clinfo, rocm-smi, amdsmi | Fedora's packages, 146 MiB | OpenCL on the AMD GPU for Blender, DaVinci Resolve, Darktable and AI tools. Checked: `rocm-clinfo` lists the AMD platform; `/dev/kfd` is open to all users on both bases. HIP (`rocm-hip`) isn't on Bazzite either. |
| fira-code-fonts, lato-fonts, twitter-twemoji-fonts, Noto Sans Balinese, Javanese, Sundanese, Egyptian hieroglyphs | Fedora's packages | Fonts web pages and apps ask for by name. |
| google-noto-sans-cjk-fonts (static) | **Not added** | Kinoite has the same Chinese, Japanese and Korean glyphs as variable fonts (`google-noto-sans-cjk-vf-fonts`); the static set is 130 MiB more. |
| nerd-fonts (COPR) | Symbols Nerd Font 3.5.1 from upstream, SHA-256 checked, with Nerd Fonts' fontconfig file | Prompt icons (Starship, oh-my-posh, `eza --icons`) in any monospace font. The same files as Bazzite's (same SHA-256). |
| tesseract-langpack-* (ces, chi_sim, chi_tra and their _vert, deu, ell, ita, jpn, jpn_vert, nld, pol, por, rus, spa, tur) | Fedora's packages, 45 MiB | Text recognition in those languages. English and French come with Spark Scan. |
| `ls-iommu` (Terra) | `files/fedora-parity/ls-iommu`, a small script | Lists IOMMU groups for GPU passthrough. |
| `/etc/profile.d/open.sh`, `askpass.sh`; `podman.socket` on for every user (Bazzite's loose files and preset) | The same, from `fedora-parity.sh` (added 2026-11-23) | `open FILE` in a terminal opens it in its app; `sudo -A` asks for the password in KDE's window; Podman's Docker-compatible socket for docker-compose and editors' container tools. |
| `boot-windows`, `protontricks`, `protontricks-launch`, `pulseaudio` (link to `true`), `edit` (link to msedit) (loose files) | SparkOS's own: `boot-windows` runs `spark windows`; the protontricks commands run Flathub's Protontricks or say how to get it; the two links as on Bazzite | Names people type. `pulseaudio --check` succeeds for games and launchers that look for it (PipeWire plays its part). |
| ntfs-3g, ntfsprogs, exfatprogs, dosfstools; kernel `ntfs3` | Already in Kinoite | The owner's NTFS drives mount with the kernel's `ntfs3` on Bazzite today; Fedora's kernel has `ntfs3.ko` too. |
| Nova's libraries (llama-server with Vulkan, PySide6 with Qt WebEngine) | Nothing missing | `ldd` over every program and library in Nova's install, run in the Fedora image, finds the same short list of unresolved optional Qt plugins (SQL drivers, Wayland compositor, PDF) as in the Bazzite image. |

**Not added** (one line each):

- `lxc`: LXC without a service using it (off on Bazzite). `edk2-ovmf` is in the image now, with libvirt and QEMU, for `spark virt setup` (added 2026-11-24).
- `cosign` (Sigstore, 145 MiB): signature checks on updates are done by the container tools themselves (`signing.sh`'s policy); cosign is only needed to sign, which the build does.
- `webapp-manager`, `rom-properties` (Terra): not in Fedora; another project's app, and ROM thumbnails for Dolphin (Spark Files is the file manager).
- `plasma-oxygen`, `oxygen-sounds`, `oxygen-icon-theme`, `oxygen-cursor-themes` (165 MiB): an old KDE look; SparkOS uses its own theme and icons.
- `perl` (the full set): `perl-interpreter` and what scripts need are there; the rest came with ScopeBuddy and `perl-CPAN`.
- `openrazer`, `xwiimote-ng`, `linux-cec`, `libcec`, `inputattach-cec-units`, `nct6687d`, `uld` (Samsung/HP laser printer driver, negativo17), `intel-opencl`, `intel-vaapi-driver`: hardware the owner doesn't have (AMD GPUs have no HDMI-CEC).
- `framework-system`, `fw-fanctrl`, `fw-ectool`, `ayaneo-platform`, `jupiter-sd-mounting-btrfs`, `steamdeck-kde-presets-desktop`, `cardwire`, `system76-*`, `sc0710`, `t150`, `gcadapter_oc`, `sd0`, `gameclass`, `cec-control`: Framework laptops, handhelds, Steam Deck, laptop GPU switching.
- `bazaar`, `krunner-bazaar`, `krunner-yafti`, `bazzite-portal`, `ublue-os-*`, `terra-release*`, `umu-wrapper`, `copr` (a `dnf5 copr` shortcut), Bazzite's rollback and Steam helpers: Bazzite's and Universal Blue's own; Spark Store, Spark Update and `spark` cover them.
- `cage`, `bpfrag`, `cicpoffs`, `qt6-controllable`, `ScopeBuddy`, `vulkan-low-latency-layer`, `scx-*`, `bpftune`, `ryzenadj`: Terra extras Bazzite doesn't turn on, or skipped in [Performance and tuning](#performance-and-tuning).
- `kernel-devel`, `tesseract-devel`, `leptonica-devel`, `*-srpm-macros`, `redhat-rpm-config`, `annobin`: build-only.
- `webkit2gtk4.1`, `webkitgtk6.0`, `gtksourceview4/5`, `gnome-desktop3`, `libdex`, `python3-pydantic`, `python3-protobuf`, `python3-moddb`, `python3-pypresence`, `python3-icoextract`, `python3-gbinder`, `apr-util-*`: libraries that only came with apps SparkOS removes on Bazzite too (Lutris, Waydroid, Bazaar, yafti).
- `libcamera-tools`, `libcamera-gstreamer`: the C920 is a UVC camera and works through V4L2 and PipeWire's camera plugin (already in Kinoite).

**Checked in containers of `sparkos-fedora`** (2026-11-22): every package resolves from Fedora,
RPM Fusion free and Cisco's repository; `fedora-parity.sh` runs to the end (checksums match,
fontconfig finds Symbols Nerd Font, both greenboot services enabled); `ls-iommu` lists the
PC's groups; `winetricks --version` reports 20260125 with Bazzite's SHA-256; `pulseaudio --check`
succeeds; `rocm-clinfo` finds the AMD platform. **Needs the real PC:** `rocm-clinfo` listing the
RX 6800 XT, a HEIC photo opening, greenboot clearing `boot_counter` after a good boot.

## Spark Update staging a newer image

Tried on 2026-11-22 in a VM (QEMU with KVM on the owner's PC, 4 cores, 8 GB), with
[tools/spark-update-vm-test.sh](../tools/spark-update-vm-test.sh), which repeats the whole test.
The installed system was `ghcr.io/wolklaw/sparkos-fedora:latest` (45.20261122.0, built that
morning) with this branch's Spark Update copied in and a marker file
`/usr/share/sparkos-update-test` saying `old`. Two small images built on top of it, `new` (.91)
and `newer` (.92), changed only the marker and the version. All three were served from a local
registry, and the VM followed `10.0.2.2:5055/sparkos-fedora:latest` (installed with
`bootc install to-disk --target-imgref`), so for the VM the registry was where updates come from.
Every update below was started the way the timer starts it, `systemctl start
spark-update.service`, with the next check made due.

| Step | Result | Time |
|---|---|---|
| Install `old` and boot it | `spark-update.timer` enabled, nothing else updating; `spark-update --status` reads the booted image | first boot to SSH 20 s |
| Timer run while the registry can't be reached (plain HTTP, before the VM knew it was allowed) | `result: failed` with bootc's error in `state.json` and the log; Flatpak still updated; the next hourly run did nothing (a failed check waits an hour) | 5.5 s |
| `new` in the registry; timer run | `bootc upgrade` found it, downloaded one 184-byte layer, deployed and staged it (`result: staged`, 45.…91); system Flatpak apps updated (nothing to update) | 54 s (16 s of it deploying) |
| Check now, check only (`spark-update-now@check`) | "No changes"; still `staged` | 1 s |
| Restart | the marker says `new`; 45.…91 booted, 45.…90 is the rollback | SSH after 22 s; boot 9.7 s (`systemd-analyze`) |
| `spark-update --rollback` (the window's Roll back) | `rpm-ostree rollback`; status says the next restart starts .90 | 3 s |
| Restart | the marker says `old` | SSH after 13 s |
| Next timer run | **bug: it staged .91 again** (33 s), so the notification would have offered it and the next restart undone the roll back | |
| Same, with the fix below | not staged: `bootc upgrade --check` only, `result: up_to_date`, `--status` says `Held: SparkOS 45.…91` | under 1 s |
| `newer` in the registry; timer run | staged .92 ("newer than the version you rolled back from"), the hold ends | 53 s |
| Restart | the marker says `newer` | SSH after 24 s |

The script then ran the whole sequence on its own, fixed code included, and passed in 15 minutes
(884 s): building the tools and test images 1.5 min, `bootc install to-disk` 320 s, staging `new`
102 s, the run after the roll back 1 s (nothing staged, `held` recorded), staging `newer` 55 s,
SSH 15 to 55 s after each start.

**The bug, fixed in this branch.** Roll back used to last only until the next scheduled check
(at most 6 hours): Spark Update staged the newest image again even when it was the one you had
just left, which is what the README and the roll back dialog said would happen ("Automatic updates
will download the newest version again later"). A roll back is usually because that version has a
problem, so now Roll back records the image it leaves (`held` in
`/var/lib/spark-update/state.json`), scheduled runs skip that exact image and stage the next newer
one, and Check now (your click) or booting the held image again ends the hold. The dialog and the
README say so. Unit tests cover it; the VM test checks it for real.

**Not tested here:**

- **Signature checking.** The local registry is plain HTTP and unsigned, and the VM's policy
  accepts any image from it. A real PC follows `ostree-image-signed:docker://ghcr.io/wolklaw/sparkos-fedora`
  with the sigstore key; that path (download, check the signature, stage, boot) is what
  `boot-test.yml`'s `spark_update_test` does against the real registry.
- **A full-size download.** The test images differ by one tiny layer. A real update changes many
  of the image's 81 layers; the download takes longer, the staging is the same.
- **UEFI.** The disk was installed from a BIOS-booted helper VM and booted with BIOS, so
  `bootloader-update.service` failed (no EFI directory to adopt). That comes from the test setup,
  not SparkOS; the real boot test boots with UEFI.
- **The notification and the window**: they need a signed-in desktop. The window doesn't show the
  hold yet (it says "up to date"); `spark-update --status` does.
- `mcelog.service` failed at every boot in the VM ("CPU is unsupported"). On the PC it is skipped
  because `edac_mce_amd` is loaded, and Bazzite adds `ConditionVirtualization=no`. The Fedora image
  now has the same condition (`fedora-tuning.sh`), so it no longer fails in VMs either.

## What still ties the prototype to someone else

- **Fedora**: the base image, kernel, Mesa, firmware, Plasma. That's the goal of Release 3: one
  big, stable upstream instead of Fedora plus Bazzite plus the repositories Bazzite pulls in.
- **Cisco's OpenH264**, through Fedora's own repository, for H.264.
- **Valve's `ds-inhibit`**, copied into `files/ds-inhibit`.
- **Device rules** from game-devices-udev, udev-joystick-blacklist and Oversteer, copied into
  `files/device-rules` (Valve's come from Fedora's `steam-devices` since 2026-11-22).
- **Flathub**, for every app users install. Same as today.
- **RPM Fusion free**, for FFmpeg and Mesa video decode (H.265, and H.264/H.265 on the GPU). In the
  image since 2026-11-22.
- **Terra**, for `umu-launcher` and the VRAM booster (`dmemcg-booster`,
  `plasma-foreground-booster-dmemcg`, `kcgroups-dmemcg`) only (Fedora doesn't package them), at build time; the repository
  isn't left on the system, so updates to it come with each image build.
- **RPM Fusion free** also for `akmod-v4l2loopback`, built into a kmod package for the image's kernel.
- **The kernel modules' own projects** (zenergy, ryzen_smu, xonedo, hid-fanatecff, new-lg4ff,
  hid-tmff2, hid-tminit, vhba-module), as source pinned to a commit or release with a SHA-256.
- **Microsoft**, for the Xbox wireless dongle's firmware, taken from Windows Update packages and
  checked by SHA-256.

Gone compared with today: Universal Blue (images, COPRs, akmods, `uupd`, `ujust`, Bazaar), Terra
as a system repository (Mesa, gamescope and the rest), negativo17, the OGC kernel, Tailscale's repository, and several smaller COPRs.

## Recommendation

**Moving SparkOS to Fedora Kinoite is practical, and cheaper than expected.** The prototype is
smaller, boots to a usable system faster on first boot, and passes every SparkOS check except
three, each with a known answer. Main's eight new Spark apps and the Release 2 cleanup built and
passed on Fedora unchanged. Suggested path for Release 3:

1. **Codecs: add RPM Fusion's free repository**, for `ffmpeg` and `mesa-va-drivers-freeworld`
   only. One established repository replaces Terra, negativo17 and Universal Blue's packages for
   this. The alternative, dropping H.265 from Spark Media's requirements, would break phone videos.
2. **Store and updates:** already covered. Spark Update runs on its own timer when `uupd` is
   missing, stages a newer image, restarts into it and rolls back (tried in a VM on 2026-11-22;
   a roll back no longer gets undone by the next check). Spark Store is the store (done
   2026-11-22).
3. **Homebrew:** the shell setup is SparkOS's own since 2026-11-22, so an installed Homebrew keeps
   working after the switch. `spark brew` installs it on request. Claude Code doesn't need it.
4. **Small things to own:** the device rules in `files/device-rules` (done 2026-11-22; refresh
   them from their projects now and then).
5. **Kernel modules:** the ones the owner uses are built while the image builds; see
   [Kernel modules](#kernel-modules). They still need trying on the real PC.
6. **Before switching:** try the prototype on the real PC (games, the GPU, controllers, video
   decode on the GPU), which a VM can't test. Later boot times swapped between runs 2 and 4
   (one sample each), so time them on the real PC too.

Switching the real build is the owner's decision; this PR changes nothing in it.

## Runs

All in Wolklaw/sparkos Actions:

- `build-fedora` run 1 (44689696398): first build, base comparison, first boot (plasma-setup and unverified install found)
- `build-fedora` run 2 (44692514690): signed install, sysctls, boot time of both images (the run 2 numbers quoted above)
- `build-fedora` run 3 (44697823679): real OpenH264, encode/decode measurements, RPM Fusion results above
- `build-fedora` run 4 (44756897649): rebuilt with main merged (all 13 Spark apps, Release 2 cleanup); sizes, boot numbers and checks above
- `boot-test` run 44731730758: the real SparkOS image at 53f54a8 (14.2 s boot, 1,241 MB)
- `inspect` runs 44689712753, 44692012851, 44692618124: package sources, signing setup and services in `sparkos:latest`
- Registry sizes read from the image manifests (amd64) after run 4
