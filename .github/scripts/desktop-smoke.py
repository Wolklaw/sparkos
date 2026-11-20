#!/usr/bin/python3
"""Open every preinstalled app on the real Plasma desktop, the way the app menu does.

Run by boot-test.yml inside the test VM, over SSH, as the signed-in user (spark), after Plasma
has started. For each app in /usr/share/applications (dev.wolklaw.*.desktop and FreeSuite):

  1. start it from its desktop entry with the launcher Plasma's menu uses (KIO's
     ApplicationLauncherJob, through kstart), in the Plasma session's environment
  2. wait until KWin has a window for it (KWin's scripting D-Bus interface: a small script
     lists the windows and calls back to this program over D-Bus)
  3. screenshot the screen through KWin's ScreenShot2 interface and save it as PNG
  4. fail if no window appears, the window closes by itself, or the app's output or the
     journal shows a Python traceback
  5. close the window, then end the app's processes if they are still there

--passes en,fr runs the whole thing once in the session's language, then once more with
LANG=fr_CA.UTF-8 (Spark apps only). Results go to OUT/results.json; screenshots and each app's
output to OUT. Exit status 1 if any app failed. Needs PyGObject and Pillow, which the image
has for Spark Snip.
"""

import argparse
import configparser
import glob
import json
import os
import re
import secrets
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib  # noqa: E402
from PIL import Image  # noqa: E402

APPS_DIR = '/usr/share/applications'
OTHER_ENTRIES = ['freesuite.desktop']           # named in the Containerfile (freesuite.sh)
WINDOW_TIMEOUT = {'spark': 45, 'other': 90}     # seconds for the first window
SETTLE = {'spark': 3.0, 'other': 8.0}           # let the window draw before the screenshot
CLOSE_TIMEOUT = 8
SERVICE = 'dev.wolklaw.DesktopSmoke'
FRENCH = {'LANG': 'fr_CA.UTF-8', 'LC_MESSAGES': 'fr_CA.UTF-8', 'LANGUAGE': 'fr_CA:fr'}
TRACEBACK = 'Traceback (most recent call last)'

SCRIPT = r"""
var P = %s;
try {
var list = workspace.windowList();
var out = [];
var g = workspace.virtualScreenGeometry || {x: 0, y: 0, width: 0, height: 0};
for (var i = 0; i < list.length; i++) {
  var w = list[i];
  var id = String(w.internalId);
  if (P.ids.indexOf(id) >= 0) {
    if (P.action === "close") w.closeWindow();
    if (P.action === "activate") { w.minimized = false; workspace.activeWindow = w; }
  }
  var f = w.frameGeometry;
  out.push({id: id, caption: String(w.caption), cls: String(w.resourceClass),
            name: String(w.resourceName), desktop: String(w.desktopFileName || ""),
            pid: w.pid, normal: !!w.normalWindow, dialog: !!w.dialog,
            minimized: !!w.minimized, active: workspace.activeWindow === w,
            x: f.x, y: f.y, w: f.width, h: f.height});
}
callDBus(P.service, "/", P.service, "Report", P.token,
         JSON.stringify({windows: out, screen: {x: g.x, y: g.y, w: g.width, h: g.height}}));
} catch (e) {
  callDBus(P.service, "/", P.service, "Report", P.token, JSON.stringify({error: String(e)}));
}
"""

IFACE_XML = f"""<node><interface name="{SERVICE}">
<method name="Report"><arg type="s" direction="in"/><arg type="s" direction="in"/></method>
</interface></node>"""


def log(msg):
    print(msg, flush=True)


# ─── The Plasma session ──────────────────────────────────────

def session_environment():
    """The environment of this user's plasmashell: what an app started from the menu gets."""
    uid = os.getuid()
    for pid in sorted(int(p) for p in os.listdir('/proc') if p.isdigit()):
        try:
            if os.stat(f'/proc/{pid}').st_uid != uid:
                continue
            with open(f'/proc/{pid}/comm') as f:
                if f.read().strip() != 'plasmashell':
                    continue
            with open(f'/proc/{pid}/environ', 'rb') as f:
                raw = f.read()
        except OSError:
            continue
        env = {}
        for item in raw.split(b'\0'):
            key, sep, value = item.decode('utf-8', 'replace').partition('=')
            if sep:
                env[key] = value
        return pid, env
    return None, None


