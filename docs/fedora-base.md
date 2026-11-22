# SparkOS on plain Fedora: prototype results

SparkOS is built on Bazzite today. This prototype builds the same SparkOS layer on Fedora's own
atomic KDE image, Fedora Kinoite 45, to find out what moving off Bazzite (Release 3 in
[PLAN.md](../PLAN.md)) would cost. It's a separate test image, `ghcr.io/wolklaw/sparkos-fedora`.

**Since 2026-11-22 it's built from the same Containerfile as SparkOS** (see
[building.md, The Fedora build](building.md#the-fedora-build)), every time main's image builds and
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
  `sparkos-dev-setup --brew` points to Homebrew's installer. No update timers.
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
Homebrew's timers, Bazaar) and expects `.flatpakref` files to open in Spark Store.

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
| **Out-of-tree kernel modules** | 20 from Universal Blue's akmods, prebuilt for the OGC kernel (xone, zenergy, ryzen_smu, v4l2loopback, the wheel drivers, vhba, kvmfr, openrazer, ...) | Built by SparkOS while the image builds: zenergy, ryzen_smu, v4l2loopback, xone, hid-fanatecff, new-lg4ff, hid-tmff2 and vhba (see [Kernel modules](#kernel-modules)). xpad, hid-playstation, hid-nintendo and hid-steam are in Fedora's kernel. | About 1 to 2 minutes per build, and 254 MB of kernel-devel in a build stage that isn't kept. A source pin to bump when a module breaks on a new kernel. Signing, if Secure Boot is ever turned on. | The modules' own projects (pinned sources), RPM Fusion's akmod-v4l2loopback, Microsoft's xone firmware |
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
| **Updates** | `uupd` (Universal Blue) downloads, daily at 04:00; Spark Update adds the notification, the window and roll back | Spark Update does it all: with no `uupd` in the image, `spark-update.sh` turns on its own timer (every 6 hours, stages the new image, updates Flatpak apps). Measured: enabled and active, no other updater on. Its staging hasn't been tried against a newer image. | Nothing new: Spark Update already ships. Its built-in image name would need changing only for a separately named image like this one. | None |
| **The Store** | Bazaar (Universal Blue COPR), with Spark Store installed next to it | Bazaar isn't available in Fedora. Spark Store is installed and `.flatpakref` files already open in it (measured); Kinoite's Discover is there too. | Done (2026-11-22): the dock, `.flatpakref` files and `sparkos-open-package` all use Spark Store. | None |
| **Homebrew** (`sparkos-dev-setup --brew`) | Bazzite ships a Homebrew tarball and a first-boot service | Not present: `sparkos-dev-setup --brew` says Homebrew isn't ready | Shell setup owned since 2026-11-22 (three small files; an existing `/var/home/linuxbrew` keeps working). `spark brew` installs Homebrew on request (Homebrew's installer pinned to one commit, SHA-256 checked). Not owned: Homebrew's update timers. Claude Code itself installs fine (`sparkos-dev-setup --claude` passed). | Homebrew's installer |
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

**Secure Boot.** It is off on the owner's PC, so the modules aren't signed. With Secure Boot on,
Fedora's kernel locks down and refuses any module not signed by a key it trusts: these modules
would fail to load (the system still boots). To turn it on later:

1. Make a key pair once (`openssl req -new -x509 -newkey rsa:2048 -nodes -days 36500
   -outform DER -keyout MOK.priv -out MOK.der -subj "/CN=SparkOS kernel modules/"`) and store
   the private key as a GitHub Actions secret, never in the repository.
2. In the build stage, mount the secret and sign each `.ko` before it's compressed:
   `/usr/src/kernels/<kernel>/scripts/sign-file sha256 MOK.priv MOK.der module.ko`. For
   v4l2loopback, akmods signs with the key in `/etc/pki/akmods/` when one is there.
3. Ship `MOK.der` in the image and enroll it once per PC: `sudo mokutil --import MOK.der`,
   choose a password, reboot, and confirm in the blue MOK manager screen. Bazzite asks for the
   same step with Universal Blue's key.

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
   missing (measured); before switching, run its staging once against a newer image. Spark Store
   is the store (done 2026-11-22).
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
