"""Epic, GOG and Amazon inside Spark Games: sign-in, the games you own, install records,
updates, taking over what Heroic installed, and the command that starts a game.

The store clients (clients.py) do the store work. This file only runs them, reads what they
print, and keeps three small files:

  ~/.config/spark-games/accounts/   tokens (0600; nothing here is ever logged)
  ~/.cache/spark-games/owned-<store>.json   what you own, refreshed in the background
  ~/.local/share/spark-games/stores.json    what is installed (registry.py)

What a client prints is parsed defensively: a missing field gives a plain message, never a
stack trace. The shapes below come from reading each client's source; no real account has been
used with them yet (README, Known gaps).
"""

import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from . import APP_SLUG, STORES, VERSION, heroic, registry
from .core import (Game, accounts_dir, cache_dir, data_dir, home, load_settings, log, now,
                   read_json, write_json)
from . import clients
from .launch import LaunchError, Plan

OWNED_MAX_AGE = 24 * 3600
UMU_STORE = {'epic': 'egs', 'gog': 'gog', 'amazon': 'amazon'}
FOLDER = {'epic': 'epic', 'gog': 'gog', 'amazon': 'amazon'}
EPIC_LOGIN = 'https://legendary.gl/epiclogin'
GOG_LOGIN = ('https://auth.gog.com/auth?client_id=46899977096215655&redirect_uri='
             'https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient'
             '&response_type=code&layout=client2')
GOG_PRODUCTS = 'https://embed.gog.com/account/getFilteredProducts?mediaType=1&page={page}'
GOG_USER = 'https://embed.gog.com/userData.json'
PROGRESS = re.compile(r'=\s*Progress:\s*([\d.]+)\s*%?.*?ETA:\s*(\d+):(\d+):(\d+)', re.I)
SPEED = re.compile(r'Download\s*-\s*([\d.]+)\s*([KMG]i?B)/s', re.I)
SECRET = re.compile(r'(AUTH_PASSWORD|access_token|refresh_token|authorizationCode|code)'
                    r'[=:"\s]+[^\s",&]+', re.I)


def scrub(text: str) -> str:
    """Hide anything token-like in a client's message before it is shown or logged."""
    return SECRET.sub(r'\1=…', text or '')


def safe_name(text: str) -> str:
    """A folder name: letters, digits, spaces, dashes and dots only."""
    clean = re.sub(r'[^\w .-]+', '', text, flags=re.UNICODE).strip(' .')
    return clean or 'game'


# ─── Accounts ─────────────────────────────────────────────────

def token_files(store: str) -> List[str]:
    base = accounts_dir()
    return {'epic': [os.path.join(base, 'epic', 'user.json')],
            'gog': [os.path.join(base, 'gog.json')],
            'amazon': [os.path.join(base, 'amazon', 'nile', 'current_user.json')]}[store]


def signed_in(store: str) -> bool:
    """Looks at the token files only (no client call), so the window opens fast."""
    path = token_files(store)[0]
    if not os.path.isfile(path):
        return False
    if store == 'amazon':          # nile writes {name, user_id} here; the token is in an .enc file
        data = read_json(path, {})
        return bool(isinstance(data, dict) and data.get('user_id'))
    return os.path.getsize(path) > 2


def signed_in_any() -> bool:
    return any(signed_in(s) for s in STORES)


def account_name(store: str) -> str:
    """The name to show next to "signed in" (empty when the client doesn't store one)."""
    base = accounts_dir()
    if store == 'epic':
        data = read_json(os.path.join(base, 'epic', 'user.json'), {})
        return str(data.get('displayName') or '') if isinstance(data, dict) else ''
    if store == 'amazon':
        data = read_json(token_files('amazon')[0], {})
        return str(data.get('name') or '') if isinstance(data, dict) else ''
    cached = read_json(owned_path('gog'), {})
    return str(cached.get('name') or '') if isinstance(cached, dict) else ''


