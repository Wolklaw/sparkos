# Spark Connect probe. Spark Connect pipes this file to `sh -s` over SSH and reads one JSON
# document back. It only reads: it starts no service, writes no file, and installs nothing.
#
# What it reads: /proc (uptime, load, CPU, memory, network counters), /sys (temperatures),
# df, ss (the tunnel's connections), systemctl show and journalctl for the units named below,
# the list of failed units, and, on a failover standby, the names, dates and first lines of
# the newest incident files and the last lines of the network monitor's log. It reads no
# other file: no keys, no credentials, no configuration.
#
# Spark Connect puts these settings above this comment (each one quoted for sh); with none set
# the probe still runs and reports the machine itself:
#   SC_UNITS          system units to report, space separated
#   SC_USER_UNITS     user units to report, space separated
#   SC_TUNNEL         the tunnel's unit as user:NAME or system:NAME (empty: no tunnel)
#   SC_FAILOVER_DIR   the failover folder on a standby (empty: not a standby)
#   SC_ACTIVE_UNIT    user:NAME or system:NAME that runs only while the standby has taken over
#   SC_NETMON_LOG     the network monitor's log, relative to SC_FAILOVER_DIR
#   SC_LOCAL_URLS     name=url pairs checked from the server itself (127.0.0.1 health URLs)
#   SC_LOG_LINES      journal lines per unit
#
# Needs only what a stock Ubuntu or Fedora server has: sh, sed, awk, tr, df, and systemctl,
# journalctl, ss, curl when they are there. Without systemd it still prints valid JSON.

LC_ALL=C
export LC_ALL
: "${SC_UNITS:=}" "${SC_USER_UNITS:=}" "${SC_TUNNEL:=}" "${SC_FAILOVER_DIR:=}"
: "${SC_ACTIVE_UNIT:=}" "${SC_NETMON_LOG:=}" "${SC_LOCAL_URLS:=}" "${SC_LOG_LINES:=5}"
case $SC_LOG_LINES in ''|*[!0-9]*) SC_LOG_LINES=5 ;; esac
# systemctl --user needs the user's runtime folder; a non-interactive SSH login may not set it
if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
  XDG_RUNTIME_DIR=/run/user/$(id -u)
  export XDG_RUNTIME_DIR
fi

# ─── JSON helpers ─────────────────────────────────────────────
# str: one JSON string from $1. lines: a JSON array of strings, one per stdin line.
clean() { tr -d '\000-\010\013-\037' | tr '\t' ' ' | cut -c1-400; }
str() { printf '%s' "$1" | clean | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' \
          | awk 'BEGIN{printf "\""} NR>1{printf " "} {printf "%s",$0} END{printf "\""}'; }
lines() { clean | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' \
          | awk 'BEGIN{printf "["} NR>1{printf ","} {printf "\"%s\"",$0} END{printf "]"}'; }
num() { case $1 in ''|-|.|*[!0-9.-]*) printf 'null' ;; *) printf '%s' "$1" ;; esac; }
have() { command -v "$1" >/dev/null 2>&1; }

SYSTEMD=false
if have systemctl && [ -d /run/systemd/system ]; then SYSTEMD=true; fi

# ─── the machine ──────────────────────────────────────────────
up=$(awk '{print int($1)}' /proc/uptime 2>/dev/null)
now=$(date +%s)
os=$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release 2>/dev/null | tr -d '"')
cpus=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null)
set -- $(cat /proc/loadavg 2>/dev/null)
l1=${1:-}; l5=${2:-}; l15=${3:-}
cpu1=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8+$9, $5+$6; exit}' /proc/stat 2>/dev/null)
sleep 0.3 2>/dev/null || sleep 1
cpu2=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8+$9, $5+$6; exit}' /proc/stat 2>/dev/null)
cpu=$(echo "$cpu1 $cpu2" | awk 'NF==4 && $3>$1 {printf "%.1f", 100*(1-($4-$2)/($3-$1))}')
mem=$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2}
           END{printf "%s %s %s %s", t*1024, a*1024, st*1024, sf*1024}' /proc/meminfo 2>/dev/null)
set -- $mem

printf '{"probe":1,"time":%s,"hostname":%s,"os":%s,"kernel":%s,"systemd":%s,' \
  "$(num "$now")" "$(str "$(uname -n)")" "$(str "$os")" "$(str "$(uname -r)")" "$SYSTEMD"
printf '"uptime_s":%s,"cpus":%s,"load":[%s,%s,%s],"cpu_pct":%s,' \
  "$(num "$up")" "$(num "$cpus")" "$(num "$l1")" "$(num "$l5")" "$(num "$l15")" "$(num "$cpu")"
