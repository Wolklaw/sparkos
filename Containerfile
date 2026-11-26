# SparkOS: the whole image, built from this file (no BlueBuild since 2026-11-20).
#
# Base: Fedora Kinoite (Fedora's atomic KDE Plasma image), since 2026-11-23. The last step removes
# KDE, Plasma and KWin: SparkOS runs its own session (spark-compositor, Spark Shell, Spark
# Greeter). Bazzite was the base before that; docs/fedora-base.md has what SparkOS took over from it and how the two compared.
# Built and signed by .github/workflows/build.yml and published as ghcr.io/wolklaw/sparkos:latest.
# docs/building.md explains each step.
#
# App policy (owner's decision, 2026-11-20): SparkOS ships only the owner's own apps (Soot,
# FreeSuite and the Spark apps: Snip, Media, Welcome, Games, Monitor, Edit, Calc, Archive, Scan,
# Run, Link, Store, Launcher, Files, Terminal and Update). Every other company's or project's app is removed;
# people install what they want from Spark Store. What stays is the platform: drivers, printing,
# scanning, Flatpak. KDE is gone (files/scripts/sparkos-no-kde.sh): the Spark session replaces
# Plasma and KWin, Spark Greeter replaces Plasma Login Manager, Spark Files replaces Dolphin,
# Spark Terminal replaces Konsole, Spark Settings replaces System Settings, Spark Monitor replaces
# Plasma System Monitor and Spark Snip replaces Spectacle. GNOME Keyring keeps passwords until
# there is a Spark one; Breeze's icon and cursor artwork stays as files. Discover, GNOME Disks,
# firewall-config and Tailscale are removed too (files/scripts/sparkos-apps.sh).
#
# Build it locally (from the repo root, as root, with about 40 GB free):
#   sudo podman build -t localhost/sparkos:test .

ARG BASE_IMAGE=quay.io/fedora/fedora-kinoite:45
# Which GPU driver: amd (the main image, ghcr.io/wolklaw/sparkos: AMD and Intel GPUs with Mesa)
# or nvidia (ghcr.io/wolklaw/sparkos-nvidia: Nvidia's driver too, build_files/nvidia.sh).
#   sudo podman build --build-arg GPU=nvidia --build-arg IMAGE_NAME=sparkos-nvidia -t localhost/sparkos-nvidia:test .
ARG GPU=amd

# 0. sparkos-capslock, compiled on the same base so it links against the image's own libevdev.
#    Only the program is copied into the image (step 3b); the compiler stays in this stage.
FROM ${BASE_IMAGE} AS capslock-build
RUN --mount=type=bind,source=files/sparkos-capslock,target=/src \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    dnf -y --setopt=install_weak_deps=False install gcc libevdev-devel pkgconf-pkg-config && \
    gcc -O2 -Wall -Wextra -Werror -std=gnu11 -D_FORTIFY_SOURCE=3 -fstack-protector-strong \
        -o /sparkos-capslock /src/sparkos-capslock.c $(pkg-config --cflags --libs libevdev)

# 0a. spark-compositor (files/spark-compositor), the experimental wlroots compositor, compiled on
#     the same base so it links against the image's own libraries. Only the program is copied
#     into the image (step 3c).
FROM ${BASE_IMAGE} AS compositor-build
RUN --mount=type=bind,source=files/spark-compositor,target=/src \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    dnf -y --setopt=install_weak_deps=False install gcc make pkgconf-pkg-config wlroots-devel \
        wayland-devel wayland-protocols-devel wlr-protocols-devel libxkbcommon-devel libinput-devel \
        pixman-devel libdrm-devel cairo-devel pango-devel librsvg2-devel freerdp-devel libwinpr-devel && \
    cp -r /src /build && make -C /build && install -Dm755 /build/spark-compositor /spark-compositor && \
    make -C /build/spark-wl-windows && install -Dm755 /build/spark-wl-windows/spark-wl-windows /spark-wl-windows && \
    make -C /build/spark-rdp && install -Dm755 /build/spark-rdp/spark-rdp /spark-rdp

# 0b. The out-of-tree kernel modules Fedora's kernel doesn't have (zenergy, ryzen_smu,
#     v4l2loopback, xone, the racing wheel drivers, vhba, and Nvidia's when GPU=nvidia), compiled here against kernel-devel of
#     the exact kernel in the base, from pinned, checksummed sources (build_files/kmods.sh).
#     Step 4b puts them in the image.
FROM ${BASE_IMAGE} AS kmods-build
ARG GPU
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    /tmp/build_files/kmods.sh build

