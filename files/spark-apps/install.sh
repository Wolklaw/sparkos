#!/usr/bin/env bash
# Install Spark Apps (signed live updates for the Spark apps), system-wide, as root. It is part
# of the SparkOS image (files/scripts/spark-apps.sh runs it before the apps are installed).
#
#   bash install.sh [--deps] [--key FILE] [--no-test]
#   bash install.sh --uninstall
#
# What it puts where (all of it root-owned code from the image; nothing here reads /var):
#   /usr/lib/spark-apps/            the Python package and launch.py (what /usr/bin/spark-<app> runs)
#   /usr/libexec/spark-apps-update  the root service program (systemd starts it)
#   /usr/lib/systemd/system/        spark-apps-update.service and .timer (enabled), spark-apps-now@.service
#   /usr/share/polkit-1/rules.d/    50-spark-apps.rules (Update now without a password)
#   /usr/share/spark-apps/index-key.pub   the public key the index is checked against
# --key FILE  the public key (default: /etc/pki/containers/sparkos.pub, which the image's
#             Containerfile copies from cosign.pub). Without a key the install stops: an updater
#             that can't check signatures must not be installed.
# --deps      install openssl and python3 with dnf first (Fedora; the image build).
# --no-test   skip the self-test.
# What the apps ask of it: each app's install.sh copies its spark-app.json to
# /usr/share/spark-apps/<slug>.json and points /usr/bin/<slug> at launch.py.
# Live copies (/var/lib/spark-apps) are not removed by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
PREFIX=/usr/lib/spark-apps
KEY=/etc/pki/containers/sparkos.pub
DEPS=0
TEST=1
UNINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --key) KEY=$2; shift ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: Spark Apps installs system-wide and needs root." >&2
  exit 1
fi

SYSTEM_UNITS=/usr/lib/systemd/system
if [ "$UNINSTALL" = 1 ]; then
  if command -v systemctl >/dev/null; then
    systemctl disable spark-apps-update.timer 2>/dev/null || true
  fi
  rm -f /etc/systemd/system/timers.target.wants/spark-apps-update.timer \
        "$SYSTEM_UNITS"/spark-apps-update.service "$SYSTEM_UNITS"/spark-apps-update.timer \
        "$SYSTEM_UNITS"/spark-apps-now@.service /usr/libexec/spark-apps-update \
        /usr/share/polkit-1/rules.d/50-spark-apps.rules
  rm -rf -- "$PREFIX" /usr/share/spark-apps/index-key.pub
  echo "Spark Apps removed. Each app keeps its built-in copy; /var/lib/spark-apps is left alone."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 openssl; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi
test -x /usr/bin/openssl || { echo "install.sh: /usr/bin/openssl is missing (use --deps)" >&2; exit 1; }
test -s "$KEY" || { echo "install.sh: no public key at $KEY (use --key FILE)" >&2; exit 1; }
openssl pkey -pubin -in "$KEY" -noout || { echo "install.sh: $KEY isn't a public key" >&2; exit 1; }

rm -rf -- "$PREFIX"
install -d "$PREFIX/sparkapps" /usr/libexec /usr/share/spark-apps
install -m 0644 "$here"/sparkapps/*.py "$PREFIX/sparkapps/"
install -m 0644 "$here/launch.py" "$here/README.md" "$PREFIX/"
install -m 0755 "$here/spark-apps-update" /usr/libexec/spark-apps-update
install -m 0644 "$KEY" /usr/share/spark-apps/index-key.pub
python3 -m compileall -q "$PREFIX"

for unit in spark-apps-update.service spark-apps-update.timer spark-apps-now@.service; do
  install -Dm 0644 "$here/systemd/$unit" "$SYSTEM_UNITS/$unit"
done
install -d /etc/systemd/system/timers.target.wants
if command -v systemctl >/dev/null; then
  systemctl enable spark-apps-update.timer
else
  ln -sfn "$SYSTEM_UNITS/spark-apps-update.timer" /etc/systemd/system/timers.target.wants/spark-apps-update.timer
fi
install -Dm 0644 "$here/polkit/50-spark-apps.rules" /usr/share/polkit-1/rules.d/50-spark-apps.rules

test -f "$PREFIX/launch.py"
test -f "$PREFIX/sparkapps/store.py"
test -x /usr/libexec/spark-apps-update
test -e /etc/systemd/system/timers.target.wants/spark-apps-update.timer
if [ "$TEST" = 1 ]; then
  /usr/libexec/spark-apps-update self-test
fi
echo "Spark Apps installed to $PREFIX."