printf '"memory":{"total":%s,"available":%s,"swap_total":%s,"swap_free":%s},' \
  "$(num "${1:-}")" "$(num "${2:-}")" "$(num "${3:-}")" "$(num "${4:-}")"

# disks: one entry per real filesystem
printf '"disks":['
df -P -k -x tmpfs -x devtmpfs -x squashfs -x overlay -x efivarfs 2>/dev/null \
  | awk 'NR>1 && $2>0 {gsub(/"/,"",$6); gsub(/\\/,"",$6);
         printf "%s{\"mount\":\"%s\",\"size\":%d,\"used\":%d,\"free\":%d}", (n++?",":""),
         $6, $2*1024, $3*1024, $4*1024}'
printf '],'

# temperatures, in degrees C: thermal zones and hwmon sensors
printf '"temps":['
first=1
for f in /sys/class/thermal/thermal_zone*/temp /sys/class/hwmon/hwmon*/temp*_input; do
  [ -r "$f" ] || continue
  v=$(cat "$f" 2>/dev/null)
  case $v in ''|*[!0-9-]*) continue ;; esac
  d=${f%/*}
  case $f in
    */thermal_zone*) name=$(cat "$d/type" 2>/dev/null) ;;
    *) name=$(cat "$d/name" 2>/dev/null); lab=$(cat "${f%_input}_label" 2>/dev/null)
       [ -n "$lab" ] && name="$name $lab" ;;
  esac
  [ $first = 1 ] || printf ','
  first=0
  printf '{"name":%s,"c":%s}' "$(str "$name")" "$(awk -v v="$v" 'BEGIN{printf "%.1f", v/1000}')"
done
printf '],'

# network: bytes since boot per interface (Spark Connect works out the rate)
printf '"net":['
awk -F'[: ]+' 'NR>2 {o=($1==""?1:0); i=$(1+o);
     if (i!="lo") printf "%s{\"iface\":\"%s\",\"rx\":%s,\"tx\":%s}", (n++?",":""), i, $(2+o), $(10+o)}' \
  /proc/net/dev 2>/dev/null
printf '],'

# ─── units ────────────────────────────────────────────────────
# unit SCOPE NAME: one JSON object. SCOPE is system or user.
unit() {
  if [ "$1" = user ]; then sc="systemctl --user"; jc="journalctl --user"
  else sc="systemctl"; jc="journalctl"; fi
  props=$($sc show "$2" --no-pager -p LoadState -p ActiveState -p SubState -p NRestarts \
            -p StateChangeTimestampMonotonic -p Result -p Description 2>/dev/null)
  get() { printf '%s\n' "$props" | sed -n "s/^$1=//p" | head -n1; }
  since=$(get StateChangeTimestampMonotonic)
  case $since in ''|*[!0-9]*) ago= ;; 0) ago= ;; *) ago=$(( ${up:-0} - since / 1000000 )) ;; esac
  printf '{"name":%s,"scope":"%s","load":%s,"active":%s,"sub":%s,"result":%s,"restarts":%s,' \
    "$(str "$2")" "$1" "$(str "$(get LoadState)")" "$(str "$(get ActiveState)")" \
    "$(str "$(get SubState)")" "$(str "$(get Result)")" "$(num "$(get NRestarts)")"
  printf '"since_s":%s,"description":%s,"log":' "$(num "$ago")" "$(str "$(get Description)")"
  $jc -u "$2" -n "$SC_LOG_LINES" --no-pager -o short-iso -q 2>/dev/null | tail -n "$SC_LOG_LINES" | lines
  printf '}'
}

printf '"units":['
first=1
if [ "$SYSTEMD" = true ]; then
  for u in $SC_UNITS; do [ $first = 1 ] || printf ','; first=0; unit system "$u"; done
  for u in $SC_USER_UNITS; do [ $first = 1 ] || printf ','; first=0; unit user "$u"; done
fi
printf '],'

printf '"failed":['
if [ "$SYSTEMD" = true ]; then
  { systemctl list-units --state=failed --no-legend --plain --no-pager 2>/dev/null \
      | awk '{print "system " $1}'
    systemctl --user list-units --state=failed --no-legend --plain --no-pager 2>/dev/null \
      | awk '{print "user " $1}'; } \
    | awk '{printf "%s{\"scope\":\"%s\",\"name\":\"%s\"}", (n++?",":""), $1, $2}'
fi
printf '],'

