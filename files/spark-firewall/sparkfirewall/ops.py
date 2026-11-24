"""Changes to the firewall, as data. The window builds a list of operations, the helper (root,
through pkexec) validates the list again and turns each into exact command lines. Nothing is run
through a shell, every name is checked against a strict pattern, and an operation that is not
one of the five below is refused, so a bug in the window (or another program running as the
user) can only do what this window can do.

  {"op": "service",      "zone": "public", "name": "steam-streaming", "add": true}
  {"op": "port",         "zone": "public", "port": "8080/tcp",        "add": false}
  {"op": "default-zone", "zone": "public"}
  {"op": "network-zone", "device": "eno1", "connection": "<uuid>" or "", "zone": "home"}
  {"op": "power",        "on": false}

Rules are written to the permanent configuration and applied at once with one reload, so what
the window shows is what is still there after a restart."""

import json
import re
from typing import Any, Dict, List, NamedTuple

from .fw import parse_port

MAX_OPS = 64
MAX_BYTES = 64 * 1024
ZONE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
SERVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
DEVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,14}")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
CMD = "firewall-cmd"


class OpError(ValueError):
    """The operation list is not one this app would send."""


class Step(NamedTuple):
    argv: List[str]
    needs_daemon: bool = False     # skipped when firewalld is stopped (a live-only change)


def _check(pattern, value: Any, what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise OpError(f"bad {what}: {value!r}")
    return value


def normalise_port(spec: Any) -> str:
    parsed = parse_port(spec) if isinstance(spec, str) else None
    if not parsed or parsed[2] not in ("tcp", "udp"):
        raise OpError(f"bad port: {spec!r}")
    low, high, proto = parsed
    return f"{low}/{proto}" if low == high else f"{low}-{high}/{proto}"


def validate_op(op: Any) -> Dict[str, Any]:
    if not isinstance(op, dict):
        raise OpError("an operation must be an object")
    kind = op.get("op")
    if kind == "service":
        return {"op": kind, "zone": _check(ZONE, op.get("zone"), "zone"),
                "name": _check(SERVICE, op.get("name"), "service"), "add": op.get("add") is True}
    if kind == "port":
        return {"op": kind, "zone": _check(ZONE, op.get("zone"), "zone"),
                "port": normalise_port(op.get("port")), "add": op.get("add") is True}
    if kind == "default-zone":
        return {"op": kind, "zone": _check(ZONE, op.get("zone"), "zone")}
    if kind == "network-zone":
        connection = op.get("connection") or ""
        if connection:
            _check(UUID, connection, "connection")
        return {"op": kind, "device": _check(DEVICE, op.get("device"), "device"),
                "connection": connection, "zone": _check(ZONE, op.get("zone"), "zone")}
    if kind == "power":
        return {"op": kind, "on": op.get("on") is True}
    raise OpError(f"unknown operation: {kind!r}")


def validate(ops: Any) -> List[Dict[str, Any]]:
    if not isinstance(ops, list) or not ops:
        raise OpError("no operations")
    if len(ops) > MAX_OPS:
        raise OpError("too many operations")
    clean = [validate_op(op) for op in ops]
    if any(op["op"] == "power" for op in clean) and len(clean) > 1:
        raise OpError("turning the firewall on or off goes alone")
    return clean


def loads(text: str) -> List[Dict[str, Any]]:
    if len(text) > MAX_BYTES:
        raise OpError("too much input")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise OpError(f"not JSON: {exc}")
    return validate(data.get("ops") if isinstance(data, dict) else data)


def steps(op: Dict[str, Any]) -> List[Step]:
    """The command lines for one validated operation."""
    kind = op["op"]
    if kind == "service":
        verb = "--add-service=" if op["add"] else "--remove-service="
        return [Step([CMD, "--permanent", f"--zone={op['zone']}", verb + op["name"]])]
    if kind == "port":
        verb = "--add-port=" if op["add"] else "--remove-port="
        return [Step([CMD, "--permanent", f"--zone={op['zone']}", verb + op["port"]])]
    if kind == "default-zone":
        return [Step([CMD, f"--set-default-zone={op['zone']}"], True)]
    if kind == "network-zone":
        zone, device = op["zone"], op["device"]
        out: List[Step] = []
        if op["connection"]:
            # NetworkManager hands the interface to this zone every time it connects
            out.append(Step(["nmcli", "connection", "modify", "uuid", op["connection"],
                             "connection.zone", zone]))
        else:
            out.append(Step([CMD, "--permanent", f"--zone={zone}", f"--change-interface={device}"]))
        out.append(Step([CMD, f"--zone={zone}", f"--change-interface={device}"], True))
        return out
    if op["on"]:
        return [Step(["systemctl", "enable", "--now", "firewalld.service"])]
    return [Step(["systemctl", "disable", "--now", "firewalld.service"])]


def needs_reload(ops: List[Dict[str, Any]]) -> bool:
    return any(op["op"] in ("service", "port") for op in ops)


def describe(op: Dict[str, Any]) -> str:
    """One line for the log and the helper's output."""
    return " ".join(f"{k}={v}" for k, v in op.items() if v not in ("", None))
