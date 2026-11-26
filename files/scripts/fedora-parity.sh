#!/usr/bin/env bash
# Containerfile step 5. What Bazzite had as loose files or as packages Fedora doesn't carry, as SparkOS's own (docs/fedora-base.md, "Package parity").
# The packages Fedora does carry are installed by build_files/packages.sh (step 4).
#
#   winetricks              upstream's script, pinned and checked (Fedora's package pulls in all
#                           of Wine, 1.6 GiB; Bazzite ships the script alone, the same file)
#   Symbols Nerd Font       the icons terminal prompts use (Starship, oh-my-posh, eza --icons),
#                           with Nerd Fonts' fontconfig file so every monospace font falls back to
#                           it; Bazzite's comes from a COPR, this is the same release from upstream
#   ls-iommu                IOMMU groups for GPU passthrough (files/fedora-parity/ls-iommu)
#   boot-windows            Bazzite's name for `spark windows`
#   protontricks(-launch)   run Flathub's Protontricks, as on Bazzite
#   pulseaudio              a link to `true`, as on Bazzite: PipeWire plays PulseAudio's part, and
#                           games and launchers that run `pulseaudio --check` or `--start` go on
#   edit                    Microsoft Edit by the name Bazzite gives it (Fedora calls it msedit)
#   greenboot               Bazzite's settings, and its two services on: a PC that fails to boot
#                           an update three times goes back to the previous system by itself
#   open                    a shell alias for xdg-open, as on Bazzite (/etc/profile.d/open.sh)
#   SUDO_ASKPASS            a password window for `sudo -A`, as on Bazzite (askpass.sh); Bazzite
#                           uses KDE's, SparkOS uses spark-ask's (spark-askpass)
#   podman.socket           on for every user, as on Bazzite: the Docker-compatible socket that
#                           docker-compose, VS Code's container tools and similar talk to
set -oue pipefail

src=${CONFIG_DIRECTORY:-/tmp/files}/fedora-parity
lic=/usr/share/licenses/sparkos-parity
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fetch() { # url sha256 file
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c - || { echo "checksum mismatch: $1"; exit 1; }
}

# winetricks 20260125 (LGPL-2.1-or-later), the file Bazzite ships (same SHA-256)
winetricks_ver=20260125
fetch "https://raw.githubusercontent.com/Winetricks/winetricks/${winetricks_ver}/src/winetricks" \
  431f82fc74000e6c864409f1d8fb495d696c03928808e3e8acffc45179312a7b "$tmp/winetricks"
install -Dm755 "$tmp/winetricks" /usr/bin/winetricks
fetch "https://raw.githubusercontent.com/Winetricks/winetricks/${winetricks_ver}/COPYING" \
  dc626520dcd53a22f727af3ee42c770e56c97a64fe3adb063799d8ab032fe551 "$tmp/COPYING"
install -Dm644 "$tmp/COPYING" "$lic/winetricks-COPYING"

# Symbols Nerd Font 3.5.1 (MIT), the version and files Bazzite ships
nf_ver=3.5.1
fetch "https://github.com/ryanoasis/nerd-fonts/releases/download/v${nf_ver}/NerdFontsSymbolsOnly.tar.xz" \
  01172f37db8543edb102e5cb5c64101c9f4686630804d49b419aa07b23a69996 "$tmp/nf.tar.xz"
mkdir "$tmp/nf"
tar -xJf "$tmp/nf.tar.xz" -C "$tmp/nf" SymbolsNerdFont-Regular.ttf SymbolsNerdFontMono-Regular.ttf \
  10-nerd-font-symbols.conf LICENSE
install -Dm644 -t /usr/share/fonts/nerd-fonts "$tmp/nf/SymbolsNerdFont-Regular.ttf" \
  "$tmp/nf/SymbolsNerdFontMono-Regular.ttf"
install -Dm644 "$tmp/nf/10-nerd-font-symbols.conf" /usr/share/fontconfig/conf.avail/10-nerd-font-symbols.conf
ln -sf ../../../usr/share/fontconfig/conf.avail/10-nerd-font-symbols.conf /etc/fonts/conf.d/10-nerd-font-symbols.conf
install -Dm644 "$tmp/nf/LICENSE" "$lic/nerd-fonts-LICENSE"
fc-cache -f /usr/share/fonts/nerd-fonts >/dev/null

# Small commands
install -Dm755 "$src/ls-iommu" /usr/bin/ls-iommu
install -Dm755 "$src/boot-windows" /usr/bin/boot-windows
install -Dm755 "$src/protontricks" /usr/bin/protontricks
ln -sf protontricks /usr/bin/protontricks-launch
[ -e /usr/bin/pulseaudio ] || ln -s true /usr/bin/pulseaudio
[ -e /usr/bin/edit ] || ln -s msedit /usr/bin/edit

# greenboot: Bazzite's settings, services on
install -Dm644 "$src/greenboot.conf" /etc/greenboot/greenboot.conf
systemctl enable greenboot-healthcheck.service greenboot-set-rollback-trigger.service

# Shell: `open FILE` opens it in its app; `sudo -A` asks in a KDE window. Same names as Bazzite's
# files, so on a move from Bazzite they replace its copies.
cat > /etc/profile.d/open.sh <<'EOS'
# SparkOS: open a file or URL in its app, as on macOS and Bazzite
alias open="xdg-open &>/dev/null"
EOS
cat > /etc/profile.d/askpass.sh <<'EOS'
# SparkOS: `sudo -A` asks for the password in a Spark window
[ -x /usr/bin/spark-askpass ] && export SUDO_ASKPASS=/usr/bin/spark-askpass
EOS
ln -sfn spark-ask /usr/bin/spark-askpass

# Podman's Docker-compatible socket, on for every user as on Bazzite
systemctl --global enable podman.socket

# Record, and stop the build if anything is missing
out=/usr/share/sparkos/fedora-base/parity.txt
mkdir -p "${out%/*}"
{
  echo "winetricks ${winetricks_ver} (upstream script)"
  echo "Symbols Nerd Font ${nf_ver}"
  echo "commands: ls-iommu boot-windows protontricks protontricks-launch pulseaudio edit"
  echo "greenboot: $(rpm -q greenboot), checks off: dns, update platforms"
  echo "shell: open alias, SUDO_ASKPASS=spark-askpass; podman.socket on for every user"
} >"$out"
for f in /usr/bin/winetricks /usr/bin/ls-iommu /usr/bin/boot-windows /usr/bin/protontricks \
         /usr/bin/protontricks-launch /usr/bin/pulseaudio /usr/bin/edit \
         /usr/share/fonts/nerd-fonts/SymbolsNerdFont-Regular.ttf /etc/fonts/conf.d/10-nerd-font-symbols.conf \
         /etc/profile.d/open.sh /etc/profile.d/askpass.sh /usr/bin/spark-askpass; do
  test -e "$f" || { echo "missing: $f"; exit 1; }
done
[[ $(fc-list : family) == *'Symbols Nerd Font'* ]] || { echo "Symbols Nerd Font not found by fontconfig"; exit 1; }
[ "$(systemctl --global is-enabled podman.socket)" = enabled ] || { echo "podman.socket isn't on for users"; exit 1; }
for s in greenboot-healthcheck.service greenboot-set-rollback-trigger.service; do
  [ "$(systemctl is-enabled "$s")" = enabled ] || { echo "$s isn't enabled"; exit 1; }
done
echo "Package parity files installed:"; cat "$out"
