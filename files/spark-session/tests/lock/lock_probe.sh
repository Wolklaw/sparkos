#!/bin/bash
# Runs inside `dbus-run-session` with a private XDG_RUNTIME_DIR (run_lock_test.sh sets both up).
# Starts a headless Spark compositor with three outputs, locks it with the Spark lock screen
# (spark-shell --lock), kills the lock screen, and checks the session stays locked and a new lock
# screen can take over. Prints KEY=VALUE lines.
# Never run this on a desktop: it locks a screen (a private, headless one, but still).
set -u
say() { printf '%s\n' "$*"; }
log=$XDG_RUNTIME_DIR/compositor.log
cfg=$XDG_RUNTIME_DIR/cfg
mkdir -p "$cfg"
printf 'output HEADLESS-1 mode=1920x1080@60 pos=0,0\noutput HEADLESS-2 mode=1920x1080@60 pos=1920,0\noutput HEADLESS-3 mode=1920x1080@60 pos=3840,0\n' >"$cfg/outputs.conf"
export SPARK_HEADLESS_OUTPUTS=3 WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 SPARK_COMPOSITOR_CONFIG_DIR=$cfg

coproc COMP { spark-compositor -d 2>"$log"; }
comp=$COMP_PID
lockers=()
cleanup() { kill "${lockers[@]}" "$comp" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

read -r -t 20 line <&"${COMP[0]}" || line=
case "$line" in
  WAYLAND_DISPLAY=*) export WAYLAND_DISPLAY=${line#WAYLAND_DISPLAY=} ;;
  *) say "COMPOSITOR=did-not-start"; tail -20 "$log" >&2; exit 1 ;;
esac
say "COMPOSITOR=running"
export GDK_BACKEND=wayland GSK_RENDERER=cairo

if command -v wayland-info >/dev/null; then
  grep -q ext_session_lock_manager_v1 <<<"$(wayland-info 2>/dev/null)" \
    && say "EXT_SESSION_LOCK=yes" || say "EXT_SESSION_LOCK=no"
fi

count() { grep -c "$1" "$log"; }
wait_count() {   # pattern n: wait until the log has n lines matching
  for _ in $(seq 1 150); do [ "$(count "$1")" -ge "$2" ] && return 0; sleep 0.1; done
  return 1
}

spark-shell --lock >"$XDG_RUNTIME_DIR/lock1.log" 2>&1 &
first=$!
lockers+=("$first")
wait_count 'session locked' 1 && say "LOCK=locked" || { say "LOCK=not-locked"; tail -20 "$XDG_RUNTIME_DIR/lock1.log" "$log" >&2; exit 1; }
say "GREETER=running"

kill -9 "$first"
sleep 1
if [ "$(count 'session unlocked')" = 0 ] && kill -0 "$comp" 2>/dev/null; then
  say "AFTER_GREETER_KILLED=still-locked"
else
  say "AFTER_GREETER_KILLED=UNLOCKED"
fi

spark-shell --lock >"$XDG_RUNTIME_DIR/lock2.log" 2>&1 &
lockers+=("$!")
wait_count 'session locked' 2 && say "GREETER_RESTARTED=yes" || say "GREETER_RESTARTED=no"
[ "$(count 'session unlocked')" = 0 ] && say "STILL_LOCKED_AFTER_WAIT=yes" || say "STILL_LOCKED_AFTER_WAIT=NO"
tail -15 "$log" >&2