def extract_code(store: str, text: str) -> str:
    """The sign-in code from whatever was pasted: the page's text, the address, or the code."""
    text = (text or '').strip()
    if not text:
        return ''
    if store == 'epic':
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get('authorizationCode'):
                return str(data['authorizationCode'])
        except ValueError:
            pass
        match = re.search(r'authorizationCode["\s:=]+([0-9a-zA-Z]{20,})', text)
        if match:
            return match.group(1)
        bare = text.strip('"\' ')
        return bare if re.fullmatch(r'[0-9a-zA-Z]{20,64}', bare) else ''
    key = 'code' if store == 'gog' else 'openid.oa2.authorization_code'
    match = re.search(r'[?&]' + re.escape(key) + r'=([^&\s#]+)', text)
    if match:
        return urllib.parse.unquote(match.group(1))
    bare = text.strip('"\' ')
    return bare if re.fullmatch(r'[0-9A-Za-z_\-.~]{16,}', bare) else ''


def begin_signin(store: str) -> Dict[str, Any]:
    """{'url': the page to open, 'state': what finish_signin needs}. Raises ClientError."""
    clients.ensure(clients.CLIENT_OF[store])
    if store == 'epic':
        return {'url': EPIC_LOGIN, 'state': {}}
    if store == 'gog':
        return {'url': GOG_LOGIN, 'state': {}}
    code, out, _err = clients.run('amazon', ['auth', '--login', '--non-interactive'], timeout=60)
    data = _first_json(out)
    if code != 0 or not isinstance(data, dict) or not data.get('url') \
            or not data.get('code_verifier'):
        raise clients.ClientError('signin', 'amazon')
    return {'url': str(data['url']),
            'state': {'client_id': str(data.get('client_id', '')),
                      'code_verifier': str(data['code_verifier']),
                      'serial': str(data.get('serial', ''))}}


def finish_signin(store: str, pasted: str, state: Optional[Dict[str, str]] = None) -> str:
    """Finish a sign-in. Returns '' on success, else a strings.py key saying what went wrong."""
    code = extract_code(store, pasted)
    if not code:
        return 'signin_bad_code'
    state = state or {}
    if store == 'epic':
        args = ['auth', '--code', code]
    elif store == 'gog':
        args = ['auth', '--code', code]
    else:
        args = ['register', '--code', code, '--client-id', state.get('client_id', ''),
                '--code-verifier', state.get('code_verifier', ''),
                '--serial', state.get('serial', '')]
    rc, _out, _err = clients.run(store, args, timeout=90)
    if rc == 124:
        return 'signin_timeout'
    if rc != 0 or not signed_in(store):
        return 'signin_failed'
    log.info("%s: signed in", store)
    return ''


def sign_out(store: str) -> None:
    """Delete the tokens. Games you installed stay installed."""
    if store == 'epic' and clients.find('legendary'):
        clients.run('epic', ['auth', '--delete'], timeout=30)
    elif store == 'amazon' and clients.find('nile') and signed_in('amazon'):
        clients.run('amazon', ['auth', '--logout'], timeout=60)
    for path in token_files(store):
        try:
            os.unlink(path)
        except OSError:
            pass
    try:
        os.unlink(owned_path(store))
    except OSError:
        pass
    log.info("%s: signed out", store)


