#!/usr/bin/env bash
# Run as a normal user (CI does, in Fedora and inside the SparkOS image): install Spark Games for
# this user with no root, run its self-test, uninstall it, and check nothing is left in ~/.local.
#
#   bash tests/user_install_check.sh <spark-games source folder>
set -euxo pipefail

src=${1:?usage: user_install_check.sh <spark-games source folder>}
if [ "$(id -u)" = 0 ]; then
  echo "run this as a normal user, not root" >&2
  exit 1
fi

bash "$src/install.sh" --user
test -x ~/.local/bin/spark-games
test -f ~/.local/lib/spark-games/sparkgames/app.py
test -f ~/.local/share/applications/dev.wolklaw.SparkGames.desktop
~/.local/bin/spark-games --version
~/.local/bin/spark-games --self-test

bash "$src/install.sh" --user --uninstall
test ! -e ~/.local/bin/spark-games
test ! -e ~/.local/lib/spark-games
test ! -e ~/.local/share/applications/dev.wolklaw.SparkGames.desktop
left=$(find ~/.local -type f 2>/dev/null || true)
if [ -n "$left" ]; then
  echo "left behind after --uninstall:"
  echo "$left"
  exit 1
fi
echo "user install check passed"
