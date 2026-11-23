"""Screens for the stores: accounts and launchers, the sign-in paste box, and the install panel
on a game's page (size, progress, pause, resume, cancel, update, verify, uninstall)."""

import os
from typing import Any, Dict, Optional

import tkinter as tk
from . import dialogs as messagebox

from . import STORES, clients, jobs, launchers, registry, signin_window, stores
from .core import Game, open_uri, pick_folder
from .strings import tr
from .widgets import T, GlitchText, WolkButton


def human_size(n: int) -> str:
    value = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.0f} {unit}' if unit in ('B', 'KB') else f'{value:.1f} {unit}'
        value /= 1024
    return str(n)


def error_text(exc: Exception) -> str:
    if isinstance(exc, clients.ClientError):
        return tr('err_client_' + exc.kind, detail=stores.scrub(exc.detail))
    return tr('err_unexpected', detail=type(exc).__name__)


def clear(frame: tk.Misc) -> None:
    for child in frame.winfo_children():
        child.destroy()


def progress_bar(parent: tk.Misc, app, percent: float, paused: bool = False) -> tk.Canvas:
    width, height = app.px(360), app.px(8)
    bar = tk.Canvas(parent, width=width, height=height, bg=T["panel"], highlightthickness=1,
                    highlightbackground=T["line2"], bd=0)
    fill = int(width * max(0.0, min(100.0, percent)) / 100)
    colour = T["gold"] if paused else T["accent"]
    if fill:
        bar.create_rectangle(0, 0, fill, height, fill=colour, outline="")
        bar.create_rectangle(fill, 0, fill + app.px(2), height, fill=T["ch_a"], outline="")
    return bar


def job_line(job: Dict[str, Any]) -> str:
    """One plain line about a running job."""
    state, kind = job.get('state'), job.get('kind', 'install')
    if state == 'queued':
        return tr('job_queued')
    if job.get('message') in ('fetching_client', 'fetching_installer', 'installer_open'):
        text = tr('job_' + job['message'])
        if job['message'] == 'fetching_installer' or job['message'] == 'fetching_client':
            text += f" {job.get('percent', 0):.0f}%"
        return text
    parts = [tr('job_' + kind), f"{job.get('percent', 0):.0f}%"]
    if state == 'paused':
        parts.append(tr('job_paused'))
    else:
        if job.get('speed'):
            parts.append(job['speed'])
        if job.get('eta'):
            parts.append(tr('job_eta', eta=job['eta']))
    return '   '.join(parts)


