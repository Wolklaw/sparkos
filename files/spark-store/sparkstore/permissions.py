"""An app's Flatpak permissions in plain words.

The permissions are in the app's metadata (the [Context] group and the bus policies), which
flatpak reads from Flathub's index without installing anything. Each line is (group, level,
sentence): group is files, devices, network or other; level 'warn' marks the ones that reach
past the sandbox in a way people should know about."""

import configparser
from typing import List, Tuple

from .text import t

Line = Tuple[str, str, str]          # (group, level, sentence)
GROUPS = ('files', 'devices', 'network', 'other')

XDG_FOLDERS = {
    'xdg-download': 'perm.f.downloads', 'xdg-documents': 'perm.f.documents',
    'xdg-music': 'perm.f.music', 'xdg-pictures': 'perm.f.pictures',
    'xdg-videos': 'perm.f.videos', 'xdg-desktop': 'perm.f.desktop',
    'xdg-public-share': 'perm.f.public', 'xdg-templates': 'perm.f.templates',
}

# session bus names people would recognise; the rest are summed up in one line
KNOWN_TALK = {
    'org.freedesktop.Notifications': ('other', 'info', 'perm.o.notifications'),
    'org.kde.StatusNotifierWatcher': ('other', 'info', 'perm.o.tray'),
    'org.freedesktop.secrets': ('other', 'warn', 'perm.o.secrets'),
    'org.freedesktop.Flatpak': ('other', 'warn', 'perm.o.escape'),
    'org.freedesktop.ScreenSaver': ('other', 'info', 'perm.o.screensaver'),
    'org.freedesktop.PowerManagement': ('other', 'info', 'perm.o.screensaver'),
    'org.gnome.SessionManager': ('other', 'info', 'perm.o.screensaver'),
    'org.freedesktop.FileManager1': ('files', 'info', 'perm.f.show_in_folder'),
    'com.canonical.AppMenu.Registrar': ('other', 'info', None),
    'com.canonical.indicator.application': ('other', 'info', 'perm.o.tray'),
    'org.kde.kwalletd5': ('other', 'warn', 'perm.o.secrets'),
    'org.kde.kwalletd6': ('other', 'warn', 'perm.o.secrets'),
    'org.freedesktop.UPower': ('other', 'info', None),
    'org.a11y.Bus': ('other', 'info', None),
}


def _list(value: str) -> List[str]:
    return [v.strip() for v in value.split(';') if v.strip()]


def _folder(path: str) -> Tuple[str, str]:
    """('ro'|'rw'|'create', path without the :mode)."""
    if ':' in path:
        base, _, mode = path.rpartition(':')
        if mode in ('ro', 'rw', 'create'):
            return mode, base
    return 'rw', path


