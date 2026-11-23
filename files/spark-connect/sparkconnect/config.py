"""The machine list: ~/.config/spark-connect/machines.toml (on Windows,
%APPDATA%\\spark-connect\\machines.toml). The owner writes it by hand; Spark Connect only reads it.
machines.example.toml next to the app shows every field, with made-up names.

Every name that ends up in a command on a server (units, the host, paths) is checked against
a short list of safe characters here, and quoted again where it is used."""

import fnmatch
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import tomllib                      # Python 3.11+
except ImportError:                     # pragma: no cover - older Pythons
    tomllib = None                      # type: ignore[assignment]

KINDS = ('linux',)                      # 'tablet' comes with a later part
TRANSPORTS = ('ssh',)                   # 'hub' comes with a later part
POWER = ('update', 'reboot')            # what a machine's `allow` can name
SYSTEM, USER = 'system', 'user'

_UNIT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9@._\-\\:]{0,127}$')
_HOST = re.compile(r'^[A-Za-z0-9_\[][A-Za-z0-9@._\-\[\]:]{0,252}$')
_LOCAL_URL = re.compile(r'^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?(/[^\s\'"`$\\;|&<>]*)?$')
_SITE_URL = re.compile(r'^https?://[^\s]+$')
_PATH = re.compile(r'^[A-Za-z0-9~/._\- ]{1,200}$')
_PATTERN = re.compile(r'^[A-Za-z0-9@._\-\\:*?\[\]]{1,128}$')


class ConfigError(ValueError):
    pass


@dataclass
class Failover:
    dir: str
    active_unit: Optional[Tuple[str, str]] = None   # (scope, name): runs only after a takeover
    netmon_log: str = ''
    failback: str = ''
    watches: str = ''                               # the machine this standby takes over for


@dataclass
class Machine:
    name: str
    host: str
    port: Optional[int] = None
    kind: str = 'linux'
    transport: str = 'ssh'
    units: List[str] = field(default_factory=list)
    user_units: List[str] = field(default_factory=list)
    restartable: List[Tuple[str, str]] = field(default_factory=list)
    known_failed: List[str] = field(default_factory=list)
    tunnel: Optional[Tuple[str, str]] = None
    tunnel_hostnames: List[str] = field(default_factory=list)
    local_checks: List[Tuple[str, str]] = field(default_factory=list)
    failover: Optional[Failover] = None
    allow: List[str] = field(default_factory=list)  # 'update', 'reboot'
    desktop: bool = False                           # a SparkOS desktop: see and control its screen
    console: bool = False                           # a server with no desktop: see its console

    def watched(self) -> List[Tuple[str, str]]:
        return [(SYSTEM, u) for u in self.units] + [(USER, u) for u in self.user_units]

    def can_restart(self, scope: str, unit: str) -> bool:
        return (scope, unit) in self.restartable

    def is_known_failed(self, unit: str) -> bool:
        return any(fnmatch.fnmatchcase(unit, p) or fnmatch.fnmatchcase(unit, p + '.service')
                   for p in self.known_failed)

    def is_tunnel(self, scope: str, unit: str) -> bool:
        return self.tunnel is not None and self.tunnel == (scope, _bare(unit))

    def is_takeover_unit(self, scope: str, unit: str) -> bool:
        return bool(self.failover and self.failover.active_unit == (scope, _bare(unit)))


@dataclass
class Site:
    name: str
    url: str


@dataclass
class Config:
    machines: List[Machine] = field(default_factory=list)
    sites: List[Site] = field(default_factory=list)
    path: str = ''
    found: bool = False


def _bare(unit: str) -> str:
    return unit[:-8] if unit.endswith('.service') else unit


def parse_scoped(text: str, where: str) -> Tuple[str, str]:
    """'user:cloudflared' -> ('user', 'cloudflared'); 'caddy' or 'system:caddy' -> system."""
    scope, sep, name = text.partition(':')
    if not sep:
        scope, name = SYSTEM, text
    if scope not in (SYSTEM, USER):
        raise ConfigError(f"{where}: '{text}' should be NAME, system:NAME or user:NAME")
    return scope, _unit(_bare(name), where)


def _unit(name: Any, where: str) -> str:
    if not isinstance(name, str) or not _UNIT.match(name):
        raise ConfigError(f"{where}: '{name}' is not a unit name")
    return name


def _strings(value: Any, where: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where} should be a list of strings")
    return list(value)


