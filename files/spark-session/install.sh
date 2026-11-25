#!/usr/bin/env bash
# Install the Spark session's security pieces, system-wide (root): the polkit agent
# (spark-polkit), the sign-in screen (spark-greeter) and the files that let `spark greeter`
# turn it on. Nothing is turned on: greetd stays disabled and Plasma Login Manager stays the
# display manager. The session script that starts spark-polkit belongs to the Spark shell
# (files/spark-shell), not to this folder.
#
#   bash install.sh [--root DIR] [--deps] [--no-test]
#
# --root DIR   install into DIR instead of / (staging, tests)
# --deps       install what it needs with dnf first (Fedora)
# --no-test    skip the self-test at the end
#
# This is not an app: no live-update manifest. These files run as root or before anyone is
# signed in, so they change only with the image (see PLAN.md, "Replacing KDE").
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
ROOT=
DEPS=0
TEST=1
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT=${2%/}; shift ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$DEPS" = 1 ]; then
  dnf -y install python3 python3-gobject python3-cairo gobject-introspection gtk4 polkit polkit-libs greetd kwin
fi

PREFIX=$ROOT/usr/lib/spark-session
install -d "$PREFIX/sparksession"
install -m 0644 "$here"/sparksession/*.py "$PREFIX/sparksession/"
python3 -m compileall -q "$PREFIX"

# The system tree: wrappers and helper scripts executable, everything else plain.
while IFS= read -r file; do
  target=$ROOT/${file#./}
  case "$file" in
    ./usr/bin/*|./usr/libexec/*) mode=0755 ;;
    *) mode=0644 ;;
  esac
  install -D -m "$mode" "$here/system/${file#./}" "$target"
done < <(cd "$here/system" && find . -type f | sort)

if [ "$TEST" = 1 ]; then
  PYTHONPATH=$PREFIX python3 -s -m sparksession.polkit_agent --self-test
  PYTHONPATH=$PREFIX python3 -s -m sparksession.polkit_agent --version
  PYTHONPATH=$PREFIX python3 -s -m sparksession.greeter --version
fi
echo "Spark session pieces installed${ROOT:+ into $ROOT}."