FROM ${BASE_IMAGE}

ARG BASE_IMAGE=quay.io/fedora/fedora-kinoite:45
# Where the scripts find the repo's files/ folder (they read CONFIG_DIRECTORY). It's a bind mount:
# nothing in files/ is copied into the image except what the steps install.
ARG CONFIG_DIRECTORY=/tmp/files
ARG IMAGE_REGISTRY=ghcr.io/wolklaw
ARG IMAGE_NAME=sparkos
ARG GPU

# 1. The public key that signed updates are checked against, named after the image.
COPY cosign.pub /etc/pki/containers/${IMAGE_NAME}.pub

# 2. Prepare /opt so packages and scripts that install there land in /usr/lib/opt, which is part
#    of the image.
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/pre-build.sh

# 3. files/system/* into the image root.
RUN --mount=type=bind,source=files,target=/tmp/files,rw \
    --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/copy-files.sh system /

# 3b. Caps Lock turns on and off when pressed, like Windows (files/sparkos-capslock). udev starts
#     sparkos-capslock@<device>.service for each physical keyboard (80-sparkos-capslock.rules).
COPY --from=capslock-build /sparkos-capslock /usr/libexec/sparkos-capslock

# 3c. The experimental Spark compositor (session "spark-wl", the login screen's default). Its runtime
#     library and portal come from packages.sh in step 4.
COPY --from=compositor-build /spark-compositor /usr/bin/spark-compositor
COPY --from=compositor-build /spark-wl-windows /usr/libexec/spark-wl-windows
#     spark-rdp: the RDP server spark-share starts for Spark Connect's Take control (FreeRDP's
#     shadow server on the compositor's screencopy and virtual input; runtime library from step 4).
COPY --from=compositor-build /spark-rdp /usr/libexec/spark-rdp

# 4. Packages (build_files/packages.sh lists each one and why): what Bazzite
#    brought (printing, scanning, ImageMagick, the gaming layer, distrobox, btop, tmux and other
#    tools, compilers, ROCm OpenCL, fonts, greenboot, umu-run from Terra for this one package;
#    docs/fedora-base.md "Package parity") and RPM Fusion free's FFmpeg and Mesa video
#    decode, so H.264/H.265 play. Then the SparkOS list (Claude Code's
#    sandbox, kdialog, FUSE 2 for AppImages, Inter, the libraries Androidbox needs).
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    --mount=type=cache,dst=/var/cache/rpm-ostree,id=rpm-ostree-cache-sparkos,sharing=locked \
    /tmp/build_files/packages.sh

# 4b. The kernel modules from step 0b into /usr/lib/modules/<kernel>/extra, with their firmware,
#     udev rules and boot-time loading, then depmod. Stops the build if the image's kernel isn't
#     the one they were built for. With the kmod_signing_key build secret (never written to a
#     layer) it signs them for Secure Boot and ships secureboot/sparkos-kmods.der; without it
#     the modules stay unsigned.
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    --mount=type=bind,from=kmods-build,source=/kmods,target=/tmp/kmods \
    --mount=type=bind,source=secureboot,target=/tmp/secureboot \
    --mount=type=secret,id=kmod_signing_key,required=false \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    /tmp/build_files/kmods.sh install

