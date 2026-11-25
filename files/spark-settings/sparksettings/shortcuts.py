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
