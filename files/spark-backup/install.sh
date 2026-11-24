#!/usr/bin/env bash
# Install Spark Backup, system-wide (root). A root service takes the snapshots and copies them,
# and polkit guards saving settings, so unlike the optional Spark apps it can't live in one
# user's home.
#
#   bash install.sh [--deps] [--prefix /usr/lib/spark-backup] [--no-test]
#   bash install.sh --uninstall
#
# --deps     install what it needs with dnf first (Fedora; the image build): Python with tkinter,
#            polkit, btrfs-progs, rsync, util-linux, a mono font.
# --no-test  skip the self-test at the end.
#
# Installs: the app and its launchers (/usr/bin/spark-backup, /usr/libexec/spark-backup-helper),
# the service and timer (spark-backup.service, spark-backup.timer; nothing is enabled until you
# save a schedule in the window), the polkit action, the desktop entry and the icons.
# Settings (/etc/spark-backup), the schedule drop-in, the history and your snapshots are not
# touched by --uninstall. Install and uninstall never create or delete a snapshot.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkBackup
SLUG=spark-backup
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
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"
SYSTEM_FILES="usr/lib/systemd/system/spark-backup.service
usr/lib/systemd/system/spark-backup.timer
usr/share/polkit-1/actions/dev.wolklaw.SparkBackup.policy"

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: Spark Backup installs system-wide and needs root." >&2
  exit 1
fi

if [ "$UNINSTALL" = 1 ]; then
  systemctl stop spark-backup.timer 2>/dev/null || true
  systemctl disable spark-backup.timer 2>/dev/null || true
  rm -rf -- "$PREFIX"
  rm -f /usr/bin/$SLUG /usr/libexec/$SLUG-helper \
        "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for file in $SYSTEM_FILES; do rm -f "/$file"; done
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  systemctl daemon-reload 2>/dev/null || true
  command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
  echo "Spark Backup removed from the system. Your snapshots, /etc/spark-backup and the copies on your drive stay."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter polkit btrfs-progs rsync util-linux xrdb cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

rm -rf "$PREFIX"
install -d "$PREFIX/sparkbackup" "$PREFIX/icons"
install -m 0644 "$here"/sparkbackup/*.py "$PREFIX/sparkbackup/"
install -m 0644 "$here/spark_backup.py" "$here/spark-app.json" "$PREFIX/"
install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

# The window. The helper runs as root (the service and pkexec start it), so it starts Python
# in isolated mode (-I: no PYTHONPATH, no current directory) and imports only from the
# installed folder.
cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_backup.py "\$@"
EOF
install -d /usr/libexec
cat > /usr/libexec/$SLUG-helper <<EOF
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "$PREFIX"); from sparkbackup.helper import main; sys.exit(main())' "\$@"
EOF
chmod 0755 /usr/bin/$SLUG /usr/libexec/$SLUG-helper

for file in $SYSTEM_FILES; do
  install -Dm 0644 "$here/system/$file" "/$file"
done
install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
# The timer is not enabled here: the window enables it when you save a schedule
systemctl daemon-reload 2>/dev/null || true

test -x /usr/bin/$SLUG
test -x /usr/libexec/$SLUG-helper
test -f "$PREFIX/sparkbackup/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Backup installed to $PREFIX."