class StorePanel(tk.Frame):
    """Install, update, verify and uninstall for one store game, or remove for a launcher."""

    def __init__(self, parent: tk.Misc, app, game: Game):
        super().__init__(parent, bg=T["bg"])
        self.app, self.game = app, game
        info = game.launch or {}
        self.store = info.get('store') or game.source
        self.is_launcher = bool(info.get('launcher'))
        self.root_dir = stores.games_root(self.store)
        self._tick_id: Optional[str] = None
        self._was_active = False
        self._last = None
        self.buttons = tk.Frame(self, bg=T["bg"])
        self.buttons.pack(anchor="w", fill="x")
        self.progress = tk.Frame(self, bg=T["bg"])
        self.progress.pack(anchor="w", fill="x", pady=(app.px(8), 0))
        self.refresh()

    def destroy(self):
        if self._tick_id:
            self.after_cancel(self._tick_id)
        super().destroy()

    # drawing
    def refresh(self):
        px, font = self.app.px, self.app.font
        job = jobs.job_for(self.game.key)
        active = bool(job and job.get('state') in jobs.ACTIVE)
        self._last = (job or {}).get('state'), (job or {}).get('percent')
        clear(self.buttons)
        clear(self.progress)
        if active:
            self._active_buttons(job)
            progress_bar(self.progress, self.app, job.get('percent', 0),
                         job.get('state') == 'paused').pack(anchor="w")
            tk.Label(self.progress, text=job_line(job), bg=T["bg"], fg=T["muted"],
                     font=font(8, False), anchor="w").pack(anchor="w", pady=(px(4), 0))
        else:
            self._idle_buttons()
            if job and job.get('state') in ('failed', 'cancelled'):
                text = tr('job_cancelled') if job['state'] == 'cancelled' else \
                    tr(job.get('message') or 'err_job_failed') + (
                        f" {job['detail']}" if job.get('detail') else '')
                tk.Label(self.progress, text=text, bg=T["bg"],
                         fg=T["pink"] if job['state'] == 'failed' else T["muted"],
                         font=font(8, False), justify="left", anchor="w",
                         wraplength=px(560)).pack(anchor="w")
        if active and not self._tick_id:
            self._tick_id = self.after(1000, self._tick)
        self._was_active = active

    def _button(self, text: str, command, variant: str = "ghost") -> WolkButton:
        b = WolkButton(self.buttons, text, command, self.app.font(8), variant=variant,
                       padx=self.app.px(10), pady=self.app.px(4))
        b.pack(side="left", padx=(0, self.app.px(8)))
        return b

    def _idle_buttons(self):
        game, px = self.game, self.app.px
        if self.is_launcher:
            self._button(tr('launcher_remove'), self.remove_launcher, "danger")
            return
        if not game.installed:
            where = tk.Frame(self.buttons, bg=T["bg"])
            where.pack(side="left")
            self._where = tk.Label(where, text=tr('install_to', path=self.root_dir), bg=T["bg"],
                                   fg=T["muted"], font=self.app.font(8, False), anchor="w")
            self._where.pack(side="left", padx=(0, px(8)))
            WolkButton(where, tr('install_change'), self.change_folder, self.app.font(8),
                       padx=px(8), pady=px(3)).pack(side="left", padx=(0, px(12)))
            WolkButton(where, tr('install'), lambda: self.start_job('install'),
                       self.app.font(10), variant="primary", padx=px(22),
                       pady=px(6)).pack(side="left")
            return
        if stores.update_available(game):
            self._button(tr('update'), lambda: self.start_job('update'), "primary")
        self._button(tr('verify'), lambda: self.start_job('verify'))
        self._button(tr('uninstall_btn'), self.uninstall, "danger")

    def _active_buttons(self, job: Dict[str, Any]):
        if job.get('state') == 'paused':
            self._button(tr('job_resume'), lambda: self._ctl(jobs.resume, job))
        else:
            self._button(tr('job_pause'), lambda: self._ctl(jobs.pause, job))
        self._button(tr('job_cancel'), lambda: self._ctl(jobs.cancel, job), "danger")

    def _ctl(self, fn, job):
        fn(job['id'])
        self.after(300, self.refresh)

    def _tick(self):
        self._tick_id = None
        job = jobs.job_for(self.game.key)
        active = bool(job and job.get('state') in jobs.ACTIVE)
        if active or self._was_active:
            if (job or {}).get('state') in ('done',):
                self._was_active = False
                self.app.rescan()          # the page rebuilds itself when the game changed
                return
            self.refresh()
            if active:
                return
            self.app.rescan()

    # actions
    def change_folder(self):
        chosen = pick_folder(self.root_dir)
        if chosen:
            self.root_dir = os.path.join(chosen, stores.FOLDER[self.store]) \
                if not os.path.basename(chosen) == stores.FOLDER[self.store] else chosen
            self._where.configure(text=tr('install_to', path=self.root_dir))

    def start_job(self, kind: str):
        game = self.game
        info = game.launch or {}
        app_id = str(info.get('app') or game.store_id)
        spec = {'kind': kind, 'store': self.store, 'app': app_id, 'key': game.key,
                'title': game.title, 'root': self.root_dir,
                'path': stores.target_dir(self.store, game.title, self.root_dir)
                if kind == 'install' else game.install_dir}
        if kind != 'install':
            self._spawn(spec)
            return
        self.app.set_status(tr('install_checking'), hold_ms=60000)

        def work():
            clients.ensure(clients.CLIENT_OF[self.store])
            return stores.install_info(self.store, app_id)

        def done(sizes):
            self.app._status_idle()
            if isinstance(sizes, Exception):
                messagebox.showerror(tr('install'), error_text(sizes), parent=self)
                return
            download, disk = sizes
            free = stores.free_space(spec['path'])
            if disk and free < disk:
                messagebox.showerror(tr('install'), tr('err_space_detail', need=human_size(disk),
                                                       free=human_size(free)), parent=self)
                return
            text = tr('install_confirm', title=game.title, path=spec['path'],
                      size=human_size(download) if download else tr('size_unknown'),
                      disk=human_size(disk) if disk else tr('size_unknown'),
                      free=human_size(free))
            if messagebox.askyesno(tr('install'), text, parent=self):
                self._spawn(spec)

        self.app.background(work, done)

    def _spawn(self, spec: Dict[str, Any]):
        jobs.spawn(spec)
        jobs.prune()
        self.refresh()

    def uninstall(self):
        rec = registry.load()['games'].get(self.game.key, {})
        text = tr('uninstall_forget' if rec.get('via') == 'heroic' else 'uninstall_confirm',
                  title=self.game.title, path=self.game.install_dir)
        if not messagebox.askyesno(tr('uninstall_btn'), text, parent=self):
            return
        self.app.set_status(tr('uninstalling'), hold_ms=60000)

        def done(result):
            self.app._status_idle()
            if isinstance(result, Exception) or result:
                messagebox.showerror(tr('uninstall_btn'), tr(result) if isinstance(result, str)
                                     else error_text(result), parent=self)
                return
            self.app.go_back()
            self.app.rescan()

        self.app.background(lambda: stores.uninstall(self.game.key), done)

    def remove_launcher(self):
        slug = self.store
        if messagebox.askyesno(tr('launcher_remove'), tr('launcher_remove_confirm',
                                                         name=self.game.title), parent=self):
            launchers.remove(slug)
            self.app.go_back()
            self.app.rescan()


