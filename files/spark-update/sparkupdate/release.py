"""What is inside a SparkOS version, read from its files, never invented.

The image build (files/scripts/spark-update.sh) writes /usr/share/sparkos/release.json with
`spark-update --write-release`. For a version built before that file existed, the same reading
runs against that version's files on disk (/ostree/deploy/...), so most of it still shows.
"""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import IMAGE, RELEASE_PATH
from .text import EN, t

SCHEMA = 1


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def _json(path: str) -> Any:
    text = _read(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _clean(version: str) -> str:
    return version.strip().lstrip('vV')


def _spark_apps(root: str) -> List[Dict[str, str]]:
    """Every /usr/lib/spark-* app, from its spark-app.json, or its package's VERSION."""
    lib = os.path.join(root, 'usr', 'lib')
    try:
        names = sorted(n for n in os.listdir(lib) if n.startswith('spark-'))
    except OSError:
        return []
    apps = []
    for slug in names:
        folder = os.path.join(lib, slug)
        meta = _json(os.path.join(folder, 'spark-app.json'))
        name = version = ''
        if isinstance(meta, dict):
            name = str(meta.get('name') or '')
            version = str(meta.get('version') or '')
        if not version:
            try:
                packages = [p for p in os.listdir(folder) if p.startswith('spark')
                            and os.path.isfile(os.path.join(folder, p, '__init__.py'))]
            except OSError:
                packages = []
            for package in packages:
                match = re.search(r'^VERSION\s*=\s*["\']([^"\']+)',
                                  _read(os.path.join(folder, package, '__init__.py')) or '', re.M)
                if match:
                    version = match.group(1)
                    break
        if not version:
            continue
        if not name:
            name = ' '.join(w.capitalize() for w in slug.split('-'))
        apps.append({'id': slug, 'name': name, 'version': _clean(version)})
    return apps


def _rpm_versions(root: str, packages: Dict[str, str]) -> Dict[str, str]:
    """Versions of a few packages from the image's own RPM database (read only)."""
    dbpath = os.path.join(root, 'usr', 'lib', 'sysimage', 'rpm')
    if not os.path.isdir(dbpath):
        return {}
    out: Dict[str, str] = {}
    for key, package in packages.items():
        try:
            proc = subprocess.run(['rpm', '--dbpath', dbpath, '-q', '--qf', '%{VERSION}\n',
                                   package], capture_output=True, text=True, timeout=30,
                                  stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return out
        version = rpm_version(proc.stdout) if proc.returncode == 0 else ''
        if version:
            out[key] = version
    return out


def rpm_version(stdout: str) -> str:
    """One version from `rpm -q --qf '%{VERSION}\n'`: the 64- and 32-bit packages print one
    line each; Fedora's '1.19.0^really1.18.4' means 1.18.4."""
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        return ''
    return lines[0].split('^really', 1)[-1]


def _kernel(root: str) -> str:
    try:
        names = os.listdir(os.path.join(root, 'usr', 'lib', 'modules'))
    except OSError:
        return ''

    def key(name):
        return [int(p) if p.isdigit() else p for p in re.split(r'[.\-_]', name)]

    names = [n for n in names if re.match(r'\d', n)]
    return max(names, key=key).split('.fc')[0].split('-')[0] if names else ''


def _os_release(root: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in (_read(os.path.join(root, 'usr', 'lib', 'os-release')) or '').splitlines():
        if '=' in line and not line.startswith('#'):
            key, _, value = line.partition('=')
            out[key.strip()] = value.strip().strip('"\'')
    return out


def collect(root: str = '/', use_rpm: bool = True, built: Optional[float] = None,
            image: str = IMAGE) -> Dict[str, Any]:
    """Read what's in the SparkOS files under root."""
    osr = _os_release(root)
    info = _json(os.path.join(root, 'usr', 'share', 'ublue-os', 'image-info.json')) or {}
    components: List[Dict[str, str]] = []
    soot = _read(os.path.join(root, 'usr', 'lib', 'soot', 'SOOT_RELEASE'))
    if soot and soot.strip():
        components.append({'id': 'soot', 'name': 'Soot', 'version': _clean(soot)})
    for package_json in ('usr/lib/opt/freesuite/resources/app/package.json',):
        meta = _json(os.path.join(root, package_json))
        if isinstance(meta, dict) and meta.get('version'):
            components.append({'id': 'freesuite', 'name': 'FreeSuite',
                               'version': _clean(str(meta['version']))})
    components += _spark_apps(root)

    platform: List[Dict[str, str]] = []
    base = str(info.get('version') or '') if isinstance(info, dict) else ''
    if base:   # Bazzite's image-info.json: an image from before 2026-11-23
        platform.append({'id': 'base', 'name': 'Bazzite base', 'version': base})
    elif osr.get('ID') == 'fedora' and osr.get('VERSION_ID'):
        platform.append({'id': 'base', 'name': 'Fedora base', 'version': osr['VERSION_ID']})
    kernel = _kernel(root)
    if kernel:
        platform.append({'id': 'kernel', 'name': 'Linux kernel', 'version': kernel})
    if use_rpm:
        found = _rpm_versions(root, {'mesa': 'mesa-dri-drivers', 'plasma': 'plasma-workspace',
                                     'flatpak': 'flatpak'})
        for key, name in (('mesa', 'Mesa graphics drivers'), ('plasma', 'KDE Plasma'),
                          ('flatpak', 'Flatpak')):
            if key in found:
                platform.append({'id': key, 'name': name, 'version': found[key]})
    return {
        'schema': SCHEMA,
        'name': osr.get('NAME', 'SparkOS'),
        'image': image,
        'version': osr.get('OSTREE_VERSION') or osr.get('VERSION_ID') or '',
        'built': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(built)) if built else '',
        'components': components,
        'platform': platform,
    }


def load(root: str, use_rpm: bool = True) -> Optional[Dict[str, Any]]:
    """The release file of the version under root, or what can be read from its files.
    None when root isn't readable at all."""
    if not root or not os.path.isdir(root):
        return None
    data = _json(os.path.join(root, RELEASE_PATH.lstrip('/')))
    if isinstance(data, dict) and data.get('schema') == SCHEMA:
        data['from_file'] = True
        return data
    if not os.path.isdir(os.path.join(root, 'usr')):
        return None
    data = collect(root, use_rpm=use_rpm)
    data['from_file'] = False
    return data


@dataclass
class Change:
    name: str
    old: str        # '' when added
    new: str        # '' when removed
    group: str      # 'apps' or 'platform'

    @property
    def kind(self) -> str:
        if not self.old:
            return 'added'
        if not self.new:
            return 'removed'
        return 'changed' if self.old != self.new else 'same'


def diff(old: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]]) -> List[Change]:
    """Every component and platform part in either version, apps first."""
    changes: List[Change] = []
    for group, key in (('apps', 'components'), ('platform', 'platform')):
        before = {c['id']: c for c in (old or {}).get(key) or [] if isinstance(c, dict)}
        after = {c['id']: c for c in (new or {}).get(key) or [] if isinstance(c, dict)}
        for cid in list(after) + [c for c in before if c not in after]:
            a, b = before.get(cid), after.get(cid)
            name = (b or a).get('name', cid)
            if group == 'platform' and f'platform.{cid}' in EN:
                name = t(f'platform.{cid}')          # release.json has the English name
            changes.append(Change(name=name,
                                  old=str((a or {}).get('version', '')),
                                  new=str((b or {}).get('version', '')), group=group))
    return changes