# ─── KWin ────────────────────────────────────────────────────

class KWin:
    """KWin's scripting interface (window list, activate, close) and ScreenShot2."""

    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                          'RequestName', GLib.Variant('(su)', (SERVICE, 4)), '(u)')
        if reply[0] != 1:
            raise RuntimeError(f'could not own {SERVICE} on the session bus')
        self.node = Gio.DBusNodeInfo.new_for_xml(IFACE_XML)
        self.bus.register_object('/', self.node.interfaces[0], self._on_call, None, None)
        self.replies = {}
        self.count = 0
        self.folder = tempfile.mkdtemp(prefix='desktop-smoke-')

    def call(self, name, path, iface, method, args=None, reply_type=None, timeout=15):
        reply = self.bus.call_sync(name, path, iface, method, args,
                                   GLib.VariantType(reply_type) if reply_type else None,
                                   Gio.DBusCallFlags.NONE, timeout * 1000, None)
        return reply.unpack() if reply is not None else None

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        token, data = params.unpack()
        self.replies[token] = data
        invocation.return_value(None)

    def script(self, action='list', ids=()):
        """Runs a KWin script; returns {'windows': [...], 'screen': {...}}."""
        self.count += 1
        token = secrets.token_hex(8)
        plugin = f'desktopsmoke{os.getpid()}x{self.count}'
        path = os.path.join(self.folder, plugin + '.js')
        with open(path, 'w') as f:
            f.write(SCRIPT % json.dumps({'service': SERVICE, 'token': token,
                                         'action': action, 'ids': list(ids)}))
        script_id = self.call('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting',
                              'loadScript', GLib.Variant('(ss)', (path, plugin)), '(i)')[0]
        try:
            if script_id < 0:
                raise RuntimeError(f'KWin refused to load the window script ({script_id})')
            self.call('org.kde.KWin', f'/Scripting/Script{script_id}', 'org.kde.kwin.Script',
                      'run')
            ctx = GLib.MainContext.default()
            deadline = time.monotonic() + 10
            while token not in self.replies:
                if time.monotonic() > deadline:
                    raise RuntimeError('KWin ran the window script but it never answered')
                if not ctx.iteration(False):
                    time.sleep(0.01)
        finally:
            try:
                self.call('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting',
                          'unloadScript', GLib.Variant('(s)', (plugin,)), '(b)')
            except GLib.Error:
                pass
            os.remove(path)
        answer = json.loads(self.replies.pop(token))
        if 'error' in answer:
            raise RuntimeError(f"KWin's window script failed: {answer['error']}")
        return answer

    def wake(self):
        """As if someone moved the mouse: the screen comes back on and the idle time restarts."""
        try:
            self.call('org.freedesktop.ScreenSaver', '/ScreenSaver', 'org.freedesktop.ScreenSaver',
                      'SimulateUserActivity')
        except GLib.Error:
            pass

    def screenshot(self, dest):
        """The whole screen through ScreenShot2.CaptureWorkspace -> PNG. Returns (w, h, colours)."""
        read_end, write_end = os.pipe()
        chunks, errors = [], []

        def reader():
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([read_end], [], [], 0.5)
                    if ready:
                        chunk = os.read(read_end, 1 << 20)
                        if not chunk:
                            return
                        chunks.append(chunk)
                errors.append('no pixels from KWin after 30 s')
            finally:
                os.close(read_end)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        fds = Gio.UnixFDList.new()
        index = fds.append(write_end)
        os.close(write_end)
        opts = {'include-cursor': GLib.Variant('b', False),
                'native-resolution': GLib.Variant('b', True)}
        try:
            reply, _ = self.bus.call_with_unix_fd_list_sync(
                'org.kde.KWin.ScreenShot2', '/org/kde/KWin/ScreenShot2',
                'org.kde.KWin.ScreenShot2', 'CaptureWorkspace',
                GLib.Variant('(a{sv}h)', (opts, index)), GLib.VariantType('(a{sv})'),
                Gio.DBusCallFlags.NONE, 15000, fds, None)
        finally:
            for fd in fds.steal_fds():
                os.close(fd)
        info = reply.unpack()[0]
        thread.join(31)
        if errors:
            raise RuntimeError(errors[0])
        modes = {4: ('RGB', 'BGRX'), 5: ('RGBA', 'BGRA'), 6: ('RGBA', 'BGRa'),
                 16: ('RGB', 'RGBX'), 17: ('RGBA', 'RGBA'), 18: ('RGBA', 'RGBa')}
        fmt = int(info['format'])
        if fmt not in modes:
            raise RuntimeError(f'KWin sent pixel format {fmt}')
        mode, raw = modes[fmt]
        width, height = int(info['width']), int(info['height'])
        image = Image.frombytes(mode, (width, height), b''.join(chunks), 'raw', raw,
                                int(info['stride']), 1).convert('RGB')
        image.save(dest)
        colours = image.resize((64, 40)).getcolors(4096)
        return width, height, len(colours) if colours else 4096


