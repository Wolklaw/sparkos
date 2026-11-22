"""What is installed: the booted SparkOS version, the one staged for the next restart, and the
previous one (the rollback). Read from `rpm-ostree status --json` (works as any user) or
`bootc status --json` (root only), both turned into the same Host."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import IMAGES
from .core import Env, parse_time, run


@dataclass
class Deployment:
    version: str = ""
    timestamp: Optional[float] = None
    image: str = ""                 # 'ghcr.io/wolklaw/sparkos:latest'
    transport: str = ""             # 'ostree-image-signed:docker://' etc., as written
    digest: str = ""
    checksum: str = ""
    serial: int = 0
    osname: str = "default"
    booted: bool = False
    staged: bool = False
    pinned: bool = False
    layered: List[str] = field(default_factory=list)   # rpm-ostree install'd packages

    @property
    def key(self) -> str:
        """Identifies this deployment for 'have I told the user about it yet'."""
        return self.digest or self.checksum or self.version

    def root(self, env: Env) -> str:
        """The deployment's files on disk; '/' for the booted one."""
        if self.booted:
            return env.path('/')
        if not self.checksum:
            return ''
        return env.path(f'/ostree/deploy/{self.osname}/deploy/{self.checksum}.{self.serial}')

    def same_image_as(self, other: Optional['Deployment']) -> bool:
        if other is None:
            return False
        if self.digest and other.digest:
            return self.digest == other.digest
        return bool(self.checksum) and self.checksum == other.checksum


@dataclass
class Host:
    booted: Optional[Deployment] = None
    staged: Optional[Deployment] = None       # downloaded, starts at the next restart
    rollback: Optional[Deployment] = None     # the previous version
    next_boot: Optional[Deployment] = None    # what the next restart starts, if not booted
    rollback_queued: bool = False             # the next restart goes back to the previous one
    others: List[Deployment] = field(default_factory=list)   # pinned extras
    source: str = ""                          # 'rpm-ostree', 'bootc', or why none
    error: str = ""

    @property
    def update_ready(self) -> bool:
        return self.staged is not None and not self.staged.same_image_as(self.booted)

    @property
    def restart_changes(self) -> bool:
        return self.update_ready or self.rollback_queued


def split_ref(ref: str):
    """'ostree-image-signed:docker://ghcr.io/wolklaw/sparkos:latest' ->
    ('ostree-image-signed:docker://', 'ghcr.io/wolklaw/sparkos:latest')"""
    if not ref:
        return '', ''
    if '://' in ref:
        head, _, tail = ref.partition('://')
        return head + '://', tail
    if ref.startswith('ostree-unverified-registry:'):
        return 'ostree-unverified-registry:', ref.split(':', 1)[1]
    return '', ref


def image_name(image: str) -> str:
    """'ghcr.io/wolklaw/sparkos:latest' -> 'ghcr.io/wolklaw/sparkos'"""
    name = image.split('@', 1)[0]
    last = name.rsplit('/', 1)[-1]
    if ':' in last:
        name = name[:len(name) - len(last)] + last.split(':', 1)[0]
    return name


# ─── rpm-ostree ────────────────────────────────────────────────

def _from_rpm_ostree(d: Dict[str, Any]) -> Deployment:
    transport, image = split_ref(d.get('container-image-reference') or '')
    layered = list(d.get('requested-packages') or []) + \
        list(d.get('requested-local-packages') or [])
    return Deployment(
        version=str(d.get('version') or ''),
        timestamp=parse_time(d.get('timestamp')),
        image=image, transport=transport,
        digest=str(d.get('container-image-reference-digest') or ''),
        checksum=str(d.get('checksum') or ''),
        serial=int(d.get('serial') or 0),
        osname=str(d.get('osname') or 'default'),
        booted=bool(d.get('booted')), staged=bool(d.get('staged')),
        pinned=bool(d.get('pinned')), layered=[str(p) for p in layered])


def parse_rpm_ostree(data: Any) -> Host:
    host = Host(source='rpm-ostree')
    deps = [_from_rpm_ostree(d) for d in (data or {}).get('deployments') or []
            if isinstance(d, dict)]
    if not deps:
        host.error = "no deployments"
        return host
    booted_i = next((i for i, d in enumerate(deps) if d.booted), None)
    if booted_i is None:
        host.error = "no booted deployment"
        return host
    host.booted = deps[booted_i]
    host.staged = next((d for d in deps if d.staged), None)
    # deployments[0] is the default for the next boot; staged ones come first
    unstaged = [d for d in deps if not d.staged]
    if unstaged and not unstaged[0].booted:
        host.next_boot = unstaged[0]
        host.rollback_queued = True
        host.rollback = unstaged[0]
    else:
        after = [d for d in unstaged[unstaged.index(host.booted) + 1:]]
        host.rollback = after[0] if after else None
    if host.staged is not None and not host.rollback_queued:
        host.next_boot = host.staged
    host.others = [d for d in deps if d is not host.booted and d is not host.staged
                   and d is not host.rollback]
    return host