# ─── tunnel ───────────────────────────────────────────────────
scope_of() { case $1 in user:*) echo user ;; *) echo system ;; esac; }
name_of() { echo "${1#*:}"; }
state_of() {   # active state of user:NAME or system:NAME
  if [ "$SYSTEMD" != true ]; then echo unknown; return; fi
  if [ "$(scope_of "$1")" = user ]; then systemctl --user is-active "$(name_of "$1")" 2>/dev/null
  else systemctl is-active "$(name_of "$1")" 2>/dev/null; fi
}
if [ -n "$SC_TUNNEL" ]; then
  t=$(name_of "$SC_TUNNEL")
  conns=
  if [ "$(scope_of "$SC_TUNNEL")" = user ] || [ "$(id -u)" = 0 ]; then
    # QUIC tunnels hold UDP sockets, older ones TCP; ss shows a socket's owner only for your
    # own processes, which a user unit is
    if have ss; then conns=$(ss -Htunp 2>/dev/null | grep -c "\"$t\"" ); fi
  elif have curl && have journalctl; then
    # A system unit runs as someone else, so ss can't tell its sockets apart. Ask cloudflared:
    # its metrics server's /ready gives readyConnections. The address is in the unit's log.
    # If the log can't be read, the count stays unknown rather than a false 0.
    addr=$(journalctl -u "$t" -b -o cat --no-pager 2>/dev/null \
      | sed -n 's/.*[Ss]tarting metrics server on \([0-9.:]*\).*/\1/p' | tail -n 1)
    case $addr in
      127.0.0.1:*|localhost:*)
        conns=$(curl -s -m 3 "http://$addr/ready" 2>/dev/null \
          | sed -n 's/.*"readyConnections":\([0-9]*\).*/\1/p') ;;
    esac
  fi
  printf '"tunnel":{"unit":%s,"active":%s,"connections":%s},' \
    "$(str "$SC_TUNNEL")" "$(str "$(state_of "$SC_TUNNEL")")" "$(num "$conns")"
else
  printf '"tunnel":null,'
fi

# ─── failover standby ─────────────────────────────────────────
if [ -n "$SC_FAILOVER_DIR" ]; then
  dir=$SC_FAILOVER_DIR
  case $dir in "~") dir=$HOME ;; "~/"*) dir="$HOME/${dir#\~/}" ;; esac
  active=
  [ -n "$SC_ACTIVE_UNIT" ] && active=$(state_of "$SC_ACTIVE_UNIT")
  printf '"failover":{"dir_found":%s,"active_unit":%s,"active_state":%s,"incidents":[' \
    "$([ -d "$dir" ] && echo true || echo false)" "$(str "$SC_ACTIVE_UNIT")" "$(str "$active")"
  first=1
  if [ -d "$dir/incidents" ]; then
    for f in $(ls -1t "$dir/incidents" 2>/dev/null | head -n 5); do
      [ -f "$dir/incidents/$f" ] || continue
      [ $first = 1 ] || printf ','
      first=0
      printf '{"name":%s,"mtime":%s,"first_line":%s}' "$(str "$f")" \
        "$(num "$(stat -c %Y "$dir/incidents/$f" 2>/dev/null)")" \
        "$(str "$(head -n 1 "$dir/incidents/$f" 2>/dev/null)")"
    done
  fi
  printf '],"netmon":'
  if [ -n "$SC_NETMON_LOG" ] && [ -f "$dir/$SC_NETMON_LOG" ]; then
    tail -n 8 "$dir/$SC_NETMON_LOG" 2>/dev/null | lines
  else
    printf '[]'
  fi
  printf '},'
else
  printf '"failover":null,'
fi

# ─── health URLs checked from the server itself ───────────────
printf '"local_checks":['
first=1
for pair in $SC_LOCAL_URLS; do
  name=${pair%%=*}; url=${pair#*=}
  code=; ms=; err=
  if have curl; then
    out=$(curl -s -o /dev/null -m 5 -w '%{http_code} %{time_total}' "$url" 2>/dev/null)
    code=${out%% *}; secs=${out#* }
    ms=$(awk -v s="$secs" 'BEGIN{printf "%d", s*1000}')
    [ "$code" = 000 ] && { code=; ms=; err="no answer"; }
  else
    err="curl is not installed"
  fi
  [ $first = 1 ] || printf ','
  first=0
  printf '{"name":%s,"url":%s,"status":%s,"ms":%s,"error":%s}' "$(str "$name")" "$(str "$url")" \
    "$(num "$code")" "$(num "$ms")" "$(str "$err")"
done
printf ']}\n'