def _machine(raw: Any, index: int) -> Machine:
    where = f"machine {index + 1}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} should be a table")
    name = raw.get('name')
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{where}: needs a name")
    where = f"machine '{name}'"
    known = {'name', 'host', 'port', 'kind', 'transport', 'units', 'user_units', 'restartable',
             'known_failed', 'tunnel', 'tunnel_hostnames', 'local_checks', 'failover',
             'allow', 'desktop', 'console'}
    extra = sorted(set(raw) - known)
    if extra:
        raise ConfigError(f"{where}: unknown setting {', '.join(extra)}")
    host = raw.get('host')
    if not isinstance(host, str) or not _HOST.match(host):
        raise ConfigError(f"{where}: host should be an ssh alias or user@address")
    port = raw.get('port')
    if port is not None and (not isinstance(port, int) or not 0 < port < 65536):
        raise ConfigError(f"{where}: port should be a number from 1 to 65535")
    kind = raw.get('kind', 'linux')
    if kind not in KINDS:
        raise ConfigError(f"{where}: kind '{kind}' isn't supported yet (only {', '.join(KINDS)})")
    transport = raw.get('transport', 'ssh')
    if transport not in TRANSPORTS:
        raise ConfigError(f"{where}: transport '{transport}' isn't supported yet "
                          f"(only {', '.join(TRANSPORTS)})")
    units = [_bare(_unit(u, f"{where} units")) for u in _strings(raw.get('units'), f"{where} units")]
    user_units = [_bare(_unit(u, f"{where} user_units"))
                  for u in _strings(raw.get('user_units'), f"{where} user_units")]
    restartable = [parse_scoped(u, f"{where} restartable")
                   for u in _strings(raw.get('restartable'), f"{where} restartable")]
    watched = {(SYSTEM, u) for u in units} | {(USER, u) for u in user_units}
    for scope, unit in restartable:
        if (scope, unit) not in watched:
            list_name = 'units' if scope == SYSTEM else 'user_units'
            raise ConfigError(f"{where}: restartable {scope}:{unit} is not in {list_name}")
    known_failed = _strings(raw.get('known_failed'), f"{where} known_failed")
    for p in known_failed:
        if not _PATTERN.match(p):
            raise ConfigError(f"{where}: known_failed '{p}' is not a unit name or pattern")
    tunnel = parse_scoped(raw['tunnel'], f"{where} tunnel") if raw.get('tunnel') else None
    hostnames = _strings(raw.get('tunnel_hostnames'), f"{where} tunnel_hostnames")
    checks_raw = raw.get('local_checks') or {}
    if not isinstance(checks_raw, dict):
        raise ConfigError(f"{where}: local_checks should be a table of name = \"url\"")
    checks = []
    for cname, url in checks_raw.items():
        if not re.match(r'^[A-Za-z0-9._\-]{1,40}$', cname):
            raise ConfigError(f"{where}: local check name '{cname}' should be one word")
        if not isinstance(url, str) or not _LOCAL_URL.match(url):
            raise ConfigError(f"{where}: local check '{cname}' should be an http URL on "
                              "127.0.0.1 or localhost (it is fetched on the server itself)")
        checks.append((cname, url))
    failover = None
    if raw.get('failover') is not None:
        fo = raw['failover']
        if not isinstance(fo, dict) or not isinstance(fo.get('dir'), str) \
                or not _PATH.match(fo['dir']):
            raise ConfigError(f"{where}: failover needs dir = \"path on the server\"")
        netmon = fo.get('netmon_log', '')
        if netmon and (not isinstance(netmon, str) or not _PATH.match(netmon)
                       or '..' in netmon or netmon.startswith('/')):
            raise ConfigError(f"{where}: failover netmon_log should be a file name in dir")
        failback = fo.get('failback', '')
        if not isinstance(failback, str) or '\n' in failback or '\r' in failback:
            raise ConfigError(f"{where}: failover failback should be one command line")
        active = parse_scoped(fo['active_unit'], f"{where} failover active_unit") \
            if fo.get('active_unit') else None
        watches = fo.get('watches', '')
        if not isinstance(watches, str):
            raise ConfigError(f"{where}: failover watches should be a machine's name")
        failover = Failover(fo['dir'], active, netmon, failback, watches.strip())
    allow = _strings(raw.get('allow'), f"{where} allow")
    for a in allow:
        if a not in POWER:
            raise ConfigError(f"{where}: allow '{a}' should be one of {', '.join(POWER)}")
    flags = {}
    for flag in ('desktop', 'console'):
        value = raw.get(flag, False)
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: {flag} should be true or false")
        flags[flag] = value
    if flags['desktop'] and flags['console']:
        raise ConfigError(f"{where}: desktop and console are for different machines: "
                          "a machine with a desktop shares its screen, a server shows its console")
    return Machine(name=name.strip(), host=host, port=port, kind=kind, transport=transport,
                   units=units, user_units=user_units, restartable=restartable,
                   known_failed=known_failed, tunnel=tunnel, tunnel_hostnames=hostnames,
                   local_checks=checks, failover=failover, allow=list(dict.fromkeys(allow)), **flags)


def parse(data: Dict[str, Any], path: str = '') -> Config:
    extra = sorted(set(data) - {'machine', 'site'})
    if extra:
        raise ConfigError(f"unknown section {', '.join(extra)} (use [[machine]] and [[site]])")
    machines_raw = data.get('machine', [])
    sites_raw = data.get('site', [])
    if not isinstance(machines_raw, list) or not isinstance(sites_raw, list):
        raise ConfigError("write machines as [[machine]] and sites as [[site]]")
    machines = [_machine(m, i) for i, m in enumerate(machines_raw)]
    names = [m.name for m in machines]
    for n in names:
        if names.count(n) > 1:
            raise ConfigError(f"two machines are called '{n}'")
    for m in machines:
        if m.failover and m.failover.watches and m.failover.watches not in names:
            raise ConfigError(f"machine '{m.name}': failover watches '{m.failover.watches}', "
                              "which isn't in the list")
    sites = []
    for i, s in enumerate(sites_raw):
        if not isinstance(s, dict) or not isinstance(s.get('url'), str) \
                or not _SITE_URL.match(s['url']):
            raise ConfigError(f"site {i + 1} needs url = \"https://...\"")
        sites.append(Site(str(s.get('name') or s['url']), s['url']))
    return Config(machines, sites, path, True)


def load(path: str) -> Config:
    """The config at path. A missing file is an empty list, not an error."""
    if not os.path.isfile(path):
        return Config(path=path, found=False)
    if tomllib is None:
        raise ConfigError("reading machines.toml needs Python 3.11 or newer")
    try:
        with open(path, 'rb') as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{os.path.basename(path)}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"can't read {path}: {exc.strerror}") from exc
    return parse(data, path)
