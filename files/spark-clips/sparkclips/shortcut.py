"""The save-a-clip shortcut. It is registered by the desktop entry (an action with
X-KDE-Shortcuts, read by KDE's kglobalaccel). This only asks kglobalaccel who owns the key, so
the window can say when something else has taken it instead of stealing it."""

from typing import Optional

from . import APP_ID

KEYS = 'Meta+Alt+G'
QT_KEY = 0x10000000 | 0x08000000 | 0x47        # Qt::META | Qt::ALT | 'G'
OURS = APP_ID + '.desktop'


def owner(key: int = QT_KEY) -> Optional[str]:
    """The name of the program that holds the key; None when it is free, ours, or when
    kglobalaccel can't be asked (not KDE, no session bus)."""
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync('org.kde.kglobalaccel', '/kglobalaccel', 'org.kde.KGlobalAccel',
                              'action', GLib.Variant('(i)', (key,)), GLib.VariantType('(as)'),
                              Gio.DBusCallFlags.NO_AUTO_START, 1500, None)
        ids = list(reply.unpack()[0])
    except Exception:                               # noqa: BLE001 - not KDE, no bus, no gi
        return None
    if not ids or ids[0] == OURS:
        return None
    return (ids[2] if len(ids) > 2 and ids[2] else ids[0]) or None
