#!/usr/bin/env python3
"""A fake `flatpak` for the tests: it answers the commands Spark Store runs from a JSON state
file ($FAKE_FLATPAK_STATE) and records every call ($FAKE_FLATPAK_STATE.log). Installs print progress the way flatpak
does (percentages on one line), wait $delay seconds, and fail for IDs listed in "fail".

    SPARK_STORE_FLATPAK='["python3", "tests/fake_flatpak.py"]'
"""

import json
import os
import shutil
import sys
import time

DEFAULT_METADATA = """[Application]
name={id}
runtime=org.freedesktop.Platform/x86_64/24.08

[Context]
shared=network;ipc;
sockets=wayland;fallback-x11;pulseaudio;
devices=dri;
filesystems=xdg-download;xdg-music:ro;

[Session Bus Policy]
org.freedesktop.Notifications=talk
"""


def load(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(path, state):
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=1)
    os.replace(path + '.tmp', path)


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    path = os.environ.get('FAKE_FLATPAK_STATE', '')
    state = load(path)
    state.setdefault('installed', [])
    state.setdefault('remotes', {'user': ['flathub'], 'system': ['flathub']})
    state.setdefault('updates', [])
    state.setdefault('fail', [])
    # every call goes to its own log, one JSON line each; the state file is only rewritten
    # by commands that change something, so a test's edits are never lost to a read
    with open(path + '.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(argv) + '\n')
    scope = 'system'
    args = []
    for a in argv:
        if a == '--user':
            scope = 'user'
        elif a == '--system':
            scope = 'system'
        else:
            args.append(a)
    if not args:
        return 1
    cmd, rest = args[0], args[1:]
    opts = [a for a in rest if a.startswith('-')]
    pos = [a for a in rest if not a.startswith('-')]
    out = sys.stdout

    if cmd == '--version':
        print("Flatpak 1.16.1")
        return 0
    if cmd == 'list' and '--runtime' in opts:
        for rt in state.get('runtimes', []):
            out.write(rt['id'] + '\t' + rt.get('installation', 'user') + '\n')
        return 0
    if cmd == 'list':
        for app in state['installed']:
            out.write('\t'.join([app['id'], app.get('name', app['id']), app.get('version', ''),
                                 app.get('branch', 'stable'), app.get('origin', 'flathub'),
                                 app.get('installation', 'user'), app.get('size', '10.0 MB')])
                      + '\n')
        return 0
    if cmd == 'remotes':
        for name in state['remotes'].get(scope, []):
            print(name)
        return 0
    if cmd == 'remote-add':
        name = pos[0]
        if name not in state['remotes'].setdefault(scope, []):
            state['remotes'][scope].append(name)
        save(path, state)
        return 0
    if cmd == 'remote-ls':
        for up in state['updates']:
            if up.get('scope', 'user') != scope:
                continue
            ref = up.get('ref') or f"app/{up['id']}/x86_64/{up.get('branch', 'stable')}"
            print('\t'.join([up['id'], up.get('version', ''), up.get('branch', 'stable'), ref]))
        return 0
    if cmd == 'remote-info':
        if 'flathub' not in state['remotes'].get(scope, []):
            print("error: Remote \"flathub\" not found", file=sys.stderr)
            return 1
        ref = pos[1] if len(pos) > 1 else ''
        app_id = ref.split('/')[1] if ref.count('/') >= 1 else ref
        if app_id in state.get('missing', []):
            print(f"error: No remote refs found for ‘{app_id}’", file=sys.stderr)
            return 1
        if '--show-metadata' in opts:
            out.write(state.get('metadata', {}).get(app_id, DEFAULT_METADATA.format(id=app_id)))
            return 0
        print(f"        ID: {app_id}\n       Ref: app/{app_id}/x86_64/stable\n"
              f"      Arch: x86_64\n    Branch: stable\n   Version: 2.0\n"
              f"  Download: 41.5 MB\n Installed: 108.3 MB\n")
        return 0
    if cmd == 'info':
        app_id = pos[0]
        if not any(a['id'] == app_id for a in state['installed']):
            print(f"error: {app_id} not installed", file=sys.stderr)
            return 1
        out.write(state.get('metadata', {}).get(app_id, DEFAULT_METADATA.format(id=app_id)))
        return 0
    if cmd == 'install':
        if '--from' in rest:
            ref_path = rest[rest.index('--from') + 1]
            app_id = ''
            with open(ref_path, encoding='utf-8') as f:
                for line in f:
                    if line.startswith('Name='):
                        app_id = line.strip()[5:]
        else:
            ref = pos[-1]
            app_id = ref.split('/')[1] if ref.startswith(('app/', 'runtime/')) else ref
        ref_is_runtime = '--from' not in rest and pos[-1].startswith('runtime/')
        if scope == 'user' and '--from' not in rest and \
                'flathub' not in state['remotes'].get('user', []):
            print("error: No remote 'flathub'", file=sys.stderr)
            return 1
        print("Looking for matches…")
        out.flush()
        delay = float(state.get('delay', 0))
        for pct in (0, 25, 50, 75, 100):
            out.write(f"\rInstalling 1/1… {pct}%  1.2 MB/s")
            out.flush()
            time.sleep(delay / 5)
            if pct == 50 and app_id in state['fail']:
                out.write("\n")
                out.flush()
                print(f"error: Failed to install {app_id}: Not enough disk space to complete "
                      f"this operation", file=sys.stderr)
                return 1
        out.write("\nInstallation complete.\n")
        state = load(path)
        if ref_is_runtime:
            state.setdefault('runtimes', []).append({'id': app_id, 'installation': scope})
            save(path, state)
            return 0
        state.setdefault('installed', []).append({'id': app_id, 'name': state.get('names', {}).get(
            app_id, app_id.rsplit('.', 1)[-1]), 'version': '2.0', 'installation': scope,
            'size': '108.3 MB'})
        save(path, state)
        return 0
    if cmd == 'uninstall' and pos[-1].startswith('runtime/'):
        rt_id = pos[-1].split('/')[1]
        before = state.get('runtimes', [])
        state['runtimes'] = [r for r in before if r['id'] != rt_id]
        if len(state['runtimes']) == len(before):
            print(f"error: {rt_id} not installed", file=sys.stderr)
            return 1
        save(path, state)
        return 0
    if cmd == 'uninstall':
        app_id = pos[-1]
        before = len(state['installed'])
        state['installed'] = [a for a in state['installed'] if a['id'] != app_id]
        if len(state['installed']) == before:
            print(f"error: {app_id}/*unspecified*/*unspecified* not installed", file=sys.stderr)
            return 1
        if '--delete-data' in opts:
            state.setdefault('deleted_data', []).append(app_id)
        save(path, state)
        print(f"Uninstalling {app_id}… 100%")
        return 0
    if cmd == 'update':
        if '--appstream' in opts:
            src = os.environ.get('FAKE_FLATPAK_APPSTREAM_SRC', '')
            base = os.environ.get('FLATPAK_USER_DIR', '')
            arch = os.environ.get('FAKE_FLATPAK_ARCH', 'x86_64')
            if not src or not base:
                print("error: Unable to load summary from remote flathub: Could not resolve "
                      "hostname", file=sys.stderr)
                return 1
            dest = os.path.join(base, 'appstream', 'flathub', arch, 'active')
            os.makedirs(dest, exist_ok=True)
            shutil.copy(src, os.path.join(dest, os.path.basename(src)))
            print("Updating appstream data for user remote flathub… 100%")
            return 0
        targets = pos
        state['updates'] = [u for u in state['updates'] if u.get('scope', 'user') != scope or
                            (targets and u['id'] not in targets)]
        save(path, state)
        print("Updating 1/1… 100%\nUpdates complete.")
        return 0
    if cmd == 'run':
        return 0
    print(f"error: unknown command {cmd}", file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
