#!/usr/bin/env bash
# Run as root inside the SparkOS image (CI: podman run ... -v files/spark-files:/src:ro).
# Installs Spark Files for a normal user with install.sh --user, runs the self-test and the
# tests on the image's own Python, Tk and GIO (window tests under Xvfb, D-Bus tests in a
# session bus, when the image has them), uninstalls, and checks nothing is left in ~/.local
# or /usr.
set -euo pipefail

useradd -m tester
home=$(getent passwd tester | cut -d: -f6)
cp -r /src "$home/spark-files"
chown -R tester: "$home/spark-files"
# setpriv, not su or runuser: those open a PAM session, which fails in a container
as() {
  (cd "$home" && setpriv --reuid=tester --regid=tester --init-groups \
     env -i HOME="$home" USER=tester LOGNAME=tester PATH=/usr/local/bin:/usr/bin:/bin \
     LANG=C.UTF-8 bash -c "$1")
}
usr_before=$(find /usr -newer /etc/hostname 2>/dev/null | wc -l)
echo "image: $(. /etc/os-release; echo "$PRETTY_NAME"), $(python3 --version), Tk $(python3 -c 'import tkinter; print(tkinter.TkVersion)')"

echo "--- install --user"
as "bash ~/spark-files/install.sh --user"
as "test -x ~/.local/bin/spark-files"
as "grep -qx 'Exec=$home/.local/bin/spark-files %U' ~/.local/share/applications/dev.wolklaw.SparkFiles.desktop"
as "grep -qx 'Exec=$home/.local/bin/spark-files --service' ~/.local/share/dbus-1/services/org.freedesktop.FileManager1.service"
as "test -f ~/.local/share/icons/hicolor/256x256/apps/dev.wolklaw.SparkFiles.png"
test ! -e /usr/bin/spark-files || grep -q /usr/lib/spark-files /usr/bin/spark-files   # the image's own copy is fine

echo "--- self-test and tests on the image's Python"
as "~/.local/bin/spark-files --version"
as "~/.local/bin/spark-files --self-test"
run_tests='cd ~/spark-files && python3 -m unittest discover -s tests -v'
if command -v dbus-run-session >/dev/null; then
  run_tests="dbus-run-session -- bash -c '$run_tests'"
fi
if command -v xvfb-run >/dev/null; then
  as "xvfb-run -a -s '-screen 0 1920x1080x24' $run_tests"
  as "mkdir -p /tmp/many && for i in \$(seq 1 10000); do : > /tmp/many/f\$i.txt; done"
  as "xvfb-run -a -s '-screen 0 1920x1080x24' ~/.local/bin/spark-files --bench /tmp/many"
else
  echo "(no xvfb-run in the image: window tests are skipped here; the fedora job runs them)"
  as "$run_tests"
fi

echo "--- uninstall"
as "bash ~/spark-files/install.sh --user --uninstall"
left=$(as "find ~/.local -path ~/.local/state -prune -o \( -iname '*spark*files*' -o -iname '*SparkFiles*' -o -name 'org.freedesktop.FileManager1.service' \) -print" || true)
if [ -n "$left" ]; then echo "left behind:"; echo "$left"; exit 1; fi
usr_after=$(find /usr -newer /etc/hostname 2>/dev/null | wc -l)
[ "$usr_before" = "$usr_after" ] || { echo "/usr changed"; exit 1; }
echo "installed, tested and removed without root"
