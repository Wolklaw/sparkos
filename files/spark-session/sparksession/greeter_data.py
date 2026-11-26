"""What the greeter lists and remembers: users, sessions, the last choice. No GTK."""

import json
import os
import pwd
import shlex

SESSION_DIRS = ('/usr/share/wayland-sessions',)
NOLOGIN = ('/sbin/nologin', '/usr/sbin/nologin', '/bin/false', '/usr/bin/false')


class User:
    def __init__(self, name, full_name, uid):
        self.name, self.full_name, self.uid = name, full_name, uid

    @property
    def label(self):
        return self.full_name or self.name


def list_users(passwd=None, minimum=1000, maximum=60000):
    """Real people: uid in the normal range with a login shell."""
    entries = passwd if passwd is not None else pwd.getpwall()
    users = []
    for p in entries:
        if minimum <= p.pw_uid < maximum and p.pw_shell not in NOLOGIN and p.pw_name != 'nobody':
            users.append(User(p.pw_name, p.pw_gecos.split(',')[0], p.pw_uid))
    return sorted(users, key=lambda u: u.uid)


class Session:
    def __init__(self, name, cmd, desktop_names, ident):
        self.name, self.cmd, self.desktop_names, self.ident = name, cmd, desktop_names, ident

    @property
    def env(self):
        env = ['XDG_SESSION_TYPE=wayland', f'XDG_SESSION_DESKTOP={self.ident}']
        if self.desktop_names:
            env.append('XDG_CURRENT_DESKTOP=' + self.desktop_names)
        return env


def parse_session(path):
    fields, in_entry = {}, False
    with open(path, encoding='utf-8', errors='replace') as handle:
        for line in handle:
            line = line.strip()
            if line.startswith('['):
                in_entry = line == '[Desktop Entry]'
            elif in_entry and '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                if '[' not in key:                       # skip Name[fr]= and the like
                    fields[key.strip()] = value.strip()
    if fields.get('Hidden') == 'true' or fields.get('NoDisplay') == 'true':
        return None
    if not fields.get('Exec') or not fields.get('Name'):
        return None
    try_exec = fields.get('TryExec')
    if try_exec and not _executable(try_exec):
        return None
    ident = os.path.splitext(os.path.basename(path))[0]
    names = fields.get('DesktopNames', '').strip(';').replace(';', ':')
    return Session(fields['Name'], shlex.split(fields['Exec']), names, ident)


def _executable(name):
    if os.path.isabs(name):
        return os.access(name, os.X_OK)
    return any(os.access(os.path.join(d, name), os.X_OK)
               for d in os.environ.get('PATH', '/usr/bin').split(':'))


def list_sessions(dirs=SESSION_DIRS):
    """The Spark session first when it exists, then the rest by name."""
    found = []
    for directory in dirs:
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            if name.endswith('.desktop'):
                try:
                    session = parse_session(os.path.join(directory, name))
                except OSError:
                    continue
                if session:
                    found.append(session)
    found.sort(key=lambda s: (s.ident not in ('spark-wl', 'spark'), s.ident != 'spark-wl', s.name.lower()))
    return found


class Memory:
    """The last user and the last session per user, in a small json file the greeter user owns."""

    def __init__(self, path=None):
        self.path = path or os.path.join(
            os.environ.get('SPARK_GREETER_CACHE', '/var/cache/spark-greeter'), 'state.json')
        try:
            with open(self.path) as handle:
                self.data = json.load(handle)
        except (OSError, ValueError):
            self.data = {}
        if not isinstance(self.data, dict):
            self.data = {}

    def last_user(self):
        return self.data.get('user')

    def last_session(self, user):
        return self.data.get('sessions', {}).get(user)

    def remember(self, user, session_ident):
        self.data['user'] = user
        self.data.setdefault('sessions', {})[user] = session_ident
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as handle:
                json.dump(self.data, handle)
            os.replace(tmp, self.path)
        except OSError:
            pass                                          # a cache: never block a login on it
