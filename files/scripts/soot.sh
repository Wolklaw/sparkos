#!/usr/bin/env bash
# Install Soot, the SparkOS browser, from a pinned commit of github.com/Wolklaw/Soot.
# Soot's own linux/install.sh downloads Mozilla's Firefox engine, checks it against
# Mozilla's SHA256SUMS, and installs to /usr/lib/soot, /usr/bin/soot and /usr/share.
# The engine's self-updater is off; the daily image rebuild brings the newest engine.
set -oue pipefail

SOOT_VERSION=0.2.0
SOOT_COMMIT=24150cf585e61fa93cebd098a7091115d41fc0db   # tag v0.2.0

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsSL --retry 5 --retry-delay 5 -o "$tmp/soot.tar.gz" \
  "https://github.com/Wolklaw/Soot/archive/${SOOT_COMMIT}.tar.gz"
tar -xzf "$tmp/soot.tar.gz" -C "$tmp"

bash "$tmp/Soot-${SOOT_COMMIT}/linux/install.sh"

# Fail the build if anything is missing, so a broken Soot never ships.
test -x /usr/lib/soot/engine/firefox
test -x /usr/lib/soot/soot
test -L /usr/bin/soot
test -f /usr/share/applications/dev.wolklaw.Soot.desktop
grep -q '"DisableAppUpdate": true' /usr/lib/soot/engine/distribution/policies.json

echo "Soot ${SOOT_VERSION} installed."
