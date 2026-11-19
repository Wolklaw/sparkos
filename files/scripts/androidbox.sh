#!/usr/bin/env bash
# Install Androidbox, the Android emulator, from its latest release on github.com/Wolklaw/Androidbox.
# Every image build (daily) picks up the newest release. Androidbox's own packaging/linux/install.sh puts
# the program in /usr/lib/androidbox (with its Python packages in a virtual environment beside it),
# the `androidbox` command in /usr/bin and the menu entry and icon under /usr/share.
#
# Androidbox downloads Google's Android Emulator and an Android image the first time it is opened, into
# ~/.local/share/Androidbox, so none of that is in the image. Android needs KVM, which Bazzite provides.
# Androidbox doesn't check for updates on SparkOS: the daily image rebuild brings the newest release.
set -oue pipefail

REPO=Wolklaw/Androidbox

# The latest release, found from GitHub's redirect (no API call, so no API rate limit)
tag=$(curl -fsSI --retry 5 "https://github.com/$REPO/releases/latest" | tr -d '\r' \
      | sed -n 's|^[Ll]ocation: .*/releases/tag/||p' | tail -1)
[[ $tag =~ ^v[0-9]+(\.[0-9]+)*$ ]] || { echo "Could not work out Androidbox's latest release (got '$tag')"; exit 1; }
echo "Androidbox latest release: $tag"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 5 --retry-delay 5 -o "$tmp/androidbox.tar.gz" \
  "https://github.com/$REPO/archive/refs/tags/$tag.tar.gz"
tar -xzf "$tmp/androidbox.tar.gz" -C "$tmp"
src=$(find "$tmp" -mindepth 1 -maxdepth 1 -type d -iname 'Androidbox-*' | head -1)
# The first releases were Windows only. Fail with a clear message rather than a missing file
test -f "$src/packaging/linux/install.sh" \
  || { echo "Androidbox $tag has no Linux build yet (packaging/linux/install.sh is missing)"; exit 1; }

# --deps installs the libraries Qt, SDL and Google's emulator load, skipping what Bazzite already has.
# The script ends by starting the app headless, so a broken install fails the build here.
bash "$src/packaging/linux/install.sh" --deps

# Record what was installed (the boot test reads it)
echo "$tag" > /usr/lib/androidbox/ANDROIDBOX_RELEASE

# Fail the build if anything is missing, so a broken Androidbox never ships.
test -x /usr/bin/androidbox
test -x /usr/lib/androidbox/venv/bin/python
test -f /usr/lib/androidbox/app/Androidbox.pyw
test -f /usr/lib/androidbox/app/assets/androidbox-icons.ttf
test -f /usr/share/applications/dev.wolklaw.Androidbox.desktop
test -f /usr/share/icons/hicolor/256x256/apps/androidbox.png
grep -q '^StartupWMClass=Androidbox$' /usr/share/applications/dev.wolklaw.Androidbox.desktop

echo "$(QT_QPA_PLATFORM=offscreen /usr/bin/androidbox --version) installed ($tag)."