# ─── Apps ────────────────────────────────────────────────────

def read_entry(path):
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    with open(path, encoding='utf-8') as f:
        parser.read_file(f)
    return dict(parser['Desktop Entry']) if parser.has_section('Desktop Entry') else {}


def kill_patterns(exec_line):
    """What the app's processes have in their command line: the program's real path, its
    folder when it has one of its own, and the .py files a /usr/bin wrapper runs."""
    words = [w for w in shlex.split(exec_line) if not w.startswith('%')]
    while words and (words[0] == 'env' or '=' in words[0]):
        words.pop(0)
    program = shutil.which(words[0]) if words else None
    if not program:
        return [], None
    real = os.path.realpath(program)
    patterns = {real}
    folder = os.path.dirname(real)
    if folder not in ('/usr/bin', '/bin', '/usr/local/bin', '/usr/sbin'):
        patterns.add(folder + '/')
    try:
        if os.path.getsize(real) < 4096:
            with open(real, encoding='utf-8', errors='replace') as f:
                for path in re.findall(r'(/[\w./-]+\.py)\b', f.read()):
                    patterns.add(path)
                    patterns.add(os.path.dirname(path) + '/')
    except OSError:
        pass
    return sorted(patterns), program


def find_apps(expect):
    apps, problems = [], []
    paths = sorted(glob.glob(os.path.join(APPS_DIR, 'dev.wolklaw.*.desktop')))
    paths += [os.path.join(APPS_DIR, name) for name in OTHER_ENTRIES]
    for path in paths:
        desktop_id = os.path.basename(path)[:-len('.desktop')]
        if not os.path.exists(path):
            continue
        entry = read_entry(path)
        if (entry.get('Type') != 'Application' or entry.get('NoDisplay') == 'true'
                or entry.get('Hidden') == 'true' or 'Exec' not in entry):
            continue
        patterns, program = kill_patterns(entry['Exec'])
        apps.append({'id': desktop_id, 'path': path, 'name': entry.get('Name', desktop_id),
                     'exec': entry['Exec'], 'program': program,
                     'wmclass': entry.get('StartupWMClass', ''), 'patterns': patterns,
                     'spark': desktop_id.startswith('dev.wolklaw.Spark')})
    found = {a['id'] for a in apps}
    for desktop_id in expect:
        if desktop_id not in found:
            problems.append(desktop_id)
    return apps, problems


def processes(patterns):
    """{pid: cmdline} for this user's processes whose command line has one of the patterns."""
    out = {}
    if not patterns:
        return out
    uid = os.getuid()
    for p in os.listdir('/proc'):
        if not p.isdigit() or int(p) == os.getpid():
            continue
        try:
            if os.stat(f'/proc/{p}').st_uid != uid:
                continue
            with open(f'/proc/{p}/cmdline', 'rb') as f:
                cmd = f.read().replace(b'\0', b' ').decode('utf-8', 'replace').strip()
        except OSError:
            continue
        if cmd and any(pat in cmd for pat in patterns):
            out[int(p)] = cmd
    return out


def process_lang(pid):
    try:
        with open(f'/proc/{pid}/environ', 'rb') as f:
            env = dict(item.decode('utf-8', 'replace').partition('=')[::2]
                       for item in f.read().split(b'\0') if b'=' in item)
    except OSError:
        return None
    for key in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        if env.get(key):
            return f'{key}={env[key]}'
    return ''


