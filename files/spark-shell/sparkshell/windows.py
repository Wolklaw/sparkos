"""The task list's data: which windows exist, which is active, and acting on them.

Why a KWin script: KWin only hands org_kde_plasma_window_management to plasmashell (it checks
the client's desktop file), and it has no wlr-foreign-toplevel. What every client can use is
KWin's scripting D-Bus API. A small script, loaded through org.kde.KWin /Scripting, watches the
windows and calls dev.wolklaw.SparkShell /Shell Windows(json) on every change. Actions (raise,
minimise, close) go back the same way: a one-line script per action, loaded and run once.

The same script registers the volume, mute and brightness keys (KWin hosts kglobalacceld), so
they work with no plasmashell and no powerdevil."""

import json
import logging
import os

from gi.repository import Gio, GLib

from .dbusutil import call

log = logging.getLogger('spark-shell')

KWIN = 'org.kde.KWin'
SCRIPT_NAME = 'spark-shell-windows'
SHELL_NAME = 'dev.wolklaw.SparkShell'

TRACKER_JS = r"""
// Spark shell window tracker (loaded by spark-shell through org.kde.KWin /Scripting).
var SHELL = "dev.wolklaw.SparkShell";

function describe(w) {
    return {
        id: String(w.internalId),
        title: String(w.caption || ""),
        app: String(w.desktopFileName || ""),
        cls: String(w.resourceClass || ""),
        pid: w.pid | 0,
        minimized: !!w.minimized,
        attention: !!w.demandsAttention,
        output: (w.output && w.output.name) ? String(w.output.name) : "",
        active: workspace.activeWindow === w
    };
}

function listed(w) {
    return w && w.normalWindow && !w.skipTaskbar && !w.deleted;
}

function push() {
    var out = [];
    var all = workspace.windowList();
    for (var i = 0; i < all.length; i++) {
        if (listed(all[i])) { out.push(describe(all[i])); }
    }
    callDBus(SHELL, "/Shell", "dev.wolklaw.SparkShell", "Windows", JSON.stringify(out));
}

function watch(w) {
    if (!w || w.sparkWatched) { return; }
    w.sparkWatched = true;
    var again = function () { push(); };
    if (w.captionChanged) { w.captionChanged.connect(again); }
    if (w.minimizedChanged) { w.minimizedChanged.connect(again); }
    if (w.desktopFileNameChanged) { w.desktopFileNameChanged.connect(again); }
    if (w.demandsAttentionChanged) { w.demandsAttentionChanged.connect(again); }
    if (w.skipTaskbarChanged) { w.skipTaskbarChanged.connect(again); }
    if (w.outputChanged) { w.outputChanged.connect(again); }
}

workspace.windowAdded.connect(function (w) { watch(w); push(); });
workspace.windowRemoved.connect(function (w) { push(); });
workspace.windowActivated.connect(function (w) { push(); });
var existing = workspace.windowList();
for (var i = 0; i < existing.length; i++) { watch(existing[i]); }
push();

function key(name) {
    return function () {
        callDBus(SHELL, "/Shell", "dev.wolklaw.SparkShell", "Key", name);
    };
}
registerShortcut("Spark: Volume up", "Spark shell", "Volume Up", key("volume-up"));
registerShortcut("Spark: Volume down", "Spark shell", "Volume Down", key("volume-down"));
registerShortcut("Spark: Mute", "Spark shell", "Volume Mute", key("mute"));
registerShortcut("Spark: Brightness up", "Spark shell", "Monitor Brightness Up",
                 key("brightness-up"));
registerShortcut("Spark: Brightness down", "Spark shell", "Monitor Brightness Down",
                 key("brightness-down"));
"""

# One-shot actions. %s is the window id (a UUID in braces; never anything else, see _safe_id).
ACTIONS_JS = {
    'activate': """
var all = workspace.windowList();
for (var i = 0; i < all.length; i++) {
    if (String(all[i].internalId) === "%s") {
        if (all[i].minimized) { all[i].minimized = false; }
        workspace.activeWindow = all[i];
    }
}""",
    'minimize': """
var all = workspace.windowList();
for (var i = 0; i < all.length; i++) {
    if (String(all[i].internalId) === "%s") { all[i].minimized = true; }
}""",
    'close': """
var all = workspace.windowList();
for (var i = 0; i < all.length; i++) {
    if (String(all[i].internalId) === "%s") { all[i].closeWindow(); }
}""",
}


