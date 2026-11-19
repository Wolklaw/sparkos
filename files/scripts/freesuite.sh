#!/usr/bin/env bash
# Install FreeSuite (mail, documents, sheets, slides, PDF, calendar, files) from its
# pinned Linux release on github.com/Wolklaw/freesuite-releases.
#
# The release tarball installs under /opt/freesuite. On Fedora Atomic /opt is a link
# into /var, which is not part of the OS image, so the program goes to
# /usr/lib/opt/freesuite instead and a tmpfiles rule links /var/opt/freesuite to it.
# App updates arrive as signed packages in each user's ~/.local/share/FreeSuite/components,
# so the read-only /usr is fine.
set -oue pipefail

FREESUITE_VERSION=0.4.0
FREESUITE_SHA256=2ac98dcdad2606df519a422ee49ab4fa0248fe7e76a55a3246fb8a4517aec49a
FILE="freesuite-${FREESUITE_VERSION}-linux-x64.tar.gz"
URL="https://github.com/Wolklaw/freesuite-releases/releases/download/v${FREESUITE_VERSION}/${FILE}"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsSL --retry 5 --retry-delay 5 -o "$tmp/$FILE" "$URL"
echo "${FREESUITE_SHA256}  $tmp/$FILE" | sha256sum -c -
tar -xzf "$tmp/$FILE" -C "$tmp"

root=$(find "$tmp" -mindepth 2 -maxdepth 2 -type d -name opt -printf '%h\n' | head -1)
test -n "$root" && test -d "$root/opt/freesuite" && test -d "$root/usr"

# Program files
mkdir -p /usr/lib/opt
rm -rf /usr/lib/opt/freesuite
cp -a "$root/opt/freesuite" /usr/lib/opt/freesuite
chmod 4755 /usr/lib/opt/freesuite/chrome-sandbox

# Desktop entries, icons, docs (everything under usr/ except the /usr/bin link, made below)
rm -f "$root/usr/bin/freesuite"
cp -a "$root/usr/." /usr/
ln -sfn /usr/lib/opt/freesuite/freesuite /usr/bin/freesuite

# Keep /opt/freesuite working for anything that expects the upstream path.
cat > /usr/lib/tmpfiles.d/freesuite.conf <<'EOF'
L+ /var/opt/freesuite - - - - /usr/lib/opt/freesuite
EOF

command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

# Fail the build if anything is missing.
test -x /usr/lib/opt/freesuite/freesuite
test -x /usr/lib/opt/freesuite/freesuite-bin
test -f /usr/share/applications/freesuite.desktop
test -f /usr/share/applications/freesuite-writer.desktop

echo "FreeSuite ${FREESUITE_VERSION} installed."
