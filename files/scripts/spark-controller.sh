#!/usr/bin/env bash
# Spark Controller: fans, RGB lighting and firmware for the PC (replaces SignalRGB, Armoury
# Crate, NZXT CAM and Fan Xpert). Its source lives in this repo at files/spark-controller.
#
# install.sh --deps installs it system-wide: the window, the fan service (enabled; it starts
# only once curves are saved), the polkit action, the sensor-chip module list (nct6775), the
# udev rules and the login autostart for saved lighting. The self-test reads /sys of the build
# container; the build fails if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-controller"
test -f "$SRC/install.sh" || { echo "Spark Controller source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-controller
test -x /usr/bin/spark-controller-daemon
test -x /usr/libexec/spark-controller-helper
test -f /usr/share/applications/dev.wolklaw.SparkController.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkController.svg
test -f /usr/lib/systemd/system/spark-controller.service
test -f /usr/share/polkit-1/actions/dev.wolklaw.SparkController.policy
test -f /usr/lib/udev/rules.d/71-spark-controller.rules
test -f /etc/xdg/autostart/dev.wolklaw.SparkController.rgb.desktop
grep -qx 'nct6775' /usr/lib/modules-load.d/sparkos-nct6775.conf
[ "$(systemctl is-enabled spark-controller.service)" = enabled ] \
  || { echo "spark-controller.service isn't enabled"; exit 1; }
# The helper's path in the polkit action is what lets pkexec use it
grep -q 'exec.path">/usr/libexec/spark-controller-helper<' \
  /usr/share/polkit-1/actions/dev.wolklaw.SparkController.policy
python3 -c 'import liquidctl' || { echo "python3-liquidctl isn't installed"; exit 1; }
test -x /usr/bin/openrgb
command -v fwupdmgr >/dev/null

# Spark Controller replaces OpenRGB's window; OpenRGB stays as the command it runs
if [ -f /usr/share/applications/org.openrgb.OpenRGB.desktop ]; then
  grep -q '^NoDisplay=true' /usr/share/applications/org.openrgb.OpenRGB.desktop \
    || sed -i '/^\[Desktop Entry\]/a NoDisplay=true' /usr/share/applications/org.openrgb.OpenRGB.desktop
fi

# The helper refuses anything that isn't a fan configuration
if echo '{"fans": 5}' | /usr/libexec/spark-controller-helper install-config 2>/dev/null; then
  echo "the helper accepted a broken configuration"; exit 1
fi
test ! -e /etc/spark-controller/fans.json

report=$(/usr/bin/spark-controller --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
echo "$(/usr/bin/spark-controller --version) installed."
