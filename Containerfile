# SparkOS: the whole image, built from this file (no BlueBuild since 2026-11-20).
#
# Base: Bazzite (KDE Plasma, AMD/Intel GPUs, current Mesa drivers, gaming kernel).
# Built and signed by .github/workflows/build.yml and published as ghcr.io/wolklaw/sparkos:latest.
#
# The same file builds the test image on plain Fedora Kinoite (ghcr.io/wolklaw/sparkos-fedora,
# .github/workflows/build-fedora.yml), so the two never drift apart:
#   --build-arg BASE_IMAGE=quay.io/fedora/fedora-kinoite:45 --build-arg SPARKOS_BASE=fedora
#   --build-arg IMAGE_NAME=sparkos-fedora
# docs/building.md explains each step.
#
# App policy (owner's decision, 2026-11-20): SparkOS ships only the owner's own apps (Soot,
# FreeSuite and the Spark apps: Snip, Media, Welcome, Games, Monitor, Edit, Calc, Archive, Scan,
# Run, Link, Store, Launcher, Files, Terminal and Update). Every other company's or project's app is removed, Bazzite's
# included; people install what they want from the Store (Spark Store, or Bazaar next to it). What
# stays is the platform SparkOS needs to work: Plasma, Dolphin, System Settings, Ark (zip
# support), KDE Connect, the Store, drivers, printing and scanning. Where a Spark app does the job,
# KDE's own is removed too: Spark Monitor replaces Plasma System Monitor (and takes its shortcuts),
# Spark Snip replaces Spectacle (it captures through KWin itself), Spark Terminal replaces Konsole
# (Konsole stays installed but hidden for one release, as a fallback) and Spark Files replaces Dolphin:
# it is the default file manager and answers "Show in folder"; Dolphin stays installed but out of
# the menu for one release (files/scripts/spark-files.sh). Ark and KDE Connect stay until
# Spark Archive and Spark Link are tried on real hardware. Tailscale, a company's VPN service, is
# removed too.
#
# Build it locally (from the repo root, as root, with about 40 GB free):
#   sudo podman build -t localhost/sparkos:test .

ARG BASE_IMAGE=ghcr.io/ublue-os/bazzite:stable

# 0. sparkos-capslock, compiled on the same base so it links against the image's own libevdev.
#    Only the program is copied into the image (step 3b); the compiler stays in this stage.
FROM ${BASE_IMAGE} AS capslock-build
RUN --mount=type=bind,source=files/sparkos-capslock,target=/src \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    dnf -y --setopt=install_weak_deps=False install gcc libevdev-devel pkgconf-pkg-config && \
    gcc -O2 -Wall -Wextra -Werror -std=gnu11 -D_FORTIFY_SOURCE=3 -fstack-protector-strong \
        -o /sparkos-capslock /src/sparkos-capslock.c $(pkg-config --cflags --libs libevdev)

FROM ${BASE_IMAGE}

ARG BASE_IMAGE=ghcr.io/ublue-os/bazzite:stable
# Where the scripts find the repo's files/ folder (they read CONFIG_DIRECTORY). It's a bind mount:
# nothing in files/ is copied into the image except what the steps install.
ARG CONFIG_DIRECTORY=/tmp/files
ARG IMAGE_REGISTRY=ghcr.io/wolklaw
ARG IMAGE_NAME=sparkos
# Which base this build is on: bazzite (the real SparkOS) or fedora (sparkos-fedora, the test
# image on plain Fedora Kinoite). Steps 4 and 5 differ by base; everything else is shared.
# (An ARG, so the scripts see it while building but it isn't set in the finished system.)
ARG SPARKOS_BASE=bazzite

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