def _safe_id(window_id: str) -> str:
    """Only what a QUuid looks like gets into a script."""
    cleaned = ''.join(c for c in str(window_id) if c in '0123456789abcdefABCDEF-{}')
    return cleaned


class WindowTracker:
    """Loads the tracker script into KWin and keeps `windows` current.
    on_changed(windows) is called after every update."""

    def __init__(self, conn, runtime_dir=None):
        self.conn = conn
        self.windows = []
        self.on_changed = lambda windows: None
        base = runtime_dir or os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
        self.dir = os.path.join(base, 'spark-shell')
        self._action_seq = 0
        self.loaded = False

    # script loading ----------------------------------------------------------------------
    def start(self):
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        path = os.path.join(self.dir, 'tracker.js')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(TRACKER_JS)
        # KWin may not be on the bus yet when the shell starts at login: wait for it
        Gio.bus_watch_name_on_connection(self.conn, KWIN, Gio.BusNameWatcherFlags.NONE,
                                         lambda c, n, owner: self._load(path), None)

    def _load(self, path):
        def unloaded(result, error):
            self._load_script(path, SCRIPT_NAME, True)
        # a leftover copy from a shell that crashed would make the load fail
        call(self.conn, KWIN, '/Scripting', 'org.kde.kwin.Scripting', 'unloadScript', 's',
             (SCRIPT_NAME,), unloaded, '(b)')

    def _load_script(self, path, name, track, then=None):
        def loaded(result, error):
            if error or not result or result[0] < 0:
                log.error('KWin would not load %s: %s', name, error or result)
                return
            self._run(result[0], name, track, then)
        call(self.conn, KWIN, '/Scripting', 'org.kde.kwin.Scripting', 'loadScript', 'ss',
             (path, name), loaded, '(i)')

    def _run(self, number, name, track, then):
        def ran(result, error):
            if error:
                # KWin 6 has used both paths over its releases
                if track and not getattr(self, '_retry', False):
                    self._retry = True
                    call(self.conn, KWIN, '/%d' % number, 'org.kde.kwin.Script', 'run', '', (),
                         ran)
                    return
                log.error('KWin would not run %s: %s', name, error.message)
                return
            if track:
                self.loaded = True
                log.info('window tracker running in KWin')
            if then:
                then()
        call(self.conn, KWIN, '/Scripting/Script%d' % number, 'org.kde.kwin.Script', 'run',
             '', (), ran)

    def stop(self):
        call(self.conn, KWIN, '/Scripting', 'org.kde.kwin.Scripting', 'unloadScript', 's',
             (SCRIPT_NAME,))

    # from the script ---------------------------------------------------------------------
    def update(self, payload: str):
        try:
            rows = json.loads(payload)
        except ValueError:
            return
        windows = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get('id'):
                windows.append({
                    'id': str(row['id']), 'title': str(row.get('title', '')),
                    'app': str(row.get('app', '')), 'cls': str(row.get('cls', '')),
                    'pid': int(row.get('pid') or 0), 'minimized': bool(row.get('minimized')),
                    'attention': bool(row.get('attention')), 'active': bool(row.get('active')),
                    'output': str(row.get('output', '')),
                })
        self.windows = windows
        self.on_changed(windows)

    # actions -----------------------------------------------------------------------------
    def act(self, action: str, window_id: str):
        template = ACTIONS_JS.get(action)
        wid = _safe_id(window_id)
        if not template or not wid:
            return
        self._action_seq += 1
        name = 'spark-shell-act-%d' % self._action_seq
        path = os.path.join(self.dir, name + '.js')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(template % wid)

        def finished():
            call(self.conn, KWIN, '/Scripting', 'org.kde.kwin.Scripting', 'unloadScript', 's',
                 (name,), lambda r, e: self._remove(path), '(b)')
        self._load_script(path, name, False, finished)

    @staticmethod
    def _remove(path):
        try:
            os.unlink(path)
        except OSError:
            pass

    def active_window(self):
        return next((w for w in self.windows if w['active']), None)


def match_app(window: dict, desktop_id: str, startup_class: str = '') -> bool:
    """Does this window belong to the app with this desktop file id ('x.desktop' or 'x')?"""
    want = desktop_id[:-8] if desktop_id.endswith('.desktop') else desktop_id
    want = want.lower()
    if not want:
        return False
    app = window.get('app', '').lower()
    cls = window.get('cls', '').lower()
    startup_class = startup_class.lower()
    return want in (app, cls) or (bool(startup_class) and startup_class in (app, cls))

