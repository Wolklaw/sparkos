#!/usr/bin/env bash
# Show "SparkOS" as the system name (About This System, fastfetch, boot menu, hostname).
#
# Only the fields people see change. ID=bazzite, ID_LIKE=fedora and
# /usr/share/ublue-os/image-info.json stay as Bazzite set them, because
# Bazzite's own tools (ujust, hardware setup, rollback helper) read them.
set -oue pipefail

OS_RELEASE=/usr/lib/os-release

sed -i \
  -e 's/^NAME=.*/NAME="SparkOS"/' \
  -e 's/^PRETTY_NAME=.*/PRETTY_NAME="SparkOS"/' \
  -e 's/^DEFAULT_HOSTNAME=.*/DEFAULT_HOSTNAME="sparkos"/' \
  -e 's|^HOME_URL=.*|HOME_URL="https://github.com/Wolklaw/sparkos"|' \
  -e 's|^BUG_REPORT_URL=.*|BUG_REPORT_URL="https://github.com/Wolklaw/sparkos/issues"|' \
  -e 's/^BOOTLOADER_NAME="Bazzite/BOOTLOADER_NAME="SparkOS/' \
  "$OS_RELEASE"

# Fail the build if the rename did not take, so a broken image never ships.
grep -q '^NAME="SparkOS"$' "$OS_RELEASE"
grep -q '^ID=bazzite$' "$OS_RELEASE"

echo "--- os-release after SparkOS rename"
cat "$OS_RELEASE"