# 5. SparkOS's own scripts (files/scripts), in this order:
#    - identity: shows "SparkOS" as the system name
#    - apps: no preinstalled third-party apps (removes Kinoite's RPM apps and first-boot wizard)
#    - fedora-gaming: the device rules Fedora doesn't package (controllers,
#      not-a-joystick list, wheels; files/device-rules), uinput, gaming sysctls
#    - fedora-tuning: Bazzite's system tuning as SparkOS config (network sysctls,
#      zram, I/O schedulers, btrfs reclaim, stop timeouts, memlock, ds-inhibit, VRAM booster)
#    - fedora-homebrew: Homebrew on PATH and completion in bash, zsh and fish, when Homebrew
#      is installed
#    - fedora-parity: what Bazzite had that Fedora doesn't package, as SparkOS's
#      own (winetricks, the Nerd Font symbols, ls-iommu, boot-windows, protontricks), and
#      greenboot's settings (back to the previous system after three failed boots)
#    - soot, freesuite: the browser and the office apps, latest releases
#    - spark-apps, then the Spark apps: signed live updates for them (no reboot; root code
#      stays in the image). spark-update comes after the others (it lists their versions). Spark
#      Update is the one updater: its timer downloads and stages updates daily
#    - spark-controller: fans (curves, run by a small root service), RGB and firmware; the
#      sensor-chip module for the motherboard's fan headers loads at boot (modules-load.d)
#    - spark-backup: snapshots of /home, a copy on another drive, file restore (a root service
#      and a timer; the timer stays off until a schedule is saved)
#    - sparkos-security: the closed "sparkos" firewall zone as the default (only what SparkOS
#      uses is open), Tailscale in the trusted zone, ptrace limited to a program's children
#    - sparkos-cleanup: Spark Monitor takes Plasma System Monitor's keys, no Tailscale repo, no
#      usage counting
#    - sparkos-defaults: default apps; downloaded installers open the SparkOS way
#    - sparkos-icons: the SparkOS icon theme over Breeze Dark (files/sparkos-icons), the default
#    - sparkos-theme: boot splash, sign-in, desktop, dock, wallpaper, fonts (rebuilds the initramfs)
#    - sparkos-no-kde, last: removes KDE, Plasma, KWin and Plasma Login Manager; greetd with the
#      Spark greeter signs you in, GNOME Keyring keeps passwords. Fails if any KDE package is left
RUN --mount=type=bind,source=files,target=/tmp/files,rw \
    --mount=type=bind,source=build_files,target=/tmp/build_files \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    --mount=type=cache,dst=/var/cache/rpm-ostree,id=rpm-ostree-cache-sparkos,sharing=locked \
    /tmp/build_files/run-scripts.sh \
        sparkos-identity.sh \
        sparkos-apps.sh \
        fedora-gaming.sh \
        fedora-tuning.sh \
        fedora-homebrew.sh \
        fedora-parity.sh \
        soot.sh \
        freesuite.sh \
        spark-apps.sh \
        spark-snip.sh \
        spark-media.sh \
        spark-welcome.sh \
        spark-games.sh \
        spark-monitor.sh \
        spark-controller.sh \
        spark-firewall.sh \
        spark-backup.sh \
        spark-disks.sh \
        spark-edit.sh \
        spark-calc.sh \
        spark-fonts.sh \
        spark-clock-wake.sh \
        spark-archive.sh \
        spark-scan.sh \
        spark-run.sh \
        spark-link.sh \
        spark-store.sh \
        spark-files.sh \
        spark-settings.sh \
        spark-terminal.sh \
        spark-shell.sh \
        spark-emoji.sh \
        spark-notes.sh \
        spark-boxes.sh \
        spark-audio.sh \
        spark-tray.sh \
        spark-update.sh \
        spark-session.sh \
        sparkos-security.sh \
        sparkos-cleanup.sh \
        sparkos-defaults.sh \
        sparkos-icons.sh \
        sparkos-theme.sh \
        sparkos-no-kde.sh

# 6. Flathub for the system and for each user, so the Store works; installs no apps.
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/flathub.sh

# 7. The signing policy, so updates are only accepted when signed with SparkOS's key.
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/signing.sh "${IMAGE_REGISTRY}" "${IMAGE_NAME}"

# 8. Clean up: links for anything installed in /opt, empty /tmp and /var, and keep rpm-ostree's
#    package database in step with what's installed.
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/post-build.sh

# Labels last, so changing them never rebuilds a layer. The ones not set here (version,
# containers.bootc, ostree.*) come from the base.
ARG BUILD_DATE=unknown
ARG REVISION=unknown
ARG BASE_DIGEST=unknown
ARG DESCRIPTION="SparkOS, a desktop for gaming and everyday work, built on Fedora Kinoite."
LABEL org.opencontainers.image.title="${IMAGE_NAME}" \
      org.opencontainers.image.description="${DESCRIPTION}" \
      org.opencontainers.image.source="https://github.com/Wolklaw/sparkos" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.base.name="${BASE_IMAGE}" \
      org.opencontainers.image.base.digest="${BASE_DIGEST}" \
      io.artifacthub.package.readme-url="https://raw.githubusercontent.com/Wolklaw/sparkos/main/README.md"
