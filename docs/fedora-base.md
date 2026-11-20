# SparkOS on plain Fedora: prototype results

SparkOS is built on Bazzite today. This prototype builds the same SparkOS layer on Fedora's own
atomic KDE image, Fedora Kinoite 45, to find out what moving off Bazzite (Release 3 in
[PLAN.md](../PLAN.md)) would cost. It's a separate test image, `ghcr.io/wolklaw/sparkos-fedora`.
The real SparkOS build, its recipe and its boot test are unchanged.

Measured on 2026-11-20 with Kinoite 45 (built 2026-11-19), Bazzite `stable` and
`ghcr.io/wolklaw/sparkos:latest` from the same morning. Every number below comes from a CI run
listed at the end.

**Short answer:** SparkOS runs on plain Fedora. Every SparkOS app, the look, the sign-in, signed
updates and the gaming tools work. The image is about 1.2 GB smaller to download and 3.8 GB smaller
on disk. One thing SparkOS requires today doesn't work with Fedora's own packages: **H.265 video**
(and H.264/H.265 decoding on the GPU). H.264, AAC and MP3 decode with Fedora's own packages plus
Cisco's OpenH264. Fixing H.265 takes one outside package source (RPM Fusion: one 16 MiB swap,
measured), a smaller tie than the five or so Bazzite brings. Details and the
recommendation are at the end.

## What was built

| File | What it does |
|---|---|
| [recipes/recipe-fedora.yml](../recipes/recipe-fedora.yml) | Base `quay.io/fedora/fedora-kinoite:45`. The same `files/system`, the same package list, and the same scripts as the real recipe where they work unchanged (Soot, FreeSuite, Spark Snip, Welcome, Games, Monitor, defaults, theme). Plus gamescope, MangoHud and GameMode from Fedora. |
| [files/scripts/fedora-identity.sh](../files/scripts/fedora-identity.sh) | "SparkOS" as the system name. Replaces `sparkos-identity.sh`, which checks for `ID=bazzite`. |
| [files/scripts/fedora-apps.sh](../files/scripts/fedora-apps.sh) | The app policy on Kinoite: removes Firefox, KWrite, Filelight and the other apps Kinoite installs as RPMs, plus Fedora's first-boot wizard, crash reporter and third-party repository switch. Replaces `sparkos-apps.sh`, which empties Bazzite's lists. |
| [files/scripts/fedora-gaming.sh](../files/scripts/fedora-gaming.sh) | Valve's Steam controller and VR udev rules (from Valve's own repository, pinned and checksummed), `uinput` at boot, and Bazzite's gaming kernel settings. |
| [files/scripts/fedora-media.sh](../files/scripts/fedora-media.sh) | Spark Media, with Cisco's real OpenH264 in place of Kinoite's empty `noopenh264` stand-in, recording which formats really decode (encode-then-decode test) instead of failing the build. |
| [files/scripts/fedora-signing-fix.sh](../files/scripts/fedora-signing-fix.sh) | The lowercase signing-policy fix for the `sparkos-fedora` name, and the install setting that makes a fresh install check signatures. |
| [.github/workflows/build-fedora.yml](../.github/workflows/build-fedora.yml) | Compares the three images, builds and signs the prototype, checks it inside a container, boots it in QEMU with the same checks as `boot-test.yml`, and boots both images twice to compare boot time. |

## Size

| | Fedora Kinoite 45 | Bazzite stable | SparkOS (Bazzite) | SparkOS on Fedora |
|---|---|---|---|---|
| Download (compressed, amd64) | 3.32 GB | 4.45 GB | 5.42 GB | **4.25 GB** |
| On disk (uncompressed image) | 7.34 GB | 11.00 GB | 13.17 GB | **9.41 GB** |
| `/usr` | 6,810 MB | 10,760 MB | 11,700 MB | **7,503 MB** |
| RPM packages | 1,736 | 2,408 (+237 more, mostly 32-bit library copies) | 2,400 (+237 more, mostly 32-bit library copies) | **1,744** |
| Kernel | 7.3.4-300.fc45 (Fedora) | 7.3.4-ogc8.1 (OGC) | 7.3.4-ogc8.1 (OGC) | 7.3.4-300.fc45 (Fedora) |

SparkOS's own layer costs about the same on either base (+1 GB download). The difference is the
base: Bazzite adds 714 packages and 2.7 GB (installed size) on top of Kinoite.

## Boot and idle

| Test VM, one run each (run 2) | SparkOS (Bazzite) | SparkOS on Fedora |
|---|---|---|
| First power-on until SSH answers | 86 s (includes an automatic reboot at 57 s by `bazzite-hardware-setup`) | **31 s** (no reboot) |
| First boot, `systemd-analyze` | 13.6 s (the boot after that automatic reboot) | 27.0 s, of which 12.6 s is a one-time man-page index (`fedora-atomic-desktop-mandb-update`) |
| Later boot, `systemd-analyze` | **10.9 s** (1.1 kernel + 2.5 initrd + 7.3 userspace) | 13.0 s (0.9 + 2.7 + 9.3) |
| Reboot until SSH answers | **10 s** | 21 s |
| Memory used at the sign-in screen | 1,193 MB | **1,115 MB** |
| Running services | 32 | 30 |
| Space used after install (`/sysroot`) | 14 GB | **6.5 GB** |
| Test disk image (qcow2) | 6.48 GB | **4.75 GB** |

