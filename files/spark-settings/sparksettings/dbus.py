"""D-Bus through busctl (systemd, always in the image), so there is no Python D-Bus package to
carry. busctl reads DBUS_SYSTEM_BUS_ADDRESS and DBUS_SESSION_BUS_ADDRESS, which is how the tests
point it at python-dbusmock's fake services instead of the real ones."""

import json
from typing import Any, Optional, Tuple

from .core import run

SYSTEM, SESSION = '--system', '--user'


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def call(bus: str, dest: str, path: str, iface: str, method: str, sig: str = '',
         *args: str, timeout: float = 30) -> Tuple[bool, Any, str]:
    """(ok, the reply's data, the error text). A method with one return value gives that value
    ([x] -> x); several give the list."""
    cmd = ['busctl', bus, '--json=short', f'--timeout={int(timeout)}', 'call', dest, path, iface,
           method]
    if sig:
        cmd += [sig, *args]
    rc, text, err = run(cmd, timeout=timeout + 5)
    if rc != 0:
        return False, None, err.strip() or f"{method} failed"
    data = (_json(text) or {}).get('data')
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    return True, data, ''


def get(bus: str, dest: str, path: str, iface: str, prop: str) -> Optional[Any]:
    rc, text, _ = run(['busctl', bus, '--json=short', 'get-property', dest, path, iface, prop],
                      timeout=15)
    if rc != 0:
        return None
    return (_json(text) or {}).get('data')


def set_(bus: str, dest: str, path: str, iface: str, prop: str, sig: str, value: str
         ) -> Tuple[bool, str]:
    rc, _, err = run(['busctl', bus, 'set-property', dest, path, iface, prop, sig, value],
                     timeout=20)
    return rc == 0, err.strip()

