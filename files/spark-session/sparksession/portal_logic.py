"""The plain parts of spark-portal, the Spark session's xdg-desktop-portal backend: settings
values, namespace globs, notification and mailto conversion, printer lists, the account's
details. No bus and no window here, so the tests (and --self-test) run anywhere with PyGObject.
"""

import fnmatch
import json
import os
import pwd
import subprocess
from urllib.parse import quote

from gi.repository import Gio, GLib

# ─── Settings ────────────────────────────────────────────────

ACCENT = '#3de8c8'          # Spark Settings' accent
APPEARANCE = 'org.freedesktop.appearance'

# GSettings keys that apps read through the portal, by schema (the portal namespace is the
# schema id). A key is passed on only when the schema is installed and has it.
GSETTINGS_KEYS = {
    'org.gnome.desktop.interface': (
        'gtk-theme', 'icon-theme', 'cursor-theme', 'cursor-size', 'font-name',
        'monospace-font-name', 'document-font-name', 'text-scaling-factor', 'clock-format',
        'color-scheme', 'enable-animations'),
}
# Values the session decides, whatever GSettings says: SparkOS is always dark.
GSETTINGS_FORCED = {
    ('org.gnome.desktop.interface', 'color-scheme'): 'prefer-dark',
}


def accent_rgb(color: str = ACCENT):
    """'#3de8c8' as the (r, g, b) floats, 0 to 1, the appearance portal wants."""
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def config_home(environ=None) -> str:
    env = os.environ if environ is None else environ
    return env.get('XDG_CONFIG_HOME') or os.path.join(env.get('HOME') or os.path.expanduser('~'),
                                                      '.config')


def appearance_file(environ=None) -> str:
    return os.path.join(config_home(environ), 'spark', 'appearance.json')


