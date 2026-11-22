#!/usr/bin/env bash
# Install FreeSuite (mail, documents, sheets, slides, PDF, calendar, files) from its
# latest Linux release on github.com/Wolklaw/freesuite-releases. Every image build (daily)
# picks up the newest release; the download is checked against the SHA256SUMS file
# published with that release.
#
# The release tarball installs under /opt/freesuite. On Fedora Atomic /opt is a link
# into /var, which is not part of the OS image, so the program goes to
# /usr/lib/opt/freesuite instead and a tmpfiles rule links /var/opt/freesuite to it.
# App updates arrive as signed packages in each user's ~/.local/share/FreeSuite/components,
# so the read-only /usr is fine.
set -oue pipefail

REPO=Wolklaw/freesuite-releases

# The latest release, found from GitHub's redirect (no API call, so no API rate limit)
tag=$(curl -fsSI --retry 5 "https://github.com/$REPO/releases/latest" | tr -d '\r' \
      | sed -n 's|^[Ll]ocation: .*/releases/tag/||p' | tail -1)
[[ $tag =~ ^v[0-9]+(\.[0-9]+)*$ ]] || { echo "Could not work out FreeSuite's latest release (got '$tag')"; exit 1; }
FREESUITE_VERSION=${tag#v}
FILE="freesuite-${FREESUITE_VERSION}-linux-x64.tar.gz"
BASE="https://github.com/$REPO/releases/download/$tag"
echo "FreeSuite latest release: $tag"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsSL --retry 5 --retry-delay 5 -o "$tmp/$FILE" "$BASE/$FILE"
curl -fsSL --retry 5 --retry-delay 5 -o "$tmp/SHA256SUMS" "$BASE/SHA256SUMS"
want=$(awk -v f="$FILE" '$2 == f {print $1}' "$tmp/SHA256SUMS")
[[ $want =~ ^[0-9a-f]{64}$ ]] || { echo "SHA256SUMS of $tag has no entry for $FILE"; exit 1; }
echo "$want  $tmp/$FILE" | sha256sum -c -
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

# FreeSuite runs under XWayland for now (until FreeSuite shows its window on native Wayland).
# FreeSuite makes its window hidden and shows it on Electron's ready-to-show, which never comes
# under native Wayland: the window gets no Wayland role until it is shown, so it is never
# painted. The boot test saw it (KWin never got a window; WAYLAND_DEBUG showed no
# get_toplevel, the page itself had loaded); with --ozone-platform=x11 the window is there in
# under a second. Remove this wrapper, and go back to the link
#   ln -sfn /usr/lib/opt/freesuite/freesuite /usr/bin/freesuite
# once a FreeSuite release shows its window without ready-to-show on Linux.
cat > /usr/bin/freesuite <<'EOF'
#!/bin/sh
# SparkOS: FreeSuite under XWayland until it shows its window on native Wayland (files/scripts/freesuite.sh)
exec /usr/lib/opt/freesuite/freesuite --ozone-platform=x11 "$@"
EOF
chmod 0755 /usr/bin/freesuite
# Every menu entry goes through that wrapper
sed -i -E 's#^(Exec=|TryExec=)(/usr/lib/opt/freesuite/freesuite|/opt/freesuite/freesuite)\b#\1/usr/bin/freesuite#' \
  /usr/share/applications/freesuite*.desktop
grep -H '^Exec=' /usr/share/applications/freesuite*.desktop

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
grep -q -- '--ozone-platform=x11' /usr/bin/freesuite

echo "FreeSuite ${FREESUITE_VERSION} installed."
