"""What Spark Clock remembers, in a few small JSON files, written without ever leaving a half
file (write to a temporary name, then rename) and under one lock, because the window and the
background service both change them.

  ~/.config/spark-clock/clock.json            alarms, timer presets, world clocks, settings
  ~/.local/state/spark-clock/timers.json      the timers, running or not
  ~/.local/state/spark-clock/stopwatch.json   the stopwatch
  ~/.local/state/spark-clock/service.json     the service's own notes: last beat, snoozes
  ~/.local/state/spark-clock/commands.json    what the window asks the service to do
"""

import contextlib
import copy
import fcntl
import json
import os
import tempfile
import time
import uuid
from typing import Any, Callable, Dict, List

from . import core
from .schedule import parse_time

DEFAULT_PRESETS = [60, 180, 300, 600, 900, 1800]       # seconds
SOUNDS = ('beacon', 'pulse', 'chime', 'drift', 'static')
SNOOZES = (5, 9, 10, 15)
DEFAULT_CONFIG: Dict[str, Any] = {
    'alarms': [],
    'presets': DEFAULT_PRESETS,
    'world': ['America/Toronto'],
    'settings': {'sound': 'beacon', 'snooze': 9, 'ring_minutes': 5, 'volume': 80},
}
MAX_ALARMS = 100
MAX_TIMERS = 50


def path(name: str) -> str:
    base = core.config_dir() if name == 'clock.json' else core.state_dir()
    return os.path.join(base, name)


@contextlib.contextmanager
def locked():
    """One writer at a time, across processes."""
    fd = os.open(os.path.join(core.state_dir(), 'lock'), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)             # closing releases the lock