The prototype's later boots are about 2 s slower in userspace and its reboot 11 s slower; the
cause wasn't investigated (one sample each). The prototype's first boot across three runs took
18.8 to 27.0 s.

These are test-VM numbers (QEMU on a GitHub runner, 4 cores, 8 GB, no GPU), not the 7800X3D's.
They compare the two images under the same conditions.

## The same checks as the real boot test

From the `boot` job (run 3); same checks as `boot-test.yml`, adapted where they name Bazzite things.

| Check | Result |
|---|---|
| System name, signing policy | pass |
| Updates signature-checked (`ostree-image-signed:docker://ghcr.io/wolklaw/sparkos-fedora`) | pass (failed in run 1, before `20-sparkos.toml`) |
| Soot and FreeSuite, Soot's smoke test, default apps | pass |
| Printing, scanning, devices | pass |
| Startup sound | pass |
| Claude Code installed and runs | pass |
| Spark Snip self-test (OCR, H.264 and VP8 recording) | pass (H.264 recording failed in run 2, before the OpenH264 fix) |
| Spark Welcome, Games, Monitor self-tests | pass |
| Spark Media with H.264, H.265, AAC, MP3 | **fail: no H.265 decoder.** H.264, AAC, MP3 decode for real |
| No third-party apps; only Flathub configured | pass |
| Gaming layer (uinput, Steam rules, sysctls, gamescope, MangoHud, GameMode) | pass |
| Installing apps the Windows way | pass |
| SparkOS look, sign-in screen, desktop layout (screenshots) | pass |
| The Store (Bazaar) | **fail: not in Fedora** (Discover is installed) |
| Homebrew for `sparkos-dev-setup --brew` | **fail: not set up** |

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
| **Controller drivers** | xpad, hid-playstation, hid-nintendo, hid-steam in the kernel, plus xone and 19 other out-of-tree modules | The same four in Fedora's kernel (checked with `modinfo` in the VM); no xone | xone is for Microsoft's Xbox wireless USB dongle; wired Xbox controllers use xpad, which Fedora has. Owning an out-of-tree kernel module means building it for every kernel update and signing it for Secure Boot: real, ongoing work. Only worth it if the owner uses that dongle. | Fedora; xone would need its own build |
| **Mesa (OpenGL, Vulkan)** | Terra's build of Mesa 26.2.7 | Fedora's Mesa 26.2.7, same version | Nothing for games: RADV and RadeonSI are the same code. | Fedora |
| **Hardware video decode (VA-API)** | Terra's Mesa decodes H.264 and H.265 on the GPU | Fedora builds Mesa with Mesa's default, patent-free codecs only: no H.264/H.265 on the GPU. Software decoding of H.264 still works (OpenH264). | Not measurable in the VM (no AMD GPU). RPM Fusion has a `mesa-va-drivers-freeworld` package that adds them; see the RPM Fusion results below. | RPM Fusion (or Terra) |
| **FFmpeg and codecs** | negativo17's full FFmpeg | Fedora's `ffmpeg-free` + Cisco's OpenH264 (from Fedora's `fedora-cisco-openh264` repo, swapped in for Kinoite's empty `noopenh264`). Measured by encoding and decoding: **H.264, AAC and MP3 decode; H.265 does not.** | One swap: `dnf swap ffmpeg-free ffmpeg` from RPM Fusion. Measured below. | RPM Fusion (or negativo17) |
| **gamescope, MangoHud, GameMode** | Terra's gamescope 3.17.0 and MangoHud 0.8.4; no GameMode | Fedora's gamescope 3.16.31, MangoHud 0.8.3~rc1, GameMode 1.8.2 | Nothing; Fedora's are one release behind Terra's. | Fedora |
| **Steam controller and VR rules** | `steam-devices` (Terra), Valve commit 22ec85e | The same Valve files at the same commit 22ec85e, fetched from Valve's repository and checked by SHA-256 | A pinned commit to bump now and then. | Valve's files (MIT), no package repository |
| **More controller rules** | `game-devices-udev` (Terra): permissions for 8BitDo, PowerA, Hori, Nacon, wheels and so on | Not added | Small: the rules are MIT-licensed text files at codeberg.org/fabiscafe/game-devices-udev; the same pin-and-checksum approach as Valve's. | That project's files |
| **Gaming kernel settings** | `kernel.split_lock_mitigate=0`, `vm.max_map_count=2147483642`, inotify limits | The same values in `/usr/lib/sysctl.d/70-sparkos-gaming.conf` | Nothing; 4 lines. | None |
| **Hardware setup service** | `bazzite-hardware-setup` (328 lines), which reboots the PC once on first boot | None | For a desktop AMD PC, a few kernel arguments at most (listed above); none was needed to boot and pass the checks in the VM. The rest is for handhelds and laptops SparkOS doesn't target. | None |
| **Firmware** | Fedora's `linux-firmware` (449 MB) plus a few extras | Fedora's `linux-firmware` 20261019 (438 MB), `amd-gpu-firmware`, `amd-ucode-firmware` | Nothing for this PC. | Fedora |
| **Flathub** | Bazzite's flatpak manager adds Flathub, turns Fedora's remote off, sets overrides | BlueBuild's `default-flatpaks` module adds Flathub (system and user); Kinoite 45 ships no Fedora remote in the image. Measured: only Flathub is configured. | Nothing extra. | Flathub; BlueBuild's module |
| **Signing** | BlueBuild's signing module + `sparkos-signing-fix.sh`; Bazzite's `/usr/lib/bootc/install/20-bazzite.toml` makes installs deploy as `ostree-image-signed` | The same signing module and fix, and SparkOS's own `20-sparkos.toml` with the same setting | Nothing: one file. Without it (first prototype run) the test install deployed as `ostree-unverified-registry`, which never checks signatures. | BlueBuild's module |
| **Updates** | `uupd` (Universal Blue), daily at 04:00 | Kinoite's default path: Discover's rpm-ostree backend and update notifier (both installed; not tried). No automatic update timer is enabled. | Spark Update (Release 2 brief) replaces `uupd` on either base. | None once Spark Update ships |
| **The Store** | Bazaar (Universal Blue COPR) | Not available in Fedora. Kinoite's KDE Discover (with its Flatpak backend) is installed instead, and Flathub is configured. Not tried by hand. | Spark Store (Release 3 brief) replaces Bazaar on either base. Until then, Discover: `.flatpakref` files already fall back to it (measured), but the dock's Bazaar pin and `sparkos-open-package`'s "open the Store" button would need Discover's entry. | KDE (Discover) until Spark Store |
| **Homebrew** (`sparkos-dev-setup --brew`) | Bazzite ships a Homebrew tarball and a first-boot service | Not present: `sparkos-dev-setup --brew` says Homebrew isn't ready | Either own a small setup service and pin Homebrew's installer, or drop Homebrew for Node/Python/GitHub CLI/JDK in a Toolbox (Kinoite has `toolbox`) or from Flathub. Claude Code itself installs fine (`sparkos-dev-setup --claude` passed). | Homebrew, or nothing |
| **ujust, rollback helper, motd** | Universal Blue | Gone | Nothing SparkOS's own files use them. Rollback is in the boot menu either way; Spark Update covers the rest. | None |
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