class StoresView(tk.Frame):
    """Accounts (Epic, GOG, Amazon), Heroic takeover, and the launchers you can add."""

    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px, font = app.px, app.font
        col = tk.Frame(self, bg=T["bg"])
        col.pack(fill="both", expand=True, padx=px(28), pady=px(22))
        self.heading = GlitchText(col, tr('stores_title'), app.tkfont(16), T["bg"])
        self.heading.pack(anchor="w")
        tk.Label(col, text=tr('stores_note'), bg=T["bg"], fg=T["muted"], font=font(8, False),
                 justify="left", wraplength=px(680)).pack(anchor="w", pady=(px(6), 0))
        self.body = tk.Frame(col, bg=T["bg"])
        self.body.pack(fill="x")
        self.paste_area = tk.Frame(col, bg=T["bg"])
        self.paste_area.pack(fill="x", pady=(px(10), 0))
        self.message = tk.Label(col, text="", bg=T["bg"], fg=T["muted"], font=font(8, False),
                                justify="left", anchor="w", wraplength=px(680))
        self.message.pack(anchor="w", pady=(px(8), 0))
        self._tick_id: Optional[str] = None
        self._sig = None
        self.state: Dict[str, Any] = {}
        self.rebuild()
        self._tick()

    def destroy(self):
        if self._tick_id:
            self.after_cancel(self._tick_id)
        super().destroy()

    def say(self, text: str, bad: bool = False):
        self.message.configure(text=text, fg=T["pink"] if bad else T["muted"])

    def signature(self):
        return [(j['id'], j.get('state')) for j in jobs.all_jobs() if j.get('kind') == 'launcher']

    def _tick(self):
        self._tick_id = None
        sig = self.signature()
        active = any(s in jobs.ACTIVE for _i, s in sig)
        if sig != self._sig:
            if self._sig is not None:
                self.app.rescan()
            self.rebuild()
        elif active:
            self.rebuild()
        self._tick_id = self.after(1500, self._tick)

    def rebuild(self):
        self._sig = self.signature()
        clear(self.body)
        px, font = self.app.px, self.app.font
        base = self.app.scan_home or ''
        tk.Label(self.body, text=tr('accounts'), bg=T["bg"], fg=T["muted"], font=font(7),
                 anchor="w").pack(fill="x", pady=(px(14), px(4)))
        for store in STORES:
            row = tk.Frame(self.body, bg=T["bg"])
            row.pack(fill="x", pady=px(3))
            tk.Label(row, text=tr('store_' + store), bg=T["bg"], fg=T["text"], font=font(9),
                     width=18, anchor="w").pack(side="left")
            signed = stores.signed_in(store)
            name = stores.account_name(store)
            tk.Label(row, text=(tr('signed_in_as', name=name) if name else tr('signed_in'))
                     if signed else tr('not_signed_in'), bg=T["bg"],
                     fg=T["accent"] if signed else T["dim"], font=font(8),
                     width=26, anchor="w").pack(side="left")
            if signed:
                WolkButton(row, tr('sign_out'), lambda s=store: self.sign_out(s), font(8),
                           padx=px(10), pady=px(3)).pack(side="left")
            else:
                WolkButton(row, tr('sign_in'), lambda s=store: self.sign_in(s), font(8),
                           variant="primary", padx=px(10), pady=px(3)).pack(side="left")
        found = stores.takeable(base or os.path.expanduser('~'))
        if found:
            line = tk.Frame(self.body, bg=T["bg"])
            line.pack(fill="x", pady=(px(8), 0))
            tk.Label(line, text=tr('takeover_found', count=len(found)), bg=T["bg"], fg=T["muted"],
                     font=font(8, False)).pack(side="left", padx=(0, px(10)))
            WolkButton(line, tr('takeover_btn'), self.take_over, font(8), padx=px(10),
                       pady=px(3)).pack(side="left")

        tk.Label(self.body, text=tr('launchers_title'), bg=T["bg"], fg=T["muted"], font=font(7),
                 anchor="w").pack(fill="x", pady=(px(18), px(4)))
        tk.Label(self.body, text=tr('launchers_note'), bg=T["bg"], fg=T["muted"],
                 font=font(8, False), justify="left", anchor="w",
                 wraplength=px(680)).pack(fill="x", pady=(0, px(6)))
        lutris_found = {i['slug']: i for i in launchers.lutris_launchers(
            base or os.path.expanduser('~'))}
        for slug, info in launchers.LAUNCHERS.items():
            row = tk.Frame(self.body, bg=T["bg"])
            row.pack(fill="x", pady=px(3))
            tk.Label(row, text=info['name'], bg=T["bg"], fg=T["text"], font=font(9), width=24,
                     anchor="w").pack(side="left")
            job = jobs.job_for(f'{slug}:launcher')
            active = bool(job and job.get('state') in jobs.ACTIVE)
            have = launchers.known(slug)
            if active:
                text, colour = job_line(job), T["gold"]
            elif have:
                text, colour = tr('launcher_added'), T["accent"]
            elif job and job.get('state') == 'failed':
                text, colour = tr(job.get('message') or 'err_job_failed'), T["pink"]
            else:
                text, colour = tr('launcher_not_added'), T["dim"]
            tk.Label(row, text=text, bg=T["bg"], fg=colour, font=font(8), width=34,
                     anchor="w").pack(side="left")
            if active:
                WolkButton(row, tr('job_cancel'), lambda j=job: jobs.cancel(j['id']), font(8),
                           variant="danger", padx=px(10), pady=px(3)).pack(side="left")
            elif not have:
                WolkButton(row, tr('launcher_add'), lambda s=slug: self.add_launcher(s),
                           font(8), variant="primary", padx=px(10),
                           pady=px(3)).pack(side="left")
                if slug in lutris_found:
                    WolkButton(row, tr('launcher_use_lutris'),
                               lambda i=lutris_found[slug]: self.use_lutris(i), font(8),
                               padx=px(10), pady=px(3)).pack(side="left", padx=(px(8), 0))

    # accounts
    def sign_in(self, store: str):
        self.say(tr('signin_preparing', store=tr('store_' + store)))
        self.app.background(lambda: stores.begin_signin(store),
                            lambda r: self._signin_ready(store, r))

    def _signin_ready(self, store: str, result: Any):
        if isinstance(result, Exception):
            self.say(error_text(result), bad=True)
            return
        self.say('')
        self.show_paste(store, result)
        if signin_window.available():
            self.app.background(lambda: signin_window.run(store, result['url']),
                                lambda code: self._window_closed(store, result, code))
        else:
            open_uri(result['url'])

    def _window_closed(self, store: str, pending: Dict[str, Any], code: Any):
        if isinstance(code, str) and code:
            self.finish(store, code, pending['state'])

    def show_paste(self, store: str, pending: Dict[str, Any]):
        clear(self.paste_area)
        px, font = self.app.px, self.app.font
        from .views import entry
        tk.Label(self.paste_area, text=tr('signin_how_' + store, store=tr('store_' + store)),
                 bg=T["bg"], fg=T["text"], font=font(8, False), justify="left", anchor="w",
                 wraplength=px(680)).pack(anchor="w")
        line = tk.Frame(self.paste_area, bg=T["bg"])
        line.pack(anchor="w", pady=(px(6), 0))
        box, _field, var = entry(line, self.app, width=48)
        box.pack(side="left")
        WolkButton(line, tr('signin_finish'),
                   lambda: self.finish(store, var.get(), pending['state']), font(8),
                   variant="primary", padx=px(12), pady=px(4)).pack(side="left", padx=(px(8), 0))
        WolkButton(line, tr('signin_open_again'), lambda: open_uri(pending['url']), font(8),
                   padx=px(10), pady=px(4)).pack(side="left", padx=(px(8), 0))
        tk.Label(self.paste_area, text=tr('signin_argv_note'), bg=T["bg"], fg=T["dim"],
                 font=font(7, False), justify="left", wraplength=px(680)).pack(anchor="w",
                                                                              pady=(px(4), 0))

    def finish(self, store: str, pasted: str, state: Dict[str, str]):
        self.say(tr('signin_working'))
        self.app.background(lambda: stores.finish_signin(store, pasted, state),
                            lambda r: self._finished(store, r))

    def _finished(self, store: str, result: Any):
        if isinstance(result, Exception):
            self.say(error_text(result), bad=True)
            return
        if result:
            self.say(tr(result), bad=True)
            return
        clear(self.paste_area)
        self.say(tr('signin_done', store=tr('store_' + store)))
        self.rebuild()
        self.app.refresh_owned(force=True)
        self.app.offer_heroic_takeover()

    def sign_out(self, store: str):
        if not messagebox.askyesno(tr('sign_out'), tr('sign_out_confirm',
                                                      store=tr('store_' + store)), parent=self):
            return
        self.app.background(lambda: stores.sign_out(store), lambda _r: self._signed_out())

    def _signed_out(self):
        self.rebuild()
        self.app.rescan()

    def take_over(self):
        self.app.take_over_heroic()
        self.say(tr('takeover_working'))

    # launchers
    def add_launcher(self, slug: str):
        name = launchers.LAUNCHERS[slug]['name']
        if not messagebox.askyesno(tr('launcher_add'), tr('launcher_add_confirm', name=name),
                                   parent=self):
            return
        jobs.spawn({'kind': 'launcher', 'store': slug, 'key': f'{slug}:launcher',
                    'title': name, 'path': launchers.prefix_dir(slug)})
        self.rebuild()

    def use_lutris(self, item: Dict[str, str]):
        if messagebox.askyesno(tr('launcher_use_lutris'), tr('launcher_lutris_confirm',
                                                             name=item['name'],
                                                             prefix=item['prefix']),
                               parent=self):
            launchers.use_lutris(item)
            self.app.rescan()
            self.rebuild()

    def key(self, _event) -> bool:
        return False

    def focus_default(self):
        self.focus_set()
