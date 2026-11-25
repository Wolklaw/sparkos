#!/bin/bash
# Runs inside `dbus-run-session` with a private XDG_RUNTIME_DIR (lock_test.sh sets both up).
# Starts a headless KWin, looks for ext-session-lock-v1, locks through org.freedesktop.ScreenSaver,
# kills the lock screen process, and checks the session stays locked. Prints KEY=VALUE lines.
# Never run this on a desktop: it locks a screen (a private, headless one, but still).
set -u
SOCKET=spark-lock-test
say() { printf '%s\n' "$*"; }
saver() {   # method [args]: org.freedesktop.ScreenSaver on the private bus
  dbus-send --session --print-reply --dest=org.freedesktop.ScreenSaver /ScreenSaver \
    "org.freedesktop.ScreenSaver.$1" 2>/dev/null
}
active() { saver GetActive | grep -q 'boolean true'; }

kwin_wayland --virtual --socket "$SOCKET" --no-global-shortcuts >"$XDG_RUNTIME_DIR/kwin.log" 2>&1 &
kwin=$!
trap 'kill "$kwin" 2>/dev/null; wait "$kwin" 2>/dev/null' EXIT

for _ in $(seq 1 100); do [ -S "$XDG_RUNTIME_DIR/$SOCKET" ] && break; sleep 0.1; done
[ -S "$XDG_RUNTIME_DIR/$SOCKET" ] || { say "KWIN=did-not-start"; tail -20 "$XDG_RUNTIME_DIR/kwin.log" >&2; exit 1; }
say "KWIN=$(kwin_wayland --version 2>/dev/null | head -1)"

globals=$(WAYLAND_DISPLAY=$SOCKET wayland-info 2>/dev/null)
if grep -q 'ext_session_lock_manager_v1' <<<"$globals"; then say "EXT_SESSION_LOCK=yes"; else say "EXT_SESSION_LOCK=no"; fi
if grep -q 'ext_idle_notifier_v1' <<<"$globals"; then say "EXT_IDLE_NOTIFY=yes"; else say "EXT_IDLE_NOTIFY=no"; fi

for _ in $(seq 1 100); do saver GetActive >/dev/null && break; sleep 0.1; done
active && { say "LOCKED_AT_START=yes"; } || say "LOCKED_AT_START=no"

dbus-send --session --print-reply --dest=org.freedesktop.ScreenSaver /ScreenSaver \
  org.freedesktop.ScreenSaver.Lock >/dev/null 2>&1
for _ in $(seq 1 100); do active && break; sleep 0.1; done
active && say "LOCK=locked" || { say "LOCK=not-locked"; exit 1; }

for _ in $(seq 1 100); do pgrep -x kscreenlocker_g >/dev/null && break; sleep 0.1; done
first=$(pgrep -x kscreenlocker_g | head -1)
[ -n "$first" ] && say "GREETER=running" || say "GREETER=missing"

if [ -n "$first" ]; then
  kill -9 "$first"
  sleep 1
  active && say "AFTER_GREETER_KILLED=still-locked" || say "AFTER_GREETER_KILLED=UNLOCKED"
  for _ in $(seq 1 100); do
    second=$(pgrep -x kscreenlocker_g | head -1)
    [ -n "$second" ] && [ "$second" != "$first" ] && break
    sleep 0.1
  done
  [ -n "${second:-}" ] && [ "$second" != "$first" ] && say "GREETER_RESTARTED=yes" || say "GREETER_RESTARTED=no"
  active && say "STILL_LOCKED_AFTER_WAIT=yes" || say "STILL_LOCKED_AFTER_WAIT=NO"
  echo "--- processes: $(pgrep -a -f 'kscreenlocker|kwin' | tr '\n' ';')" >&2
  tail -15 "$XDG_RUNTIME_DIR/kwin.log" >&2
fi