def _first_json(text: str) -> Any:
    """The first JSON value in a client's output (clients print log lines around it)."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text or ''):
        if ch in '[{':
            try:
                return decoder.raw_decode(text[i:])[0]
            except ValueError:
                continue
    return None


# ─── Owned games ──────────────────────────────────────────────

def owned_path(store: str) -> str:
    return os.path.join(cache_dir(), f'owned-{store}.json')


def covers_dir() -> str:
    path = os.path.join(cache_dir(), 'store-covers')
    os.makedirs(path, exist_ok=True)
    return path


def cover_file(url: str) -> str:
    return os.path.join(covers_dir(), hashlib.sha256(url.encode('utf-8')).hexdigest() + '.img') \
        if url else ''


def load_owned(store: str) -> Dict[str, Any]:
    data = read_json(owned_path(store), {})
    if not isinstance(data, dict) or not isinstance(data.get('games'), list):
        return {'fetched': 0, 'games': [], 'updates': [], 'name': ''}
    data.setdefault('updates', [])
    return data


def owned_stale(store: str) -> bool:
    return now() - int(load_owned(store).get('fetched') or 0) > OWNED_MAX_AGE


def _epic_owned() -> List[Dict[str, str]]:
    rc, out, _e = clients.run('epic', ['list', '--json'], timeout=300)
    data = _first_json(out)
    if rc != 0 or not isinstance(data, list):
        raise clients.ClientError('list', 'epic')
    games = []
    for item in data:
        if not isinstance(item, dict) or not item.get('app_name'):
            continue
        assets = item.get('asset_infos')
        if isinstance(assets, dict) and assets and 'Windows' not in assets:
            continue
        art = ''
        meta = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
        images = [i for i in meta.get('keyImages') or [] if isinstance(i, dict)]
        for wanted in ('DieselGameBoxTall', 'DieselGameBox', 'Thumbnail'):
            art = next((i.get('url', '') for i in images if i.get('type') == wanted), '')
            if art:
                break
        build = ''
        if isinstance(assets, dict) and isinstance(assets.get('Windows'), dict):
            build = str(assets['Windows'].get('build_version') or '')
        games.append({'app': str(item['app_name']), 'title': str(item.get('app_title') or ''),
                      'art': art, 'version': build})
    return games


def _gog_token() -> str:
    """A fresh access token: gogdl refreshes an expired one and prints the credentials."""
    rc, out, _e = clients.run('gog', ['auth'], timeout=60)
    data = _first_json(out)
    if rc != 0 or not isinstance(data, dict) or not data.get('access_token'):
        raise clients.ClientError('signin', 'gog')
    return str(data['access_token'])


def _get_json(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}', 'User-Agent': f'{APP_SLUG}/{VERSION}'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode('utf-8', 'replace'))


def _gog_owned() -> Tuple[List[Dict[str, str]], str]:
    token = _gog_token()
    games, page, pages = [], 1, 1
    try:
        while page <= pages and page <= 50:
            data = _get_json(GOG_PRODUCTS.format(page=page), token)
            pages = int(data.get('totalPages') or 1)
            for item in data.get('products') or []:
                if not isinstance(item, dict) or not item.get('id'):
                    continue
                image = str(item.get('image') or '')
                games.append({'app': str(item['id']), 'title': str(item.get('title') or ''),
                              'art': ('https:' + image + '.jpg') if image.startswith('//')
                              else '', 'version': '',
                              'platforms': sorted(k.lower() for k, v in
                                                  (item.get('worksOn') or {}).items() if v)})
            page += 1
        name = ''
        try:
            name = str(_get_json(GOG_USER, token).get('username') or '')
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            pass
    except (urllib.error.URLError, OSError, ValueError, AttributeError) as exc:
        raise clients.ClientError('network', str(getattr(exc, 'reason', exc))) from exc
    return games, name


def _amazon_owned() -> Tuple[List[Dict[str, str]], List[str]]:
    clients.run('amazon', ['library', 'sync'], timeout=300)
    rc, out, _e = clients.run('amazon', ['library', 'list', '--json'], timeout=120)
    data = _first_json(out)
    if rc != 0 or not isinstance(data, list):
        raise clients.ClientError('list', 'amazon')
    games = []
    for item in data:
        product = item.get('product') if isinstance(item, dict) else None
        if not isinstance(product, dict) or not product.get('id'):
            continue
        detail = product.get('productDetail') if isinstance(product.get('productDetail'),
                                                             dict) else {}
        details = detail.get('details') if isinstance(detail.get('details'), dict) else {}
        games.append({'app': str(product['id']), 'title': str(product.get('title') or ''),
                      'art': str(detail.get('iconUrl') or details.get('logoUrl') or ''),
                      'version': ''})
    updates: List[str] = []
    rc, out, _e = clients.run('amazon', ['list-updates', '--json'], timeout=120)
    found = _first_json(out)
    if rc == 0 and isinstance(found, list):
        updates = [str(i) for i in found]
    return games, updates


def refresh_owned(store: str, force: bool = False) -> Dict[str, Any]:
    """The owned list, fetched at most once a day (or when forced), then cached. Runs in a
    background thread; raises clients.ClientError when the client or the store can't answer."""
    cached = load_owned(store)
    if not force and cached['games'] and not owned_stale(store):
        return cached
    if not signed_in(store):
        raise clients.ClientError('signin', store)
    clients.ensure(clients.CLIENT_OF[store])
    name, updates = account_name(store), []
    if store == 'epic':
        games = _epic_owned()
    elif store == 'gog':
        games, name = _gog_owned()
    else:
        games, updates = _amazon_owned()
    installed = registry.load()['games']
    if store == 'epic':
        for game in games:
            mine = installed.get(f'epic:{game["app"]}')
            if mine and mine.get('via') in ('spark', 'heroic') and game['version'] \
                    and mine.get('version') and mine['version'] != game['version']:
                updates.append(game['app'])
    data = {'fetched': now(), 'name': name, 'games': games, 'updates': updates}
    write_json(owned_path(store), data)
    log.info("%s: %d owned games", store, len(games))
    return data


