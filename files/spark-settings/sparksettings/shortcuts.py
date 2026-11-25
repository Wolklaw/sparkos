"""Keyboard shortcuts through kglobalaccel (org.kde.kglobalaccel on the session bus), which is
KWin's and Plasma's shortcut service and stays in the Spark session. List every component
(KWin, the apps) with its actions and keys, change one, put it back to the default. kglobalaccel
saves them itself, in kglobalshortcutsrc.

A key is a Qt key code: the key plus Shift 0x02000000, Ctrl 0x04000000, Alt 0x08000000,
Meta 0x10000000. Only the first key of an action is shown and set (kglobalaccel keeps up to
four)."""

from typing import Any, Dict, List, Optional

from . import dbus

BUS = dbus.SESSION
DEST = 'org.kde.kglobalaccel'
ACCEL = (BUS, DEST, '/kglobalaccel', 'org.kde.KGlobalAccel')
COMP_IFACE = 'org.kde.kglobalaccel.Component'

SHIFT, CTRL, ALT, META = 0x02000000, 0x04000000, 0x08000000, 0x10000000
MODS = ((META, 'Meta'), (CTRL, 'Ctrl'), (ALT, 'Alt'), (SHIFT, 'Shift'))
NAMED = {0x20: 'Space', 0x01000000: 'Esc', 0x01000001: 'Tab', 0x01000002: 'Backtab',
         0x01000003: 'Backspace', 0x01000004: 'Return', 0x01000005: 'Enter', 0x01000006: 'Ins',
         0x01000007: 'Del', 0x01000008: 'Pause', 0x01000009: 'Print', 0x01000010: 'Home',
         0x01000011: 'End', 0x01000012: 'Left', 0x01000013: 'Up', 0x01000014: 'Right',
         0x01000015: 'Down', 0x01000016: 'PgUp', 0x01000017: 'PgDown', 0x01000024: 'CapsLock',
         0x01000026: 'NumLock', 0x01000030: 'F1'}
for _i in range(2, 36):
    NAMED[0x01000030 + _i - 1] = f'F{_i}'
NAMED[0x01000030] = 'F1'
# the media and volume keys
NAMED.update({0x1000070: 'Volume Down', 0x1000071: 'Volume Mute', 0x1000072: 'Volume Up',
              0x1000080: 'Play', 0x1000081: 'Stop', 0x1000082: 'Previous', 0x1000083: 'Next'})


def key_text(code: int) -> str:
    """0x14000045 -> "Meta+Ctrl+E"; 0 -> "" (no key)."""
    if not code:
        return ''
    parts = [name for bit, name in MODS if code & bit]
    base = code & 0x01FFFFFF
    parts.append(NAMED.get(base) or (chr(base) if 0x20 < base < 0x7F else f'0x{base:x}'))
    return '+'.join(parts)


def key_code(keysym: str, state: int) -> Optional[int]:
    """A Tk key event (keysym and modifier state) as a Qt key code; None for a lone modifier."""
    if keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Meta_L',
                  'Meta_R', 'Super_L', 'Super_R', 'ISO_Level3_Shift', 'Caps_Lock', 'Num_Lock'):
        return None
    names = {v: k for k, v in NAMED.items()}
    alias = {'Escape': 'Esc', 'space': 'Space', 'BackSpace': 'Backspace', 'Prior': 'PgUp',
             'Next': 'PgDown', 'Delete': 'Del', 'Insert': 'Ins', 'ISO_Left_Tab': 'Backtab',
             'KP_Enter': 'Enter'}
    base = names.get(alias.get(keysym, keysym)) or names.get(keysym.capitalize())
    if base is None and len(keysym) == 1:
        base = ord(keysym.upper())
    if base is None:
        return None
    code = base
    if state & 0x4:
        code |= CTRL
    if state & 0x8:
        code |= ALT                      # Tk's Mod1
    if state & 0x1:
        code |= SHIFT
    if state & 0x40:
        code |= META                     # Tk's Mod4 (the Super key)
    return code


class Action:
    def __init__(self, row: List[Any]):
        (_cu, _cf, self.component, self.component_name, self.id, self.name,
         self.keys, self.default_keys) = row[:8]

    @property
    def text(self) -> str:
        return key_text(self.keys[0]) if self.keys else ''

    @property
    def default_text(self) -> str:
        return key_text(self.default_keys[0]) if self.default_keys else ''

    def action_id(self) -> List[str]:
        return [self.component, self.id, self.component_name, self.name]