## What still ties the prototype to someone else

- **Fedora**: the base image, kernel, Mesa, firmware, Plasma. That's the goal of Release 3: one
  big, stable upstream instead of Fedora plus Bazzite plus the repositories Bazzite pulls in.
- **BlueBuild**: the build tool, and its `default-flatpaks` and `signing` modules. Same as today.
- **Cisco's OpenH264**, through Fedora's own repository, for H.264.
- **Valve's** udev rules, as two pinned files.
- **Flathub**, for every app users install. Same as today.
- **RPM Fusion**, only if SparkOS keeps requiring H.265 (see the recommendation).

Gone compared with today: Universal Blue (images, COPRs, akmods, `uupd`, `ujust`, Bazaar), Terra,
negativo17, the OGC kernel, Tailscale's repository, and several smaller COPRs.

## Recommendation

**Moving SparkOS to Fedora Kinoite is practical, and cheaper than expected.** The prototype is
smaller, boots to a usable system faster on first boot, and passes every SparkOS check except
three, each with a known answer. Suggested path for Release 3:

1. **Codecs: add RPM Fusion's free repository**, for `ffmpeg` and `mesa-va-drivers-freeworld`
   only. One established repository replaces Terra, negativo17 and Universal Blue's packages for
   this. The alternative, dropping H.265 from Spark Media's requirements, would break phone videos.
2. **Store and updates:** finish Spark Store and Spark Update first (both are needed on either base,
   and they're the only Bazzite pieces users touch). Until then, Discover works as the store.
3. **Homebrew:** owner's call: keep it with a small setup service SparkOS owns, or move
   `sparkos-dev-setup`'s tools to a Toolbox. Claude Code doesn't need it.
4. **Small things to own:** `game-devices-udev` rules pinned like Valve's; the dock pin and
   "open the Store" button pointed at whatever store ships.
5. **Skip unless needed:** xone and the other out-of-tree kernel modules.
6. **Before switching:** try the prototype on the real PC (games, the GPU, controllers, video
   decode on the GPU), which a VM can't test, and look into the 2 s slower later boots.

Switching the real build is the owner's decision; this PR changes nothing in it.

## Runs

All in Wolklaw/sparkos Actions:

- `build-fedora` run 1 (44689696398): first build, base comparison, first boot (plasma-setup and unverified install found)
- `build-fedora` run 2 (44692514690): signed install, sysctls, boot time of both images (boot numbers above)
- `build-fedora` run 3 (44697823679): real OpenH264, encode/decode measurements, sizes and checks above
- `inspect` runs 44689712753, 44692012851, 44692618124: package sources, signing setup and services in `sparkos:latest`
- Registry sizes read from the image manifests (amd64) the same morning