def fetch_covers(store: str, limit: int = 400) -> int:
    """Download missing cover images (from the store's own CDN). Returns how many were new."""
    count = 0
    for game in load_owned(store)['games'][:limit]:
        url = game.get('art') or ''
        path = cover_file(url)
        if not url.startswith('https://') or not path or os.path.isfile(path):
            continue
        try:
            request = urllib.request.Request(url, headers={'User-Agent': f'{APP_SLUG}/{VERSION}'})
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read(4 * 1024 * 1024)
            with open(path + '.part', 'wb') as f:
                f.write(body)
            os.replace(path + '.part', path)
            count += 1
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return count


def update_available(game: Game) -> bool:
    info = game.launch or {}
    return bool(info.get('spark')) and info.get('app') in load_owned(game.source)['updates']


# ─── Library scanners ─────────────────────────────────────────

def _cover_for(store: str, app: str, owned: Optional[Dict[str, Any]] = None) -> str:
    owned = owned or load_owned(store)
    for item in owned['games']:
        if item.get('app') == app:
            path = cover_file(item.get('art') or '')
            return path if path and os.path.isfile(path) else ''
    return ''


def scan_installed(_base: str, watch: List[str]) -> List[Game]:
    """Games Spark Games installed or took over."""
    watch.append(registry.path())
    games = []
    cache = {s: load_owned(s) for s in STORES}
    for key, rec in registry.load()['games'].items():
        store = rec.get('store')
        if store not in STORES or not rec.get('app'):
            continue
        games.append(Game(
            key=key, title=rec.get('title') or rec['app'], source=store,
            install_dir=rec.get('path') or '', cover=_cover_for(store, rec['app'], cache[store]),
            store_id=str(rec['app']),
            launch={'spark': True, 'store': store, 'app': rec['app'],
                    'platform': rec.get('platform') or 'Windows', 'via': rec.get('via', 'spark')}))
    return games


def scan_owned(_base: str, watch: List[str]) -> List[Game]:
    """Games you own and haven't installed. The library keeps the first game for a key, and
    this scanner runs last, so an installed one (ours, Heroic's) always wins."""
    games = []
    for store in STORES:
        watch.append(owned_path(store))
        owned = load_owned(store)
        for item in owned['games']:
            games.append(Game(
                key=f'{store}:{item["app"]}', title=item.get('title') or item['app'], source=store,
                cover=cover_file(item.get('art') or '') if os.path.isfile(
                    cover_file(item.get('art') or '') or '/nonexistent') else '',
                store_id=item['app'], installed=False,
                launch={'spark': True, 'store': store, 'app': item['app']}))
    return games


