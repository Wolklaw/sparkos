"""Turn what udisks reports about a drive's health (SMART for SATA and NVMe) into a short
verdict and a list of facts. Pure functions on the dictionary Backend.smart() returns."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ATA attribute ids that say a drive is wearing out, and what each is called here (text key)
ATA_WATCHED = {5: 'smart.reallocated', 187: 'smart.uncorrectable', 188: 'smart.timeouts',
               196: 'smart.realloc_events', 197: 'smart.pending', 198: 'smart.offline_bad',
               199: 'smart.crc'}
ATA_WEAR = (177, 231, 233)               # SSD life left, as a normalised value (100 = new)
ATA_TEMP = (194, 190)


@dataclass
class Health:
    verdict: str = 'unknown'                       # good, warning, failing, unknown
    supported: bool = False
    temperature_c: Optional[float] = None
    hours: Optional[int] = None
    selftest: str = ''
    # (text key, value text) rows
    facts: List[Tuple[str, str]] = field(default_factory=list)
    # keys of the problems found (text keys)
    problems: List[str] = field(default_factory=list)
    updated: int = 0                               # unix time of the last SMART read, 0 = never


def kelvin_to_c(value: Any) -> Optional[float]:
    try:
        k = float(value)
    except (TypeError, ValueError):
        return None
    return round(k - 273.15, 1) if k > 0 else None


def _raw(pretty: int) -> int:
    return int(pretty) if pretty is not None else 0


def summarise(data: Dict[str, Any]) -> Health:
    """`data` is {'kind': 'ata'|'nvme'|'none', 'props': {...}, 'attributes': ...}."""
    kind = data.get('kind', 'none')
    props = data.get('props') or {}
    if kind == 'ata':
        return _ata(props, data.get('attributes') or [])
    if kind == 'nvme':
        return _nvme(props, data.get('attributes') or {})
    return Health()


def _ata(props: Dict[str, Any], attributes: List[Any]) -> Health:
    h = Health(supported=bool(props.get('SmartSupported')))
    if not h.supported:
        return h
    h.updated = int(props.get('SmartUpdated') or 0)
    if not h.updated:
        h.facts.append(('smart.not_read', ''))
        return h
    h.temperature_c = kelvin_to_c(props.get('SmartTemperature'))
    seconds = props.get('SmartPowerOnSeconds')
    h.hours = int(seconds) // 3600 if seconds else None
    h.selftest = str(props.get('SmartSelftestStatus') or '')
    failing = bool(props.get('SmartFailing'))
    worn = False
    for ident, _name, _flags, value, _worst, threshold, pretty, _unit, _more in attributes:
        if ident in ATA_WATCHED and _raw(pretty) > 0:
            h.facts.append((ATA_WATCHED[ident], str(_raw(pretty))))
            # reallocated, pending and uncorrectable sectors are the ones that predict a failure
            if ident in (5, 197, 198, 187):
                h.problems.append(ATA_WATCHED[ident])
        if threshold and 0 < value <= threshold:
            failing = True                       # a normalised value at or under its threshold
        if ident in ATA_WEAR and 0 < value <= 100:
            h.facts.append(('smart.life_left', f'{value}'))
            worn = worn or value <= 10
    if props.get('SmartNumBadSectors'):
        h.facts.append(('smart.bad_sectors', str(int(props['SmartNumBadSectors']))))
        h.problems.append('smart.bad_sectors')
    if failing:
        h.verdict = 'failing'
        h.problems.insert(0, 'smart.failing')
    elif h.problems or worn:
        h.verdict = 'warning'
        if worn:
            h.problems.append('smart.worn')
    else:
        h.verdict = 'good'
    return h


def _nvme(props: Dict[str, Any], attrs: Dict[str, Any]) -> Health:
    h = Health(supported=True)
    h.updated = int(props.get('SmartUpdated') or 0)
    if not h.updated and not attrs:
        h.facts.append(('smart.not_read', ''))
        return h
    h.temperature_c = kelvin_to_c(props.get('SmartTemperature'))
    hours = props.get('SmartPowerOnHours')
    h.hours = int(hours) if hours else None
    h.selftest = str(props.get('SmartSelftestStatus') or '')
    warnings = [str(w) for w in (props.get('SmartCriticalWarning') or [])]
    used = attrs.get('percent_used')
    spare, spare_min = attrs.get('avail_spare'), attrs.get('spare_thresh')
    media = attrs.get('media_errors') or 0
    if used is not None:
        h.facts.append(('smart.life_left', str(max(0, 100 - int(used)))))
    if spare is not None:
        h.facts.append(('smart.spare', f'{int(spare)}'))
    if media:
        h.facts.append(('smart.media_errors', str(int(media))))
    for key, label in (('power_cycles', 'smart.power_cycles'),
                       ('unsafe_shutdowns', 'smart.unsafe_shutdowns'),
                       ('num_err_log_entries', 'smart.error_log')):
        if attrs.get(key) is not None:
            h.facts.append((label, str(int(attrs[key]))))
    for key, label in (('total_data_read', 'smart.read'), ('total_data_written', 'smart.written')):
        if attrs.get(key) is not None:
            h.facts.append((label, str(int(attrs[key]))))      # bytes; the window formats it
    if warnings:
        h.problems.append('smart.critical')
    if media:
        h.problems.append('smart.media_errors')
    low_spare = spare is not None and spare_min is not None and int(spare) <= int(spare_min)
    if low_spare:
        h.problems.append('smart.spare_low')
    worn = used is not None and int(used) >= 90
    if worn:
        h.problems.append('smart.worn')
    if warnings and any(w in ('reliability', 'media_read_only', 'volatile_memory') for w in warnings):
        h.verdict = 'failing'
    elif h.problems:
        h.verdict = 'warning'
    else:
        h.verdict = 'good'
    return h
