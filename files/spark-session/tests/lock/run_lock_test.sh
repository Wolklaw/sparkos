#!/bin/bash
# The lock screen check for the Spark session, in a headless Spark compositor (CI, in a container;
# see .github/workflows/spark-session.yml). It proves the property a lock screen needs: killing
# the lock screen process does not unlock the session, and a new lock screen takes over.
#
# Never run this on a desktop. It locks a screen, though only a private headless one, and the
# lock code also sets the logind locked hint of the session it runs in.
set -u
here=$(cd "$(dirname "$0")" && pwd)

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ -z "${SPARK_ALLOW_LOCK_TEST:-}" ]; then
  echo "run_lock_test.sh: looks like a desktop session; set SPARK_ALLOW_LOCK_TEST=1 in a container" >&2
  exit 2
fi
command -v spark-compositor >/dev/null || { echo "run_lock_test.sh: no spark-compositor here" >&2; exit 2; }

XDG_RUNTIME_DIR=$(mktemp -d)
chmod 700 "$XDG_RUNTIME_DIR"
export XDG_RUNTIME_DIR
unset DISPLAY WAYLAND_DISPLAY XDG_SESSION_ID

out=$(dbus-run-session -- bash "$here/lock_probe.sh" 2>"$XDG_RUNTIME_DIR/probe.err")
rc=$?
printf '%s\n' "$out"
cat "$XDG_RUNTIME_DIR/probe.err" >&2
rm -rf "$XDG_RUNTIME_DIR"

fail=0
expect() {
  grep -qx "$1" <<<"$out" || { echo "FAIL: expected $1" >&2; fail=1; }
}
expect 'LOCK=locked'
expect 'GREETER=running'
expect 'AFTER_GREETER_KILLED=still-locked'
expect 'GREETER_RESTARTED=yes'
expect 'STILL_LOCKED_AFTER_WAIT=yes'
[ "$rc" = 0 ] || { echo "FAIL: probe exited $rc" >&2; fail=1; }
exit "$fail"