def components() -> List[Dict[str, str]]:
    """[{path, id, name}] for every component, named ones first."""
    ok, paths, _ = dbus.call(*ACCEL, 'allComponents')
    if not ok or not isinstance(paths, list):
        return []
    found = []
    for p in paths:
        ident = dbus.get(BUS, DEST, p, COMP_IFACE, 'uniqueName')
        name = dbus.get(BUS, DEST, p, COMP_IFACE, 'friendlyName')
        if isinstance(ident, str):
            found.append({'path': p, 'id': ident, 'name': name if isinstance(name, str) and name else ident})
    return sorted(found, key=lambda c: (c['id'] not in ('kwin', 'plasmashell'), c['name'].lower()))


def actions(path: str) -> List[Action]:
    ok, rows, _ = dbus.call(BUS, DEST, path, COMP_IFACE, 'allShortcutInfos')
    if not ok or not isinstance(rows, list):
        return []
    out = [Action(r) for r in rows if isinstance(r, list) and len(r) >= 8]
    return sorted(out, key=lambda a: a.name.lower())


def set_key(action: Action, code: int) -> str:
    """Give the action this key (0 clears it). Returns '' or what went wrong."""
    args = ['4', *action.action_id(), '1' if code else '0']
    if code:
        args.append(str(code))
    ok, _d, err = dbus.call(*ACCEL, 'setForeignShortcut', 'asai', *args)
    if ok:
        action.keys = [code] if code else []
    return '' if ok else (err or "could not set the shortcut")


def reset(action: Action) -> str:
    return set_key(action, action.default_keys[0] if action.default_keys else 0)


def conflict(path_actions: List[Action], action: Action, code: int) -> Optional[Action]:
    """Another action in the same component that already has this key."""
    for a in path_actions:
        if a is not action and code and code in a.keys:
            return a
    return None


# ── spark-wl: no kglobalaccel there. The Spark compositor owns every shortcut ──
# Its built-in binds are mirrored in DEFAULTS (keep in step with set_default_binds() in
# spark-compositor.c). Changes go into a marked block of ~/.config/spark/compositor/compositor.conf
# as "bind KEY ACTION [COMMAND]" lines, "bind KEY none" turns a built-in key off, and a SIGHUP
# makes the compositor read the file again. A key here is the compositor's own text,
# "Super+Shift+s", not a Qt code.
import os as _os
import re as _re

SPARKWL = 'sparkwl' in _os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
_SHELL_KEY = ('gdbus call --session --dest dev.wolklaw.SparkShell --object-path /Shell '
              '--method dev.wolklaw.SparkShell.Key ')
# (name, action, command, default keys)
DEFAULTS = [
    ("Open the start menu", 'exec', 'spark-shell --toggle', ['Super_L', 'Super_R']),
    ("Open a terminal", 'exec', 'spark-terminal || foot || xterm', ['Super+Return', 'Ctrl+Alt+t']),
    ("Spark Monitor", 'exec', 'spark-monitor', ['Ctrl+Shift+Escape', 'Super+Escape', 'Ctrl+Escape']),
    ("Emoji", 'exec', 'spark-emoji', ['Super+period']),
    ("Clipboard history", 'exec', 'spark-notes --clipboard', ['Super+v']),
    ("Calculator", 'exec', 'spark-calc', ['XF86Calculator']),
    ("Files", 'exec', 'spark-files', ['Super+e']),
    ("Settings", 'exec', 'spark-settings', ['Super+i']),
    ("Close the window", 'close', '', ['Super+q', 'Alt+F4']),
    ("Next window", 'focus-next', '', ['Alt+Tab', 'Super+Tab']),
    ("Full screen", 'fullscreen', '', ['Super+f']),
    ("Maximize the window", 'maximize', '', ['Super+Up']),
    ("Move the window to the next screen", 'output-next', '', ['Super+o']),
    ("Snap the window to the left half", 'snap-left', '', ['Super+Left']),
    ("Snap the window to the right half", 'snap-right', '', ['Super+Right']),
    ("Restore, then minimize the window", 'restore-down', '', ['Super+Down']),
    ("Show the desktop", 'show-desktop', '', ['Super+d']),
    ("Lock the screen", 'exec', 'loginctl lock-session', ['Super+l']),
    ("Screenshot", 'exec', 'spark-snip image', ['Print', 'Super+Shift+s']),
    ("Copy text from the screen", 'exec', 'spark-snip text', ['Super+Shift+t']),
    ("Record the screen", 'exec', 'spark-snip video', ['Super+Shift+r']),
    ("Volume up", 'exec', _SHELL_KEY + 'volume-up', ['XF86AudioRaiseVolume']),
    ("Volume down", 'exec', _SHELL_KEY + 'volume-down', ['XF86AudioLowerVolume']),
    ("Mute", 'exec', _SHELL_KEY + 'mute', ['XF86AudioMute']),
    ("Play or pause", 'exec', _SHELL_KEY + 'play-pause', ['XF86AudioPlay', 'XF86AudioPause']),
    ("Next track", 'exec', _SHELL_KEY + 'next', ['XF86AudioNext']),
    ("Previous track", 'exec', _SHELL_KEY + 'previous', ['XF86AudioPrev']),
    ("Stop playback", 'exec', _SHELL_KEY + 'stop', ['XF86AudioStop']),
    ("Reload the compositor settings", 'reload', '', ['Super+Ctrl+Shift+r']),
    ("Sign out at once", 'quit', '', ['Super+Shift+e']),
]
_BEGIN, _END = '# shortcuts: written by Spark Settings', '# shortcuts end'
_WL_MODS = (('super', 'Super'), ('ctrl', 'Ctrl'), ('alt', 'Alt'), ('shift', 'Shift'))
_MOD_ALIAS = {'logo': 'super', 'mod4': 'super', 'mod1': 'alt', 'control': 'ctrl'}
_PRETTY = {'Super_L': 'Super (left)', 'Super_R': 'Super (right)', 'Return': 'Enter',
           'Escape': 'Esc', 'Prior': 'PgUp', 'Next': 'PgDown', 'XF86AudioRaiseVolume': 'Volume Up',
           'XF86AudioLowerVolume': 'Volume Down', 'XF86AudioMute': 'Mute',
           'XF86AudioPlay': 'Play', 'XF86AudioPause': 'Pause', 'XF86AudioNext': 'Next track', 'XF86AudioPrev': 'Previous track',
           'XF86AudioStop': 'Stop', 'space': 'Space', 'BackSpace': 'Backspace', 'Delete': 'Del',
           'period': '.', 'comma': ',', 'XF86Calculator': 'Calculator'}


