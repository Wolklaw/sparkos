"""What the service tells the window: state.json (what it is doing now, in /run) and
history.json (the last runs, in /var/lib). Both are world readable and hold no secrets."""

import json
import os
import time
from typing import Any, Dict, Optional

from . import RUN_DIR, STATE_DIR

HISTORY_KEEP = 30
STALE_S = 6 * 3600       # a "running" note this old belongs to a run that died


def run_dir() -> str:
    return os.environ.get("SPARK_BACKUP_RUN_DIR") or RUN_DIR


def state_dir() -> str:
    return os.environ.get("SPARK_BACKUP_STATE_DIR") or STATE_DIR


def _write(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def _read(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_progress(phase: str, detail: str = "") -> None:
    _write(os.path.join(run_dir(), "state.json"),
           {"phase": phase, "detail": detail, "time": time.time(), "pid": os.getpid()})


def read_progress() -> Optional[Dict[str, Any]]:
    """What a run is doing now, or None when nothing is running (idle, or stopped writing)."""
    data = _read(os.path.join(run_dir(), "state.json"))
    if not isinstance(data, dict) or data.get("phase") in (None, "idle"):
        return None
    try:
        if time.time() - float(data.get("time", 0)) > STALE_S:
            return None
        pid = int(data.get("pid", 0))
        if pid and not os.path.exists(f"/proc/{pid}"):
            return None
    except (TypeError, ValueError):
        return None
    return data


def clear_progress() -> None:
    try:
        _write(os.path.join(run_dir(), "state.json"), {"phase": "idle", "time": time.time()})
    except OSError:
        pass


def load_history() -> Dict[str, Any]:
    data = _read(os.path.join(state_dir(), "history.json"))
    if not isinstance(data, dict):
        return {"runs": [], "last_copied": ""}
    runs = data.get("runs")
    last = data.get("last_copied")
    return {"runs": runs if isinstance(runs, list) else [],
            "last_copied": last if isinstance(last, str) else ""}


def add_run(entry: Dict[str, Any], copied: str = "") -> None:
    data = load_history()
    data["runs"] = (data["runs"] + [entry])[-HISTORY_KEEP:]
    if copied:
        data["last_copied"] = copied
    _write(os.path.join(state_dir(), "history.json"), data)


def last_run() -> Optional[Dict[str, Any]]:
    runs = load_history()["runs"]
    return runs[-1] if runs and isinstance(runs[-1], dict) else None
