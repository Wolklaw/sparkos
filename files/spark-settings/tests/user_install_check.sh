#!/usr/bin/env bash
# Run as root inside the SparkOS image (CI: podman run ... -v files/spark-settings:/src:ro).
# Installs Spark Settings for a normal user with install.sh --user, runs the self-test and the
# tests on the image's own Python and Tk (window tests under Xvfb when the image has it),
# checks the image's stand-ins for systemsettings and kcmshell6, uninstalls, and checks nothing
# is left in ~/.local.
set -euo pipefail

useradd -m tester
home=$(getent passwd tester | cut -d: -f6)
cp -r /src "$home/spark-settings"
chown -R tester: "$home/spark-settings"
# setpriv, not su or runuser: those open a PAM session, which fails in a container
as() {
  (cd "$home" && setpriv --reuid=tester --regid=tester --init-groups \
     env -i HOME="$home" USER=tester LOGNAME=tester PATH=/usr/local/bin:/usr/bin:/bin \
     LANG=C.UTF-8 bash -c "$1")
}
echo "image: $(. /etc/os-release; echo "$PRETTY_NAME"), $(python3 --version), Tk $(python3 -c 'import tkinter; print(tkinter.TkVersion)')"

if [ -x /usr/bin/spark-settings ]; then
  echo "--- the image's own copy and its stand-ins"
  /usr/bin/spark-settings --version
  for tool in systemsettings kcmshell6; do
    grep -q 'spark-settings --route' "/usr/bin/$tool" || { echo "/usr/bin/$tool is not the stand-in"; exit 1; }
    test -x "/usr/libexec/sparkos/kde-settings/$tool" || { echo "the real $tool was not kept"; exit 1; }
  done
  grep -q '^NoDisplay=true' /usr/share/applications/systemsettings.desktop
  /usr/bin/kcmshell6 --list | head -3
else
  echo "(this image was built before Spark Settings: its own copy and stand-ins are checked once it is rebuilt)"
fi

echo "--- install --user"
as "bash ~/spark-settings/install.sh --user"
as "test -x ~/.local/bin/spark-settings"
as "grep -qx 'Exec=$home/.local/bin/spark-settings' ~/.local/share/applications/dev.wolklaw.SparkSettings.desktop"
as "test -f ~/.local/share/icons/hicolor/256x256/apps/dev.wolklaw.SparkSettings.png"

echo "--- the image's tools: self-test with every one required"
if [ -x /usr/bin/spark-settings ]; then
  as "~/.local/bin/spark-settings --self-test --strict"
else
  # an image built before this change: report what is missing, don't fail on it
  as "~/.local/bin/spark-settings --self-test --strict" || echo "(tools missing in this older image: see above)"
fi

echo "--- tests on the image's Python"
run_tests='cd ~/spark-settings && python3 -m unittest discover -s tests -v'
if command -v xvfb-run >/dev/null; then
  as "xvfb-run -a -s '-screen 0 1920x1080x24' $run_tests"
else
  echo "(no xvfb-run in the image: window tests are skipped here; the fedora job runs them)"
  as "$run_tests"
fi

echo "--- uninstall"
as "bash ~/spark-settings/install.sh --user --uninstall"
left=$(as "find ~/.local -path ~/.local/state -prune -o \( -iname '*spark*settings*' -o -iname '*SparkSettings*' \) -print" || true)
if [ -n "$left" ]; then echo "left behind:"; echo "$left"; exit 1; fi
echo "installed, tested and removed without root"