def _norm(combo: str) -> str:
    """"shift+SUPER+S" -> "Super+Shift+s": one spelling for every key."""
    parts = [p.strip() for p in combo.split('+') if p.strip()]
    mods, key = set(), ''
    for p in parts:
        m = _MOD_ALIAS.get(p.lower(), p.lower())
        if m in dict(_WL_MODS) and p not in ('Super_L', 'Super_R'):
            mods.add(m)
        else:
            key = p.lower() if len(p) == 1 else p
    return '+'.join([n for m, n in _WL_MODS if m in mods] + [key])


def _wl_key_text(key) -> str:
    if not key:
        return ''
    parts = key.split('+')
    last = parts[-1]
    parts[-1] = _PRETTY.get(last) or (last.upper() if len(last) == 1 else last)
    return '+'.join(parts)


def _wl_key_code(keysym: str, state: int) -> Optional[str]:
    if keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Meta_L',
                  'Meta_R', 'Super_L', 'Super_R', 'ISO_Level3_Shift', 'Caps_Lock', 'Num_Lock',
                  '??', ''):
        return None
    mods = [n for bit, n in ((0x40, 'Super'), (0x4, 'Ctrl'), (0x8, 'Alt'), (0x1, 'Shift')) if state & bit]
    if keysym == 'ISO_Left_Tab':
        keysym = 'Tab'
    return _norm('+'.join(mods + [keysym]))


class WlAction:
    def __init__(self, name: str, act: str, cmd: str, defaults: List[str]):
        from .i18n import _
        self.name, self.act, self.cmd = _(name), act, cmd
        self.default_keys = [_norm(k) for k in defaults]
        self.keys: List[str] = []

    @property
    def ident(self):
        return (self.act, self.cmd)

    @property
    def text(self) -> str:
        return ', '.join(_wl_key_text(k) for k in self.keys)

    @property
    def default_text(self) -> str:
        return ', '.join(_wl_key_text(k) for k in self.default_keys)


def _conf_path() -> str:
    from . import core
    return _os.path.join(core.xdg_config_home(), 'spark', 'compositor', 'compositor.conf')


def _read() -> List[str]:
    try:
        return open(_conf_path(), encoding='utf-8').read().splitlines()
    except OSError:
        return []


def _bind(line: str):
    """"bind KEY ACTION [COMMAND]" -> (key, action, command), or None."""
    m = _re.match(r'\s*bind\s+(\S+)\s+(\S+)\s*(.*)$', line)
    return (_norm(m.group(1)), m.group(2), m.group(3).strip()) if m else None


