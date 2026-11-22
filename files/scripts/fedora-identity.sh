#!/usr/bin/env bash
# PROTOTYPE (recipes/recipe-fedora.yml). Show "SparkOS" as the system name on the Fedora-based
# test image. Same visible fields as sparkos-identity.sh, but ID stays "fedora" (there are no
# Bazzite tools here that read it) and VARIANT says this is the prototype.
set -oue pipefail

OS_RELEASE=/usr/lib/os-release

sed -i \
  -e 's/^NAME=.*/NAME="SparkOS"/' \
  -e 's/^PRETTY_NAME=.*/PRETTY_NAME="SparkOS (Fedora base prototype)"/' \
  -e 's/^DEFAULT_HOSTNAME=.*/DEFAULT_HOSTNAME="sparkos"/' \
  -e 's|^HOME_URL=.*|HOME_URL="https://github.com/Wolklaw/sparkos"|' \
  -e 's|^BUG_REPORT_URL=.*|BUG_REPORT_URL="https://github.com/Wolklaw/sparkos/issues"|' \
  -e 's/^VARIANT=.*/VARIANT="Fedora base prototype"/' \
  "$OS_RELEASE"
grep -q '^DEFAULT_HOSTNAME=' "$OS_RELEASE" || echo 'DEFAULT_HOSTNAME="sparkos"' >> "$OS_RELEASE"

grep -q '^NAME="SparkOS"$' "$OS_RELEASE"
grep -q '^ID=fedora$' "$OS_RELEASE"

echo "--- os-release after SparkOS rename"
cat "$OS_RELEASE"
