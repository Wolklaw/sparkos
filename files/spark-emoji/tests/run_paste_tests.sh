#!/bin/bash
# Run the portal tests on a private session bus with nothing on it but the fake portal.
# Needs dbus-run-session; never touches the real session.
set -e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here/.."
export SPARK_EMOJI_FAKE_BUS=1
exec dbus-run-session --config-file="$here/dbus-test.conf" -- python3 -m unittest -v tests.test_paste
