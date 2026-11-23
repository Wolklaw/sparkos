"""Stand-ins for legendary, gogdl and nile. They print recorded output in the shapes read from
each client's source, keep a little state under their config folder, and write every call to
$FAKE_CLIENT_LOG (arguments only). No network, no accounts. Never ship these."""

import json
import os
import sys
import time

TOKEN = 'fake-secret-token-123'


def log_call(name, args):
    path = os.environ.get('FAKE_CLIENT_LOG')
    if path:
        with open(path, 'a') as f:
            f.write(json.dumps([name] + args) + '\n')


def config(name):
    var = {'legendary': 'LEGENDARY_CONFIG_PATH', 'nile': 'NILE_CONFIG_PATH',
           'gogdl': 'GOGDL_CONFIG_PATH'}[name]
    path = os.environ.get(var, '')
    if not path:
        sys.exit('no config path')
    os.makedirs(path, exist_ok=True)
    return path


def state_file(name):
    return os.path.join(config(name), 'fake_state.json')


def load_state(name):
    try:
        with open(state_file(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(name, data):
    with open(state_file(name), 'w') as f:
        json.dump(data, f)


def progress(lines=5):
    """Progress lines in the clients' own format; FAKE_SLOW makes them slow enough to pause."""
    fail = os.environ.get('FAKE_FAIL')
    delay = 0.25 if os.environ.get('FAKE_SLOW') else 0.0
    for i in range(1, lines + 1):
        pct = 100.0 * i / lines
        print(f'[DLManager] INFO: = Progress: {pct:.2f}% ({i}/{lines}), Running for 00:00:0{i}, '
              f'ETA: 00:00:{lines - i:02d}', flush=True)
        print(f'[DLManager] INFO:  + Download\t- {10 + i}.50 MiB/s (raw) / 6.22 MiB/s '
              f'(decompressed)', flush=True)
        if fail == 'space' and i == 2:
            print('OSError: [Errno 28] No space left on device', flush=True)
            sys.exit(1)
        if fail == 'crash' and i == 2:
            print('Something broke access_token=abc123', flush=True)
            sys.exit(1)
        time.sleep(delay)


def value(args, flag):
    return args[args.index(flag) + 1] if flag in args else ''


def legendary(args):
    args = [a for a in args if a not in ('-y', '-J')]
    cmd, rest = args[0], args[1:]
    cfg = config('legendary')
    user = os.path.join(cfg, 'user.json')
    if cmd == 'auth':
        if '--delete' in rest:
            if os.path.exists(user):
                os.unlink(user)
            return
        if (value(rest, '--code') or 'bad').startswith('bad'):
            print('[cli] ERROR: Logging in failed', flush=True)
            sys.exit(1)
        with open(user, 'w') as f:
            json.dump({'displayName': 'Fake Player', 'access_token': TOKEN}, f)
        print('[cli] INFO: Successfully logged in as "Fake Player"')
    elif cmd == 'list':
        print('[cli] INFO: Logging in...')
        print(json.dumps([
            {'app_name': 'Sugar', 'app_title': 'Celeste',
             'asset_infos': {'Windows': {'build_version': '1.4.0.1'}},
             'metadata': {'keyImages': [{'type': 'DieselGameBoxTall',
                                         'url': 'https://cdn.example.invalid/celeste.jpg'}]},
             'dlcs': []},
            {'app_name': 'Fox', 'app_title': 'Free Fox Game',
             'asset_infos': {'Windows': {'build_version': '2.0'}}, 'metadata': {}, 'dlcs': []},
            {'app_name': 'MacOnly', 'app_title': 'Mac Only',
             'asset_infos': {'Mac': {'build_version': '1'}}, 'metadata': {}, 'dlcs': []},
            # an Unreal Engine sample an Epic account owns: not a game
            {'app_name': 'CitySample_5.6', 'app_title': 'City Sample',
             'asset_infos': {'Windows': {'build_version': '5.6.1+++UE5+Release-5.6-Windows'}},
             'metadata': {'categories': [{'path': 'projects'},
                                         {'path': 'asset-format/game-engine/unreal-engine'}]},
             'dlcs': []}]))
    elif cmd == 'list-installed':
        data = load_state('legendary')
        print(json.dumps([{'app_name': a, 'title': i['title'], 'install_path': i['path'],
                           'version': i['version'], 'platform': 'Windows', 'is_dlc': False}
                          for a, i in data.items()]))
    elif cmd == 'info':
        print(json.dumps({'game': {'title': 'x'}, 'manifest': {'download_size': 1048576,
                                                              'disk_size': 2097152}}))
    elif cmd == 'install':
        app = rest[0]
        progress()
        data = load_state('legendary')
        if '--base-path' in rest:
            path = os.path.join(value(rest, '--base-path'), 'FoxGame')
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, 'Fox.exe'), 'w') as f:
                f.write('MZ')
            data[app] = {'title': 'Free Fox Game', 'path': path, 'version': '2.0'}
        elif app in data:
            data[app]['version'] = '1.4.0.1' if app == 'Sugar' else data[app]['version']
        save_state('legendary', data)
    elif cmd == 'launch':
        wine = value(rest, '--wine')
        print(json.dumps({
            'launch_command': [wine] if wine else [], 'game_directory': '/games/fox',
            'game_executable': 'Fox.exe', 'game_parameters': ['-AUTH_LOGIN=unused',
                                                                f'-AUTH_PASSWORD={TOKEN}'],
            'user_parameters': ['-user'], 'egl_parameters': ['-egl'],
            'environment': {'FOO': 'bar'}, 'working_directory': '/games/fox',
            'pre_launch_command': ''}))
    elif cmd == 'import':
        app, path = [a for a in rest if not a.startswith('--')][:2]
        data = load_state('legendary')
        data[app] = {'title': app, 'path': path, 'version': '1.4.0.0'}
        save_state('legendary', data)
    elif cmd == 'uninstall':
        data = load_state('legendary')
        data.pop(rest[0], None)
        save_state('legendary', data)
    elif cmd == 'sync-saves':
        pass
    else:
        sys.exit('unknown command ' + cmd)


