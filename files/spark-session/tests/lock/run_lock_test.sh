#!/bin/bash
# The lock screen check for the Spark session, in a headless KWin (CI, in a container; see
# .github/workflows/spark-session.yml). It records whether this KWin offers ext-session-lock-v1
# (it does not, as of KWin 6.8, so the Spark session keeps kscreenlocker) and proves the one
# property a lock screen needs: killing the lock screen process does not unlock the session.
#
# Never run this on a desktop. It locks a screen, though only a private headless one, and the
# lock code also sets the logind locked hint of the session it runs in.
set -u
here=$(cd "$(dirname "$0")" && pwd)

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ -z "${SPARK_ALLOW_LOCK_TEST:-}" ]; then
  echo "run_lock_test.sh: looks like a desktop session; set SPARK_ALLOW_LOCK_TEST=1 in a container" >&2
  exit 2
fi
command -v kwin_wayland >/dev/null || { echo "run_lock_test.sh: no kwin_wayland here" >&2; exit 2; }

XDG_RUNTIME_DIR=$(mktemp -d)
chmod 700 "$XDG_RUNTIME_DIR"
export XDG_RUNTIME_DIR QT_QPA_PLATFORM=offscreen
unset DISPLAY WAYLAND_DISPLAY XDG_SESSION_ID

out=$(dbus-run-session -- bash "$here/lock_probe.sh" 2>"$XDG_RUNTIME_DIR/probe.err")
rc=$?
printf '%s\n' "$out"
rm -rf "$XDG_RUNTIME_DIR"

fail=0
expect() {
  grep -qx "$1" <<<"$out" || { echo "FAIL: expected $1" >&2; fail=1; }
}
expect 'LOCK=locked'
expect 'GREETER=running'
expect 'AFTER_GREETER_KILLED=still-locked'
expect 'STILL_LOCKED_AFTER_WAIT=yes'
if grep -qx 'EXT_SESSION_LOCK=yes' <<<"$out"; then
  echo "NOTICE: this KWin offers ext-session-lock-v1. A Spark lock screen is possible now; see files/spark-session/README.md"
fi
[ "$rc" = 0 ] || { echo "FAIL: probe exited $rc" >&2; fail=1; }
exit "$fail"
