#!/usr/bin/env bash
# Spark Launcher's tests: QML lint on the package, then the Qt Quick tests (search.js on its
# own, and the open launcher with a fake app list). Screenshots go to $SHOTS.
#
#   bash tests/run.sh            needs qmllint and qmltestrunner (Fedora: qt6-qtdeclarative-devel)
#                                and Kirigami (kf6-kirigami); no display needed
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
pkg="$here/../package"
SHOTS=${SHOTS:-/tmp/spark-launcher-shots}
mkdir -p "$SHOTS"

find_tool() {
  for name in "$@"; do
    command -v "$name" 2>/dev/null && return 0
    [ -x "/usr/lib64/qt6/bin/$name" ] && { echo "/usr/lib64/qt6/bin/$name"; return 0; }
  done
  echo "missing: $1 (Fedora: dnf install qt6-qtdeclarative-devel)" >&2
  return 1
}
QMLLINT=$(find_tool qmllint-qt6 qmllint)
RUNNER=$(find_tool qmltestrunner-qt6 qmltestrunner)

echo "--- qmllint"
# Plasma's own modules are C++ plugins with type info; warnings about them are not ours.
# Errors (syntax, unknown properties on our own types) fail the run.
"$QMLLINT" --bare -I /usr/lib64/qt6/qml \
  -W 0 \
  "$pkg"/contents/ui/*.qml "$here"/*.qml
for js in "$pkg"/contents/code/*.js; do
  "$QMLLINT" --bare -W 0 "$js"
done
echo "qmllint: no errors"

echo "--- Qt Quick tests"
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
export QT_QUICK_BACKEND=${QT_QUICK_BACKEND:-software}
export QT_QUICK_CONTROLS_STYLE=${QT_QUICK_CONTROLS_STYLE:-Basic}
# tst_launcher.qml saves its screenshots in /tmp/spark-launcher-shots (QML can't read the
# environment); they're copied to $SHOTS afterwards.
rm -rf /tmp/spark-launcher-shots
mkdir -p /tmp/spark-launcher-shots
"$RUNNER" -input "$here" -import /usr/lib64/qt6/qml
if [ "$SHOTS" != /tmp/spark-launcher-shots ]; then
  cp /tmp/spark-launcher-shots/*.png "$SHOTS"/
fi
echo "screenshots in $SHOTS: $(cd "$SHOTS" && ls ./*.png | tr '\n' ' ')"
