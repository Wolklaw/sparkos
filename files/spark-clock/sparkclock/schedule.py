"""When an alarm next rings. Pure functions, no files, no clock of their own."""

import datetime as dt
import re
from typing import Dict, List, Optional

TIME_RE = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')
EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]
WEEKDAYS = [0, 1, 2, 3, 4]


def parse_time(text: str):
    """'7:05' -> (7, 5); None if it isn't a 24 hour time."""
    match = TIME_RE.match((text or '').strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def next_alarm_time(alarm: Dict, after: float) -> Optional[float]:
    """The first moment strictly after `after` (epoch seconds) when this alarm rings, in the
    PC's local time, so a daylight saving change moves nothing: 07:30 stays 07:30. An alarm with
    no days rings once, at the next time that comes."""
    parsed = parse_time(alarm.get('time', ''))
    if parsed is None:
        return None
    hour, minute = parsed
    days = alarm.get('days') or []
    start = dt.datetime.fromtimestamp(after)
    for offset in range(0, 9):
        day = (start + dt.timedelta(days=offset)).date()
        if days and day.weekday() not in days:
            continue
        moment = dt.datetime(day.year, day.month, day.day, hour, minute).timestamp()
        if moment > after:
            return moment
    return None


def days_words(days: List[int], names: List[str], every: str, weekdays: str, weekend: str,
               once: str) -> str:
    """[0,1,2,3,4] -> 'Weekdays'; [] -> 'Once'; [0,2] -> 'Mon Wed'."""
    days = sorted(set(days))
    if not days:
        return once
    if days == EVERY_DAY:
        return every
    if days == WEEKDAYS:
        return weekdays
    if days == [5, 6]:
        return weekend
    return " ".join(names[d] for d in days)


def until_words(seconds: float, h: str = "h", m: str = "min", d: str = "d") -> str:
    """8000 -> '2 h 13 min'; 40 -> '< 1 min'. For "rings in ..."."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"< 1 {m}"
    minutes = seconds // 60
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days} {d} {hours} {h}" if hours else f"{days} {d}"
    if hours:
        return f"{hours} {h} {mins:02d} {m}" if mins else f"{hours} {h}"
    return f"{mins} {m}"
