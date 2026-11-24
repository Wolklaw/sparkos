#!/usr/bin/env bash
# Spark Apps: signed live updates for the Spark apps (files/spark-apps). A root service checks
# one signed index and installs newer app bundles into /var/lib/spark-apps without a reboot;
# the launchers in /usr/bin/spark-<app> start the newest verified copy, else the built-in one
# this image carries. Root code (this service, the units, polkit) always comes from the image.
#
# Runs before the apps, so their install.sh finds /usr/lib/spark-apps/launch.py. The index is
# checked against the same public key that verifies the image (cosign.pub, copied by the
# Containerfile to /etc/pki/containers/sparkos.pub). The build stops if it is missing, or if
# the self-test (a throwaway-key round trip with openssl) fails.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-apps"
test -f "$SRC/install.sh" || { echo "Spark Apps source not found at $SRC"; exit 1; }

KEY=/etc/pki/containers/sparkos.pub
test -s "$KEY" || { echo "no $KEY: the Containerfile copies cosign.pub there"; exit 1; }

bash "$SRC/install.sh" --deps --key "$KEY"

test -f /usr/lib/spark-apps/launch.py
test -x /usr/libexec/spark-apps-update
test -f /usr/share/spark-apps/index-key.pub
cmp "$KEY" /usr/share/spark-apps/index-key.pub
test -f /usr/lib/systemd/system/spark-apps-update.timer
test -f /usr/lib/systemd/system/spark-apps-now@.service
test -f /usr/share/polkit-1/rules.d/50-spark-apps.rules
test -e /etc/systemd/system/timers.target.wants/spark-apps-update.timer
/usr/libexec/spark-apps-update self-test | tail -n 1
echo "Spark Apps installed."
