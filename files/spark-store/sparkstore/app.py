"""The window: header with search, the pages, the queue bar at the bottom, and the work that
happens behind it (loading the catalog, asking flatpak what is installed, checking for
updates). Background work runs in threads and reports back through one inbox; the window
reads it only while something is running, so it uses no CPU when idle."""

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, CATALOG_MAX_AGE_H, VERSION
from . import flatpak, sparkapps
from .appstream import App, find_sources, installation_dirs
from .catalog import Catalog
from .core import load_json, log, reduced_motion, save_json
from .jobs import DONE, FAILED, RUNNING, WAITING, Job, JobQueue
from .text import t
from .ui import Icons, Progress, SearchBox, TabBar, style
from .widgets import MONO_FAMILIES, T, Glitch, GlitchText, Mark, Strip, WolkButton
from . import core

TABS = ('home', 'installed', 'updates', 'queue')
UPDATE_CHECK_EVERY = 6 * 3600        # seconds between automatic update checks


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_STORE_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    if os.name != 'nt' and shutil.which('xrdb'):
        try:
            out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True,
                                 timeout=3).stdout
            match = re.search(r'^Xft\.dpi:\s*([0-9.]+)', out, re.M)
            if match:
                return max(1.0, min(4.0, float(match.group(1)) / 96))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    try:
        return max(1.0, min(4.0, root.winfo_fpixels('1i') / 96))
    except tk.TclError:
        return 1.0


def pick_mono_cached(root: tk.Tk) -> str:
    """The mono font, remembered between runs: listing every font family takes a moment on
    a PC with many fonts, and the window should open at once."""
    path = os.path.join(core.cache_dir(), 'font')
    try:
        with open(path, encoding='utf-8') as f:
            name = f.read().strip()
        if name and tkfont.Font(root, family=name).actual('family') == name:
            return name
    except OSError:
        pass
    families = {n.lower(): n for n in tkfont.families(root)}
    name = next((families[w.lower()] for w in MONO_FAMILIES if w.lower() in families),
                "TkFixedFont")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(name)
    except OSError:
        pass
    return name


def load_icon(root: tk.Misc) -> Optional[tk.PhotoImage]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (os.path.join(here, 'icons', f'{APP_SLUG}-64.png'),
                 os.path.join(here, 'icons', f'{APP_SLUG}-256.png')):
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                pass
    return None


