#!/usr/bin/env bash
# Install Spark Launcher, SparkOS's app menu (a Plasma widget), for the whole system or one user.
#
#   bash install.sh [--no-test]                 system-wide (the image build), root
#   bash install.sh --uninstall                 remove the system-wide install, root
#   bash install.sh --user [--no-test]          just you, into ~/.local/share/plasma; no root
#   bash install.sh --user --uninstall          remove what --user installed
#   bash install.sh --self-test                 check what it needs; no display needed
#
# It's a widget, not a program: installing it adds "Spark Launcher" to Plasma's widget list.
# The SparkOS desktop layout puts it on the dock and the top bar in place of Kickoff; with
# --user, add it yourself (right-click the panel, Add Widgets) or swap it for Kickoff there.
# Pinned apps are kept by Plasma (~/.local/share/kactivitymanagerd); --uninstall leaves them.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
ID=dev.wolklaw.sparklauncher
NAME="Spark Launcher"
TEST=1
USER_MODE=0
UNINSTALL=0
SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --deps) ;;                                   # nothing to add: Plasma has what it needs
    --no-test) TEST=0 ;;
    --self-test) SELF_TEST=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

version() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["KPlugin"]["Version"])' "$1/metadata.json"
}

# What the widget needs from Plasma, and where it is installed. Exit 1 if anything is missing.
self_test() {
  local fail=0 qml dir where="" installed
  for dir in "${XDG_DATA_HOME:-$HOME/.local/share}/plasma/plasmoids/$ID" "/usr/share/plasma/plasmoids/$ID"; do
    [ -f "$dir/metadata.json" ] && { where=$dir; break; }
  done
  installed=${where:-no (the package in $here/package is checked instead)}
  where=${where:-$here/package}
  echo "$NAME $(version "$where") self-test"
  echo "installed: $installed"
  for f in metadata.json contents/config/main.xml contents/ui/main.qml contents/ui/Launcher.qml \
           contents/code/search.js contents/code/strings.js; do
    [ -f "$where/$f" ] || { echo "missing:   $where/$f"; fail=1; }
  done
  grep -q '"org.kde.plasma.launchermenu"' "$where/metadata.json" \
    && echo "meta key:  opens it (it provides org.kde.plasma.launchermenu)" \
    || { echo "meta key:  metadata.json doesn't provide org.kde.plasma.launchermenu"; fail=1; }
  # Plasma's QML modules it uses: Kickoff's models, session actions, the command runner
  qml=""
  for dir in /usr/lib64/qt6/qml /usr/lib/qt6/qml /usr/lib/x86_64-linux-gnu/qt6/qml; do
    [ -d "$dir/org/kde" ] && { qml=$dir; break; }
  done
  for mod in org/kde/plasma/private/kicker org/kde/plasma/private/sessions \
             org/kde/plasma/plasma5support org/kde/plasma/plasmoid org/kde/kirigami; do
    if [ -n "$qml" ] && [ -f "$qml/$mod/qmldir" ]; then
      echo "module:    ${mod//\//.}"
    else
      echo "missing:   QML module ${mod//\//.} (Plasma 6)"; fail=1
    fi
  done
  if command -v spark-calc >/dev/null && [ "$(spark-calc --eval '0.1+0.2' 2>/dev/null)" = "0.3" ]; then
    echo "sums:      spark-calc answers (0.1+0.2 = 0.3)"
  else
    echo "sums:      spark-calc not found; typed sums show no answer (everything else works)"
  fi
  if command -v kpackagetool6 >/dev/null; then
    echo "packages:  kpackagetool6"
  else
    echo "missing:   kpackagetool6"; fail=1
  fi
  if [ "$fail" = 0 ]; then echo "self-test passed"; else echo "FAILED"; fi
  return "$fail"
}

if [ "$SELF_TEST" = 1 ]; then
  self_test
  exit $?
fi

command -v kpackagetool6 >/dev/null || { echo "install.sh: kpackagetool6 not found (Plasma 6)" >&2; exit 1; }

# kpackagetool6 installs, or upgrades when it's already there
put() {   # $@: extra kpackagetool6 options (-g for system-wide)
  if kpackagetool6 "$@" -t Plasma/Applet --show "$ID" >/dev/null 2>&1; then
    kpackagetool6 "$@" -t Plasma/Applet --upgrade "$here/package"
  else
    kpackagetool6 "$@" -t Plasma/Applet --install "$here/package"
  fi
}

if [ "$USER_MODE" = 1 ]; then
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || { echo "install.sh --user: HOME is not set" >&2; exit 1; }
  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    exit 1
  fi
  if [ "$UNINSTALL" = 1 ]; then
    if kpackagetool6 -t Plasma/Applet --show "$ID" 2>/dev/null | grep -q "$HOME"; then
      kpackagetool6 -t Plasma/Applet --remove "$ID"
      echo "$NAME removed for $(id -un)."
    else
      echo "$NAME isn't installed for $(id -un)."
    fi
    exit 0
  fi
  put
  echo "$NAME $(version "$here/package") installed for $(id -un). Add it to a panel: right-click"
  echo "the panel, Add Widgets, search Spark Launcher. Remove it with:"
  echo "  bash $here/install.sh --user --uninstall"
  if [ "$TEST" = 1 ]; then self_test; fi
  exit 0
fi

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: system-wide needs root. For just you, without root: install.sh --user" >&2
  exit 1
fi
if [ "$UNINSTALL" = 1 ]; then
  rm -rf -- "/usr/share/plasma/plasmoids/$ID"
  echo "$NAME removed from the system."
  exit 0
fi
# Copied, not through kpackagetool6 -g: it writes the same files and the build container
# has no session for it to talk to.
rm -rf -- "/usr/share/plasma/plasmoids/$ID"
install -d "/usr/share/plasma/plasmoids/$ID"
cp -r "$here/package/." "/usr/share/plasma/plasmoids/$ID/"
find "/usr/share/plasma/plasmoids/$ID" -type d -exec chmod 0755 {} + -o -type f -exec chmod 0644 {} +
echo "$NAME $(version "$here/package") installed in /usr/share/plasma/plasmoids/$ID."
if [ "$TEST" = 1 ]; then self_test; fi
