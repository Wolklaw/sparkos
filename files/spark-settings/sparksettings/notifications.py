"""Notifications: how long a pop-up stays, where it appears, and whether notification sounds are
muted. Saved in ~/.config/spark/notifications.json (the Spark shell's notification service
reads it) and in Plasma's plasmanotifyrc so Plasma follows today."""

from typing import Dict

from . import core, plasma

POSITIONS = (("Top right", 'TopRight'), ("Top left", 'TopLeft'), ("Bottom right", 'BottomRight'),
             ("Bottom left", 'BottomLeft'), ("Top", 'TopCenter'), ("Bottom", 'BottomCenter'))
SECONDS = (3, 5, 8, 12, 20)


def get() -> Dict[str, object]:
    saved = core.spark_load('notifications')
    now = plasma.notify_get()
    return {'seconds': int(saved.get('seconds') or int(now['timeout_ms']) // 1000 or 5),
            'position': saved.get('position') or now['position'] or 'BottomRight',
            'sounds_muted': saved.get('sounds_muted', now['sounds_muted'])}


def save(seconds: int = None, position: str = None, sounds_muted: bool = None) -> bool:
    values = {k: v for k, v in (('seconds', seconds), ('position', position),
                                ('sounds_muted', sounds_muted)) if v is not None}
    ok = core.spark_save('notifications', **values)
    return plasma.notify_set(seconds * 1000 if seconds is not None else None, position,
                             sounds_muted) and ok
