"""Battle.net, EA, Ubisoft Connect and Rockstar launchers, run by Spark Games through umu-run,
and Mojang's own Linux Minecraft Launcher.

"Add a launcher" downloads the vendor's installer, runs it in its own Wine prefix under
~/.local/share/spark-games/prefixes/<launcher>, and when the launcher's program shows up there
it gets a tile. The launcher's own window then installs and starts its games, as it does anywhere.

The installers can't be pinned to a SHA-256: each vendor replaces the file at the same address
whenever it updates, so any pin would fail within weeks. What Spark Games checks instead: HTTPS
only (also after every redirect), a host allowlist, a plausible size, a Windows program header
("MZ"), and it logs the SHA-256 of what it ran. The README says so.

The Minecraft Launcher is native ("native": True): its download is a .tar.gz holding one Linux
program, unpacked into ~/.local/share/spark-games/minecraft-launcher. No Wine, no installer window.
It gets no tile of its own: minecraft.py shows "Minecraft: Java Edition" and starts this program.
Its worlds and settings stay in ~/.minecraft, as with any copy of the launcher.

umu-protonfixes has no entry for these launchers, so they run with a placeholder GAMEID
(umu-<launcher>), which means no launcher-specific fixes.
"""

import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from . import ADDED_LAUNCHERS, APP_SLUG, VERSION, lutris, registry
from .core import Game, data_dir, log, private_dir
from .core import which as real_which

CHUNK = 256 * 1024
MIN_SIZE, MAX_SIZE = 500 * 1024, 400 * 1024 * 1024

LAUNCHERS: Dict[str, Dict[str, Any]] = {
    'battlenet': {
        'name': 'Battle.net',
        'url': 'https://www.battle.net/download/getInstallerForGame?os=win'
               '&gameProgram=BATTLENET_APP&version=Live',
        'hosts': ('battle.net', 'blizzard.com', 'akamaihd.net'),
        'exes': ('drive_c/Program Files (x86)/Battle.net/Battle.net Launcher.exe',
                 'drive_c/Program Files (x86)/Battle.net/Battle.net.exe'),
        'lutris': ('battlenet', 'battle-net')},
    'ea': {
        'name': 'EA app',
        'url': 'https://origin-a.akamaihd.net/EA-Desktop-Client-Download/installer-releases/'
               'EAappInstaller.exe',
        'hosts': ('ea.com', 'akamaihd.net'),
        'exes': ('drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop/EADesktop.exe',),
        'lutris': ('ea-app', 'ea-desktop', 'electronic-arts', 'origin')},
    'ubisoft': {
        'name': 'Ubisoft Connect',
        'url': 'https://static3.cdn.ubi.com/orbit/launcher_installer/UbisoftConnectInstaller.exe',
        'hosts': ('ubi.com', 'ubisoft.com', 'ubi.li'),
        'exes': ('drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/UbisoftConnect.exe',
                 'drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/upc.exe'),
        'lutris': ('ubisoft-connect', 'uplay', 'ubisoft')},
    'rockstar': {
        'name': 'Rockstar Games Launcher',
        'url': 'https://gamedownloads.rockstargames.com/public/installer/'
               'Rockstar-Games-Launcher.exe',
        'hosts': ('rockstargames.com',),
        'exes': ('drive_c/Program Files/Rockstar Games/Launcher/Launcher.exe',),
        'lutris': ('rockstar-games-launcher', 'rockstar-launcher', 'rockstar')},
    'minecraft': {
        'name': 'Minecraft Launcher',
        'url': 'https://launcher.mojang.com/download/Minecraft.tar.gz',
        'hosts': ('mojang.com', 'minecraft.net'),
        'native': True, 'header': b'\x1f\x8b', 'ext': '.tar.gz',
        'exes': ('minecraft-launcher/minecraft-launcher',),
        'lutris': ()},
}
assert tuple(LAUNCHERS) == ADDED_LAUNCHERS


