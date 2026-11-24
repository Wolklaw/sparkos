#!/usr/bin/env bash
# Install Spark Firewall, system-wide (root). It changes firewalld through a small root helper
# that polkit guards, so unlike the optional Spark apps it can't live in one user's home.
#
#   bash install.sh [--deps] [--prefix /usr/lib/spark-firewall] [--no-test]
#   bash install.sh --uninstall
#
# --deps     install what it needs with dnf first (Fedora; the image build): Python with tkinter,
#            polkit, firewalld.
# --no-test  skip the self-test at the end (the self-test only reads the firewall).
#
# Installs: the app and its launchers (/usr/bin/spark-firewall, /usr/libexec/spark-firewall-helper),
# the polkit action, the desktop entry and the icons. It never changes the firewall itself: no
# rule, zone or service state is touched by installing or removing it.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkFirewall
SLUG=spark-firewall
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
POLICY=usr/share/polkit-1/actions/$APP_ID.policy

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: Spark Firewall installs system-wide and needs root." >&2
  exit 1
fi

if [ "$UNINSTALL" = 1 ]; then
  rm -rf -- "$PREFIX"
  rm -f /usr/bin/$SLUG /usr/libexec/$SLUG-helper "/$POLICY" \
        "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
  echo "Spark Firewall removed from the system. The firewall itself is as you left it."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter polkit firewalld xrdb cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

rm -rf "$PREFIX"
install -d "$PREFIX/sparkfirewall" "$PREFIX/icons"
install -m 0644 "$here"/sparkfirewall/*.py "$PREFIX/sparkfirewall/"
install -m 0644 "$here/spark_firewall.py" "$here/spark-app.json" "$PREFIX/"
install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

# The window. The helper runs as root, so it starts Python in isolated mode (-I: no PYTHONPATH,
# no current directory) and imports only from the installed folder.
cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_firewall.py "\$@"
EOF
install -d /usr/libexec
cat > /usr/libexec/$SLUG-helper <<EOF
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "$PREFIX"); from sparkfirewall.helper import main; sys.exit(main())' "\$@"
EOF
chmod 0755 /usr/bin/$SLUG /usr/libexec/$SLUG-helper

install -Dm 0644 "$here/system/$POLICY" "/$POLICY"
install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

test -x /usr/bin/$SLUG
test -x /usr/libexec/$SLUG-helper
test -f "$PREFIX/sparkfirewall/app.py"
test -f "/$POLICY"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Firewall installed to $PREFIX."