# ─── Taking over Heroic's installs ────────────────────────────

def heroic_games(base: str) -> List[Dict[str, str]]:
    """Installed Epic, GOG and Amazon games in Heroic's files (read only), with their store."""
    found = []
    for root, _flatpak in heroic.roots(base):
        for store, (_runner, parts, _caches) in heroic.STORES.items():
            data = read_json(os.path.join(root, *parts))
            if data is None:
                continue
            try:
                items = heroic._installed(store, data)
            except heroic.FormatError:
                continue
            for item in items:
                if item['path'] and os.path.isdir(item['path']):
                    found.append(dict(item, store=store))
    return found


def heroic_unclaimed(base: str, store: Optional[str] = None) -> List[Dict[str, str]]:
    mine = registry.load()['games']
    return [g for g in heroic_games(base)
            if f'{g["store"]}:{g["app"]}' not in mine and (store is None or g['store'] == store)]


def takeable(base: str) -> List[Dict[str, str]]:
    """Heroic games Spark Games can take over now: any GOG one (a record is enough), and the
    Epic and Amazon ones once you are signed in to that store."""
    return [g for g in heroic_unclaimed(base) if g['store'] == 'gog' or signed_in(g['store'])]


def take_over(base: str, store: str) -> Tuple[int, int]:
    """Record Heroic's installed games of one store as ours. Nothing is downloaded, and Heroic's
    files are only read. Epic and Amazon games are also imported into the client's own record
    (legendary import, nile import), which reads the folder. Returns (taken, failed)."""
    taken = failed = 0
    games = heroic_unclaimed(base, store)
    if games and store != 'gog':
        try:
            clients.ensure(clients.CLIENT_OF[store])
        except clients.ClientError as exc:
            log.warning("take over %s: client not available (%s)", store, exc.kind)
            return 0, len(games)
    for game in games:
        if store == 'epic':
            rc, _o, _e = clients.run('epic', ['import', '--disable-check', game['app'],
                                              game['path']], timeout=180)
        elif store == 'amazon':
            rc, _o, _e = clients.run('amazon', ['import', '--path', game['path'], game['app']],
                                     timeout=180)
        else:
            rc = 0
        if rc != 0:
            failed += 1
            log.warning("take over %s:%s failed (exit %s)", store, game['app'], rc)
            continue
        registry.add_game(f'{store}:{game["app"]}', {
            'store': store, 'app': game['app'], 'title': game['title'] or game['app'],
            'path': game['path'], 'platform': game['platform'] or 'Windows',
            'version': game.get('version', ''), 'via': 'heroic', 'root': ''})
        taken += 1
    return taken, failed


# ─── Installing ───────────────────────────────────────────────

def games_root(store: str) -> str:
    """Where new games go: the folder set in Spark Games' settings, else ~/Games/<store>."""
    chosen = load_settings().get('games_dir')
    base = chosen if isinstance(chosen, str) and chosen else os.path.join(home(), 'Games')
    return os.path.join(base, FOLDER[store])


def nearest_existing(path: str) -> str:
    while path and not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path or '/'


def free_space(path: str) -> int:
    try:
        return shutil.disk_usage(nearest_existing(path)).free
    except OSError:
        return 0


def _find_number(data: Any, names: Tuple[str, ...]) -> int:
    if isinstance(data, dict):
        for name in names:
            value = data.get(name)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
        for value in data.values():
            found = _find_number(value, names)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_number(value, names)
            if found:
                return found
    return 0


