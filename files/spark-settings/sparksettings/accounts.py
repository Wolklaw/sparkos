"""Users, through AccountsService (org.freedesktop.Accounts on the system bus): the list, the
name, standard or administrator, add and remove. polkit asks for the admin password when a
change needs it. Passwords are not handled here: "Change password" runs `passwd` in Spark
Terminal, so no password passes through this app."""

import os
from typing import Any, List

from . import dbus
from .core import spawn, have

BUS = dbus.SYSTEM
DEST = 'org.freedesktop.Accounts'
ROOT = '/org/freedesktop/Accounts'
USER_IFACE = 'org.freedesktop.Accounts.User'
STANDARD, ADMIN = 0, 1


class User:
    def __init__(self, path: str, props: dict):
        self.path = path
        self.name = props.get('UserName', '')
        self.real_name = props.get('RealName', '') or self.name
        self.uid = int(props.get('Uid', -1))
        self.admin = int(props.get('AccountType', 0)) == ADMIN
        self.icon = props.get('IconFile', '')
        self.locked = bool(props.get('Locked', False))

    @property
    def me(self) -> bool:
        return self.uid == os.getuid()


def _unwrap(v: Any) -> Any:
    """busctl's {"type":..,"data":..} wrappers in a GetAll reply, down to plain values."""
    if isinstance(v, dict) and 'data' in v and 'type' in v:
        return _unwrap(v['data'])
    if isinstance(v, dict):
        return {k: _unwrap(x) for k, x in v.items()}
    return v


def users() -> List[User]:
    ok, paths, _ = dbus.call(BUS, DEST, ROOT, 'org.freedesktop.Accounts', 'ListCachedUsers')
    if not ok or not isinstance(paths, list):
        return []
    found = []
    for path in paths:
        ok, props, _ = dbus.call(BUS, DEST, path, 'org.freedesktop.DBus.Properties', 'GetAll', 's',
                                 USER_IFACE)
        if ok and isinstance(props, dict):
            found.append(User(path, _unwrap(props)))
    return sorted(found, key=lambda u: (not u.me, u.uid))


def _user_call(user: User, method: str, sig: str, *args: str) -> str:
    ok, _d, err = dbus.call(BUS, DEST, user.path, USER_IFACE, method, sig, *args, timeout=60)
    return '' if ok else (err or f"{method} failed")


def set_real_name(user: User, name: str) -> str:
    return _user_call(user, 'SetRealName', 's', name)


def set_admin(user: User, admin: bool) -> str:
    return _user_call(user, 'SetAccountType', 'i', str(ADMIN if admin else STANDARD))


def set_icon(user: User, path: str) -> str:
    return _user_call(user, 'SetIconFile', 's', path)


def create(name: str, real_name: str, admin: bool) -> str:
    ok, _d, err = dbus.call(BUS, DEST, ROOT, 'org.freedesktop.Accounts', 'CreateUser', 'ssi',
                            name, real_name, str(ADMIN if admin else STANDARD), timeout=60)
    return '' if ok else (err or "could not add the user")


def remove(user: User, delete_files: bool) -> str:
    ok, _d, err = dbus.call(BUS, DEST, ROOT, 'org.freedesktop.Accounts', 'DeleteUser', 'xb',
                            str(user.uid), 'true' if delete_files else 'false', timeout=60)
    return '' if ok else (err or "could not remove the user")


def change_password() -> bool:
    """`passwd` for you, in Spark Terminal."""
    return have('spark-terminal') and spawn(['spark-terminal', '--hold', '-T', 'passwd', '-e', 'passwd'])


def valid_name(name: str) -> bool:
    import re
    return bool(re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', name))