def gogdl(args):
    auth_file = value(args, '--auth-config-path')
    if '--auth-config-path' in args:
        i = args.index('--auth-config-path')
        args = args[:i] + args[i + 2:]
    cmd, rest = args[0], args[1:]
    config('gogdl')
    creds = {'46899977096215655': {'access_token': TOKEN, 'refresh_token': 'r', 'expires_in': 3600,
                                   'loginTime': 1}}
    if cmd == 'auth':
        if '--code' in rest:
            if value(rest, '--code').startswith('bad'):
                print('{"error": true}')
                sys.exit(1)
            with open(auth_file, 'w') as f:
                json.dump(creds, f)
        elif not os.path.exists(auth_file):
            sys.exit(1)
        print(json.dumps(creds['46899977096215655']))
    elif cmd == 'info':
        print(json.dumps({'size': {'*': {'download_size': 3145728, 'disk_size': 6291456}}}))
    elif cmd in ('download', 'update', 'repair'):
        path = value(rest, '--path')
        progress()
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'game.exe'), 'w') as f:
            f.write('MZ')
    elif cmd == 'launch':
        pass
    else:
        sys.exit('unknown command ' + cmd)


def nile(args):
    cmd, rest = args[0], args[1:]
    base = os.path.join(config('nile'), 'nile')
    os.makedirs(base, exist_ok=True)
    cfg, installed = os.path.join(base, 'current_user.json'), os.path.join(base, 'installed.json')
    if cmd == 'auth' and '--login' in rest:
        print(json.dumps({'client_id': 'cid', 'code_verifier': 'verifier', 'serial': 'ser',
                          'url': 'https://www.amazon.com/ap/signin?fake=1'}))
    elif cmd == 'register':
        if value(rest, '--code').startswith('bad'):
            sys.exit(1)
        with open(cfg, 'w') as f:
            json.dump({'user_id': 'u1', 'name': 'Fake Amazon'}, f)
    elif cmd == 'auth' and '--logout' in rest:
        if os.path.exists(cfg):
            os.unlink(cfg)
    elif cmd == 'library' and rest[0] == 'sync':
        print('Synced')
    elif cmd == 'library' and rest[0] == 'list':
        print(json.dumps([{'product': {'id': 'amzn1.adg.product.0000-example',
                                       'title': 'Amazon Example',
                                       'productDetail': {'iconUrl': 'https://cdn.example.invalid/a.png',
                                                         'details': {}}}},
                          {'product': {'id': 'amzn1.adg.product.1111-other', 'title': 'Other',
                                       'productDetail': {}}}]))
    elif cmd == 'list-updates':
        print(json.dumps(['amzn1.adg.product.0000-example']))
    elif cmd in ('install', 'update', 'verify'):
        if '--info' in rest:
            print(json.dumps({'download_size': 2097152, 'install_size': 4194304}))
            return
        app, path = rest[0], value(rest, '--path')
        progress()
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'a.exe'), 'w') as f:
            f.write('MZ')
        try:
            with open(installed) as f:
                items = json.load(f)
        except (OSError, ValueError):
            items = []
        items = [i for i in items if i['id'] != app] + [{'id': app, 'path': path, 'version': '7'}]
        with open(installed, 'w') as f:
            json.dump(items, f)
    elif cmd == 'import':
        app, path = rest[-1], value(rest, '--path')
        with open(installed, 'w') as f:
            json.dump([{'id': app, 'path': path, 'version': '1'}], f)
    elif cmd in ('launch', 'uninstall'):
        pass
    else:
        sys.exit('unknown command ' + cmd)


def main(name):
    args = sys.argv[1:]
    if args == ['--version']:
        print({'legendary': 'legendary version "0.21.1", codename "Dread"',
               'gogdl': 'gogdl 1.4.0', 'nile': 'nile 1.2.0'}[name])
        return
    log_call(name, args)
    {'legendary': legendary, 'gogdl': gogdl, 'nile': nile}[name](args)
