#!/usr/bin/env bash
# Run by CI as a normal user inside the SparkOS image (.github/workflows/spark-welcome.yml):
# install Spark Welcome for this user with no root, self-test it, check the first-login
# shortcut and the entries, run the unit tests on the image's Python, uninstall, and check
# that no file was left in the home folder.
#
#   bash tests/ci-user-install.sh /path/to/files/spark-welcome
set -euo pipefail
src=$(cd "${1:?usage: ci-user-install.sh APP_FOLDER}" && pwd)
if [ "$(id -u)" = 0 ]; then echo "run this as a normal user, not root" >&2; exit 1; fi
echo "--- as $(id -un) on $(. /etc/os-release && echo "$PRETTY_NAME"), $(python3 --version)"

files_in_home() { find "$HOME" \( -type f -o -type l \) -printf '%P\n' | sort; }
before=$(mktemp); after=$(mktemp)
files_in_home > "$before"

echo "--- install --user"
bash "$src/install.sh" --user
bin=$HOME/.local/bin/spark-welcome
"$bin" --version

echo "--- what it installed"
test -x "$bin"
test -f "$HOME/.local/lib/spark-welcome/sparkwelcome/app.py"
test -f "$HOME/.local/share/icons/hicolor/256x256/apps/dev.wolklaw.SparkWelcome.png"
menu=$HOME/.local/share/applications/dev.wolklaw.SparkWelcome.desktop
auto=$HOME/.config/autostart/dev.wolklaw.SparkWelcome.desktop
grep -qx "Exec=\"$bin\"" "$menu"
grep -qx "Exec=\"$bin\" --first-login" "$auto"
if command -v desktop-file-validate >/dev/null; then
  desktop-file-validate "$menu"
  desktop-file-validate "$auto"
fi

echo "--- self-test"
"$bin" --self-test

echo "--- first login: exits at once once done exists, without a display"
cfg=$(mktemp -d)
mkdir -p "$cfg/spark-welcome" && touch "$cfg/spark-welcome/done"
start=$(date +%s%N)
env -u DISPLAY -u WAYLAND_DISPLAY XDG_CONFIG_HOME="$cfg" "$bin" --first-login
echo "exited in $(( ($(date +%s%N) - start) / 1000000 )) ms"
rm -rf "$cfg"

echo "--- unit tests on this Python (UI tests skip: no display)"
work=$(mktemp -d)
cp -r "$src/." "$work/"
(cd "$work" && env -u DISPLAY python3 -m unittest discover -s tests)
rm -rf "$work"

echo "--- uninstall"
bash "$src/install.sh" --user --uninstall
test ! -e "$bin"
test ! -e "$auto"
test ! -e "$HOME/.local/lib/spark-welcome"
files_in_home > "$after"
if ! diff -u "$before" "$after"; then
  echo "files were left in the home folder (above)" >&2
  exit 1
fi
echo "--- ok: installed, tested and removed for $(id -un) with no root"