def install_info(store: str, app: str) -> Tuple[int, int]:
    """(download bytes, disk bytes) from the client, or (0, 0) when it can't say."""
    if store == 'epic':
        args = ['info', app, '--json']
    elif store == 'gog':
        args = ['info', app, '--platform', 'windows']
    else:
        args = ['install', app, '--info', '--json']
    rc, out, _e = clients.run(store, args, timeout=120)
    data = _first_json(out)
    if rc != 0 or data is None:
        return 0, 0
    return (_find_number(data, ('download_size',)),
            _find_number(data, ('disk_size', 'install_size', 'size')))


def target_dir(store: str, title: str, root: str) -> str:
    return os.path.join(root, safe_name(title))


def job_args(kind: str, store: str, app: str, target: str) -> List[str]:
    """The client's arguments for an install, update or verify (repair)."""
    if store == 'epic':
        if kind == 'install':
            return ['install', app, '--base-path', os.path.dirname(target), '-y',
                    '--platform', 'Windows']
        if kind == 'update':
            return ['install', app, '--update-only', '-y']
        return ['install', app, '--repair', '-y']
    if store == 'gog':
        verb = {'install': 'download', 'update': 'update', 'verify': 'repair'}[kind]
        return [verb, app, '--path', target, '--platform', 'windows', '--skip-dlcs']
    verb = {'install': 'install', 'update': 'update', 'verify': 'verify'}[kind]
    return [verb, app, '--path', target]


