#!/usr/bin/env bash
# Runs a command inside a session that has KWin and no plasmashell: a private D-Bus daemon, a
# headless kwin_wayland (--virtual, no screen of anyone's is touched), and the XDG portals
# started by hand. This is what the Spark session looks like to an app.
#
#   kwin-only.sh COMMAND [ARGS...]
#
# The command sees WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS, XDG_RUNTIME_DIR and a throwaway
# HOME. XDG_CURRENT_DESKTOP is "Spark" on purpose: apps must pick their backend by what is on
# the bus, not by the desktop's name.
#
# Why a private dbus-daemon with its own service folder: the stock service files carry
# SystemdService=, and a private bus would then ask the user's real `systemd --user` to start
# the service (it did, on a developer's PC: a portal came up in their live session). The copies
# made here drop that line, so everything starts as a plain child of this script.
set -u

die() { echo "kwin-only: $*" >&2; exit 2; }
for tool in dbus-daemon kwin_wayland gdbus; do
  command -v "$tool" >/dev/null || die "$tool is not installed"
done
[ "$#" -gt 0 ] || die "usage: kwin-only.sh COMMAND [ARGS...]"

WORK=$(mktemp -d)
export XDG_RUNTIME_DIR="$WORK/run"
export HOME="$WORK/home"
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME/xdg-desktop-portal" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$WORK/services"
chmod 700 "$XDG_RUNTIME_DIR"
unset DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS DBUS_STARTER_ADDRESS DBUS_STARTER_BUS_TYPE
unset XDG_SESSION_ID XDG_SEAT XDG_VTNR XAUTHORITY SSH_AUTH_SOCK

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
  done
  sleep 0.3
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null
  done
  rm -rf "$WORK"
}
trap cleanup EXIT

# ── the bus, with service files that cannot reach systemd ──
for f in /usr/share/dbus-1/services/*.service; do
  [ -e "$f" ] || continue
  grep -v '^SystemdService=' "$f" > "$WORK/services/$(basename "$f")"
done
cat > "$WORK/bus.conf" <<EOF
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:path=$XDG_RUNTIME_DIR/bus</listen>
  <auth>EXTERNAL</auth>
  <servicedir>$WORK/services</servicedir>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
EOF
dbus-daemon --config-file="$WORK/bus.conf" --nofork --nopidfile >"$WORK/bus.log" 2>&1 &
PIDS+=($!)
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
for _ in $(seq 40); do [ -S "$XDG_RUNTIME_DIR/bus" ] && break; sleep 0.25; done
[ -S "$XDG_RUNTIME_DIR/bus" ] || die "the private bus did not start"

# ── KWin alone ──
kwin_wayland --virtual --no-lockscreen --no-global-shortcuts --socket spark-test-0 \
  >"$WORK/kwin.log" 2>&1 &
PIDS+=($!)
for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/spark-test-0" ] && break; sleep 0.5; done
[ -S "$XDG_RUNTIME_DIR/spark-test-0" ] || { cat "$WORK/kwin.log" >&2; die "kwin_wayland did not start"; }
export WAYLAND_DISPLAY=spark-test-0
export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=Spark
# What a real session does at login: bus-activated services (kded6, kio-fuse) inherit it.
dbus-update-activation-environment WAYLAND_DISPLAY XDG_SESSION_TYPE 2>/dev/null || true

names() {
  gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.ListNames 2>/dev/null
}
for _ in $(seq 40); do names | grep -q "'org.kde.KWin.ScreenShot2'" && break; sleep 0.25; done
names | grep -q "'org.kde.KWin.ScreenShot2'" || die "KWin never offered ScreenShot2"
if names | grep -qE "'org.kde.plasmashell'|'org.kde.KSplash'|'org.kde.ksmserver'|'org.kde.Shutdown'"; then
  die "a Plasma shell service is on the bus: this is not a Plasma-free session"
fi

# ── portals, started by hand (KDE's backend only: it talks to KWin, not to plasmashell) ──
if [ "${KWIN_ONLY_PORTALS:-1}" = 1 ] && [ -x /usr/libexec/xdg-desktop-portal ]; then
  printf '[preferred]\ndefault=kde\n' > "$XDG_CONFIG_HOME/xdg-desktop-portal/portals.conf"
  for impl in xdg-permission-store; do
    [ -x "/usr/libexec/$impl" ] && { "/usr/libexec/$impl" >"$WORK/$impl.log" 2>&1 & PIDS+=($!); }
  done
  [ -x /usr/libexec/xdg-desktop-portal-kde ] && {
    XDG_CURRENT_DESKTOP=${KWIN_ONLY_PORTAL_DESKTOP:-KDE} /usr/libexec/xdg-desktop-portal-kde >"$WORK/portal-kde.log" 2>&1 & PIDS+=($!); }
  /usr/libexec/xdg-desktop-portal >"$WORK/portal.log" 2>&1 &
  PIDS+=($!)
  for _ in $(seq 40); do names | grep -q "'org.freedesktop.portal.Desktop'" && break; sleep 0.25; done
fi
export KWIN_ONLY_WORK="$WORK"


"$@"
rc=$?
if [ "$rc" -ne 0 ]; then
  for log in kwin portal portal-kde; do
    [ -s "$WORK/$log.log" ] && { echo "--- $log.log (tail)" >&2; tail -n 15 "$WORK/$log.log" >&2; }
  done
fi
exit "$rc"