class Store:
    def __init__(self, target: Optional[str] = None, page: Optional[str] = None,
                 offline: bool = False):
        self.t0 = time.monotonic()
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono_cached(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.settings = load_json('config.json')
        self.offline = offline or os.environ.get('SPARK_STORE_OFFLINE') == '1'
        self.glitch = Glitch(self.root, enabled=not reduced_motion()
                             and self.settings.get("glitch", True) is not False)
        style(self.root)
        self.icons = Icons(self.root)
        self.headings: List[Any] = []

        # state
        self.flatpak_ok = flatpak.available()
        self.catalog = Catalog([])            # empty until the real one loads
        self.catalog_busy = True
        self.spark: List[sparkapps.SparkApp] = []
        self.spark_by_id: Dict[str, sparkapps.SparkApp] = {}
        self.spark_stamp = 0
        self.installed: Dict[str, flatpak.Installed] = {}
        self.runtimes: Dict[str, str] = {}      # installed runtimes and add-ons -> scope
        self.installed_loaded = False
        self.installed_stamp = 0
        self.updates: List[flatpak.Update] = []
        self.runtime_updates = 0
        self.updates_checked = 0.0
        self.updates_error = ''
        self.updates_busy = False
        self.updates_stamp = 0
        self.queue = JobQueue()
        self.dismissed: set = set()
        self.handled: set = set()       # finished jobs already reported
        self.hidden_until_idle = False
        self.pending_target: Optional[str] = target
        self.inbox: 'queue.Queue[Tuple[Callable, Any]]' = queue.Queue()
        self.bg_count = 0
        self._poll_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self.first_paint: Optional[float] = None
        self.catalog_ready_at: Optional[float] = None
        self.history: List[Tuple[str, Any]] = []
        self.page: Optional[str] = None
        self.page_arg: Any = None
        self.closed = False

        self.load_spark()
        self._build()
        from .pages import HomePage, SearchPage
        from .appview import AppPage
        from .lists import InstalledPage, QueuePage, UpdatesPage
        self.pages = {'home': HomePage(self), 'search': SearchPage(self), 'app': AppPage(self),
                      'installed': InstalledPage(self), 'updates': UpdatesPage(self),
                      'queue': QueuePage(self)}
        first = page if page in TABS else 'home'
        self.go(first, push=False, glitch=False)
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        from .instance import Listener
        self.listener = Listener(self.root, self.handle_target)

        # behind the window
        self.bg(self._load_catalog, self._catalog_loaded)
        if self.flatpak_ok:
            self.refresh_installed()
        else:
            self.installed_loaded = True
        self._status_idle()

    # — look helpers —
    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size: int, bold: bool = True) -> tkfont.Font:
        """A named font shared by every widget that uses it: Tk then makes each font once,
        not once per label (that alone halves the time to build a page)."""
        return self.tkfont(size, bold)

    def tkfont(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status(t('status.wrong'), T["pink"])
        self.glitch.now(self.title, strong=True)

    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(820), px(540))
        icon = load_icon(root)
        if icon is not None:
            root.iconphoto(True, icon)
            self._icon = icon

        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        self.mark.bind("<ButtonRelease-1>", lambda _e: self.go('home'))
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK STORE", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7),
                               anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.search = SearchBox(head, t('search.placeholder'), self.font(10, False), px, 34,
                                self._search_changed, self._search_enter)
        self.search.pack(side="right", padx=(0, px(12)))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.tabs = TabBar(root, [(k, t(f'tab.{k}')) for k in TABS], self.go, self.font(9), px)
        self.tabs.pack(fill="x", padx=px(10), pady=(px(6), 0))
        tk.Frame(root, bg=T["line"], height=1).pack(fill="x")

        # the queue bar, shown while there is work or a failure to see
        self.qbar = tk.Frame(root, bg=T["panel"], highlightthickness=1,
                             highlightbackground=T["line"])
        self.qbar_text = tk.Label(self.qbar, text="", font=self.font(8), bg=T["panel"],
                                  fg=T["accent"], anchor="w")
        self.qbar_text.pack(side="left", padx=(px(12), px(10)), pady=px(7))
        WolkButton(self.qbar, t('qbar.view'), lambda: self.go('queue'), self.font(8),
                   padx=10, pady=3).pack(side="right", padx=px(8), pady=px(4))
        self.qbar_progress = Progress(self.qbar, height=px(5), width=px(200))
        self.qbar_progress.pack(side="right", padx=px(8))
        self.qbar_shown = False

        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)

        root.bind("<KeyPress>", self._key)
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w, h = min(px(1120), int(sw * 0.85)), min(px(760), int(sh * 0.85))
            root.geometry(f"{w}x{h}")
        root.bind('<Expose>', self._exposed, add='+')

    def _exposed(self, event):
        if self.first_paint is None and event.widget is self.root:
            self.first_paint = time.monotonic()

    # — background work —
    def bg(self, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        """Run work() in a thread; done(result) runs in the window's thread afterwards."""
        self.bg_count += 1

        def run():
            try:
                result = work()
            except Exception as exc:      # noqa: BLE001 - reported, never fatal
                log.exception("background work failed")
                result = exc
            self.inbox.put((done, result))

        threading.Thread(target=run, daemon=True).start()
        self.ensure_poll()

    def ensure_poll(self):
        if self._poll_id is None and not self.closed:
            self._poll_id = self.root.after(50, self._poll)

    def _poll(self):
        self._poll_id = None
        if self.closed:
            return
        while True:
            try:
                done, result = self.inbox.get_nowait()
            except queue.Empty:
                break
            self.bg_count -= 1
            if isinstance(result, Exception):
                self.set_status(t('status.wrong'), T["pink"])
                continue
            try:
                done(result)
            except tk.TclError:
                pass
        changed = self.queue.drain()
        if changed:
            self._jobs_changed(changed)
        if self.hidden_until_idle and not self.queue.busy():
            self.close()
            return
        if self.bg_count > 0 or self.queue.busy():
            self._poll_id = self.root.after(120 if self.queue.busy() else 60, self._poll)

    # — catalog —
    def _load_catalog(self) -> Catalog:
        return Catalog().load()

    def _catalog_loaded(self, catalog: Catalog):
        self.catalog = catalog
        self.catalog_busy = False
        self.catalog_ready_at = time.monotonic()
        self._status_idle()
        self.redraw()
        if self.pending_target:
            target, self.pending_target = self.pending_target, None
            self.handle_target(target)
        self.maybe_refresh_catalog()

    def maybe_refresh_catalog(self):
        """Ask flatpak for a newer catalog when ours is more than a day old. Only through the
        user's own Flathub remote; nothing is added without asking."""
        if self.offline or not self.flatpak_ok or self.settings.get('auto_refresh') is False:
            return
        src = self.catalog.source
        if src is not None and time.time() - src.mtime < CATALOG_MAX_AGE_H * 3600:
            return

        def work():
            if flatpak.REMOTE not in flatpak.remotes().get('user', []):
                return None
            code, _out, err = flatpak.run(flatpak.cmd_refresh_catalog('user'), timeout=300)
            return code, err

        def done(result):
            if result is None:
                return
            code, err = result
            if code != 0:
                log.info("catalog refresh failed: %s", err.strip())
                return
            self.reload_catalog_if_changed()

        self.bg(work, done)

    def reload_catalog_if_changed(self):
        sources = find_sources()
        old = self.catalog.source
        new = sources[0] if sources else None
        if new is None or (old is not None and new.path == old.path and
                           int(new.mtime) == int(old.mtime) and new.size == old.size):
            return
        self.catalog_busy = True
        self.set_status(t('status.reading_catalog'), T["accent"], hold_ms=60000)
        self.bg(lambda: Catalog(sources).load(), self._catalog_loaded)

    def refresh_catalog(self):
        """The person asked for the catalog (Home, when it's missing)."""
        job = Job('catalog', 'catalog', t('catalog.job_title'),
                  steps=[flatpak.cmd_refresh_catalog('user')], needs_flathub=True)
        self.queue.add(job)
        self.ensure_poll()
        self._update_queue_ui()

    # — installed apps and updates —
    def refresh_installed(self):
        def work():
            return flatpak.installed(), flatpak.installed_runtimes()

        def done(result):
            apps, self.runtimes = result
            first = not self.installed_loaded
            self.installed = apps
            self.installed_loaded = True
            self.installed_stamp += 1
            if first:
                self.restore_updates()
            self.updates = [u for u in self.updates if u.id in apps]
            self.redraw()
        self.bg(work, done)

    def restore_updates(self):
        """The last check's answer, if it is recent; else check now (it asks Flathub)."""
        try:
            last = float(self.settings.get('updates_checked') or 0)
            saved = [flatpak.Update(*map(str, row[:4])) for row in
                     self.settings.get('updates') or [] if isinstance(row, list) and len(row) >= 4]
        except (TypeError, ValueError):
            last, saved = 0.0, []
        if 0 < time.time() - last < UPDATE_CHECK_EVERY:
            self.updates, self.updates_checked = saved, last
            self.updates_stamp += 1
        elif not self.offline:
            self.root.after(1500, self.check_updates)

    def check_updates(self):
        if self.updates_busy or not self.flatpak_ok or self.closed:
            return
        self.updates_busy = True
        self.updates_stamp += 1
        self.redraw()

        def done(result):
            apps, runtimes, error = result
            self.updates_busy = False
            self.updates, self.runtime_updates, self.updates_error = apps, runtimes, error
            self.updates_checked = time.time()
            self.updates_stamp += 1
            self.settings['updates_checked'] = self.updates_checked
            self.settings['updates'] = [[u.id, u.scope, u.version, u.branch] for u in apps]
            self.redraw()

        self.bg(flatpak.updates, done)

    # — Spark apps —
    def load_spark(self):
        self.spark = sparkapps.discover()
        self.spark_by_id = {s.id: s for s in self.spark}
        self.spark_stamp += 1

    # — pages —
    def go(self, page: str, arg: Any = None, push: bool = True, glitch: bool = True):
        if page == 'app':
            if not self.pages['app'].show(arg):
                return
        if push and self.page is not None and (self.page, self.page_arg) != (page, arg):
            self.history.append((self.page, self.page_arg))
            del self.history[:-30]
        if page == 'search' and arg and self.search.get() != arg:
            self.search.set(arg, fire=False)
        elif page not in ('search', 'app') and self.search.get():
            self.search.set('', fire=False)
        old = self.pages.get(self.page) if self.page else None
        if old is not None and self.page != page:
            old.frame.pack_forget()
        self.page, self.page_arg = page, arg
        self.headings = [h for h in self.headings if h.winfo_exists()]
        view = self.pages[page]
        if page == 'search':
            view.show(arg or '')
        elif page != 'app':
            view.refresh()
        view.frame.pack(fill="both", expand=True)
        self.tabs.select(page if page in TABS else None)
        self.settings['page'] = page if page in TABS else self.settings.get('page')
        if glitch:
            self.glitch.now(self.title, *self.headings[:2])

    def go_back(self):
        while self.history:
            page, arg = self.history.pop()
            if page == 'app' and not self.pages['app'].subject_for(arg):
                continue
            self.go(page, arg, push=False)
            return
        self.go('home', push=False)

    def open_app(self, target):
        self.go('app', target)

    def redraw(self):
        """Something changed (catalog, installed, updates): update what is on screen."""
        if self.closed:
            return
        view = self.pages.get(self.page)
        if self.page == 'app':
            view.refresh()
        elif self.page == 'search':
            view.show(view.query or '', force=True)
        elif view is not None:
            view.refresh()
        self.tabs.set_count('updates', len(self.updates))
        self._update_queue_ui()

    def _search_changed(self, text: str):
        if text.strip():
            if self.page == 'search':
                self.pages['search'].show(text)
                self.page_arg = text
            else:
                self.go('search', text)
        elif self.page == 'search':
            self.go_back()

    def _search_enter(self):
        if self.page == 'search':
            first = self.pages['search'].first()
            if first is not None:
                self.open_app(first)

    # — links from outside: .flatpakref, .flatpakrepo, appstream://, an app ID —
    def handle_target(self, target: str):
        self.bring_to_front()
        if not target:
            return
        if flatpak.is_flatpakrepo(target):
            repo = flatpak.read_flatpakrepo(flatpak.local_path(target))
            if repo is None:
                self.set_status(t('link.bad_repo'), T["pink"], hold_ms=8000)
                self.glitch.now(self.title, strong=True)
                return
            self.open_app(repo)
            return
        if flatpak.is_flatpakref(target):
            ref = flatpak.read_flatpakref(flatpak.local_path(target))
            if ref is None:
                self.set_status(t('link.bad_ref'), T["pink"], hold_ms=8000)
                self.glitch.now(self.title, strong=True)
                return
            if self.catalog_busy and ref.from_flathub:
                self.pending_target = target
                return
            self.open_app(ref)
            return
        app_id = flatpak.app_id_from_link(target)
        if not app_id:
            self.set_status(t('link.bad', link=target[:60]), T["pink"], hold_ms=8000)
            self.glitch.now(self.title, strong=True)
            return
        if self.catalog_busy:
            self.pending_target = target
            return
        if self.pages['app'].subject_for(app_id) is not None:
            self.open_app(app_id)
        else:
            self.set_status(t('link.not_found', id=app_id), T["gold"], hold_ms=8000)
            self.go('search', app_id.rsplit('.', 1)[-1])
            self.search.set(app_id.rsplit('.', 1)[-1], fire=False)

    def bring_to_front(self):
        self.hidden_until_idle = False
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    # — actions —
    def install(self, subject):
        if subject.kind == 'spark':
            cmd = sparkapps.install_command(subject.spark)
            if not cmd:
                return
            job = Job('spark_install', subject.id, subject.name, steps=[cmd], flatpak=False)
        elif subject.kind == 'ref' and subject.ref is not None and \
                not (subject.ref.from_flathub and subject.id in self.catalog.apps):
            job = Job('install_ref', subject.id, subject.name,
                      steps=[flatpak.cmd_install_ref(subject.ref.path)])
        else:
            job = Job('install', subject.id, subject.name,
                      steps=[flatpak.cmd_install(subject.id, subject.branch or 'stable')],
                      needs_flathub=True)
        self._enqueue(job)

    def remove(self, subject, scope: str, delete_data: bool = False):
        if subject.kind == 'spark':
            sp = subject.spark
            cmd = sparkapps.uninstall_command(sp)
            if cmd:
                job = Job('spark_remove', sp.id, sp.name, steps=[cmd], flatpak=False)
            else:
                job = Job('spark_remove', sp.id, sp.name, flatpak=False,
                          func=lambda: sparkapps.remove_with_manifest(sp))
        else:
            job = Job('remove', subject.id, subject.name,
                      steps=[flatpak.cmd_remove(subject.id, scope, delete_data)], scope=scope)
        self._enqueue(job)

    def update(self, app_id: str, scope: str):
        self._enqueue(Job('update', app_id, self.name_of(app_id),
                          steps=[flatpak.cmd_update(app_id, scope)], scope=scope))

    def add_remote(self, subject):
        self._enqueue(Job('remote_add', subject.id, subject.name,
                          steps=[flatpak.cmd_add_remote(subject.id, subject.repo.path)]))

    def install_addon(self, addon):
        self._enqueue(Job('addon_install', addon.id, addon.name,
                          steps=[flatpak.cmd_install_addon(addon.id, addon.branch)],
                          needs_flathub=True))

    def remove_addon(self, addon):
        scope = self.runtimes.get(addon.id, 'user')
        self._enqueue(Job('addon_remove', addon.id, addon.name, scope=scope,
                          steps=[flatpak.cmd_remove_addon(addon.id, scope, addon.branch)]))

    def update_all(self):
        scopes = ['user'] + (['system'] if any(u.scope == 'system' for u in self.updates) else [])
        for scope in scopes:
            self._enqueue(Job('update_all', f'all-{scope}',
                              t('updates.everything_user') if scope == 'user' else
                              t('updates.everything_system'),
                              steps=[flatpak.cmd_update(None, scope)], scope=scope))

    def _enqueue(self, job: Job):
        self.queue.add(job)
        self.glitch.now(self.title)
        self.ensure_poll()
        self._jobs_changed([job])

    def retry(self, job: Job):
        self.queue.retry(job)
        self.ensure_poll()
        self._jobs_changed([job])

    def dismiss(self, job: Job):
        self.dismissed.add(job.id)
        with self.queue._lock:
            if job in self.queue.jobs and job.finished:
                self.queue.jobs.remove(job)
        self._jobs_changed([job])

    def clear_finished(self):
        self.queue.clear_finished()
        self._jobs_changed([])

    def queue_position(self, job: Job) -> int:
        """How many jobs are ahead of this waiting one."""
        ahead = 0
        for other in self.queue.jobs:
            if other is job:
                return ahead
            if other.state in (RUNNING, WAITING):
                ahead += 1
        return ahead

    def launch(self, subject):
        if subject.kind == 'spark':
            self.launch_spark(subject.spark)
        else:
            self.launch_id(subject.id)

    def launch_spark(self, sp: sparkapps.SparkApp):
        if sparkapps.launch(sp):
            self.set_status(t('status.opening', name=sp.name), T["accent"])
        else:
            self.set_status(t('status.open_failed', name=sp.name), T["pink"])

    def launch_id(self, app_id: str):
        name = self.name_of(app_id)
        if flatpak.launch(app_id):
            self.set_status(t('status.opening', name=name), T["accent"])
        else:
            self.set_status(t('status.open_failed', name=name), T["pink"])

    def _jobs_changed(self, jobs: List[Job]):
        refresh_installed = False
        for job in jobs:
            if not job.finished or job.id in self.handled:
                continue
            self.handled.add(job.id)         # report each finished job once
            name = job.title
            if job.state == DONE:
                self.set_status(t(f'done.{job.kind}', name=name), T["accent"], hold_ms=6000)
                self.glitch.now(self.title)
            elif job.state == FAILED:
                self.set_status(t(f'failed.{job.kind}', name=name), T["pink"], hold_ms=10000)
                self.glitch.now(self.title, self.strip, strong=True)
            if job.kind in ('install', 'install_ref', 'remove', 'update', 'update_all',
                            'addon_install', 'addon_remove'):
                refresh_installed = True
                if job.state == DONE and job.kind == 'update':
                    self.updates = [u for u in self.updates
                                    if not (u.id == job.app_id and u.scope == job.scope)]
                    self.updates_stamp += 1
                if job.state == DONE and job.kind == 'update_all':
                    self.updates = [u for u in self.updates if u.scope != job.scope]
                    self.runtime_updates = 0
                    self.updates_stamp += 1
            elif job.kind in ('spark_install', 'spark_remove'):
                self.load_spark()
            elif job.kind == 'catalog' and job.state == DONE:
                self.reload_catalog_if_changed()
            elif job.kind == 'remote_add' and self.page == 'app':
                self.pages['app'].check_repo()
        if refresh_installed and self.flatpak_ok:
            self.refresh_installed()
        view = self.pages.get(self.page)
        if self.page == 'app':
            view.update_actions()
            if any(j.finished for j in jobs):
                view.refresh()
        elif self.page == 'queue':
            view.refresh()
        elif self.page in ('installed', 'updates', 'home') and any(
                j.finished or j.state == RUNNING for j in jobs):
            view.refresh()
        self._update_queue_ui()

    def _update_queue_ui(self):
        active = self.queue.active()
        failed = [j for j in self.queue.jobs if j.state == FAILED]
        self.tabs.set_count('queue', len(active) + len(failed))
        if not active and not failed:
            if self.qbar_shown:
                self.qbar.pack_forget()
                self.qbar_progress.stop()
                self.qbar_shown = False
            return
        current = self.queue.current()
        if current is not None:
            pct = f" {round(current.progress * 100)}%" if current.progress is not None else ""
            text = "● " + t('doing_name.' + current.kind, name=current.title).upper() + pct
            waiting = len(active) - 1
            if waiting > 0:
                text += "  ·  " + t('qbar.waiting', n=waiting)
            colour = T["accent"]
            self.qbar_progress.set(current.progress)
        elif active:
            text, colour = f"● {t('qbar.starting')}", T["accent"]
            self.qbar_progress.set(0.0)
        else:
            text = "● " + t('qbar.failed', n=len(failed))
            colour = T["pink"]
            self.qbar_progress.set(0.0)
        self.qbar_text.config(text=text, fg=colour)
        if not self.qbar_shown:
            self.qbar.pack(side="bottom", fill="x", before=self.body)
            self.qbar_shown = True

    # — little helpers for the pages —
    def name_of(self, app_id: str) -> str:
        app = self.catalog.apps.get(app_id)
        if app is not None:
            return app.name
        inst = self.installed.get(app_id)
        if inst is not None:
            return inst.name
        return app_id.rsplit('.', 1)[-1]

    def installed_icon(self, app_id: str) -> Optional[str]:
        app = self.catalog.apps.get(app_id)
        if app is not None:
            path = self.catalog.icon_path(app, self.px(64))
            if path:
                return path
        bases = [os.path.join(base, 'exports', 'share', 'icons', 'hicolor')
                 for _scope, base in installation_dirs()]
        for size in (64, 128, 48, 256):
            for base in bases:
                path = os.path.join(base, f'{size}x{size}', 'apps', f'{app_id}.png')
                if os.path.isfile(path):
                    return path
        return None

    def icon_for_id(self, app_id: str) -> Optional[str]:
        sp = self.spark_by_id.get(app_id)
        if sp is not None:
            return sparkapps.icon_path(sp)
        return self.installed_icon(app_id)

    def chips_for(self, app: App) -> List[Tuple[str, str, bool]]:
        chips = []
        job = self.queue.for_app(app.id)
        if job is not None and job.state in (RUNNING, WAITING):
            chips.append((t(f'doing.{job.kind}') + "…", T["gold"], False))
        if app.kind == 'spark':
            sp = self.spark_by_id.get(app.id)
            if sp is not None and sp.installed == 'system':
                chips.append((t('chip.in_sparkos'), T["accent"], False))
            elif sp is not None and sp.installed == 'user':
                chips.append((t('chip.installed'), T["accent"], True))
            else:
                chips.append((t('chip.optional'), T["muted"], False))
            return chips
        if app.id in self.installed:
            chips.append((t('chip.installed'), T["accent"], True))
        if app.verified:
            chips.append((t('chip.verified'), T["accent"], False))
        if app.proprietary:
            chips.append((t('chip.proprietary'), T["gold"], False))
        return chips

    # — status line —
    def _status_idle(self):
        self._status_id = None
        if self.catalog_busy:
            text, colour = t('status.reading_catalog'), T["accent"]
        elif not self.flatpak_ok:
            text, colour = t('status.no_flatpak'), T["gold"]
        elif self.catalog.apps:
            text, colour = t('status.ready', n=len(self.catalog.apps)), T["accent"]
        else:
            text, colour = t('status.no_catalog'), T["gold"]
        self.status.config(text=f"● {text}", fg=colour)

    def set_status(self, text: str, colour: str = T["accent"], hold_ms: int = 4000):
        if self.closed:
            return
        self.status.config(text=f"● {text.upper()}", fg=colour)
        if self._status_id:
            self.root.after_cancel(self._status_id)
        self._status_id = self.root.after(hold_ms, self._status_idle)

    # — keys —
    def _key(self, event):
        k = event.keysym
        ctrl = bool(event.state & 0x4)
        alt = bool(event.state & 0x8) or bool(event.state & 0x80)
        if ctrl and k in ('f', 'F', 'l', 'L', 'k', 'K'):
            self.search.entry.focus_set()
            self.search.entry.select_range(0, 'end')
            return "break"
        if ctrl and k in ('1', '2', '3', '4'):
            self.go(TABS[int(k) - 1])
            return "break"
        if ctrl and k in ('w', 'W', 'q', 'Q'):
            self.close()
            return "break"
        if (alt and k == 'Left') or (k == 'BackSpace' and event.widget is not self.search.entry):
            if self.page in ('app', 'search'):
                self.go_back()
                return "break"
        if k == 'Escape':
            if self.search.get():
                self.search.set('')
                return "break"
            if self.page == 'app':
                self.go_back()
                return "break"
        if k == 'F5':
            self.refresh_installed()
            if self.page == 'updates':
                self.check_updates()
            return "break"
        return None

    def close(self):
        """Closing the window while apps are installing hides it; the queue finishes, then
        the Store quits. Opening the Store again brings the window back."""
        if self.closed:
            return
        if self.queue.busy():
            if self.root.state() == 'normal':
                self.settings["geometry"] = self.root.geometry()
            self.hidden_until_idle = True
            self.root.withdraw()
            log.info("window closed while %d jobs run: hidden until they finish",
                     len(self.queue.active()))
            self.ensure_poll()
            return
        for job in (self._poll_id, self._status_id, self.glitch._loop):
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self.closed = True
        self._poll_id = self._status_id = self.glitch._loop = None
        try:                                # glitch frames and other short timers still queued
            # Tcl's own cancel: after_cancel() would also delete the callback's command, which
            # the widget that set the timer deletes again when it is destroyed
            for job in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.tk.call('after', 'cancel', job)
        except tk.TclError:
            pass
        if self.root.state() == 'normal' and not self.hidden_until_idle:
            self.settings["geometry"] = self.root.geometry()
        self.settings["version"] = VERSION
        if self.updates_checked:            # what is left after this session's updates
            self.settings['updates'] = [[u.id, u.scope, u.version, u.branch]
                                        for u in self.updates]
        save_json('config.json', self.settings)
        self.listener.close()
        log.info("--- shutting down ---")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Measuring ────────────────────────────────────────────────

def bench(seconds: float) -> int:
    """Open the window, report the time to first paint and until the catalog is on screen,
    then the CPU used while idle for `seconds`."""
    import faulthandler
    from .cli import T0, process_age
    # if anything hangs, say where (every thread's stack) instead of waiting forever
    faulthandler.dump_traceback_later(seconds + 60, exit=True)
    print(f"{APP_NAME} {VERSION} bench: opening", file=sys.stderr, flush=True)
    store = Store(offline=True)
    print("bench: window built", file=sys.stderr, flush=True)
    deadline = time.monotonic() + 30
    while (store.first_paint is None or store.catalog_ready_at is None) and \
            time.monotonic() < deadline:
        store.root.update()
        time.sleep(0.005)
    age = process_age()
    now = time.monotonic()
    results: Dict[str, float] = {}

    def start():
        results['t'] = time.monotonic()
        results['cpu'] = sum(os.times()[:2])
        store.root.after(int(seconds * 1000), stop)

    def stop():
        results['wall'] = time.monotonic() - results['t']
        results['used'] = sum(os.times()[:2]) - results['cpu']
        store.close()

    print("bench: catalog on screen, measuring", file=sys.stderr, flush=True)
    store.root.after(2000, start)
    store.run()
    print("bench: window closed", file=sys.stderr, flush=True)
    cat = store.catalog
    print(f"{APP_NAME} {VERSION} bench")
    if store.first_paint is not None:
        if age is not None:
            print(f"first paint:  {age - (now - store.first_paint):.2f} s after the process "
                  "started")
        print(f"first paint:  {store.first_paint - T0:.2f} s after the app's code was loaded")
    if store.catalog_ready_at is not None:
        print(f"catalog:      {len(cat.apps)} apps on screen {store.catalog_ready_at - T0:.2f} s "
              f"after the code was loaded (index {'rebuilt' if cat.rebuilt else 'cached'}, "
              f"{cat.load_seconds:.2f} s)")
    if 'wall' in results:
        print(f"idle cpu:     {100 * results['used'] / results['wall']:.2f}% of one core over "
              f"{results['wall']:.0f} s")
    faulthandler.cancel_dump_traceback_later()
    return 0

