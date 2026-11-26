"""Notifications: how long a pop-up stays and where it appears. Saved in
~/.config/spark/notifications.json, which the Spark shell's notification service reads."""

from typing import Dict

from . import core

POSITIONS = (("Top right", 'TopRight'), ("Top left", 'TopLeft'), ("Bottom right", 'BottomRight'),
             ("Bottom left", 'BottomLeft'), ("Top", 'TopCenter'), ("Bottom", 'BottomCenter'))
SECONDS = (3, 5, 8, 12, 20)


def get() -> Dict[str, object]:
    saved = core.spark_load('notifications')
    return {'seconds': int(saved.get('seconds') or 5),
            'position': saved.get('position') or 'TopRight'}


def save(seconds: int = None, position: str = None) -> bool:
    values = {k: v for k, v in (('seconds', seconds), ('position', position)) if v is not None}
    return core.spark_save('notifications', **values)