# 4. Packages (build_files/packages.sh lists each one and why). On Bazzite: remove the other
#    projects' apps it ships, Tailscale and Universal Blue's updater. On Fedora: add what Bazzite
#    brought (printing, scanning, ImageMagick, the gaming layer, distrobox, btop, tmux and other
#    tools, umu-run from Terra for this one package) and RPM Fusion free's FFmpeg and Mesa video
#    decode, so H.264/H.265 play. Then, on both, the SparkOS list (Claude Code's
#    sandbox, kdialog, FUSE 2 for AppImages, Inter, the libraries Androidbox needs).
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    --mount=type=cache,dst=/var/cache/rpm-ostree,id=rpm-ostree-cache-sparkos,sharing=locked \
    /tmp/build_files/packages.sh "${SPARKOS_BASE}"

# 5. SparkOS's own scripts (files/scripts), in this order:
#    "a|b" means a on Bazzite, b on Fedora; "-" is nothing (build_files/run-scripts.sh)
#    - identity: shows "SparkOS" as the system name
#    - apps: no preinstalled third-party apps (Bazzite: empties its first-boot list, drops the
#      Portal; Fedora: removes Kinoite's RPM apps)
#    - fedora-gaming (Fedora only): the device rules Fedora doesn't package (controllers,
#      not-a-joystick list, wheels; files/device-rules), uinput, gaming sysctls
#    - fedora-homebrew (Fedora only): Homebrew on PATH and completion in bash, zsh and fish,
#      when Homebrew is installed (Bazzite's own files do this there)
#    - soot, freesuite: the browser and the office apps, latest releases
#    - the Spark apps; spark-update comes after the others (it lists their versions). Spark
#      Launcher (the app menu, a Plasma widget) replaces Kickoff in the SparkOS layout. Spark
#      Update is the one updater: its timer downloads and stages updates daily (engine "spark";
#      until 2026-11-20 Universal Blue's uupd did the downloading)
#    - sparkos-cleanup: Spark Monitor takes Plasma System Monitor's keys, no Tailscale repo, no
#      usage counting
#    - sparkos-defaults: default apps; downloaded installers open the SparkOS way
#    - sparkos-icons: the SparkOS icon theme over Breeze Dark (files/sparkos-icons), the default
#    - sparkos-theme, last: boot splash, sign-in, desktop, dock, wallpaper, fonts (rebuilds the initramfs)
ARG SPARK_UPDATE_ENGINE=spark
RUN --mount=type=bind,source=files,target=/tmp/files,rw \
    --mount=type=bind,source=build_files,target=/tmp/build_files \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    --mount=type=cache,dst=/var/cache/rpm-ostree,id=rpm-ostree-cache-sparkos,sharing=locked \
    /tmp/build_files/run-scripts.sh \
        "sparkos-identity.sh|fedora-identity.sh" \
        "sparkos-apps.sh|fedora-apps.sh" \
        "-|fedora-gaming.sh" \
        "-|fedora-homebrew.sh" \
        soot.sh \
        freesuite.sh \
        spark-snip.sh \
        spark-media.sh \
        spark-welcome.sh \
        spark-games.sh \
        spark-monitor.sh \
        spark-edit.sh \
        spark-calc.sh \
        spark-archive.sh \
        spark-scan.sh \
        spark-run.sh \
        spark-link.sh \
        spark-store.sh \
        spark-files.sh \
        spark-terminal.sh \
        spark-launcher.sh \
        spark-update.sh \
        sparkos-cleanup.sh \
        sparkos-defaults.sh \
        sparkos-icons.sh \
        sparkos-theme.sh

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
ARG DESCRIPTION="SparkOS, a desktop for gaming and everyday work, built on Bazzite."
LABEL org.opencontainers.image.title="${IMAGE_NAME}" \
      org.opencontainers.image.description="${DESCRIPTION}" \
      org.opencontainers.image.source="https://github.com/Wolklaw/sparkos" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.base.name="${BASE_IMAGE}" \
      org.opencontainers.image.base.digest="${BASE_DIGEST}" \
      io.artifacthub.package.readme-url="https://raw.githubusercontent.com/Wolklaw/sparkos/main/README.md"
