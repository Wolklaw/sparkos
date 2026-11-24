#!/usr/bin/env bash
# Run as root inside the SparkOS image (CI: podman run ... -v .:/repo:ro). The published image
# may predate Spark Notes, so this does what the image build does first: copies files/system
# over the image and runs files/scripts/spark-notes.sh (installs the app system-wide with
# wl-clipboard, gives it Meta+V, takes Klipper out of the tray). Then, as a normal user: the
# self-test, the unit and window tests on the image's own Python and GTK, and a per-user
# install and uninstall (notes, history and settings are kept on purpose, so they don't count).
set -euo pipefail

cp -r /repo/files /tmp/files
CONFIG_DIRECTORY=/tmp/files bash /repo/build_files/copy-files.sh system /
echo "image: $(. /etc/os-release; echo "$PRETTY_NAME"), $(python3 --version)"
echo "wl-paste before: $(command -v wl-paste || echo none)"

echo "--- the image build step"
CONFIG_DIRECTORY=/tmp/files bash /tmp/files/scripts/spark-notes.sh
echo "wl-paste after: $(command -v wl-paste || echo none)"

echo "--- what the window tests need (test only, not part of the image)"
dnf -y -q install --setopt=install_weak_deps=False xorg-x11-server-Xvfb xorg-x11-xauth dbus-daemon \
  mesa-dri-drivers >/dev/null || dnf -y -q install xorg-x11-server-Xvfb xorg-x11-xauth

useradd -m tester
home=$(getent passwd tester | cut -d: -f6)
cp -r /repo/files/spark-notes "$home/spark-notes"
chown -R tester: "$home/spark-notes"
# setpriv, not su or runuser: those open a PAM session, which fails in a container
as() {
  (cd "$home" && setpriv --reuid=tester --regid=tester --init-groups \
     env -i HOME="$home" USER=tester LOGNAME=tester PATH=/usr/local/bin:/usr/bin:/bin \
     SHELL=/bin/bash LANG=C.UTF-8 GSK_RENDERER=cairo GDK_DEBUG=no-portals bash -c "$1")
}

echo "--- self-test and tests, as a normal user"
as "spark-notes --version"
as "spark-notes --self-test"
as "cd ~/spark-notes && python3 -m unittest tests.test_core -v" 2>&1 | tee /tmp/core.txt
grep -q '^OK' /tmp/core.txt
as "cd ~/spark-notes && dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' python3 -m unittest tests.test_ui -v" 2>&1 \
  | tee /tmp/ui.txt
grep -q '^OK' /tmp/ui.txt

echo "--- per-user install and uninstall (no root)"
as "bash ~/spark-notes/install.sh --user --no-test && ~/.local/bin/spark-notes --self-test >/dev/null"
as "bash ~/spark-notes/install.sh --user --uninstall"
left=$(as "find ~/.local ~/.config \( -path ~/.local/state -o -path ~/.local/share/spark-notes -o -path ~/.config/spark-notes \) -prune -o \( -iname '*spark*notes*' -o -iname '*SparkNotes*' \) -print" || true)
if [ -n "$left" ]; then echo "left behind:"; echo "$left"; exit 1; fi
echo "Spark Notes built into the image, tested, and installed and removed per user"
