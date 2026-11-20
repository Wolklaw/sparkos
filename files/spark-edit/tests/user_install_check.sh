#!/usr/bin/env bash
# Run as root inside the SparkOS image (CI: podman run ... -v files/spark-edit:/src:ro).
# Installs Spark Edit for a normal user with install.sh --user, runs the self-test and the
# tests on the image's own Python and Tk, measures opening a 50 MB log file, uninstalls, and
# checks nothing is left in ~/.local or /usr.
set -euo pipefail

useradd -m tester
home=$(getent passwd tester | cut -d: -f6)
cp -r /src "$home/spark-edit"
chown -R tester: "$home/spark-edit"
# setpriv, not su or runuser: those open a PAM session, which fails in a container
as() {
  (cd "$home" && setpriv --reuid=tester --regid=tester --init-groups \
     env -i HOME="$home" USER=tester LOGNAME=tester PATH=/usr/local/bin:/usr/bin:/bin \
     LANG=C.UTF-8 bash -c "$1")
}
usr_before=$(find /usr -newer /etc/hostname 2>/dev/null | wc -l)
echo "image: $(. /etc/os-release; echo "$PRETTY_NAME"), $(python3 --version), Tk $(python3 -c 'import tkinter; print(tkinter.TkVersion)')"

echo "--- install --user"
as "bash ~/spark-edit/install.sh --user"
as "test -x ~/.local/bin/spark-edit"
as "grep -qx 'Exec=$home/.local/bin/spark-edit %F' ~/.local/share/applications/dev.wolklaw.SparkEdit.desktop"
as "test -f ~/.local/share/icons/hicolor/256x256/apps/dev.wolklaw.SparkEdit.png"
test ! -e /usr/bin/spark-edit
test ! -e /usr/share/applications/dev.wolklaw.SparkEdit.desktop

echo "--- self-test and tests on the image's Python"
as "~/.local/bin/spark-edit --version"
as "~/.local/bin/spark-edit --self-test"
if command -v xvfb-run >/dev/null; then
  as "cd ~/spark-edit && xvfb-run -a -s '-screen 0 1920x1080x24' python3 -m unittest discover -s tests -v"
  as "python3 ~/spark-edit/tests/make_log.py /tmp/big.log 50"
  as "xvfb-run -a -s '-screen 0 1920x1080x24' ~/.local/bin/spark-edit --bench"
  as "xvfb-run -a -s '-screen 0 1920x1080x24' ~/.local/bin/spark-edit --bench /tmp/big.log"
else
  echo "(no xvfb-run in the image: window tests are skipped here; the fedora job runs them)"
  as "cd ~/spark-edit && python3 -m unittest discover -s tests -v"
fi

echo "--- uninstall"
as "bash ~/spark-edit/install.sh --user --uninstall"
left=$(as "find ~/.local -path ~/.local/state -prune -o \( -iname '*spark*edit*' -o -iname '*SparkEdit*' \) -print" || true)
if [ -n "$left" ]; then echo "left behind:"; echo "$left"; exit 1; fi
usr_after=$(find /usr -newer /etc/hostname 2>/dev/null | wc -l)
[ "$usr_before" = "$usr_after" ] || { echo "/usr changed"; exit 1; }
echo "installed, tested and removed without root"
