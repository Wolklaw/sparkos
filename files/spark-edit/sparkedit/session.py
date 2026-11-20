"""The last session (which files were open, where the cursor was) and the autosave of
unsaved work, both in ~/.local/state/spark-edit/. No Tk in here.

Every buffer with unsaved changes is written to autosave/<id>.txt a moment after the last
key press, with autosave/<id>.json saying which file it belongs to and how to save it.
Saving the file or closing it without saving removes them. Quitting keeps them: the next
start reopens those buffers with the changes still unsaved, as they were. A crash or a power
cut leaves them too, and they come back the same way. Each record names the process that
wrote it, so a second Spark Edit window never takes over the first one's buffers.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import core
from .core import log


def autosave_dir() -> str:
    path = os.path.join(core.state_dir(), 'autosave')
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return path


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if pid <= 0 or os.name != 'posix':
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass
class Autosave:
    id: str
    path: Optional[str]          # the file it belongs to; None for a new, never-saved buffer
    title: str
    fmt: Dict[str, Any] = field(default_factory=dict)
    language: Optional[str] = None
    cursor: str = '1.0'
    disk_mtime: Optional[float] = None   # the file's time when it was opened or last saved
    pid: int = 0
    time: float = 0.0
    text: Optional[str] = None   # loaded on demand

    def meta(self) -> Dict[str, Any]:
        return {'path': self.path, 'title': self.title, 'fmt': self.fmt,
                'language': self.language, 'cursor': self.cursor, 'disk_mtime': self.disk_mtime,
                'pid': self.pid, 'time': self.time}


def write_autosave(record: Autosave, text: str) -> bool:
    """Text first, then the record that points at it, each swapped in whole."""
    folder = autosave_dir()
    record.pid, record.time = os.getpid(), time.time()
    base = os.path.join(folder, record.id)
    try:
        for suffix, payload in (('.txt', text), ('.json', json.dumps(record.meta()))):
            with open(base + suffix + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(base + suffix + '.tmp', base + suffix)
        return True
    except OSError as exc:
        log.warning("autosave of %s failed: %s", record.title, exc)
        return False


def drop_autosave(autosave_id: Optional[str]) -> None:
    if not autosave_id:
        return
    base = os.path.join(autosave_dir(), autosave_id)
    for suffix in ('.txt', '.json'):
        try:
            os.unlink(base + suffix)
        except OSError:
            pass


def read_autosave(autosave_id: str) -> Optional[Autosave]:
    base = os.path.join(autosave_dir(), autosave_id)
    try:
        with open(base + '.json', encoding='utf-8') as f:
            meta = json.load(f)
        with open(base + '.txt', encoding='utf-8', newline='') as f:
            text = f.read()
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("autosave %s unreadable: %s", autosave_id, exc)
        return None
    if not isinstance(meta, dict):
        return None
    return Autosave(id=autosave_id, path=meta.get('path'), title=str(meta.get('title') or ''),
                    fmt=meta.get('fmt') or {}, language=meta.get('language'),
                    cursor=str(meta.get('cursor') or '1.0'),
                    disk_mtime=meta.get('disk_mtime'), pid=int(meta.get('pid') or 0),
                    time=float(meta.get('time') or 0), text=text)


def orphans(claimed: List[str]) -> List[Autosave]:
    """Autosaves no running Spark Edit owns and the session doesn't list, oldest first:
    what a crash left behind."""
    out = []
    try:
        names = os.listdir(autosave_dir())
    except OSError:
        return out
    for name in names:
        if not name.endswith('.json') or name[:-5] in claimed:
            continue
        record = read_autosave(name[:-5])
        if record and not pid_alive(record.pid):
            out.append(record)
    out.sort(key=lambda r: r.time)
    return out


def load_session() -> Dict[str, Any]:
    data = core.load_json(core.state_dir(), 'session.json')
    if not isinstance(data, dict) or not isinstance(data.get('tabs'), list):
        return {'tabs': [], 'current': 0}
    return data


def save_session(tabs: List[Dict[str, Any]], current: int) -> None:
    core.save_json(core.state_dir(), 'session.json',
                   {'tabs': tabs, 'current': current, 'pid': os.getpid(), 'time': time.time()})
