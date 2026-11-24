"""The App updates page's data: what Spark Apps (files/spark-apps) has installed and what the
image carries, read from the same files the launcher and the root service use. This only reads;
changes go through systemd units that root runs (spark-apps-now@<verb>[:<app>].service, which
polkit allows for the person at the PC), so nothing here writes to /var or /usr."""

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .core import Env, run

STATE = '/var/lib/spark-apps/state.json'
IMAGE_DIR = '/usr/share/spark-apps'
SLUG_RE = re.compile(r'^spark(-[a-z0-9]+)+$')
VERSION_RE = re.compile(r'^\d{1,6}(\.\d{1,6}){1,3}$')


def version_key(version: Any) -> Tuple[int, ...]:
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        return (0, 0, 0, 0)
    parts = [int(p) for p in version.split('.')]
    return tuple(parts + [0] * (4 - len(parts)))


@dataclass
class AppRow:
    slug: str
    name: str
    builtin: str                # the version the image carries
    live: str                   # the live version on disk ('' when none)
    use: str                    # 'live' or 'builtin'
    latest: str                 # the newest the signed index offered ('' when never read)
    waiting: bool               # the newest needs an OS update first (system_api differs)
    error: str                  # why the last install of this app failed ('' when fine)

    @property
    def running(self) -> str:
        """The version the next start uses."""
        if self.live and self.use == 'live' and version_key(self.live) > version_key(self.builtin):
            return self.live
        return self.builtin

    @property
    def on_live(self) -> bool:
        return self.running == self.live and bool(self.live)

    @property
    def newer(self) -> bool:
        return bool(self.latest) and not self.waiting \
            and version_key(self.latest) > version_key(self.running) and self.use == 'live'


@dataclass
class Summary:
    rows: List[AppRow]
    installed: bool             # Spark Apps is in this image
    last_check: float
    result: str                 # '', 'ok', 'offline', 'refused', 'failed'
    error: str


def read(env: Env) -> Summary:
    state = env.read_json(STATE)
    state = state if isinstance(state, dict) else {}
    apps = state.get('apps') if isinstance(state.get('apps'), dict) else {}
    rows: List[AppRow] = []
    try:
        names = sorted(os.listdir(env.path(IMAGE_DIR)))
    except OSError:
        names = []
    for name in names:
        slug = name[:-5]
        if not name.endswith('.json') or not SLUG_RE.fullmatch(slug):
            continue
        record = env.read_json(f'{IMAGE_DIR}/{name}')
        if not isinstance(record, dict) or record.get('live_update') is not True \
                or not VERSION_RE.fullmatch(str(record.get('version'))):
            continue
        app = apps.get(slug) if isinstance(apps.get(slug), dict) else {}
        active = app.get('active') if VERSION_RE.fullmatch(str(app.get('active'))) else ''
        latest = app.get('latest') if VERSION_RE.fullmatch(str(app.get('latest'))) else ''
        rows.append(AppRow(slug, str(record.get('name') or slug), record['version'], active or '',
                           'builtin' if app.get('use') == 'builtin' else 'live', latest or '',
                           app.get('waiting') == 'needs-os', str(app.get('last_error') or '')))
    last = state.get('last_check')
    return Summary(rows, os.path.isdir(env.path(IMAGE_DIR)) and bool(rows),
                   float(last) if isinstance(last, (int, float)) else 0.0,
                   str(state.get('last_result') or ''), str(state.get('last_error') or ''))


def start(verb: str, slug: Optional[str] = None) -> Tuple[int, str]:
    """Run one of the root service's actions and wait for it: 'update', or 'use-builtin' /
    'use-live' with an app. Returns (exit code, error text)."""
    if verb == 'update':
        unit = 'spark-apps-now@update.service'
    elif verb in ('use-builtin', 'use-live', 'use-previous') and slug and SLUG_RE.fullmatch(slug):
        unit = f'spark-apps-now@{verb}:{slug}.service'
    else:
        return 2, 'not an action'
    code, out, err = run(['systemctl', 'start', unit], timeout=900)
    return code, (err or out).strip()


def installed_versions(summary: Summary) -> Dict[str, str]:
    return {r.slug: r.running for r in summary.rows}


def changed(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    return sorted(s for s, v in after.items() if before.get(s) != v)

