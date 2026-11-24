"""The settings: what to back up where, how often, how many to keep. Written by the helper as
root to /etc/spark-backup/config.json, read by the service and (to show them) by the window.
The same validate() runs in all three, so the file can't hold anything else."""

import json
import os
import re
from typing import Any, Dict

from . import CONFIG_PATH

MAX_FILE_BYTES = 8192
EVERY = ("daily", "weekly")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
KEEP_MIN, KEEP_MAX = 1, 365
DEFAULT_KEEP_LOCAL, DEFAULT_KEEP_TARGET = 7, 14
UUID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z-]{3,63}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ConfigError(ValueError):
    pass


def config_path() -> str:
    return os.environ.get("SPARK_BACKUP_CONFIG") or CONFIG_PATH


def default() -> Dict[str, Any]:
    return {"version": 1, "enabled": False,
            "schedule": {"every": "daily", "time": "02:00", "weekday": "Sun"},
            "keep_local": DEFAULT_KEEP_LOCAL, "keep_target": DEFAULT_KEEP_TARGET,
            "target": None}


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be a whole number")
    if not KEEP_MIN <= value <= KEEP_MAX:
        raise ConfigError(f"{name} must be between {KEEP_MIN} and {KEEP_MAX}")
    return value


def validate(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError("the settings must be an object")
    out = default()
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            raise ConfigError("enabled must be true or false")
        out["enabled"] = data["enabled"]
    sched = data.get("schedule", out["schedule"])
    if not isinstance(sched, dict):
        raise ConfigError("schedule must be an object")
    every = sched.get("every", "daily")
    if every not in EVERY:
        raise ConfigError(f"schedule.every must be one of {', '.join(EVERY)}")
    at = sched.get("time", "02:00")
    if not isinstance(at, str) or not TIME_RE.match(at):
        raise ConfigError("schedule.time must look like 02:00")
    day = sched.get("weekday", "Sun")
    if day not in WEEKDAYS:
        raise ConfigError("schedule.weekday must be Mon to Sun")
    out["schedule"] = {"every": every, "time": at, "weekday": day}
    out["keep_local"] = _int(data.get("keep_local", DEFAULT_KEEP_LOCAL), "keep_local")
    out["keep_target"] = _int(data.get("keep_target", DEFAULT_KEEP_TARGET), "keep_target")
    target = data.get("target")
    if target is not None:
        if not isinstance(target, dict):
            raise ConfigError("target must be an object or null")
        uuid = target.get("uuid")
        if not isinstance(uuid, str) or not UUID_RE.match(uuid):
            raise ConfigError("target.uuid is not a filesystem id")
        label = target.get("label", "")
        fstype = target.get("fstype", "")
        if not isinstance(label, str) or not isinstance(fstype, str):
            raise ConfigError("target.label and target.fstype must be text")
        out["target"] = {"uuid": uuid, "label": label[:64].replace("\n", " "),
                         "fstype": re.sub(r"[^0-9a-z_]", "", fstype.lower())[:16]}
    return out


def loads(text: str) -> Dict[str, Any]:
    if len(text) > MAX_FILE_BYTES:
        raise ConfigError("the settings file is too big")
    try:
        return validate(json.loads(text))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"not valid JSON: {exc}") from exc


def load(path: str = "") -> Dict[str, Any]:
    """The saved settings, or the defaults when nothing was saved yet."""
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as f:
            return loads(f.read(MAX_FILE_BYTES + 1))
    except FileNotFoundError:
        return default()
    except OSError as exc:
        raise ConfigError(f"can't read {path}: {exc}") from exc


def save(data: Dict[str, Any], path: str = "") -> None:
    path = path or config_path()
    data = validate(data)
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
