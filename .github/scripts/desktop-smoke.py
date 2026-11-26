#!/usr/bin/env python3
"""Boot test, inside the signed-in Spark session: opens each app from its menu entry (gio launch),
waits for a new window in the compositor's window list (spark-wl-windows, wlr-foreign-toplevel),
fails on a Python traceback, screenshots the screen with grim and closes the window through the
same list. Spark apps once more in French. Writes results.json for the run's summary."""
import argparse, json, os, select, subprocess, time
ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True)
ap.add_argument('--expect', required=True)
ap.add_argument('--passes', default='en')
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

def windows():
    """The compositor's window list: spark-wl-windows prints it once connected."""
    p = subprocess.Popen(['/usr/libexec/spark-wl-windows'], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True)
    line = ''
    if select.select([p.stdout], [], [], 5)[0]:
        line = p.stdout.readline()
    p.stdin.close()
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()
    try:
        return {w['id']: w for w in json.loads(line)}
    except ValueError:
        return {}

def send(cmd):
    p = subprocess.Popen(['/usr/libexec/spark-wl-windows'], stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, text=True)
    time.sleep(1)
    p.stdin.write(cmd + '\n'); p.stdin.flush(); time.sleep(1)
    p.stdin.close()
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()

results, failed = [], False
for lang in a.passes.split(','):
    env = dict(os.environ)
    if lang == 'fr':
        env.update(LANG='fr_FR.UTF-8', LANGUAGE='fr')
    for ident in a.expect.split(','):
        if lang != 'en' and not ident.startswith('dev.wolklaw.'):
            continue
        path = f'/usr/share/applications/{ident}.desktop'
        r = {'name': ident, 'pass': lang, 'title': '', 'seconds': None, 'ok': False,
             'reason': '', 'notes': []}
        print(f'-- {ident} ({lang})', flush=True)
        if not os.path.exists(path):
            r['reason'] = 'no menu entry'
        else:
            before = windows()
            log = os.path.join(a.out, f'{ident}-{lang}.log')
            start = time.time()
            with open(log, 'w') as lf:
                subprocess.Popen(['gio', 'launch', path], env=env, stdout=lf,
                                 stderr=subprocess.STDOUT, start_new_session=True)
            new = {}
            while time.time() - start < 40 and not new:
                time.sleep(1)
                new = {k: w for k, w in windows().items() if k not in before}
            if not new:
                r['reason'] = 'no window in 40 s'
            else:
                r['seconds'] = round(time.time() - start, 1)
                time.sleep(3)
                w = next(iter(new.values()))
                r['title'] = w.get('title', '')
                subprocess.run(['grim', os.path.join(a.out, f'{ident}-{lang}.png')])
                for k in new:
                    send(f'close {k}')
                time.sleep(2)
                if any(k in windows() for k in new):
                    r['notes'].append('still open after close')
                r['ok'] = True
            with open(log) as lf:
                if 'Traceback (most recent call last)' in lf.read():
                    r['ok'], r['reason'] = False, 'Python traceback (see its log)'
        print('   ' + ('ok' if r['ok'] else 'FAIL ' + r['reason']), r['title'], flush=True)
        failed |= not r['ok']
        results.append(r)
json.dump({'launcher': 'gio launch in the Spark session', 'results': results},
          open(os.path.join(a.out, 'results.json'), 'w'), indent=1)
raise SystemExit(1 if failed else 0)