def reduced_motion(environ=None) -> int:
    """1 when the "animations" switch of Spark Settings is off (~/.config/spark/appearance.json),
    0 otherwise."""
    try:
        with open(appearance_file(environ), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    return 1 if isinstance(data, dict) and data.get('animations', True) is False else 0


def appearance_values(environ=None) -> dict:
    """The org.freedesktop.appearance namespace."""
    return {
        'color-scheme': GLib.Variant('u', 1),
        'accent-color': GLib.Variant('(ddd)', accent_rgb()),
        'contrast': GLib.Variant('u', 0),
        'reduced-motion': GLib.Variant('u', reduced_motion(environ)),
    }


def namespace_matches(namespace: str, patterns) -> bool:
    """The portal's namespace filter: no patterns means everything; a pattern is a name or a
    glob ('org.gnome.*', '*'). 'org.gnome' alone does not match 'org.gnome.desktop'."""
    patterns = [p for p in (patterns or []) if p]
    if not patterns:
        return True
    return any(fnmatch.fnmatchcase(namespace, p) for p in patterns)


def gsettings_schema(schema_id: str, source=None):
    source = source or Gio.SettingsSchemaSource.get_default()
    return source.lookup(schema_id, True) if source else None


def gsettings_value(schema_id: str, key: str, source=None):
    """The key as a Variant, or None when the schema or the key is not installed."""
    forced = GSETTINGS_FORCED.get((schema_id, key))
    schema = gsettings_schema(schema_id, source)
    if schema is None or not schema.has_key(key):
        return None
    if forced is not None:
        return GLib.Variant('s', forced)
    return Gio.Settings.new_full(schema, None, None).get_value(key)


class SettingsStore:
    """Every value the Settings portal answers with. changed(namespace, key, value) is called
    when a GSettings key or the animations switch changes."""

    def __init__(self, changed=None, environ=None, source=None):
        self.environ, self.source = environ, source
        self.changed = changed or (lambda ns, key, value: None)
        self._settings, self._monitor, self._last_motion = {}, None, None

    def values(self) -> dict:
        out = {APPEARANCE: appearance_values(self.environ)}
        for schema_id, keys in GSETTINGS_KEYS.items():
            found = {}
            for key in keys:
                value = gsettings_value(schema_id, key, self.source)
                if value is not None:
                    found[key] = value
            if found:
                out[schema_id] = found
        return out

    def read_all(self, patterns) -> dict:
        return {ns: dict(vals) for ns, vals in self.values().items()
                if namespace_matches(ns, patterns)}

    def read(self, namespace: str, key: str):
        """The value, or None when there is no such key."""
        return self.values().get(namespace, {}).get(key)

    def watch(self) -> None:
        """Start telling `changed` about changes (needs a GLib main loop)."""
        for schema_id, keys in GSETTINGS_KEYS.items():
            schema = gsettings_schema(schema_id, self.source)
            if schema is None:
                continue
            gs = Gio.Settings.new_full(schema, None, None)
            self._settings[schema_id] = gs
            gs.connect('changed', self._gsettings_changed, schema_id)
        path = appearance_file(self.environ)
        self._last_motion = reduced_motion(self.environ)
        self._monitor = Gio.File.new_for_path(path).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._monitor.connect('changed', self._file_changed)

    def _gsettings_changed(self, gs, key, schema_id):
        if key not in GSETTINGS_KEYS[schema_id]:
            return
        value = gsettings_value(schema_id, key, self.source)
        if value is not None:
            self.changed(schema_id, key, value)

    def _file_changed(self, *_args):
        now = reduced_motion(self.environ)
        if now != self._last_motion:
            self._last_motion = now
            self.changed(APPEARANCE, 'reduced-motion', GLib.Variant('u', now))


# ─── Inhibit ─────────────────────────────────────────────────

INHIBIT_LOGOUT, INHIBIT_USER_SWITCH, INHIBIT_SUSPEND, INHIBIT_IDLE = 1, 2, 4, 8


def inhibit_kinds(flags: int) -> list:
    """The names of the flags set, in a fixed order."""
    names = (('logout', INHIBIT_LOGOUT), ('user-switch', INHIBIT_USER_SWITCH),
             ('suspend', INHIBIT_SUSPEND), ('idle', INHIBIT_IDLE))
    return [name for name, bit in names if flags & bit]


def logind_what(flags: int) -> str:
    """What the logind inhibitor blocks: sleep for suspend, shutdown for logout and user
    switch (a PC that powers off ends the session too)."""
    what = []
    if flags & INHIBIT_SUSPEND:
        what.append('sleep')
    if flags & (INHIBIT_LOGOUT | INHIBIT_USER_SWITCH):
        what.append('shutdown')
    return ':'.join(what)


def inhibit_registry_path(environ=None) -> str:
    env = os.environ if environ is None else environ
    runtime = env.get('XDG_RUNTIME_DIR') or '/run/user/%d' % os.getuid()
    return os.path.join(runtime, 'spark-wl', 'portal-inhibit.json')


def write_inhibit_registry(path: str, entries: list) -> None:
    """The inhibits that are held, for the shell's sign-out to ask about (a JSON list of
    {app_id, reason, flags}). The file is gone when there are none."""
    if not entries:
        try:
            os.unlink(path)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(entries, f)
        f.write('\n')
    os.replace(path + '.tmp', path)


# ─── Notifications ───────────────────────────────────────────

URGENCY = {'low': 0, 'normal': 1, 'high': 1, 'urgent': 2}


def icon_name(icon) -> str:
    """The icon the portal sends (a serialized GIcon: ('themed', names) or ('file', uri)) as
    the name or path org.freedesktop.Notifications takes. '' when there is none."""
    if isinstance(icon, GLib.Variant):
        icon = icon.unpack()
    if not isinstance(icon, (tuple, list)) or len(icon) != 2:
        return ''
    kind, data = icon
    if isinstance(data, GLib.Variant):
        data = data.unpack()
    if kind == 'themed' and data:
        return str(data[0])
    if kind == 'file' and isinstance(data, str):
        return data
    return ''


def parse_notification(app_id: str, nid: str, vardict) -> dict:
    """The portal's notification (a{sv}) as the call to org.freedesktop.Notifications.Notify.

    Returns app_name, summary, body, icon, hints, actions (key, label, ...) and `targets`:
    {action key: (action name, target Variant or None)} for ActionInvoked on the way back."""
    n = GLib.VariantDict.new(vardict)

    def get(key, kind, default=''):
        value = n.lookup_value(key, GLib.VariantType(kind))
        return default if value is None else value.unpack()

    body = get('markup-body', 's') or get('body', 's')
    urgency = URGENCY.get(get('priority', 's', 'normal'), 1)
    hints = {'urgency': GLib.Variant('y', urgency),
             'desktop-entry': GLib.Variant('s', app_id.removesuffix('.desktop'))}
    category = get('category', 's')
    if category:
        hints['category'] = GLib.Variant('s', category)
    actions, targets = [], {}
    default_action = get('default-action', 's')
    if default_action:
        actions += ['default', '']
        targets['default'] = (default_action, n.lookup_value('default-action-target', None))
    buttons = n.lookup_value('buttons', GLib.VariantType('aa{sv}'))
    for i in range(buttons.n_children() if buttons is not None else 0):
        b = GLib.VariantDict.new(buttons.get_child_value(i))
        label, action = b.lookup_value('label', None), b.lookup_value('action', None)
        if label is None or action is None:
            continue
        key = f'{i}:{action.unpack()}'
        actions += [key, label.unpack()]
        targets[key] = (action.unpack(), b.lookup_value('target', None))
    return {'app_name': app_id, 'summary': get('title', 's'), 'body': body,
            'icon': icon_name(n.lookup_value('icon', None)), 'hints': hints,
            'actions': actions, 'targets': targets}


# ─── Email ───────────────────────────────────────────────────

def mailto_uri(options: dict) -> str:
    """A mailto: URI from the Email portal's options (addresses, cc, bcc, subject, body).
    Attachments cannot go in a mailto: link and are left out."""
    def one(value):
        return quote(str(value), safe='@,')

    to = list(options.get('addresses') or [])
    if options.get('address'):
        to.insert(0, options['address'])
    query = []
    for key in ('cc', 'bcc'):
        if options.get(key):
            query.append(f'{key}=' + ','.join(one(a) for a in options[key]))
    for key in ('subject', 'body'):
        if options.get(key):
            query.append(f'{key}=' + quote(str(options[key]), safe=''))
    uri = 'mailto:' + ','.join(one(a) for a in to)
    return uri + ('?' + '&'.join(query) if query else '')


# ─── Account ─────────────────────────────────────────────────

def user_information(home=None, entry=None) -> dict:
    """What the Account portal gives: id (the user name), name (real name, else the user name)
    and image (a file: URI of ~/.face or ~/.face.icon, only when it exists)."""
    entry = entry or pwd.getpwuid(os.getuid())
    home = home or entry.pw_dir
    name = (entry.pw_gecos or '').split(',')[0].strip() or entry.pw_name
    info = {'id': entry.pw_name, 'name': name, 'image': ''}
    for face in ('.face', '.face.icon'):
        path = os.path.join(home, face)
        if os.path.isfile(path):
            info['image'] = 'file://' + quote(path)
            break
    return info


# ─── Printing ────────────────────────────────────────────────

def parse_lpstat(text: str):
    """(printers, default) from `lpstat -p -d`. printers is a list of (name, state) with the
    state as CUPS words it (idle, printing, disabled)."""
    printers, default = [], ''
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 3 and words[0] == 'printer':
            state = ('disabled' if words[2] == 'disabled' else
                     'printing' if words[2] == 'now' else 'idle')
            printers.append((words[1], state))
        elif line.startswith('system default destination:'):
            default = line.split(':', 1)[1].strip()
    return printers, default


def list_printers():
    try:
        out = subprocess.run(['lpstat', '-p', '-d'], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return [], ''
    return parse_lpstat(out)


def lp_command(printer: str, copies: int, title: str) -> list:
    """The lp command that prints standard input."""
    cmd = ['lp']
    if printer:
        cmd += ['-d', printer]
    cmd += ['-n', str(max(1, min(int(copies), 999)))]
    if title:
        cmd += ['-t', title]
    return cmd


def trusted_launcher_app(app_id: str) -> bool:
    """Only Spark's own apps get an install token without a dialog."""
    return app_id.startswith('dev.wolklaw.Spark')
