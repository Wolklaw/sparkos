"""The fan configuration file: what each fan should do. The window writes it through the
polkit-gated helper; the daemon (root) reads it. Both validate it, because the daemon must
never trust a file that a user's program wrote."""

import json
import os
import re
from typing import Any, Dict, List

from . import SYSTEM_CONFIG
from .curve import PRESETS, FanController, fixed_curve, normalise

VERSION = 1
SOURCES = ("cpu", "gpu", "liquid", "max")      # max: the hotter of CPU and GPU
KEY_PATTERN = re.compile(r'^[A-Za-z0-9_.:+@/ -]{1,120}$')
PRESET_NAMES = tuple(PRESETS) + ("fixed", "custom")
MAX_FILE_BYTES = 256 * 1024


class ConfigError(ValueError):
    """The file isn't a fan configuration."""


DEFAULT_FAN: Dict[str, Any] = {
    "enabled": False,          # off: the fan stays on its own (firmware/BIOS) control
    "preset": "balanced",
    "source": "max",
    "fixed": 50,
    "curve": PRESETS["balanced"],
    "hysteresis": 3.0,
    "min_duty": 20,
    "max_duty": 100,
    "ramp_up": 8.0,
    "ramp_down": 2.0,
}


def config_path() -> str:
    return os.environ.get("SPARK_CONTROLLER_CONFIG") or SYSTEM_CONFIG


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number")
    if value != value or not low <= value <= high:      # NaN fails the second test
        raise ConfigError(f"{name} must be between {low:g} and {high:g}")
    return float(value)


def validate_fan(entry: Any) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        raise ConfigError("a fan entry must be an object")
    merged = dict(DEFAULT_FAN)
    merged.update({k: v for k, v in entry.items() if k in DEFAULT_FAN})
    out: Dict[str, Any] = {}
    if not isinstance(merged["enabled"], bool):
        raise ConfigError("enabled must be true or false")
    out["enabled"] = merged["enabled"]
    if merged["preset"] not in PRESET_NAMES:
        raise ConfigError(f"unknown preset {merged['preset']!r}")
    out["preset"] = merged["preset"]
    if merged["source"] not in SOURCES:
        raise ConfigError(f"unknown source {merged['source']!r}")
    out["source"] = merged["source"]
    out["fixed"] = _number(merged["fixed"], "fixed", 0, 100)
    curve = merged["curve"]
    if not isinstance(curve, list) or not 1 <= len(curve) <= 24:
        raise ConfigError("curve must be a list of 1 to 24 points")
    points: List[List[float]] = []
    for point in curve:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ConfigError("each curve point is [temperature, duty]")
        points.append([_number(point[0], "temperature", 0, 120),
                       _number(point[1], "duty", 0, 100)])
    out["curve"] = [list(p) for p in normalise(points)]
    out["hysteresis"] = _number(merged["hysteresis"], "hysteresis", 0, 15)
    out["min_duty"] = _number(merged["min_duty"], "min_duty", 0, 100)
    out["max_duty"] = _number(merged["max_duty"], "max_duty", 0, 100)
    if out["max_duty"] < out["min_duty"]:
        raise ConfigError("max_duty is below min_duty")
    out["ramp_up"] = _number(merged["ramp_up"], "ramp_up", 0.5, 100)
    out["ramp_down"] = _number(merged["ramp_down"], "ramp_down", 0.1, 100)
    return out


def validate(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError("the file must hold an object")
    fans = data.get("fans", {})
    if not isinstance(fans, dict) or len(fans) > 64:
        raise ConfigError("fans must be an object with at most 64 entries")
    out: Dict[str, Any] = {"version": VERSION, "fans": {}}
    for key, entry in fans.items():
        if not isinstance(key, str) or not KEY_PATTERN.match(key):
            raise ConfigError(f"bad fan key {key!r}")
        out["fans"][key] = validate_fan(entry)
    return out


def empty() -> Dict[str, Any]:
    return {"version": VERSION, "fans": {}}


def loads(text: str) -> Dict[str, Any]:
    try:
        return validate(json.loads(text))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"not valid JSON: {exc}") from exc


def load(path: str = "") -> Dict[str, Any]:
    """The saved configuration; an empty one when there is none yet. Raises ConfigError for a
    file that exists but is broken, so callers keep the last good one."""
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        return empty()
    if len(text) > MAX_FILE_BYTES:
        raise ConfigError("the file is too large")
    return loads(text)


def save(config: Dict[str, Any], path: str = "") -> None:
    """Validate, then write a temp file and swap it in, so a crash keeps the old file."""
    path = path or config_path()
    clean = validate(config)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def curve_for(entry: Dict[str, Any]) -> List[List[float]]:
    """The points a fan entry stands for: a preset's, a flat line, or its own."""
    preset = entry.get("preset", "balanced")
    if preset in PRESETS:
        return [list(p) for p in PRESETS[preset]]
    if preset == "fixed":
        return [list(p) for p in fixed_curve(entry.get("fixed", 50))]
    return [list(p) for p in entry.get("curve", PRESETS["balanced"])]


def controller_for(entry: Dict[str, Any]) -> FanController:
    entry = validate_fan(entry)
    fixed = entry["preset"] == "fixed"
    return FanController(
        curve_for(entry),
        hysteresis=entry["hysteresis"],
        min_duty=entry["min_duty"], max_duty=entry["max_duty"],
        ramp_up=entry["ramp_up"], ramp_down=entry["ramp_down"],
        average_s=0 if fixed else 6.0)
