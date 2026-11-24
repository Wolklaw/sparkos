#!/usr/bin/env bash
# Install Spark Disks, system-wide (root). It talks to udisks2 over D-Bus as the logged-in user;
# udisks and polkit ask for the password when a change needs it, so there is no root helper.
#
#   bash install.sh [--deps] [--prefix /usr/lib/spark-disks] [--no-test]
#   bash install.sh --uninstall
#
# --deps     install what it needs with dnf first (Fedora; the image build): Python with tkinter and
#            PyGObject, udisks2, polkit, smartmontools, lsblk, and the tools that make ext4, xfs,
#            btrfs, FAT, exFAT and NTFS.
# --no-test  skip the self-test at the end.
#
# Installs the app (/usr/bin/spark-disks), the desktop entry and the icons. Nothing else.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkDisks
SLUG=spark-disks
PREFIX=/usr/lib/$SLUG
DEPS=0
TEST=1
UNINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: Spark Disks installs system-wide and needs root." >&2
  exit 1
fi

if [ "$UNINSTALL" = 1 ]; then
  rm -rf -- "$PREFIX"
  rm -f /usr/bin/$SLUG "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
  echo "Spark Disks removed from the system."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter python3-gobject udisks2 polkit smartmontools util-linux \
             e2fsprogs xfsprogs btrfs-progs udisks2-btrfs dosfstools exfatprogs ntfsprogs \
             xrdb cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

rm -rf "$PREFIX"
install -d "$PREFIX/sparkdisks" "$PREFIX/icons"
install -m 0644 "$here"/sparkdisks/*.py "$PREFIX/sparkdisks/"
install -m 0644 "$here/spark_disks.py" "$here/spark-app.json" "$PREFIX/"
install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_disks.py "\$@"
EOF
chmod 0755 /usr/bin/$SLUG

install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

test -x /usr/bin/$SLUG
test -f "$PREFIX/sparkdisks/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Disks installed to $PREFIX."