def describe(metadata: str) -> List[Line]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(metadata)
    except configparser.Error:
        return []
    ctx = dict(parser.items('Context')) if parser.has_section('Context') else {}
    lines: List[Line] = []
    shared = _list(ctx.get('shared', ''))
    sockets = _list(ctx.get('sockets', ''))
    devices = _list(ctx.get('devices', ''))
    features = _list(ctx.get('features', ''))
    filesystems = _list(ctx.get('filesystems', ''))

    # — files —
    for entry in filesystems:
        if entry.startswith('!'):
            continue
        mode, path = _folder(entry)
        ro = mode == 'ro'
        head, _, rest = path.partition('/')
        if path in ('host', 'host-os', 'host-etc', 'host-root'):
            key = {'host': 'perm.f.host', 'host-os': 'perm.f.host_os',
                   'host-etc': 'perm.f.host_etc', 'host-root': 'perm.f.host'}[path]
            lines.append(('files', 'warn', t(key) + (t('perm.ro') if ro else '')))
        elif path in ('home', '~'):
            lines.append(('files', 'warn', t('perm.f.home') + (t('perm.ro') if ro else '')))
        elif head in XDG_FOLDERS:
            text = t(XDG_FOLDERS[head])
            if rest:
                text = t('perm.f.sub', folder=text, sub=rest)
            lines.append(('files', 'info', text + (t('perm.ro') if ro else '')))
        elif head in ('xdg-config', 'xdg-data', 'xdg-cache'):
            base = {'xdg-config': '~/.config', 'xdg-data': '~/.local/share',
                    'xdg-cache': '~/.cache'}[head]
            where = f"{base}/{rest}" if rest else base
            level = 'info' if rest else 'warn'
            lines.append(('files', level, t('perm.f.path', path=where) +
                          (t('perm.ro') if ro else '')))
        elif head.startswith('xdg-run'):
            continue                     # sockets other apps publish; not files people keep
        elif path.startswith(('~/', '/')):
            level = 'warn' if path in ('/', '/media', '/mnt', '/run/media') else 'info'
            lines.append(('files', level, t('perm.f.path', path=path) +
                          (t('perm.ro') if ro else '')))
        else:
            lines.append(('files', 'info', t('perm.f.path', path=path) +
                          (t('perm.ro') if ro else '')))

    # — devices —
    if 'all' in devices:
        lines.append(('devices', 'warn', t('perm.d.all')))
    else:
        for dev, key, level in (('dri', 'perm.d.gpu', 'info'), ('kvm', 'perm.d.kvm', 'info'),
                                ('usb', 'perm.d.usb', 'warn'),
                                ('input', 'perm.d.input', 'info'),
                                ('shm', None, 'info')):
            if dev in devices and key:
                lines.append(('devices', level, t(key)))
    if 'pulseaudio' in sockets:
        lines.append(('devices', 'info', t('perm.d.sound')))
    if 'bluetooth' in features:
        lines.append(('devices', 'info', t('perm.d.bluetooth')))
    if 'pcsc' in sockets:
        lines.append(('devices', 'info', t('perm.d.smartcard')))
    if 'cups' in sockets:
        lines.append(('devices', 'info', t('perm.d.printers')))
    if 'x11' in sockets:               # fallback-x11 only applies when Wayland is missing
        lines.append(('devices', 'warn', t('perm.d.x11')))

    # — network —
    if 'network' in shared:
        lines.append(('network', 'info', t('perm.n.network')))

    # — other —
    if 'session-bus' in sockets:
        lines.append(('other', 'warn', t('perm.o.session_bus')))
    if 'system-bus' in sockets:
        lines.append(('other', 'warn', t('perm.o.system_bus')))
    if 'ssh-auth' in sockets:
        lines.append(('other', 'warn', t('perm.o.ssh')))
    if 'gpg-agent' in sockets:
        lines.append(('other', 'warn', t('perm.o.gpg')))
    if 'devel' in features:
        lines.append(('other', 'warn', t('perm.o.devel')))
    talk = []
    for section in ('Session Bus Policy', 'System Bus Policy'):
        if parser.has_section(section):
            for name, policy in parser.items(section):
                if policy.strip() in ('talk', 'own') and section == 'Session Bus Policy':
                    talk.append(name)
    seen = set()
    others = 0
    for name in talk:
        known = KNOWN_TALK.get(name.rstrip('*').rstrip('.'))
        if known is None:
            for prefix in ('org.mpris.MediaPlayer2',):
                if name.startswith(prefix):
                    known = ('other', 'info', 'perm.o.media_keys')
            if name.startswith(('org.freedesktop.portal.', 'org.kde.kwin.',
                                'org.freedesktop.impl.')):
                known = ('other', 'info', None)
        if known is None:
            others += 1
            continue
        group, level, key = known
        if key and key not in seen:
            seen.add(key)
            lines.append((group, level, t(key)))
    if others and 'session-bus' not in sockets:
        lines.append(('other', 'info', t('perm.o.talks', n=others)))
    return lines


def broad(lines: List[Line]) -> bool:
    return any(level == 'warn' for _g, level, _s in lines)