def _split(lines: List[str]):
    """The file's lines outside our block, and the bind lines inside it."""
    outside, inside, ours = [], [], False
    for l in lines:
        if l.strip() == _BEGIN:
            ours = True
        elif l.strip() == _END:
            ours = False
        elif ours:
            inside.append(l)
        else:
            outside.append(l)
    return outside, inside


def _apply(table: Dict[str, tuple], lines: List[str]) -> None:
    for l in lines:
        b = _bind(l)
        if not b:
            continue
        if b[1] == 'none':
            table.pop(b[0], None)
        else:
            table[b[0]] = (b[1], b[2])


def _base_table(outside: List[str]) -> Dict[str, tuple]:
    """Key -> (action, command) from the built-in binds and the hand-written lines."""
    table = {}
    for _n, act, cmd, keys in DEFAULTS:
        for k in keys:
            table[_norm(k)] = (act, cmd)
    _apply(table, outside)
    return table


def _wl_components() -> List[Dict[str, str]]:
    return [{'path': 'spark-compositor', 'id': 'spark-compositor', 'name': 'Spark'}]


def _wl_actions(_path: str = '') -> List[WlAction]:
    outside, inside = _split(_read())
    table = _base_table(outside)
    _apply(table, inside)
    acts = [WlAction(*d) for d in DEFAULTS]
    by_id = {a.ident: a for a in acts}
    for key, ident in table.items():
        a = by_id.get(ident)
        if a is None:              # a hand-written bind with no built-in twin
            a = WlAction(ident[1] or ident[0], ident[0], ident[1], [])
            by_id[ident] = a
            acts.append(a)
        a.keys.append(key)
    for a in acts:                 # the user's own keys first (Change and Clear act on the first)
        a.keys.sort(key=lambda k: (k in a.default_keys,
                                   a.default_keys.index(k) if k in a.default_keys else 0))
    return acts


def _write(acts: List[WlAction]) -> str:
    lines = _read()
    outside, _inside = _split(lines)
    base = _base_table(outside)
    want = {k: a.ident for a in acts for k in a.keys}
    block = []
    for k in base:
        if k not in want:
            block.append(f'bind {k} none')
    for k, (act, cmd) in want.items():
        if base.get(k) != (act, cmd):
            block.append(f'bind {k} {act} {cmd}'.rstrip())
    squeezed = []                  # no blank runs left where the old block was
    for l in outside:
        if l.strip() or (squeezed and squeezed[-1].strip()):
            squeezed.append(l)
    outside = squeezed
    while outside and not outside[-1].strip():
        outside.pop()
    if block:
        at = next((i for i, l in enumerate(outside) if l.strip() == '# input: written by Spark Settings'),
                  len(outside))
        add = [_BEGIN] + block + [_END]
        if at and outside[at - 1].strip():
            add = [''] + add
        if at < len(outside):
            add.append('')
        outside[at:at] = add
    path = _conf_path()
    try:
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write('\n'.join(outside) + '\n')
        _os.replace(tmp, path)
    except OSError as e:
        return str(e)
    from . import inputdev
    inputdev._compositor_reload()
    return ''


def _wl_set_key(action: WlAction, code) -> str:
    """Change the first key (code) or drop it (no code); the other keys stay."""
    acts = _wl_actions()
    mine = next((a for a in acts if a.ident == action.ident), None)
    if mine is None:
        from .i18n import _
        return _("That shortcut isn't there any more.")
    rest = mine.keys[1:]
    mine.keys = ([code] if code else []) + [k for k in rest if k != code]
    for a in acts:                 # a key does one thing
        if a is not mine and code in a.keys:
            a.keys.remove(code)
    err = _write(acts)
    if not err:
        action.keys = list(mine.keys)
    return err


def _wl_reset(action: WlAction) -> str:
    acts = _wl_actions()
    mine = next((a for a in acts if a.ident == action.ident), None)
    if mine is None:
        return ''
    freed = [k for k in mine.keys if k not in mine.default_keys]
    mine.keys = list(mine.default_keys)
    for a in acts:
        if a is not mine:
            a.keys = [k for k in a.keys if k not in mine.keys]
    for k in freed:                # a key this one had taken goes back to its built-in owner
        if not any(k in a.keys for a in acts):
            owner = next((a for a in acts if k in a.default_keys), None)
            if owner is not None:
                owner.keys.append(k)
    err = _write(acts)
    if not err:
        action.keys = list(mine.keys)
    return err


if SPARKWL:
    components, actions, set_key, reset = _wl_components, _wl_actions, _wl_set_key, _wl_reset
    key_text, key_code = _wl_key_text, _wl_key_code