def matches(app, window, pids):
    if window['desktop'] in (app['id'], app['id'] + '.desktop'):
        return 'desktop entry'
    names = {app['wmclass'].lower()} - {''}
    if app['program']:
        names.add(os.path.basename(app['program']).lower())
    if window['cls'].lower() in names or window['name'].lower() in names:
        return 'window class'
    if window['pid'] in pids:
        return 'process'
    return None


def journal_since(since):
    """User and own-UID journal entries since the epoch time, as dicts."""
    entries, seen = [], set()
    for cmd in (['journalctl', '--user'], ['journalctl', f'_UID={os.getuid()}']):
        try:
            out = subprocess.run(cmd + ['--since', f'@{since:.0f}', '-o', 'json', '--no-pager'],
                                 capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in out.splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get('__CURSOR') in seen:
                continue
            seen.add(entry.get('__CURSOR'))
            message = entry.get('MESSAGE')
            if isinstance(message, list):           # journald stores non-UTF-8 as bytes
                message = bytes(message).decode('utf-8', 'replace')
            entry['MESSAGE'] = message or ''
            entries.append(entry)
    return entries


def app_journal(app, since, app_pids):
    """The app's own lines in the journal (KIO starts apps as systemd units app-<id>@...,
    whose output goes there): -> text."""
    lines = []
    for entry in journal_since(since):
        unit = entry.get('_SYSTEMD_USER_UNIT', '') + entry.get('_SYSTEMD_UNIT', '')
        pid = entry.get('_PID', '')
        if f'app-{app["id"]}@' in unit or (pid.isdigit() and int(pid) in app_pids):
            lines.append(f"{entry.get('SYSLOG_IDENTIFIER', '?')}[{pid}]: {entry['MESSAGE']}")
    return '\n'.join(lines)


def tracebacks(app, since, log_text, app_pids):
    """(the app's tracebacks, other tracebacks in the journal meanwhile)."""
    mine, others = [], []
    if TRACEBACK in log_text:
        mine.append('in its output:\n' + log_text[log_text.index(TRACEBACK):][-3000:])
    by_pid = {}
    for entry in journal_since(since):
        by_pid.setdefault(entry.get('_PID', '?'), []).append(entry)
    folders = [p for p in app['patterns'] if p.endswith('/')]
    for pid, entries in by_pid.items():
        text = '\n'.join(e['MESSAGE'] for e in entries)
        if TRACEBACK not in text:
            continue
        unit = entries[0].get('_SYSTEMD_USER_UNIT', '') + entries[0].get('_SYSTEMD_UNIT', '')
        ident = entries[0].get('SYSLOG_IDENTIFIER', '')
        snippet = f'journal (pid {pid}, {ident or "?"}, {unit or "no unit"}):\n' + \
                  text[text.index(TRACEBACK):][-3000:]
        if (str(pid).isdigit() and int(pid) in app_pids) or app['id'] in unit \
                or any(f in text for f in folders):
            mine.append(snippet)
        else:
            others.append(snippet)
    return mine, others


# ─── Launching ───────────────────────────────────────────────

def launchers():
    found = []
    kstart = shutil.which('kstart') or shutil.which('kstart6')
    if kstart:
        found.append(('kstart', lambda app: [kstart, '--application', app['id']]))
    if shutil.which('gtk-launch'):
        found.append(('gtk-launch', lambda app: ['gtk-launch', app['id']]))
    if shutil.which('gio'):
        found.append(('gio launch', lambda app: ['gio', 'launch', app['path']]))
    return found


def start(cmd, env, log_path):
    """Starts the launcher with stdout/stderr into log_path. The launcher hands the app the
    same file, so the app's own output lands there too."""
    out = open(log_path, 'ab')
    try:
        proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        out.close()
    return proc


def pick_launcher(session_env, folder):
    """Plasma's menu starts apps with KIO's ApplicationLauncherJob, which is what kstart
    --application runs. Check with a stand-in app that the launcher really runs it, passes our
    environment (LANG) through and keeps its error output where we can read it (the launcher's
    own output, or the journal); otherwise try the next launcher."""
    apps = os.path.expanduser('~/.local/share/applications')
    os.makedirs(apps, exist_ok=True)
    probe = os.path.join(folder, 'probe.sh')
    mark = os.path.join(folder, 'probe.out')
    token = os.path.join(folder, 'probe.token')
    with open(probe, 'w') as f:
        f.write(f'#!/bin/sh\necho "LANG=$LANG" > {mark}\necho "probe-stderr $(cat {token})" >&2\n')
    os.chmod(probe, 0o755)
    entry = os.path.join(apps, 'dev.wolklaw.DesktopSmokeProbe.desktop')
    with open(entry, 'w') as f:
        f.write('[Desktop Entry]\nType=Application\nName=Desktop smoke probe\n'
                f'Exec={probe}\nNoDisplay=true\n')
    for tool in ('kbuildsycoca6', 'update-desktop-database'):
        if shutil.which(tool):
            args = [tool] + ([apps] if tool == 'update-desktop-database' else [])
            subprocess.run(args, capture_output=True, timeout=60, env=session_env)
    notes, chosen = [], None
    try:
        for name, make in launchers():
            app = {'id': 'dev.wolklaw.DesktopSmokeProbe', 'path': entry}
            word = secrets.token_hex(6)
            with open(token, 'w') as f:
                f.write(word)
            for p in (mark,):
                if os.path.exists(p):
                    os.remove(p)
            log_path = os.path.join(folder, f'probe-{name.replace(" ", "-")}.log')
            env = dict(session_env, **FRENCH)
            env.pop('LC_ALL', None)
            since = time.time() - 1
            proc = start(make(app), env, log_path)
            deadline = time.monotonic() + 15
            while not os.path.exists(mark) and time.monotonic() < deadline:
                time.sleep(0.2)
            time.sleep(1.5)
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
            ran = os.path.exists(mark)
            lang = open(mark).read().strip() if ran else ''
            with open(log_path, errors='replace') as f:
                in_log = word in f.read()
            in_journal = any(word in e['MESSAGE'] for e in journal_since(since)) if ran else False
            where = 'its output' if in_log else 'the journal' if in_journal else 'nowhere'
            notes.append(f'{name}: ran={ran} {lang or "LANG not seen"} errors go to {where}'
                         f' (exit {proc.returncode})')
            if ran and lang == f'LANG={FRENCH["LANG"]}' and where != 'nowhere':
                chosen = (name, make)
                break
    finally:
        os.remove(entry)
        if shutil.which('kbuildsycoca6'):
            subprocess.run(['kbuildsycoca6'], capture_output=True, timeout=60, env=session_env)
    return chosen, notes


# ─── One app ─────────────────────────────────────────────────

def slug(app):
    return re.sub(r'[^a-z0-9]+', '-', app['name'].lower()).strip('-')


def close_app(kwin, app, window_ids, before_pids):
    """Close its windows; then end the processes it started if they stay. -> how it went."""
    try:
        kwin.script('close', window_ids)
    except (RuntimeError, GLib.Error) as exc:
        log(f'   close through KWin failed: {exc}')
    deadline = time.monotonic() + CLOSE_TIMEOUT
    windows_left = new_pids = None
    while time.monotonic() < deadline:
        state = kwin.script()['windows']
        windows_left = [w for w in state if w['id'] in window_ids]
        new_pids = set(processes(app['patterns'])) - before_pids
        if not windows_left and not new_pids:
            return 'closed'
        time.sleep(0.5)
    how = 'window closed, processes ended' if not windows_left else 'killed'
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in set(processes(app['patterns'])) - before_pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        time.sleep(2)
        if not (set(processes(app['patterns'])) - before_pids):
            break
    left = set(processes(app['patterns'])) - before_pids
    windows_left = [w for w in kwin.script()['windows'] if w['id'] in window_ids]
    if left or windows_left:
        return f'still running after SIGKILL: {sorted(left)} {len(windows_left)} window(s)'
    if how == 'killed':
        return 'did not close its window; killed'
    return 'window closed; leftover processes killed'


def run_app(kwin, app, launcher, session_env, lang, out_dir, number, screenshots):
    name, make = launcher
    tag = f'{lang}-{number:02d}-{slug(app)}'
    log_path = os.path.join(out_dir, tag + '.log')
    result = {'pass': lang, 'id': app['id'], 'name': app['name'], 'ok': False, 'title': '',
              'seconds': None, 'reason': '', 'launcher': name, 'screenshot': None,
              'close': '', 'lang_seen': None, 'notes': []}
    env = dict(session_env)
    if lang == 'fr':
        env.update(FRENCH)
        env.pop('LC_ALL', None)
    before = {w['id'] for w in kwin.script()['windows']}
    before_pids = set(processes(app['patterns']))
    since = time.time() - 1
    t0 = time.monotonic()
    proc = start(make(app), env, log_path)
    window, how, others = None, None, []
    timeout = WINDOW_TIMEOUT['spark' if app['spark'] else 'other']
    every_new = []
    while time.monotonic() - t0 < timeout:
        state = kwin.script()
        pids = set(processes(app['patterns'])) - before_pids
        every_new = [w for w in state['windows'] if w['id'] not in before]
        new = [w for w in every_new if w['normal'] or w['dialog']]
        for w in new:
            how = matches(app, w, pids)
            if how:
                window = w
                break
        others = [w for w in new if w is not window]
        if window:
            break
        time.sleep(0.4)
    seconds = round(time.monotonic() - t0, 1)
    if proc.poll() is None:
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            pass
    if not window:
        result['reason'] = f'no window within {timeout} s'
        if every_new:
            result['reason'] += '; new windows (none matched or none a normal window): ' + \
                ', '.join(f'"{w["caption"]}" ({w["cls"]}, {w["desktop"]}, pid {w["pid"]}, '
                          f'normal={w["normal"]}, {w["w"]}x{w["h"]})' for w in every_new)
        running = processes(app['patterns'])
        result['notes'].append(f'{len(set(running) - before_pids)} of its processes running: ' +
                               '; '.join(c[:120] for p, c in sorted(running.items())
                                         if p not in before_pids)[:600])
        if screenshots:
            shot = os.path.join(out_dir, tag + '-no-window.png')
            try:
                kwin.screenshot(shot)
                result['screenshot'] = os.path.basename(shot)
            except (RuntimeError, GLib.Error) as exc:
                result['notes'].append(f'screenshot failed: {exc}')
        if proc.returncode not in (None, 0):
            result['reason'] += f'; the launcher exited {proc.returncode}'
    else:
        result['seconds'] = seconds
        result['match'] = how
        result['lang_seen'] = process_lang(window['pid']) if window['pid'] else None
        time.sleep(SETTLE['spark' if app['spark'] else 'other'])
        try:
            state = kwin.script('activate', [window['id']])
        except (RuntimeError, GLib.Error) as exc:
            state = kwin.script()
            result['notes'].append(f'could not bring it to the front: {exc}')
        time.sleep(0.8)
        current = [w for w in state['windows'] if w['id'] == window['id']]
        if not current:
            result['reason'] = f'its window closed by itself after {seconds} s'
        else:
            window = current[0]
            result['title'] = window['caption']
            scr = state['screen']
            result['geometry'] = f"{window['w']}x{window['h']}+{window['x']}+{window['y']}"
            if scr['w'] and (window['x'] < scr['x'] or window['y'] < scr['y']
                    or window['x'] + window['w'] > scr['x'] + scr['w']
                    or window['y'] + window['h'] > scr['y'] + scr['h']):
                result['notes'].append(
                    f"window {result['geometry']} goes past the screen {scr['w']}x{scr['h']}")
            if screenshots:
                shot = os.path.join(out_dir, tag + '.png')
                try:
                    width, height, colours = kwin.screenshot(shot)
                    if colours < 4:                 # screen off? wake it and take it again
                        kwin.wake()
                        time.sleep(2)
                        width, height, colours = kwin.screenshot(shot)
                    result['screenshot'] = os.path.basename(shot)
                    if colours < 4:
                        result['notes'].append('the screenshot is nearly one colour')
                except (RuntimeError, GLib.Error) as exc:
                    result['notes'].append(f'screenshot failed: {exc}')
            if lang == 'fr' and not (result['lang_seen'] or '').split('=')[-1].startswith('fr'):
                result['reason'] = f"the app did not get the French locale ({result['lang_seen']})"
            else:
                result['ok'] = True
    # every window this app opened, closed together
    pids = set(processes(app['patterns'])) - before_pids
    ids = [w['id'] for w in kwin.script()['windows']
           if w['id'] not in before and matches(app, w, pids)]
    app_pids = pids | ({window['pid']} if window else set())
    journal = app_journal(app, since, app_pids)
    if journal:
        with open(log_path, 'a') as f:
            f.write('\n== its lines in the journal ==\n' + journal + '\n')
    with open(log_path, errors='replace') as f:
        log_text = f.read()
    mine, others_tb = tracebacks(app, since, log_text, app_pids)
    if mine:
        result['ok'] = False
        result['reason'] = (result['reason'] + '; ' if result['reason'] else '') + \
            'Python traceback'
        result['tracebacks'] = mine
    if others_tb:
        result['notes'].append(f'{len(others_tb)} traceback(s) from other programs in the journal')
        result['other_tracebacks'] = others_tb
    result['close'] = close_app(kwin, app, ids, before_pids)
    if result['close'].startswith('still running'):
        result['ok'] = False
        result['reason'] = (result['reason'] + '; ' if result['reason'] else '') + \
            'could not be ended'
    result['log'] = os.path.basename(log_path)
    result['output_tail'] = log_text[-1500:]
    return result


ELECTRON_TRIES = [('started again', []),
                  ('XWayland (--ozone-platform=x11)', ['--ozone-platform=x11']),
                  ('no GPU (--disable-gpu)', ['--disable-gpu']),
                  ('no KWallet (--password-store=basic)', ['--password-store=basic'])]


def diagnose(kwin, app, session_env, out_dir, number):
    """Not a fix and not part of the verdict: when an Electron app (FreeSuite) shows no window,
    start its program directly a few more ways to narrow down why. -> lines for the report."""
    folder = os.path.dirname(os.path.realpath(app['program'] or ''))
    if not glob.glob(os.path.join(folder, 'chrome-sandbox')):
        return []
    lines = []
    real = os.path.realpath(app['program'])
    try:
        if os.path.getsize(real) < 4096:
            with open(real, encoding='utf-8') as f:
                lines.append(f'{real} is a script: ' + ' / '.join(
                    l.strip() for l in f if l.strip() and not l.startswith('#')))
    except (OSError, UnicodeDecodeError):
        pass
    for n, (label, flags) in enumerate(ELECTRON_TRIES, 1):
        tag = f'diag-{number:02d}-{slug(app)}-{n}'
        kwin.wake()
        before = {w['id'] for w in kwin.script()['windows']}
        before_pids = set(processes(app['patterns']))
        t0 = time.monotonic()
        start([app['program']] + flags, session_env, os.path.join(out_dir, tag + '.log'))
        found = None
        while time.monotonic() - t0 < 40 and not found:
            time.sleep(0.5)
            pids = set(processes(app['patterns'])) - before_pids
            found = next((w for w in kwin.script()['windows']
                          if w['id'] not in before and matches(app, w, pids)), None)
        if found:
            time.sleep(SETTLE['other'])
            try:
                kwin.screenshot(os.path.join(out_dir, tag + '.png'))
            except (RuntimeError, GLib.Error):
                pass
            lines.append(f'{label}: window "{found["caption"]}" after '
                         f'{time.monotonic() - t0 - SETTLE["other"]:.1f} s ({tag}.png)')
        else:
            lines.append(f'{label}: no window in 40 s')
        close_app(kwin, app, [found['id']] if found else [], before_pids)
    return lines


# ─── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True)
    parser.add_argument('--passes', default='en,fr')
    parser.add_argument('--expect', default='', help='comma-separated desktop ids that must exist')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    plasma_pid, session_env = session_environment()
    if not session_env:
        log('FAIL: no plasmashell for this user, so no Plasma session to open apps in')
        return 2
    for key in ('DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'DISPLAY'):
        if key in session_env:
            os.environ[key] = session_env[key]
    log(f'Plasma session: plasmashell pid {plasma_pid}, '
        f'WAYLAND_DISPLAY={session_env.get("WAYLAND_DISPLAY")} DISPLAY={session_env.get("DISPLAY")} '
        f'LANG={session_env.get("LANG")} XDG_SESSION_TYPE={session_env.get("XDG_SESSION_TYPE")}')
    locales = subprocess.run(['locale', '-a'], capture_output=True, text=True).stdout.split()
    log(f'French locales installed: {", ".join(l for l in locales if l.lower().startswith("fr")) or "none"}')

    kwin = KWin()
    # No screen lock or screen off while the apps open: nobody touches the VM, and Plasma
    # locks after 5 idle minutes. The inhibit lasts as long as this program's connection.
    try:
        cookie = kwin.call('org.freedesktop.ScreenSaver', '/ScreenSaver',
                           'org.freedesktop.ScreenSaver', 'Inhibit',
                           GLib.Variant('(ss)', ('desktop-smoke', 'boot test opening apps')),
                           '(u)')[0]
        log(f'screen lock and power saving held off (cookie {cookie})')
    except GLib.Error as exc:
        log(f'could not hold off the screen lock: {exc}')
    kwin.wake()
    try:
        locked = kwin.call('org.freedesktop.ScreenSaver', '/ScreenSaver',
                           'org.freedesktop.ScreenSaver', 'GetActive', None, '(b)')[0]
    except GLib.Error:
        locked = None
    if locked:
        log('FAIL: the session is locked, so the apps would open behind the lock screen')
        return 2
    first = kwin.script()
    log(f"KWin: screen {first['screen']['w']}x{first['screen']['h']}, "
        f"{len(first['windows'])} window(s) before the test")
    width, height, _ = kwin.screenshot(os.path.join(args.out, '00-desktop.png'))
    log(f'ScreenShot2: {width}x{height}')
    # Close what is already open (Spark Welcome opens itself at the first sign-in)
    already = [w for w in first['windows'] if w['normal'] or w['dialog']]
    for w in already:
        log(f'   already open: "{w["caption"]}" ({w["cls"]}, {w["desktop"]})')
    if already:
        kwin.script('close', [w['id'] for w in already])
        time.sleep(3)

    apps, missing = find_apps([e for e in args.expect.split(',') if e])
    log(f'{len(apps)} apps in the menu: ' + ', '.join(a['name'] for a in apps))
    chosen, notes = pick_launcher(session_env, kwin.folder)
    for note in notes:
        log(f'launcher check: {note}')
    if not chosen:
        log('FAIL: no launcher passed the check')
        return 2
    log(f'Starting apps with {chosen[0]}')

    results = [{'pass': '-', 'id': m, 'name': m, 'ok': False, 'title': '', 'seconds': None,
                'reason': 'no desktop entry in /usr/share/applications', 'notes': []}
               for m in missing]
    for lang in [p for p in args.passes.split(',') if p]:
        group = apps if lang == 'en' else [a for a in apps if a['spark']]
        log(f'== pass "{lang}": {len(group)} apps')
        for number, app in enumerate(group, 1):
            log(f'-- {app["name"]} ({app["id"]}: Exec={app["exec"]})')
            kwin.wake()
            try:
                result = run_app(kwin, app, chosen, session_env, lang, args.out, number, True)
            except Exception as exc:                # noqa: BLE001 - one app must not stop the rest
                result = {'pass': lang, 'id': app['id'], 'name': app['name'], 'ok': False,
                          'title': '', 'seconds': None, 'notes': [],
                          'reason': f'the test itself failed: {type(exc).__name__}: {exc}'}
            if not result['ok'] and not app['spark'] and 'no window' in result['reason']:
                try:
                    result['diagnosis'] = diagnose(kwin, app, session_env, args.out, number)
                except Exception as exc:            # noqa: BLE001 - only extra information
                    result['diagnosis'] = [f'the extra tries failed: {exc}']
                for line in result['diagnosis']:
                    result['notes'].append(f'tried directly, {line}')
            status = 'OK' if result['ok'] else 'FAIL'
            log(f'   {status} "{result["title"]}" {result["seconds"]} s'
                f' {result.get("match", "")} {result.get("lang_seen") or ""}'
                f' close: {result.get("close", "")}'
                + (f' -- {result["reason"]}' if result['reason'] else '')
                + ''.join(f'\n   note: {n}' for n in result['notes']))
            for tb in result.get('tracebacks', []):
                log('   ' + tb.replace('\n', '\n   '))
            results.append(result)
    with open(os.path.join(args.out, 'results.json'), 'w') as f:
        json.dump({'launcher': chosen[0], 'launcher_check': notes, 'results': results}, f,
                  indent=1)
    failed = [r for r in results if not r['ok']]
    log(f'{len(results) - len(failed)} of {len(results)} OK')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
