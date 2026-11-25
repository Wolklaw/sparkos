#!/usr/bin/env bash
# Run as root inside the SparkOS image (CI: podman run ... -v .:/repo:ro). The published image
# may predate Spark Boxes, so this does what the image build does first: copies files/system
# over the image and runs files/scripts/spark-boxes.sh (installs the app system-wide with
# python3-libvirt and spice-gtk3, which build_files/packages.sh adds to the image). Then, as a
# normal user: the self-test, the unit and window tests on the image's own Python and GTK (the
# libvirt part runs on libvirt's built-in test driver, no real machine is made), and a per-user
# install and uninstall (settings and the log are kept on purpose, so they don't count).
set -euo pipefail

cp -r /repo/files /tmp/files
CONFIG_DIRECTORY=/tmp/files bash /repo/build_files/copy-files.sh system /
echo "image: $(. /etc/os-release; echo "$PRETTY_NAME"), $(python3 --version)"
echo "libvirt binding before: $(rpm -q python3-libvirt || true)"

echo "--- the image build step"
# an image published before these were added to packages.sh gets them here, as the build would
rpm -q edk2-ovmf swtpm >/dev/null 2>&1 || dnf -y -q install --setopt=install_weak_deps=False edk2-ovmf swtpm
CONFIG_DIRECTORY=/tmp/files bash /tmp/files/scripts/spark-boxes.sh
echo "libvirt binding after: $(rpm -q python3-libvirt spice-gtk3 | tr '\n' ' ')"

echo "--- what the window tests need (test only, not part of the image)"
dnf -y -q install --setopt=install_weak_deps=False xorg-x11-server-Xvfb xorg-x11-xauth dbus-daemon \
  mesa-dri-drivers >/dev/null || dnf -y -q install xorg-x11-server-Xvfb xorg-x11-xauth

useradd -m tester
home=$(getent passwd tester | cut -d: -f6)
cp -r /repo/files/spark-boxes "$home/spark-boxes"
chown -R tester: "$home/spark-boxes"
# setpriv, not su or runuser: those open a PAM session, which fails in a container
as() {
  (cd "$home" && setpriv --reuid=tester --regid=tester --init-groups \
     env -i HOME="$home" USER=tester LOGNAME=tester PATH=/usr/local/bin:/usr/bin:/bin \
     SHELL=/bin/bash LANG=C.UTF-8 GSK_RENDERER=cairo GDK_DEBUG=no-portals bash -c "$1")
}

echo "--- self-test and tests, as a normal user"
as "spark-boxes --version"
as "spark-boxes --self-test"
as "cd ~/spark-boxes && python3 -m unittest tests.test_core -v" 2>&1 | tee /tmp/core.txt
grep -q '^OK' /tmp/core.txt
as "cd ~/spark-boxes && dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' python3 -m unittest tests.test_ui -v" 2>&1 \
  | tee /tmp/ui.txt
grep -q '^OK' /tmp/ui.txt

echo "--- per-user install and uninstall (no root)"
as "bash ~/spark-boxes/install.sh --user --no-test && ~/.local/bin/spark-boxes --self-test >/dev/null"
as "bash ~/spark-boxes/install.sh --user --uninstall"
left=$(as "find ~/.local ~/.config \( -path ~/.local/state -o -path ~/.config/spark-boxes \) -prune -o \( -iname '*spark*boxes*' -o -iname '*SparkBoxes*' \) -print" || true)
if [ -n "$left" ]; then echo "left behind:"; echo "$left"; exit 1; fi
echo "Spark Boxes built into the image, tested, and installed and removed per user"