class InstallerError(Exception):
    """kind: network, host, size, header, cancelled"""

    def __init__(self, kind: str, detail: str = ''):
        super().__init__(f'{kind}: {detail}' if detail else kind)
        self.kind, self.detail = kind, detail


def host_allowed(slug: str, url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or '').lower()
    return parts.scheme == 'https' and any(host == h or host.endswith('.' + h)
                                           for h in LAUNCHERS[slug]['hosts'])


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, slug: str):
        self.slug = slug

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(self.slug, newurl):
            raise InstallerError('host', urllib.parse.urlsplit(newurl).hostname or '')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def native(slug: str) -> bool:
    return bool(LAUNCHERS[slug].get('native'))


def prefix_dir(slug: str) -> str:
    """The launcher's Wine prefix, or for a native launcher the folder its program is in."""
    if native(slug):
        return os.path.join(data_dir(), f'{slug}-launcher')
    return os.path.join(data_dir(), 'prefixes', slug)


def download_installer(slug: str, dest_dir: str,
                      progress: Optional[Callable[[int, int], None]] = None,
                      cancel: Optional[Callable[[], bool]] = None,
                      url: Optional[str] = None) -> str:
    """Download the installer into dest_dir and check it. Returns its path."""
    url = url or LAUNCHERS[slug]['url']
    if not host_allowed(slug, url):
        raise InstallerError('host', urllib.parse.urlsplit(url).hostname or '')
    private_dir(dest_dir)
    target = os.path.join(dest_dir, f"{slug}-installer{LAUNCHERS[slug].get('ext', '.exe')}")
    part = target + '.part'
    opener = urllib.request.build_opener(_Redirects(slug))
    request = urllib.request.Request(url, headers={'User-Agent': f'{APP_SLUG}/{VERSION}'})
    digest, done, first = hashlib.sha256(), 0, b''
    try:
        with opener.open(request, timeout=30) as response, open(part, 'wb') as out:
            total = int(response.headers.get('Content-Length') or 0)
            if total and not MIN_SIZE <= total <= MAX_SIZE:
                raise InstallerError('size', str(total))
            while True:
                if cancel and cancel():
                    raise InstallerError('cancelled')
                block = response.read(CHUNK)
                if not block:
                    break
                if not first:
                    first = block[:2]
                done += len(block)
                if done > MAX_SIZE:
                    raise InstallerError('size', str(done))
                digest.update(block)
                out.write(block)
                if progress:
                    progress(done, total or done)
        if done < MIN_SIZE:
            raise InstallerError('size', str(done))
        if first != LAUNCHERS[slug].get('header', b'MZ'):
            raise InstallerError('header')
        os.replace(part, target)
    except InstallerError:
        _unlink(part)
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _unlink(part)
        raise InstallerError('network', str(getattr(exc, 'reason', exc))) from exc
    log.info("%s installer: %d bytes, sha256 %s", slug, done, digest.hexdigest())
    return target


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def umu_env(slug: str, prefix: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    env = {'WINEPREFIX': prefix, 'GAMEID': f'umu-{slug}'}
    options = options or {}
    if options.get('ge_proton'):
        env['PROTONPATH'] = 'GE-Proton'
    if options.get('mangohud'):
        env['MANGOHUD'] = '1'
    return env


def detect_exe(slug: str, prefix: str) -> str:
    for rel in LAUNCHERS[slug]['exes']:
        path = os.path.join(prefix, *rel.split('/'))
        if os.path.isfile(path):
            return path
    return ''


def unpack(archive: str, dest: str) -> None:
    """Unpack a native launcher's .tar.gz: regular files and folders only, nothing outside dest."""
    root = os.path.realpath(dest)
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        for m in members:
            target = os.path.realpath(os.path.join(root, m.name))
            if not (m.isfile() or m.isdir()) or not target.startswith(root + os.sep):
                raise InstallerError('header', m.name)
        os.makedirs(root, exist_ok=True)
        for m in members:
            target = os.path.join(root, m.name)
            if m.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            src = tar.extractfile(m)
            with src, open(target, 'wb') as out:
                shutil.copyfileobj(src, out)
            os.chmod(target, 0o755 if m.mode & 0o111 else 0o644)


def perform(helper: Any, spec: Dict[str, Any]) -> str:
    """The job helper's part: download the installer, run it through umu-run (or unpack a native
    launcher), find the launcher."""
    slug = spec['store']
    prefix = prefix_dir(slug)
    umu = real_which('umu-run')
    if not umu and not native(slug):
        return helper.finish('failed', 'err_no_umu')
    try:
        def got(done: int, total: int) -> None:
            helper.save(False, percent=100.0 * done / max(total, 1), message='fetching_installer')
        installer = download_installer(slug, os.path.join(data_dir(), 'launchers', slug), got,
                                       lambda: helper.cancelled)
    except InstallerError as exc:
        if exc.kind == 'cancelled':
            return helper.finish('cancelled')
        return helper.finish('failed', {'network': 'err_network', 'host': 'err_installer_host',
                                        'size': 'err_installer_bad',
                                        'header': 'err_installer_bad'}[exc.kind])
    if native(slug):
        try:
            shutil.rmtree(prefix, ignore_errors=True)
            unpack(installer, prefix)
        except (InstallerError, tarfile.TarError, OSError) as exc:
            log.warning("%s: could not unpack %s: %s", slug, installer, exc)
            shutil.rmtree(prefix, ignore_errors=True)
            return helper.finish('failed', 'err_installer_bad')
        return _found(helper, slug, prefix, installer)
    os.makedirs(prefix, exist_ok=True)
    helper.save(percent=0.0, message='installer_open')
    env = dict(os.environ)
    env.update(umu_env(slug, prefix))
    try:
        helper.proc = subprocess.Popen([umu, installer], env=env, cwd=os.path.dirname(installer),
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
        helper.proc.wait()
    except OSError as exc:
        return helper.finish('failed', 'err_job_start', str(exc))
    if helper.cancelled:
        return helper.finish('cancelled')
    return _found(helper, slug, prefix, installer)


def _found(helper: Any, slug: str, prefix: str, installer: str) -> str:
    exe = detect_exe(slug, prefix)
    if not exe:
        return helper.finish('failed', 'err_launcher_not_found')
    registry.add_launcher(slug, {'prefix': prefix, 'exe': exe, 'via': 'spark'})
    shutil.rmtree(os.path.dirname(installer), ignore_errors=True)
    return helper.finish('done')


# ─── Library ──────────────────────────────────────────────────

def known(slug: str) -> Optional[Dict[str, Any]]:
    """The launcher's record, from the registry, or found in its prefix (then recorded)."""
    rec = registry.load()['launchers'].get(slug)
    if isinstance(rec, dict) and rec.get('exe') and os.path.isfile(rec['exe']):
        return rec
    exe = detect_exe(slug, prefix_dir(slug))
    if exe:
        rec = {'prefix': prefix_dir(slug), 'exe': exe, 'via': 'spark'}
        registry.add_launcher(slug, rec)
        return rec
    return None


def scan(_base: str, watch: List[str]) -> List[Game]:
    watch.append(registry.path())
    games = []
    for slug, info in LAUNCHERS.items():
        rec = None if native(slug) else known(slug)
        if rec:
            games.append(Game(key=f'{slug}:launcher', title=info['name'], source=slug,
                              install_dir=rec['prefix'], store_id=slug,
                              launch={'spark': True, 'store': slug, 'launcher': True,
                                      'exe': rec['exe'], 'prefix': rec['prefix'],
                                      'via': rec.get('via', 'spark')}))
    return games


def hide_lutris(games: List[Game]) -> List[Game]:
    """Drop the Lutris tile of a launcher that has its own tile here (shown once, not twice)."""
    have = [s for s in LAUNCHERS if any(g.key == f'{s}:launcher' for g in games)]
    skip = {slug for s in have for slug in LAUNCHERS[s]['lutris']}
    return [g for g in games if not (g.source == 'lutris' and g.store_id in skip)]


def plan(game: Game, options: Dict[str, Any], which: Callable[[str], Optional[str]]):
    from .launch import LaunchError, Plan
    info = game.launch or {}
    exe = info.get('exe') or ''
    if not exe or not os.path.isfile(exe):
        raise LaunchError('missing_file', exe)
    umu = which('umu-run')
    if not umu:
        raise LaunchError('no_umu')
    env = umu_env(info.get('store') or game.source, info.get('prefix') or game.install_dir,
                  options)
    gamemode = ['gamemoderun'] if options.get('gamemode') and which('gamemoderun') else []
    return Plan(gamemode + [umu, exe], env=env, cwd=os.path.dirname(exe))


def remove(slug: str) -> None:
    """Forget a launcher. Its prefix is deleted only if Spark Games made it."""
    rec = registry.load()['launchers'].get(slug) or {}
    registry.remove_launcher(slug)
    prefix = rec.get('prefix') or ''
    if rec.get('via') == 'spark' and prefix == prefix_dir(slug):
        shutil.rmtree(prefix, ignore_errors=True)


# ─── Taking over a Lutris launcher ────────────────────────────

def read_game_yml(path: str) -> Dict[str, str]:
    """prefix and exe from a Lutris game config: the "game:" block, read as plain lines (the
    file is YAML, but only these two values matter, and PyYAML isn't in the image)."""
    out: Dict[str, str] = {}
    inside = False
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if re.match(r'^\S', line):
                    inside = line.strip() == 'game:'
                    continue
                m = re.match(r'^\s+(prefix|exe):\s*(.+?)\s*$', line)
                if inside and m:
                    out[m.group(1)] = m.group(2).strip('\'"')
    except OSError:
        pass
    return out


def lutris_launchers(base: str) -> List[Dict[str, str]]:
    """Launchers installed through Lutris that aren't ours yet:
    [{slug, name, prefix, exe, source: the Lutris slug}]."""
    mine = registry.load()['launchers']
    found = []
    for data, _cache, flatpak in lutris.roots(base):
        config = os.path.join(base, '.var', 'app', 'net.lutris.Lutris', 'config', 'lutris',
                              'games') if flatpak else os.path.join(base, '.config', 'lutris',
                                                                    'games')
        try:
            rows = _rows(os.path.join(data, 'pga.db'))
        except sqlite3.Error:
            continue
        for row in rows:
            slug = next((s for s, i in LAUNCHERS.items() if row.get('slug') in i['lutris']), '')
            if not slug or slug in mine or any(f['slug'] == slug for f in found):
                continue
            rel = row.get('configpath') or ''
            values = read_game_yml(os.path.join(config, rel + '.yml')) if rel else {}
            prefix, exe = values.get('prefix', ''), values.get('exe', '')
            if prefix and os.path.isdir(prefix) and exe and os.path.isfile(exe):
                found.append({'slug': slug, 'name': LAUNCHERS[slug]['name'], 'prefix': prefix,
                              'exe': exe, 'source': row.get('slug', '')})
    return found


def _rows(db: str) -> List[Dict[str, Any]]:
    uri = 'file:' + db.replace('?', '%3F').replace('#', '%23') + '?mode=ro'
    con = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        columns = {r[1] for r in con.execute('PRAGMA table_info(games)')}
        if not {'slug', 'configpath'} <= columns:
            return []
        rows = con.execute('SELECT slug, configpath FROM games WHERE installed = 1')
        return [{'slug': a, 'configpath': b} for a, b in rows]
    finally:
        con.close()


def use_lutris(item: Dict[str, str]) -> None:
    """Record a Lutris launcher as ours: same prefix, nothing copied or moved."""
    registry.add_launcher(item['slug'], {'prefix': item['prefix'], 'exe': item['exe'],
                                         'via': 'lutris'})
