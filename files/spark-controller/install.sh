#!/usr/bin/env bash
# Install Spark Controller, system-wide (root). It sets fan speeds through a root service and
# asks polkit before saving a curve, so unlike the optional Spark apps it can't live in one
# user's home.
#
#   bash install.sh [--deps] [--prefix /usr/lib/spark-controller] [--no-test]
#   bash install.sh --uninstall
#
# --deps     install what it needs with dnf first (Fedora; the image build): Python with tkinter,
#            polkit, fwupd, lm_sensors, liquidctl (Python library), OpenRGB.
# --no-test  skip the self-test at the end.
#
# Installs: the app and its launchers (/usr/bin/spark-controller, spark-controller-daemon,
# /usr/libexec/spark-controller-helper), the fan service (spark-controller.service, enabled; it
# starts only once curves are saved), the polkit action, the sensor-chip module list, the udev
# rules for the lighting controllers, the login autostart for saved lighting, the desktop entry
# and the icons. Settings (~/.config/spark-controller) and /etc/spark-controller are not touched
# by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkController
SLUG=spark-controller
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
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"
SYSTEM_FILES="usr/lib/systemd/system/spark-controller.service
usr/lib/modules-load.d/sparkos-nct6775.conf
usr/lib/udev/rules.d/71-spark-controller.rules
usr/share/polkit-1/actions/dev.wolklaw.SparkController.policy
etc/xdg/autostart/dev.wolklaw.SparkController.rgb.desktop"

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: Spark Controller installs system-wide and needs root." >&2
  exit 1
fi

if [ "$UNINSTALL" = 1 ]; then
  systemctl stop spark-controller.service 2>/dev/null || true
  systemctl disable spark-controller.service 2>/dev/null || true
  /usr/bin/spark-controller-daemon --release 2>/dev/null || true
  rm -rf -- "$PREFIX"
  rm -f /usr/bin/$SLUG /usr/bin/$SLUG-daemon /usr/libexec/$SLUG-helper \
        "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for file in $SYSTEM_FILES; do rm -f "/$file"; done
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  systemctl daemon-reload 2>/dev/null || true
  command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
  echo "Spark Controller removed from the system. /etc/spark-controller stays."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter polkit fwupd lm_sensors xrdb cascadia-mono-fonts \
             python3-liquidctl python3-gobject openrgb; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

rm -rf "$PREFIX"
install -d "$PREFIX/sparkcontroller" "$PREFIX/icons"
install -m 0644 "$here"/sparkcontroller/*.py "$PREFIX/sparkcontroller/"
install -m 0644 "$here/spark_controller.py" "$here/spark-app.json" "$PREFIX/"
install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

# The window. The service and the helper run as root, so they start Python in isolated mode
# (-I: no PYTHONPATH, no current directory) and import only from the installed folder.
cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_controller.py "\$@"
EOF
cat > /usr/bin/$SLUG-daemon <<EOF
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "$PREFIX"); from sparkcontroller.daemon import main; sys.exit(main())' "\$@"
EOF
install -d /usr/libexec
cat > /usr/libexec/$SLUG-helper <<EOF
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "$PREFIX"); from sparkcontroller.helper import main; sys.exit(main())' "\$@"
EOF
chmod 0755 /usr/bin/$SLUG /usr/bin/$SLUG-daemon /usr/libexec/$SLUG-helper

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

# On at every boot; the unit's condition keeps it idle until a curve has been saved
systemctl daemon-reload 2>/dev/null || true
systemctl enable spark-controller.service
if [ -d /run/systemd/system ]; then
  udevadm control --reload 2>/dev/null || true
fi

test -x /usr/bin/$SLUG
test -x /usr/bin/$SLUG-daemon
test -x /usr/libexec/$SLUG-helper
test -f "$PREFIX/sparkcontroller/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
/usr/bin/$SLUG-daemon --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
  /usr/bin/$SLUG-daemon --self-test
fi
echo "Spark Controller installed to $PREFIX."