def finish_install(store: str, app: str, title: str, target: str, root: str,
                   previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record a finished install, asking the client where and which version when it can say."""
    rec: Dict[str, Any] = dict(previous or {})
    rec.update({'store': store, 'app': app, 'title': title or rec.get('title') or app,
                'path': rec.get('path') or target, 'platform': rec.get('platform') or 'Windows',
                'root': root or rec.get('root', ''), 'via': rec.get('via') or 'spark'})
    if store == 'epic':
        rc, out, _e = clients.run('epic', ['list-installed', '--json'], timeout=60)
        data = _first_json(out)
        for item in data if rc == 0 and isinstance(data, list) else []:
            if isinstance(item, dict) and item.get('app_name') == app:
                rec['path'] = item.get('install_path') or rec['path']
                rec['version'] = str(item.get('version') or '')
                rec['platform'] = item.get('platform') or rec['platform']
    elif store == 'amazon':
        data = read_json(os.path.join(accounts_dir(), 'amazon', 'nile', 'installed.json'), [])
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict) and item.get('id') == app:
                rec['path'] = item.get('path') or rec['path']
                rec['version'] = str(item.get('version') or '')
    registry.add_game(f'{store}:{app}', rec)
    return rec


def safe_to_delete(path: str, roots: List[str]) -> bool:
    """Only folders inside a games folder Spark Games installed into, never the folder itself."""
    real = os.path.realpath(path)
    for root in roots:
        top = os.path.realpath(root)
        if top and real != top and real.startswith(top + os.sep):
            return True
    return False


def uninstall(key: str) -> str:
    """Uninstall (Spark's own installs) or forget (taken over from Heroic: its files stay).
    Returns '' on success or a strings.py key."""
    rec = registry.load()['games'].get(key)
    if not rec:
        return ''
    store, app, path = rec['store'], rec['app'], rec.get('path') or ''
    if rec.get('via') == 'heroic':
        if store == 'epic':
            clients.run('epic', ['uninstall', '--keep-files', app, '-y'], timeout=60)
        registry.remove_game(key)
        return ''
    if store in ('epic', 'amazon'):
        args = ['uninstall', app, '-y'] if store == 'epic' else ['uninstall', app]
        rc, _o, _e = clients.run(store, args, timeout=600)
        if rc != 0:
            return 'err_uninstall'
    elif path and os.path.isdir(path):
        roots = [rec.get('root') or '', games_root(store)]
        if not safe_to_delete(path, [r for r in roots if r]):
            log.warning("not deleting %s: outside the games folders", path)
            return 'err_uninstall_outside'
        shutil.rmtree(path, ignore_errors=True)
    registry.remove_game(key)
    return ''


def folder_size(path: str) -> int:
    total = 0
    for folder, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


# ─── Starting a game ──────────────────────────────────────────

def prefix_for(store: str, app: str) -> str:
    return os.path.join(data_dir(), 'prefixes', f'{store}-{safe_name(app)}')


def umu_env(store: str, app: str, options: Dict[str, Any]) -> Dict[str, str]:
    env = {'WINEPREFIX': prefix_for(store, app), 'GAMEID': f'umu-{app}',
           'STORE': UMU_STORE[store]}
    if options.get('ge_proton'):
        env['PROTONPATH'] = 'GE-Proton'
    if options.get('mangohud'):
        env['MANGOHUD'] = '1'
    return env


def plan(game: Game, options: Dict[str, Any], which) -> Plan:
    """The command that starts a store game. For Epic this asks legendary for the launch
    command (and a fresh launch token), so it can take a few seconds: call it in a thread."""
    info = game.launch or {}
    if info.get('launcher'):
        from . import launchers
        return launchers.plan(game, options, which)
    store, app = info.get('store') or game.source, str(info.get('app') or game.store_id)
    if not game.installed or not game.install_dir:
        raise LaunchError('not_installed')
    if not os.path.isdir(game.install_dir):
        raise LaunchError('missing_file', game.install_dir)
    try:
        clients.ensure(clients.CLIENT_OF[store])      # a taken-over game may predate the download
    except clients.ClientError as exc:
        raise LaunchError('no_client', clients.CLIENT_OF[store]) from exc
    native = str(info.get('platform') or '').lower() == 'linux'
    umu = which('umu-run')
    if not umu and not native:
        raise LaunchError('no_umu')
    env = umu_env(store, app, options)
    gamemode = ['gamemoderun'] if options.get('gamemode') and which('gamemoderun') else []
    pre: List[Dict[str, Any]] = []
    post: List[Dict[str, Any]] = []
    if store == 'epic':
        args = ['launch', app, '--json']
        if not native:
            args += ['--wine', umu, '--wine-prefix', env['WINEPREFIX']]
        rc, out, err = clients.run('epic', args, timeout=90)
        data = _first_json(out)
        if rc != 0 or not isinstance(data, dict):
            reason = scrub((err or '').strip().splitlines()[-1] if (err or '').strip() else '')
            raise LaunchError('store_launch', reason[:140])
        argv = list(data.get('launch_command') or [])
        argv.append(os.path.join(data.get('game_directory') or game.install_dir,
                                 data.get('game_executable') or ''))
        for name in ('game_parameters', 'user_parameters', 'egl_parameters'):
            argv += [str(a) for a in data.get(name) or []]
        env.update({str(k): str(v) for k, v in (data.get('environment') or {}).items()})
        env.update(clients.client_env('epic'))
        if options.get('cloud_saves', True):
            sync_env = dict(clients.client_env('epic'), WINEPREFIX=env['WINEPREFIX'])
            program = clients.find('legendary') or ''
            pre = [{'argv': [program, '-y', 'sync-saves', app, '--skip-upload'], 'env': sync_env}]
            post = [{'argv': [program, '-y', 'sync-saves', app, '--skip-download'],
                     'env': sync_env}]
        return Plan(gamemode + argv, env=env, cwd=data.get('working_directory') or '',
                    wait=True, pre=pre, post=post)
    env.update(clients.client_env(store))
    platform = 'linux' if native else 'windows'
    if store == 'gog':
        argv = clients.command('gog', ['launch', game.install_dir, app, '--platform', platform])
    else:
        argv = clients.command('amazon', ['launch', app])
    if not native:
        argv += ['--wine', umu, '--wine-prefix', env['WINEPREFIX']]
    return Plan(gamemode + argv, env=env, watch_dir=game.install_dir)
