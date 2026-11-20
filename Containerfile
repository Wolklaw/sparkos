# SparkOS, built from its own Containerfile, without BlueBuild.
#
# Side by side with the real build: this produces the same image as recipes/recipe.yml, step for
# step, from the same Bazzite base. It's built by .github/workflows/build-containerfile.yml and
# published only as ghcr.io/wolklaw/sparkos:containerfile. The real image (latest) still comes from
# BlueBuild until the owner switches. docs/building.md explains each step, how the two images
# compare, and what's left before switching.
#
# Each RUN below matches one step of what BlueBuild generates for the recipe, in the same order.
# build_files/check-recipe-sync.py fails the build if the recipe and this file stop matching
# (packages, scripts, their order), so a change to the recipe can't silently go missing here.
#
# Build it locally (from the repo root, with podman or buildah):
#   podman build -t sparkos:local .

ARG BASE_IMAGE=ghcr.io/ublue-os/bazzite:stable
FROM ${BASE_IMAGE}

ARG BASE_IMAGE=ghcr.io/ublue-os/bazzite:stable
# Where the scripts find the repo's files/ folder (the scripts read CONFIG_DIRECTORY, as under
# BlueBuild). It's a bind mount: nothing in files/ is copied into the image except what the
# steps install.
ARG CONFIG_DIRECTORY=/tmp/files
ARG IMAGE_REGISTRY=ghcr.io/wolklaw
ARG IMAGE_NAME=sparkos

# 1. The public key that signed updates are checked against (BlueBuild: "Key RUN").
COPY cosign.pub /etc/pki/containers/sparkos.pub

# 2. Prepare /opt so packages and scripts that install there land in /usr/lib/opt, which is part
#    of the image (BlueBuild: pre_build.sh).
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/pre-build.sh

# 3. files/system/* into the image root (recipe: type files).
RUN --mount=type=bind,source=files,target=/tmp/files,rw \
    --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/copy-files.sh system /

# 4. Packages (recipe: type dnf): remove Bazzite's third-party apps (and the KDE apps a Spark app
#    replaces), then add what SparkOS needs. The recipe says why each package is there. Same order and options as BlueBuild's dnf
#    module: makecache, remove (with dependents), install (weak dependencies on).
RUN --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    --mount=type=cache,dst=/var/cache/rpm-ostree,id=rpm-ostree-cache-sparkos,sharing=locked \
    dnf -y makecache && \
    dnf -y remove \
        steam \
        lutris \
        waydroid \
        input-remapper \
        kate \
        kwrite \
        filelight \
        kfind \
        krdc \
        krfb \
        kwalletmanager5 \
        kdebugsettings \
        khelpcenter \
        plasma-systemmonitor \
        spectacle \
        tailscale && \
    dnf -y --setopt=install_weak_deps=True install \
        bubblewrap \
        socat \
        kdialog \
        fuse \
        fuse-libs \
        rsms-inter-fonts \
        python3.13 \
        SDL2 \
        xcb-util-cursor \
        libxkbcommon-x11 \
        libxkbfile \
        mesa-libGL \
        mesa-libEGL \
        mesa-libgbm \
        alsa-lib \
        pulseaudio-libs \
        nss \
        libXcomposite \
        libXcursor \
        libXdamage \
        libXi \
        libXrandr \
        libXtst

# 5. SparkOS's own scripts, in the recipe's order (recipe: first type script).
RUN --mount=type=bind,source=files,target=/tmp/files,rw \
    --mount=type=bind,source=build_files,target=/tmp/build_files \
    --mount=type=cache,dst=/var/cache/libdnf5,id=dnf-cache-sparkos,sharing=locked \
    --mount=type=cache,dst=/var/cache/rpm-ostree,id=rpm-ostree-cache-sparkos,sharing=locked \
    /tmp/build_files/run-scripts.sh \
        sparkos-identity.sh \
        sparkos-apps.sh \
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
        spark-update.sh \
        sparkos-cleanup.sh \
        sparkos-defaults.sh \
        sparkos-theme.sh

# 6. Flathub for the system and for each user, so the Store works; installs nothing
#    (recipe: type default-flatpaks). SparkOS's own shell version of BlueBuild's service.
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/flathub.sh

# 7. The signing policy, so updates are only accepted when signed with SparkOS's key
#    (recipe: type signing).
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/signing.sh "${IMAGE_REGISTRY}" "${IMAGE_NAME}"

# 8. The recipe's last script step: checks the policy entry is the lowercase image name.
RUN --mount=type=bind,source=files,target=/tmp/files,rw \
    --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/run-scripts.sh \
        sparkos-signing-fix.sh

# 9. Clean up: links for anything installed in /opt, empty /tmp and /var, and keep rpm-ostree's
#    package database in step with what's installed (BlueBuild: post_build.sh).
RUN --mount=type=bind,source=build_files,target=/tmp/build_files \
    /tmp/build_files/post-build.sh

# Labels last, so changing them never rebuilds a layer. The ones not set here (version,
# containers.bootc, ostree.*) come from Bazzite, as in the BlueBuild image.
ARG BUILD_DATE=unknown
ARG REVISION=unknown
ARG BASE_DIGEST=unknown
LABEL org.opencontainers.image.title="sparkos" \
      org.opencontainers.image.description="SparkOS, a desktop for gaming and everyday work, built on Bazzite." \
      org.opencontainers.image.source="https://github.com/Wolklaw/sparkos" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.base.name="ghcr.io/ublue-os/bazzite:stable" \
      org.opencontainers.image.base.digest="${BASE_DIGEST}" \
      io.artifacthub.package.readme-url="https://raw.githubusercontent.com/Wolklaw/sparkos/main/README.md"
