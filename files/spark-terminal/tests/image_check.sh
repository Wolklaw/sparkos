#!/usr/bin/env bash
# Run as root inside the SparkOS image (CI: podman run ... -v .:/repo:ro). The published image
# may predate Spark Terminal, so this does what the image build does first: copies files/system
# over the image and runs files/scripts/spark-terminal.sh (adds VTE, installs the app system-wide,
# makes it the default terminal, removes the old terminal's entry). Then, as a normal user: the self-test, the unit
# and window tests on the image's own Python, GTK and VTE (vim and less start and quit cleanly
# inside it), and a per-user install and uninstall.
set -euo pipefail

cp -r /repo/files /tmp/files
CONFIG_DIRECTORY=/tmp/files bash /repo/build_files/copy-files.sh system /
echo "image: $(. /etc/os-release; echo "$PRETTY_NAME"), $(python3 --version)"
echo "before: $(rpm -q vte291-gtk4 || true)"

echo "--- the image build step"
CONFIG_DIRECTORY=/tmp/files bash /tmp/files/scripts/spark-terminal.sh

echo "--- what the window tests need (test only, not part of the image)"
dnf -y -q install --setopt=install_weak_deps=False xorg-x11-server-Xvfb xorg-x11-xauth dbus-daemon \
  mesa-dri-drivers less vim-enhanced >/dev/null || dnf -y -q install xorg-x11-server-Xvfb xorg-x11-xauth less vim-minimal

useradd -m tester
home=$(getent passwd tester | cut -d: -f6)
cp -r /repo/files/spark-terminal "$home/spark-terminal"
chown -R tester: "$home/spark-terminal"
# setpriv, not su or runuser: those open a PAM session, which fails in a container
as() {
  (cd "$home" && setpriv --reuid=tester --regid=tester --init-groups \
     env -i HOME="$home" USER=tester LOGNAME=tester PATH=/usr/local/bin:/usr/bin:/bin \
     SHELL=/bin/bash LANG=C.UTF-8 GSK_RENDERER=cairo bash -c "$1")
}

echo "--- self-test and tests, as a normal user"
as "spark-terminal --version"
as "spark-terminal --self-test"
as "cd ~/spark-terminal && dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' python3 -m unittest discover -s tests -v" 2>&1 \
  | tee /tmp/tests.txt
grep -q '^OK' /tmp/tests.txt
# vim and less must really run here, not be skipped
as "cd ~/spark-terminal && dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' env PYTHONPATH=tests python3 -m unittest -v \
    test_ui.WindowTest.test_vim_starts_and_quits test_ui.WindowTest.test_less_starts_and_quits" 2>&1 \
  | tee /tmp/vim-less.txt
grep -qx 'OK' /tmp/vim-less.txt || { echo "vim or less did not start and quit cleanly (or was skipped)"; exit 1; }

echo "--- start-up time (window on screen)"
for i in 1 2 3; do
  as "dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' spark-terminal --bench" 2>/dev/null | grep '^bench'
done

echo "--- per-user install and uninstall (no root)"
as "bash ~/spark-terminal/install.sh --user --no-test && ~/.local/bin/spark-terminal --self-test >/dev/null"
as "bash ~/spark-terminal/install.sh --user --uninstall"
left=$(as "find ~/.local -path ~/.local/state -prune -o \( -iname '*spark*terminal*' -o -iname '*SparkTerminal*' \) -print" || true)
if [ -n "$left" ]; then echo "left behind:"; echo "$left"; exit 1; fi
echo "Spark Terminal built into the image, tested, and installed and removed per user"
