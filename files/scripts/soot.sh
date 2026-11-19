#!/usr/bin/env bash
# Install Soot, the SparkOS browser, from its latest release on github.com/Wolklaw/Soot.
# Every image build (daily) picks up the newest release. Soot's own linux/install.sh
# downloads Mozilla's Firefox engine, checks it against Mozilla's SHA256SUMS, and installs
# to /usr/lib/soot, /usr/bin/soot and /usr/share. The engine's self-updater is off; the
# daily image rebuild brings the newest engine.
set -oue pipefail

REPO=Wolklaw/Soot

# The latest release, found from GitHub's redirect (no API call, so no API rate limit)
tag=$(curl -fsSI --retry 5 "https://github.com/$REPO/releases/latest" | tr -d '\r' \
      | sed -n 's|^[Ll]ocation: .*/releases/tag/||p' | tail -1)
[[ $tag =~ ^v[0-9]+(\.[0-9]+)*$ ]] || { echo "Could not work out Soot's latest release (got '$tag')"; exit 1; }
echo "Soot latest release: $tag"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 5 --retry-delay 5 -o "$tmp/soot.tar.gz" \
  "https://github.com/$REPO/archive/refs/tags/$tag.tar.gz"
tar -xzf "$tmp/soot.tar.gz" -C "$tmp"
src=$(find "$tmp" -mindepth 1 -maxdepth 1 -type d -name 'Soot-*' | head -1)
test -f "$src/linux/install.sh"

bash "$src/linux/install.sh"

# Record what was installed (the boot test runs the matching smoke test)
echo "$tag" > /usr/lib/soot/SOOT_RELEASE

# Fail the build if anything is missing, so a broken Soot never ships.
test -x /usr/lib/soot/engine/firefox
test -x /usr/lib/soot/soot
test -L /usr/bin/soot
test -f /usr/share/applications/dev.wolklaw.Soot.desktop
grep -q '"DisableAppUpdate": true' /usr/lib/soot/engine/distribution/policies.json

echo "Soot $tag installed."
