#!/usr/bin/env bash
# The Spark session's security pieces (Containerfile step 5): the polkit agent, the sign-in
# screen and `spark greeter`'s helper files. Their source lives in this repo at
# files/spark-session. greetd stays off here; sparkos-no-kde.sh, the last step, turns it on.
# The build fails if something turned it on earlier.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-session"
test -f "$SRC/install.sh" || { echo "Spark session source not found at $SRC"; exit 1; }

bash "$SRC/install.sh"

test -x /usr/bin/spark-polkit
test -x /usr/bin/spark-greeter
test -x /usr/libexec/spark-greeter-session
test -x /usr/libexec/spark-greeter-ctl
test -x /usr/libexec/spark-shadow-entry
test -f /usr/share/spark-session/greetd-config.toml
test -f /usr/lib/systemd/system/greetd.service.d/10-spark-greeter.conf
test -f /usr/lib/systemd/system/spark-greeter-fallback.service
test -f /usr/share/polkit-1/rules.d/50-spark-greeter.rules
test -f /usr/lib/tmpfiles.d/spark-greeter.conf
rpm -q greetd

# Nothing may have been turned on, and the display manager must still be the one it was.
if find /etc/systemd/system -path '*.wants/*' -name 'greetd.service' | grep -q .; then
  echo "greetd is enabled before sparkos-no-kde.sh; it must stay off until then"; exit 1
fi
if [ -L /etc/systemd/system/display-manager.service ]; then
  dm=$(basename "$(readlink /etc/systemd/system/display-manager.service)")
  [ "$dm" != greetd.service ] || { echo "display-manager.service points at greetd"; exit 1; }
  echo "display-manager.service -> $dm (unchanged)"
fi
grep -q '^user = "greetd"$' /usr/share/spark-session/greetd-config.toml
# The shipped copy of greetd's own config must be the package's until sparkos-no-kde.sh
if grep -q spark-greeter /etc/greetd/config.toml 2>/dev/null; then
  echo "/etc/greetd/config.toml already points at the Spark greeter"; exit 1
fi

# spark greeter status reads the image, changes nothing
/usr/libexec/spark-greeter-ctl status
/usr/bin/spark-polkit --version
/usr/bin/spark-greeter --version
test -f /etc/pam.d/spark-lock
echo "Spark session pieces installed; sparkos-no-kde.sh turns greetd on."