# ─── bootc ─────────────────────────────────────────────────────

def _from_bootc(entry: Optional[Dict[str, Any]], **flags) -> Optional[Deployment]:
    if not isinstance(entry, dict):
        return None
    status = entry.get('image') or {}
    ref = (status.get('image') or {}) if isinstance(status, dict) else {}
    ostree = entry.get('ostree') or {}
    transport = str(ref.get('transport') or '')
    sig = ref.get('signature')
    if transport == 'registry':
        transport = ('ostree-image-signed:docker://' if sig else 'docker://')
    return Deployment(
        version=str(status.get('version') or ''),
        timestamp=parse_time(status.get('timestamp')),
        image=str(ref.get('image') or ''), transport=transport,
        digest=str(status.get('imageDigest') or ''),
        checksum=str(ostree.get('checksum') or ''),
        serial=int(ostree.get('deploySerial') or 0),
        osname=str(ostree.get('stateroot') or 'default'),
        pinned=bool(entry.get('pinned')), **flags)


def parse_bootc(data: Any) -> Host:
    host = Host(source='bootc')
    status = (data or {}).get('status') or {}
    host.booted = _from_bootc(status.get('booted'), booted=True)
    if host.booted is None:
        host.error = "not booted from an image"
        return host
    host.staged = _from_bootc(status.get('staged'), staged=True)
    host.rollback = _from_bootc(status.get('rollback'))
    host.rollback_queued = bool(status.get('rollbackQueued'))
    if host.rollback_queued:
        host.next_boot = host.rollback
    elif host.staged is not None:
        host.next_boot = host.staged
    for extra in status.get('otherDeployments') or []:
        dep = _from_bootc(extra)
        if dep:
            host.others.append(dep)
    return host


# ─── Reading the live system ───────────────────────────────────

def read_host(env: Env, prefer_bootc: bool = False) -> Host:
    """The status of this machine. rpm-ostree works for any user; bootc needs root.
    With a fake root, status/rpm-ostree.json or status/bootc.json is read instead."""
    if env.fake:
        for name, parser in (('rpm-ostree', parse_rpm_ostree), ('bootc', parse_bootc)):
            data = env.read_json(f'/status/{name}.json')
            if data is not None:
                return parser(data)
        return Host(source='none', error="no status file under the test root")
    order = ['bootc', 'rpm-ostree'] if prefer_bootc else ['rpm-ostree', 'bootc']
    errors = []
    for tool in order:
        if tool == 'bootc' and hasattr(os, 'geteuid') and os.geteuid() != 0:
            continue
        cmd = [tool, 'status', '--json'] if tool == 'rpm-ostree' else \
            ['bootc', 'status', '--json']
        code, out, err = run(cmd, timeout=60, quiet=True)
        if code == 0:
            try:
                data = json.loads(out)
            except ValueError:
                errors.append(f"{tool}: unreadable output")
                continue
            host = parse_rpm_ostree(data) if tool == 'rpm-ostree' else parse_bootc(data)
            if host.booted is not None:
                return host
            errors.append(f"{tool}: {host.error}")
        else:
            first = (err or out).strip().splitlines()
            errors.append(f"{tool}: {first[0] if first else f'exit {code}'}")
    return Host(source='none', error='; '.join(errors) or "no rpm-ostree or bootc")


def find_image_name(env: Env, host: Optional[Host] = None) -> Tuple[str, str]:
    """The image this PC follows, and where that was read. The booted deployment knows it;
    without one (a container, a build) the release file or the signing policy does."""
    if host and host.booted and host.booted.image:
        return image_name(host.booted.image), host.source + " status"
    release = env.read_json('/usr/share/sparkos/release.json')
    if isinstance(release, dict) and release.get('image'):
        return str(release['image']), "/usr/share/sparkos/release.json"
    for path in ('/etc/containers/policy.json', '/usr/etc/containers/policy.json'):
        policy = env.read_json(path)
        if not isinstance(policy, dict):
            continue
        docker = ((policy.get('transports') or {}).get('docker') or {})
        for name in docker:
            if name.rstrip('/').endswith(('/sparkos', '/sparkos-fedora')) or name in IMAGES:
                return name, path + " (signing policy)"
    return "", ""
