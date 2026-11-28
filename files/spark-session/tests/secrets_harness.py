"""Shared by the Spark Secrets tests: a keyring made by the real gnome-keyring-daemon."""

import os
import shutil
import subprocess
import tempfile

ITEMS = [
    ('First thing', {'service': 'example', 'user': 'alice'}, 's3cret one'),
    ('Second', {'service': 'other', 'user': 'bob'}, 'päss wörd ✓'),
]
PASSWORD = 'hunter2'

SCRIPT = r'''
set -e
unset WAYLAND_DISPLAY DISPLAY
printf '%s' "$GK_PASSWORD" | gnome-keyring-daemon --unlock --components=secrets --foreground >"$HOME/gk.out" 2>&1 &
gk=$!
for i in $(seq 40); do
  secret-tool search --all service nothing >/dev/null 2>&1 && break
  sleep 0.25
done
printf '%s' 's3cret one' | secret-tool store --label='First thing' service example user alice
printf '%s' "$SECOND" | secret-tool store --label='Second' service other user bob
sleep 1
kill $gk
wait $gk 2>/dev/null || true
'''


def available():
    return all(shutil.which(x) for x in ('gnome-keyring-daemon', 'dbus-run-session', 'secret-tool'))


def make_keyring(home):
    """Fill `home` with a login.keyring holding ITEMS, and return its path."""
    run = tempfile.mkdtemp(prefix='gk-run-')
    os.chmod(run, 0o700)
    env = {'PATH': os.environ['PATH'], 'HOME': home, 'XDG_RUNTIME_DIR': run,
           'XDG_DATA_HOME': home + '/.local/share', 'XDG_CONFIG_HOME': home + '/.config',
           'XDG_CACHE_HOME': home + '/.cache', 'GK_PASSWORD': PASSWORD, 'SECOND': ITEMS[1][2],
           'LANG': 'C.UTF-8'}
    try:
        subprocess.run(['dbus-run-session', '--', 'bash', '-c', SCRIPT], env=env, check=True,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
    finally:
        shutil.rmtree(run, ignore_errors=True)
    return home + '/.local/share/keyrings/login.keyring'