def read_json(name: str, default: Any) -> Any:
    try:
        with open(path(name), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return copy.deepcopy(default)


def write_json(name: str, data: Any) -> None:
    target = path(name)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix='.tmp-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def mtime(name: str) -> float:
    try:
        return os.stat(path(name)).st_mtime_ns
    except OSError:
        return 0.0


def new_id() -> str:
    return uuid.uuid4().hex[:8]


# ─── alarms, presets, settings ───

def clean_alarm(raw: Any) -> Dict[str, Any]:
    """A saved alarm made safe to use, whatever was in the file."""
    raw = raw if isinstance(raw, dict) else {}
    parsed = parse_time(str(raw.get('time', ''))) or (7, 0)
    days = sorted({d for d in raw.get('days', []) if isinstance(d, int) and 0 <= d <= 6})
    snooze = raw.get('snooze')
    return {
        'id': str(raw.get('id') or new_id()),
        'time': f"{parsed[0]:02d}:{parsed[1]:02d}",
        'days': days,
        'label': str(raw.get('label', ''))[:80],
        'sound': str(raw.get('sound') or DEFAULT_CONFIG['settings']['sound']),
        'snooze': snooze if isinstance(snooze, int) and 1 <= snooze <= 60 else 9,
        'enabled': bool(raw.get('enabled', True)),
    }


def clean_config(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    config = copy.deepcopy(DEFAULT_CONFIG)
    alarms = raw.get('alarms', [])
    config['alarms'] = [clean_alarm(a) for a in (alarms if isinstance(alarms, list) else [])
                        [:MAX_ALARMS]]
    presets = [p for p in raw.get('presets', DEFAULT_PRESETS)
               if isinstance(p, int) and 1 <= p <= 99 * 3600]
    config['presets'] = sorted(set(presets)) or list(DEFAULT_PRESETS)
    world = [z for z in raw.get('world', config['world']) if isinstance(z, str) and z]
    config['world'] = world or list(DEFAULT_CONFIG['world'])
    settings = raw.get('settings') if isinstance(raw.get('settings'), dict) else {}
    for key, default in DEFAULT_CONFIG['settings'].items():
        value = settings.get(key, default)
        config['settings'][key] = value if type(value) is type(default) else default
    config['settings']['volume'] = max(5, min(100, config['settings']['volume']))
    config['settings']['ring_minutes'] = max(1, min(60, config['settings']['ring_minutes']))
    return config


def load_config() -> Dict[str, Any]:
    return clean_config(read_json('clock.json', DEFAULT_CONFIG))


def update_config(change: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
    """Read, let `change` edit the dict, save. Returns what was saved."""
    with locked():
        config = load_config()
        change(config)
        config = clean_config(config)
        write_json('clock.json', config)
        return config


# ─── timers ───

def clean_timer(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    duration = raw.get('duration')
    duration = duration if isinstance(duration, (int, float)) and duration > 0 else 60
    state = raw.get('state') if raw.get('state') in ('running', 'paused', 'ringing', 'done') \
        else 'paused'
    end = raw.get('end') if isinstance(raw.get('end'), (int, float)) else None
    remaining = raw.get('remaining')
    remaining = remaining if isinstance(remaining, (int, float)) and remaining >= 0 else duration
    if state == 'running' and end is None:
        state = 'paused'
    return {'id': str(raw.get('id') or new_id()), 'label': str(raw.get('label', ''))[:80],
            'duration': float(duration), 'state': state, 'end': end, 'remaining': float(remaining),
            'sound': str(raw.get('sound') or ''), 'created': raw.get('created') or time.time()}


def load_timers() -> List[Dict[str, Any]]:
    data = read_json('timers.json', [])
    return [clean_timer(t) for t in (data if isinstance(data, list) else [])][:MAX_TIMERS]


def update_timers(change: Callable[[List[Dict[str, Any]]], Any]) -> List[Dict[str, Any]]:
    with locked():
        timers = load_timers()
        change(timers)
        timers = [clean_timer(t) for t in timers][:MAX_TIMERS]
        write_json('timers.json', timers)
        return timers


def timer_left(timer: Dict[str, Any], now: float) -> float:
    if timer['state'] == 'running' and timer['end'] is not None:
        return max(0.0, timer['end'] - now)
    if timer['state'] in ('ringing', 'done'):
        return 0.0
    return timer['remaining']


def add_timer(seconds: float, label: str = '', now: float = 0.0) -> Dict[str, Any]:
    now = now or time.time()
    timer = clean_timer({'duration': seconds, 'label': label, 'state': 'running',
                         'end': now + seconds, 'remaining': seconds})
    update_timers(lambda timers: timers.append(timer))
    return timer


# ─── stopwatch ───

def load_stopwatch() -> Dict[str, Any]:
    raw = read_json('stopwatch.json', {})
    raw = raw if isinstance(raw, dict) else {}
    laps = [float(x) for x in raw.get('laps', []) if isinstance(x, (int, float))]
    started = raw.get('started') if isinstance(raw.get('started'), (int, float)) else None
    elapsed = raw.get('elapsed') if isinstance(raw.get('elapsed'), (int, float)) else 0.0
    return {'started': started, 'elapsed': float(max(0.0, elapsed)), 'laps': laps}


def stopwatch_total(sw: Dict[str, Any], now: float) -> float:
    return sw['elapsed'] + (max(0.0, now - sw['started']) if sw['started'] else 0.0)


def save_stopwatch(sw: Dict[str, Any]) -> None:
    with locked():
        write_json('stopwatch.json', sw)


# ─── the service's notes and the window's requests ───

def load_service() -> Dict[str, Any]:
    raw = read_json('service.json', {})
    raw = raw if isinstance(raw, dict) else {}
    return {'pid': raw.get('pid'), 'beat': raw.get('beat', 0), 'last_tick': raw.get('last_tick'),
            'snoozes': [s for s in raw.get('snoozes', []) if isinstance(s, dict)],
            'ringing': [r for r in raw.get('ringing', []) if isinstance(r, dict)]}


def save_service(data: Dict[str, Any]) -> None:
    with locked():
        write_json('service.json', data)


def service_alive(now: float, service: Dict[str, Any] = None) -> bool:
    """The service writes a beat every few seconds; no beat for 30 s means it isn't running."""
    service = service or load_service()
    beat = service.get('beat') or 0
    return isinstance(beat, (int, float)) and abs(now - beat) < 30


def send_command(cmd: str, key: str) -> None:
    """The window asks the service to stop or snooze a ring."""
    with locked():
        commands = read_json('commands.json', [])
        commands = commands if isinstance(commands, list) else []
        commands.append({'cmd': cmd, 'key': key, 'at': time.time()})
        write_json('commands.json', commands[-20:])


def take_commands() -> List[Dict[str, Any]]:
    with locked():
        commands = read_json('commands.json', [])
        if commands:
            write_json('commands.json', [])
    return [c for c in commands if isinstance(c, dict)] if isinstance(commands, list) else []
