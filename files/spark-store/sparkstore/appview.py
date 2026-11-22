"""One app's page: who makes it, what it is, its screenshots, size, licence, what it can
use in plain words, and Install / Open / Remove. The same page shows a Spark app, a Flathub
app, an app from a .flatpakref link, and an installed app that isn't in the catalog."""

import time
import webbrowser
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

import tkinter as tk

from . import flatpak, permissions, shots, sparkapps
from .appstream import App, Details, licence_label
from .core import size as fmt_size
from .jobs import FAILED, RUNNING, WAITING
from .pages import clear, notice, wrap_on_resize
from .text import t
from .ui import Card, Progress, chip, scrollable
from .widgets import T, GlitchText, IconButton, WolkButton

if TYPE_CHECKING:
    from .app import Store


@dataclass
class Subject:
    """What the page is about, whatever it came from."""
    kind: str                        # 'flathub', 'spark', 'ref' or 'local'
    id: str
    name: str
    summary: str = ''
    developer: str = ''
    verified: bool = False
    license: str = ''
    branch: str = 'stable'
    app: Optional[App] = None
    spark: Optional[sparkapps.SparkApp] = None
    ref: Optional[flatpak.Ref] = None
    repo: Optional[flatpak.Repo] = None
    details: Details = field(default_factory=Details)

    @property
    def proprietary(self) -> bool:
        return 'proprietary' in self.license.lower()


@dataclass
class Facts:
    """What flatpak says about the app (read in the background when the page opens)."""
    download: Optional[int] = None
    installed: Optional[int] = None
    version: str = ''
    lines: Optional[List[permissions.Line]] = None
    error: str = ''
    at: float = 0.0


class AppPage:
    def __init__(self, store: 'Store'):
        self.store = store
        self.frame = tk.Frame(store.body, bg=T["bg"])
        px = store.px
        top = tk.Frame(self.frame, bg=T["bg"])
        top.pack(fill="x", padx=px(10), pady=(px(6), 0))
        self.back = IconButton(top, "back", store.go_back, px(26), tip=t('nav.back'))
        self.back.pack(side="left")
        self.crumb = tk.Label(top, text="", font=store.font(8), bg=T["bg"], fg=T["muted"])
        self.crumb.pack(side="left", padx=(px(8), 0))
        self.scroll, self.inner, self.canvas = scrollable(self.frame, T["bg"], px)
        self.scroll.pack(fill="both", expand=True)
        self.subject: Optional[Subject] = None
        self.facts: Dict[str, Facts] = {}
        self.actions: Optional[tk.Frame] = None
        self.facts_frame: Optional[tk.Frame] = None
        self.perm_frame: Optional[tk.Frame] = None
        self.confirm: Optional[tk.Frame] = None
        self.progress: Optional[Progress] = None
        self.shot_index = 0
        self.shot_images: Dict[int, tk.PhotoImage] = {}
        self.shot_state: Dict[int, str] = {}
        self.shot_view: Optional[tk.Label] = None
        self.shot_caption: Optional[tk.Label] = None
        self.shot_count: Optional[tk.Label] = None
        self.shot_token = 0
        self.title: Optional[GlitchText] = None
        self.action_key = None
        self.addon_frame: Optional[tk.Frame] = None
        self.addon_key = None
        self.addons_all = False
        self.addon_status: Dict[str, tk.Label] = {}

    # — what to show —
    def subject_for(self, target) -> Optional[Subject]:
        store = self.store
        if isinstance(target, sparkapps.SparkApp):
            sp = target
            return Subject('spark', sp.id, sp.name, sp.summary, 'Wolklaw', True, sp.license,
                           spark=sp)
        if isinstance(target, App) and target.kind == 'spark':
            sp = store.spark_by_id.get(target.id)
            return self.subject_for(sp) if sp else None
        if isinstance(target, App):
            return Subject('flathub', target.id, target.name, target.summary,
                           target.developer, target.verified, target.license, target.branch,
                           app=target, details=store.catalog.details(target.id))
        if isinstance(target, flatpak.Repo):
            return Subject('repo', target.name, target.title or target.name, target.comment,
                           target.host, False, '', '', repo=target)
        if isinstance(target, flatpak.Ref):
            app = store.catalog.apps.get(target.id)
            if app is not None and (target.from_flathub or not target.url):
                return self.subject_for(app)
            return Subject('ref', target.id, target.title or target.id, '', target.host,
                           False, '', target.branch or 'stable', ref=target)
        if isinstance(target, str):
            app = store.catalog.apps.get(target)
            if app is not None:
                return self.subject_for(app)
            sp = store.spark_by_id.get(target)
            if sp is not None:
                return self.subject_for(sp)
            inst = store.installed.get(target)
            if inst is not None:
                return Subject('local', inst.id, inst.name, '', inst.origin, False, '',
                               inst.branch)
        return None

    def show(self, target) -> bool:
        subject = self.subject_for(target)
        if subject is None:
            return False
        self.subject = subject
        self.shot_index = 0
        self.shot_images.clear()
        self.shot_state.clear()
        self.shot_token += 1
        self.crumb.config(text={'spark': t('crumb.spark'), 'flathub': t('crumb.flathub'),
                                'ref': t('crumb.ref'), 'local': t('crumb.local'),
                                'repo': t('crumb.repo')}[subject.kind])
        self.repo_added = None
        if subject.kind == 'repo':
            self.check_repo()
        self.build()
        self.canvas.yview_moveto(0)
        if subject.kind in ('flathub', 'ref', 'local'):
            self.load_facts()
        if subject.details.screenshots:
            self.load_shot(0)
        return True

    # — building —
    def build(self):
        store, px, s = self.store, self.store.px, self.subject
        clear(self.inner)
        self.action_key = None
        self.addon_frame, self.addon_key, self.addons_all = None, None, False
        self.addon_status = {}
        head = tk.Frame(self.inner, bg=T["bg"])
        head.pack(fill="x", padx=px(16), pady=(px(8), 0))
        icon = tk.Label(head, bg=T["bg"], bd=0)
        icon.pack(side="left", anchor="n")
        size = px(96)
        if s.kind == 'spark':
            path = sparkapps.icon_path(s.spark)
        elif s.app is not None:
            path = store.catalog.icon_path(s.app, size)
        else:
            path = store.installed_icon(s.id)
        store.icons.put(icon, s.id, path, size)
        col = tk.Frame(head, bg=T["bg"])
        col.pack(side="left", fill="x", expand=True, padx=(px(14), 0))
        self.title = GlitchText(col, s.name, store.tkfont(17), T["bg"])
        self.title.pack(anchor="w")
        store.headings.append(self.title)
        who = tk.Frame(col, bg=T["bg"])
        who.pack(fill="x", pady=(px(2), 0))
        if s.kind == 'spark':
            byline = t('app.by_spark')
        elif s.kind in ('ref', 'repo'):
            byline = t('app.from_host', host=s.developer or '?')
        elif s.kind == 'local':
            byline = t('app.from_remote', remote=s.developer or '?')
        else:
            byline = t('app.by', dev=s.developer) if s.developer else t('app.by_unknown')
        tk.Label(who, text=byline, font=store.font(9, False), bg=T["bg"], fg=T["muted"]
                 ).pack(side="left")
        if s.kind == 'flathub' and s.verified:
            chip(who, t('chip.verified'), store.font(7), T["accent"], px=px).pack(
                side="left", padx=(px(8), 0))
        if s.proprietary:
            chip(who, t('chip.proprietary'), store.font(7), T["gold"], px=px).pack(
                side="left", padx=(px(6), 0))
        if s.kind == 'spark':
            chip(who, t('chip.spark'), store.font(7), T["accent"], px=px).pack(
                side="left", padx=(px(8), 0))
        if s.summary:
            summary = tk.Label(col, text=s.summary, font=store.font(10, False), bg=T["bg"],
                               fg=T["text"], anchor="w", justify="left")
            summary.pack(fill="x", pady=(px(6), 0))
            wrap_on_resize(col, [summary], px(4))
        self.actions = tk.Frame(col, bg=T["bg"])
        self.actions.pack(fill="x", pady=(px(10), 0))
        self.update_actions(force=True)

        self.confirm = tk.Frame(self.inner, bg=T["bg"])
        self.confirm.pack(fill="x")

        if s.proprietary:
            notice(store, self.inner, t('prop.title'),
                   t('prop.text', name=s.name, dev=s.developer or t('prop.the_maker')),
                   T["gold"])
        if s.kind == 'flathub' and not s.verified:
            notice(store, self.inner, t('unverified.title'),
                   t('unverified.text', dev=s.developer or t('prop.the_maker')), T["muted"])
        if s.kind == 'ref' and s.ref is not None and not s.ref.from_flathub:
            notice(store, self.inner, t('ref.title'),
                   t('ref.text', host=s.ref.host, name=s.name), T["gold"])
        if s.kind == 'repo' and s.repo is not None:
            if s.repo.is_flathub:
                notice(store, self.inner, t('repo.flathub_title'), t('repo.flathub'),
                       T["accent"])
            else:
                notice(store, self.inner, t('repo.title'),
                       t('repo.text', title=s.name, host=s.repo.host), T["gold"])

        self.facts_frame = tk.Frame(self.inner, bg=T["bg"])
        self.facts_frame.pack(fill="x", padx=px(16), pady=(px(14), 0))
        self.update_facts()

        if s.details.screenshots:
            self.build_shots()
        if s.details.description:
            self.build_description()
        if s.kind != 'spark' and store.catalog.addons.get(s.id):
            self.build_addons()
        if s.kind == 'spark':
            self.build_spark_notes()
        if s.kind == 'repo' and s.repo is not None and s.repo.description:
            self._heading(t('about.title'))
            about = tk.Label(self.inner, text=s.repo.description, font=store.font(9, False),
                             bg=T["bg"], fg=T["text"], anchor="w", justify="left")
            about.pack(fill="x", padx=px(16))
            wrap_on_resize(self.inner, [about], px(36))
        self.perm_frame = None
        if s.kind != 'repo':
            self.perm_frame = tk.Frame(self.inner, bg=T["bg"])
            self.perm_frame.pack(fill="x")
            self.update_permissions()
        self.build_links()
        tk.Frame(self.inner, bg=T["bg"], height=px(24)).pack()

    def _heading(self, text: str):
        px = self.store.px
        label = GlitchText(self.inner, text.upper(), self.store.tkfont(10), T["bg"], split=1)
        label.pack(anchor="w", padx=px(14), pady=(px(18), px(4)))
        self.store.headings.append(label)
        return label

    # — Install / Open / Remove —
    def state(self):
        """(installed scope or None, the job about this app or None, has an update)."""
        store, s = self.store, self.subject
        job = store.queue.for_app(s.id)
        if s.kind == 'spark':
            return s.spark.installed, job, False
        if s.kind == 'repo':
            return ('user' if self.repo_added else None), job, False
        inst = store.installed.get(s.id)
        update = any(u.id == s.id for u in store.updates)
        return (inst.scope if inst else None), job, update

    def update_actions(self, force: bool = False):
        if self.subject is None or self.actions is None or not self.actions.winfo_exists():
            return
        self.update_addons()
        store, px, s = self.store, self.store.px, self.subject
        scope, job, update = self.state()
        key = (scope, job.id if job else None, job.state if job else None, update,
               store.installed_loaded)
        if job is not None and job.state in (RUNNING, WAITING) and key == self.action_key:
            self._progress(job)
            return
        if key == self.action_key and not force:
            return
        self.action_key = key
        if self.progress is not None:
            self.progress.stop()
            self.progress = None
        clear(self.actions)
        row = tk.Frame(self.actions, bg=T["bg"])
        row.pack(fill="x")
        f8 = store.font(9)

        if job is not None and job.state in (RUNNING, WAITING):
            verb = t(f'doing_name.{job.kind}', name=s.name)
            self.status_label = tk.Label(row, text="", font=store.font(8), bg=T["bg"],
                                         fg=T["accent"], anchor="w")
            self.status_label.pack(side="left")
            WolkButton(row, t('btn.cancel'), lambda: store.queue.cancel(job), store.font(8)
                       ).pack(side="right")
            self.progress = Progress(self.actions, height=px(6))
            self.progress.pack(fill="x", pady=(px(6), 0))
            self.line_label = tk.Label(self.actions, text="", font=store.font(8, False),
                                       bg=T["bg"], fg=T["muted"], anchor="w")
            self.line_label.pack(fill="x", pady=(px(3), 0))
            self.verb = verb
            self._progress(job)
            return

        if job is not None and job.state == FAILED and job.kind != 'catalog':
            card = Card(self.actions, bg=T["panel"])
            card.edge.config(bg=T["pink"])
            card.pack(fill="x", pady=(0, px(8)), before=row)
            tk.Label(card.inner, text=t(f'failed.{job.kind}', name=s.name).upper(),
                     font=store.font(8), bg=T["panel"], fg=T["pink"], anchor="w"
                     ).pack(fill="x", padx=px(10), pady=(px(6), 0))
            err = tk.Label(card.inner, text=job.error or t('fail.unknown'),
                           font=store.font(8, False), bg=T["panel"], fg=T["text"],
                           anchor="w", justify="left")
            err.pack(fill="x", padx=px(10), pady=(px(2), px(6)))
            wrap_on_resize(card.inner, [err], px(24))
            buttons = tk.Frame(card.inner, bg=T["panel"])
            buttons.pack(fill="x", padx=px(8), pady=(0, px(8)))
            WolkButton(buttons, t('btn.retry'), lambda: store.retry(job), f8,
                       variant="primary").pack(side="left")
            WolkButton(buttons, t('btn.dismiss'), lambda: store.dismiss(job), store.font(8)
                       ).pack(side="left", padx=(px(6), 0))
            store.glitch.now(card, strong=True)

        if s.kind == 'spark':
            sp = s.spark
            if sp.installed:
                WolkButton(row, t('btn.open'), lambda: store.launch(s), f8,
                           variant="primary").pack(side="left")
                if sp.installed == 'user':
                    WolkButton(row, t('btn.remove'), self.ask_remove, f8, variant="danger"
                               ).pack(side="left", padx=(px(8), 0))
                else:
                    self._note(row, t('spark.in_image'))
            elif sp.source:
                WolkButton(row, t('btn.install'), lambda: store.install(s), f8,
                           variant="primary").pack(side="left")
                self._note(row, t('spark.for_you'))
            else:
                self._note(row, t('spark.no_source'))
            return

        if not store.flatpak_ok:
            self._note(row, t('flatpak.missing'))
            return
        if s.kind == 'repo':
            if self.repo_added is None:
                self._note(row, t('app.checking'))
            elif self.repo_added:
                self._note(row, t('repo.added', name=s.id))
            else:
                WolkButton(row, t('repo.add'), lambda: store.add_remote(s), f8,
                           variant="primary").pack(side="left")
                self._note(row, t('install.for_you'))
            return
        if scope is not None:
            WolkButton(row, t('btn.open'), lambda: store.launch(s), f8, variant="primary"
                       ).pack(side="left")
            if update:
                WolkButton(row, t('btn.update'), lambda: store.update(s.id, scope), f8
                           ).pack(side="left", padx=(px(8), 0))
            WolkButton(row, t('btn.remove'), self.ask_remove, f8, variant="danger"
                       ).pack(side="left", padx=(px(8), 0))
            self._note(row, t('scope.user') if scope == 'user' else t('scope.system'))
        elif s.kind == 'local':
            self._note(row, t('local.removed'))
        elif not store.installed_loaded:
            self._note(row, t('app.checking'))
        else:
            label = t('btn.install') if s.kind != 'ref' or s.ref.from_flathub else \
                t('btn.install_from', host=s.ref.host)
            WolkButton(row, label, lambda: store.install(s), f8, variant="primary"
                       ).pack(side="left")
            self._note(row, t('install.for_you'))

    def _note(self, row: tk.Frame, text: str):
        tk.Label(row, text=text, font=self.store.font(8, False), bg=T["bg"], fg=T["muted"],
                 anchor="w", justify="left").pack(side="left", padx=(self.store.px(10), 0))

    def _progress(self, job):
        if self.progress is None:
            return
        if job.state == WAITING:
            ahead = self.store.queue_position(job)
            text = t('job.waiting', n=ahead) if ahead else t('job.next')
            self.progress.set(0.0)
        else:
            pct = f" {round(job.progress * 100)}%" if job.progress is not None else ""
            step = f" · {job.step_text}" if job.step_text else ""
            text = f"{self.verb.upper()}{pct}{step}"
            self.progress.set(job.progress)
        self.status_label.config(text=f"● {text}")
        line = job.line if job.state == RUNNING else ''
        if self.line_label.cget("text") != line:
            self.line_label.config(text=line[:160])

    def ask_remove(self):
        store, px, s = self.store, self.store.px, self.subject
        clear(self.confirm)
        card = Card(self.confirm, bg=T["panel"])
        card.edge.config(bg=T["pink"])
        card.pack(fill="x", padx=px(16), pady=(px(10), 0))
        inner = card.inner
        scope, _job, _u = self.state()
        if s.kind == 'spark':
            text = t('remove.spark', name=s.name, slug=s.spark.slug)
        else:
            text = t('remove.flatpak', name=s.name, id=s.id)
            if scope == 'system':
                text += "\n" + t('remove.system')
        tk.Label(inner, text=t('remove.title', name=s.name).upper(), font=store.font(8),
                 bg=T["panel"], fg=T["pink"], anchor="w").pack(fill="x", padx=px(10),
                                                               pady=(px(6), 0))
        body = tk.Label(inner, text=text, font=store.font(9, False), bg=T["panel"],
                        fg=T["text"], anchor="w", justify="left")
        body.pack(fill="x", padx=px(10), pady=(px(2), px(6)))
        wrap_on_resize(inner, [body], px(24))
        buttons = tk.Frame(inner, bg=T["panel"])
        buttons.pack(fill="x", padx=px(8), pady=(0, px(8)))

        def go(delete_data: bool):
            clear(self.confirm)
            store.remove(s, scope or 'user', delete_data)

        WolkButton(buttons, t('btn.remove'), lambda: go(False), store.font(8), variant="danger"
                   ).pack(side="left")
        if s.kind != 'spark':
            WolkButton(buttons, t('btn.remove_data'), lambda: go(True), store.font(8),
                       variant="danger").pack(side="left", padx=(px(6), 0))
        WolkButton(buttons, t('btn.cancel'), lambda: clear(self.confirm), store.font(8)
                   ).pack(side="left", padx=(px(6), 0))
        store.glitch.now(card)

    # — size, licence, version —
    def update_facts(self):
        if self.facts_frame is None or not self.facts_frame.winfo_exists():
            return
        store, px, s = self.store, self.store.px, self.subject
        clear(self.facts_frame)
        facts = self.facts.get(s.id)
        inst = store.installed.get(s.id)
        cells = []
        if s.kind == 'repo':
            cells.append((t('fact.name'), s.id))
            cells.append((t('fact.address'), s.repo.url if s.repo else '—'))
            cells.append((t('fact.from'), s.developer or '?'))
        elif s.kind == 'spark':
            sp = s.spark
            cells.append((t('fact.size'), fmt_size(sp.size_kb * 1024) if sp.size_kb else "—"))
            cells.append((t('fact.licence'), licence_label(sp.license) or t('fact.unknown')))
            cells.append((t('fact.version'), sp.version or "—"))
            cells.append((t('fact.from'), t('from.sparkos')))
        else:
            if inst is not None and inst.size:
                size = t('size.installed', size=fmt_size(inst.size))
            elif facts and facts.installed:
                size = t('size.remote', size=fmt_size(facts.installed),
                         download=fmt_size(facts.download))
            elif facts is None and s.kind != 'local':
                size = t('fact.checking')
            else:
                size = "—"
            cells.append((t('fact.size'), size))
            cells.append((t('fact.licence'), licence_label(s.license) or t('fact.unknown')))
            version = (inst.version if inst and inst.version else '') or \
                (facts.version if facts else '') or s.details.version or "—"
            if s.details.released and version == s.details.version:
                version += "  " + time.strftime('%Y-%m-%d', time.localtime(s.details.released))
            cells.append((t('fact.version'), version))
            if s.kind == 'ref':
                origin = s.ref.host if s.ref else '?'
            elif s.kind == 'local':
                origin = s.developer or '?'
            else:
                origin = t('from.flathub')
            cells.append((t('fact.from'), origin))
        for i, (label, value) in enumerate(cells):
            self.facts_frame.columnconfigure(i, weight=1, uniform="facts")
            cell = tk.Frame(self.facts_frame, bg=T["panel"], highlightthickness=1,
                            highlightbackground=T["line"])
            cell.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(4), 0))
            tk.Label(cell, text=label.upper(), font=store.font(7), bg=T["panel"],
                     fg=T["muted"], anchor="w").pack(fill="x", padx=px(10), pady=(px(6), 0))
            value_label = tk.Label(cell, text=value, font=store.font(9), bg=T["panel"],
                                   fg=T["text"], anchor="w", justify="left")
            value_label.pack(fill="x", padx=px(10), pady=(0, px(6)))
            wrap_on_resize(cell, [value_label], px(20))

    def load_facts(self):
        s = self.subject
        known = self.facts.get(s.id)
        if known is not None and time.time() - known.at < 600:
            return
        store = self.store
        app_id, branch = s.id, s.branch
        inst = store.installed.get(app_id)
        kind, ref = s.kind, s.ref

        def work() -> Facts:
            facts = Facts(at=time.time())
            if inst is not None:
                meta = flatpak.installed_metadata(app_id, inst.scope)
                if meta:
                    facts.lines = permissions.describe(meta)
            if kind in ('flathub', 'ref') and (ref is None or ref.from_flathub):
                info = flatpak.remote_info(app_id, branch or 'stable')
                facts.download, facts.installed = info.download, info.installed
                facts.version, facts.error = info.version, info.error
                if facts.lines is None and info.metadata:
                    facts.lines = permissions.describe(info.metadata)
            return facts

        def done(facts: Facts):
            self.facts[app_id] = facts
            if self.subject is not None and self.subject.id == app_id:
                self.update_facts()
                self.update_permissions()

        store.bg(work, done)

    # — what it can use —
    def update_permissions(self):
        if self.perm_frame is None or not self.perm_frame.winfo_exists():
            return
        store, px, s = self.store, self.store.px, self.subject
        clear(self.perm_frame)
        frame = self.perm_frame
        title = GlitchText(frame, t('perm.title').upper(), store.tkfont(10), T["bg"], split=1)
        title.pack(anchor="w", padx=px(14), pady=(px(18), px(4)))

        def para(text, colour=T["text"]):
            label = tk.Label(frame, text=text, font=store.font(9, False), bg=T["bg"],
                             fg=colour, anchor="w", justify="left")
            label.pack(fill="x", padx=px(16), pady=(0, px(2)))
            wrap_on_resize(frame, [label], px(36))

        if s.kind == 'spark':
            para(t('perm.spark'), T["muted"])
            return
        facts = self.facts.get(s.id)
        if facts is None:
            para(t('perm.checking'), T["muted"])
            return
        if facts.lines is None:
            if s.kind == 'ref' and s.ref is not None and not s.ref.from_flathub:
                para(t('perm.unknown_ref'), T["muted"])
            else:
                para(t('perm.failed', error=facts.error or t('fail.unknown')), T["pink"])
            return
        lines = facts.lines
        if not lines:
            para(t('perm.none'), T["accent"])
            return
        if permissions.broad(lines):
            para(t('perm.broad_note'), T["muted"])
        grid = tk.Frame(frame, bg=T["bg"])
        grid.pack(fill="x", padx=px(16), pady=(px(4), 0))
        grid.columnconfigure(1, weight=1)
        r = 0
        for group in permissions.GROUPS:
            items = [(lvl, txt) for g, lvl, txt in lines if g == group]
            if not items:
                continue
            tk.Label(grid, text=t(f'perm.group.{group}').upper(), font=store.font(7),
                     bg=T["bg"], fg=T["muted"], anchor="nw").grid(row=r, column=0, sticky="nw",
                                                                pady=(px(6), 0),
                                                                padx=(0, px(14)))
            for n, (level, text) in enumerate(items):
                mark = "!" if level == 'warn' else "·"
                colour = T["pink"] if level == 'warn' else T["text"]
                line = tk.Label(grid, text=f"{mark}  {text}", font=store.font(9, False),
                                bg=T["bg"], fg=colour, anchor="w", justify="left")
                line.grid(row=r, column=1, sticky="ew", pady=(px(6) if n == 0 else 0, 0))
                r += 1
        tk.Label(frame, text=t('perm.footer'), font=store.font(8, False), bg=T["bg"],
                 fg=T["dim"], anchor="w", justify="left", wraplength=px(720)).pack(
            fill="x", padx=px(16), pady=(px(8), 0))

    # — screenshots —
    def build_shots(self):
        store, px = self.store, self.store.px
        self._heading(t('shots.title'))
        box = tk.Frame(self.inner, bg=T["out_bg"], highlightthickness=1,
                       highlightbackground=T["line"])
        box.pack(fill="x", padx=px(16))
        self.shot_view = tk.Label(box, bg=T["out_bg"], fg=T["muted"], font=store.font(8, False),
                                  text=t('shots.loading'), height=1, cursor="hand2")
        self.shot_view.pack(fill="both", expand=True, pady=px(6))
        self.shot_view.configure(height=0)
        self.shot_view.bind("<ButtonRelease-1>", lambda _e: self.step_shot(1))
        bar = tk.Frame(self.inner, bg=T["bg"])
        bar.pack(fill="x", padx=px(16), pady=(px(4), 0))
        IconButton(bar, "prev", lambda: self.step_shot(-1), px(22)).pack(side="left")
        self.shot_count = tk.Label(bar, text="", font=store.font(8), bg=T["bg"], fg=T["muted"])
        self.shot_count.pack(side="left", padx=px(6))
        IconButton(bar, "next", lambda: self.step_shot(1), px(22)).pack(side="left")
        self.shot_caption = tk.Label(bar, text="", font=store.font(8, False), bg=T["bg"],
                                     fg=T["text"], anchor="w")
        self.shot_caption.pack(side="left", padx=(px(10), 0), fill="x", expand=True)
        self.show_shot()

    def step_shot(self, step: int):
        n = len(self.subject.details.screenshots) if self.subject else 0
        if n < 2:
            return
        self.shot_index = (self.shot_index + step) % n
        self.show_shot()
        self.load_shot(self.shot_index)

    def show_shot(self):
        if self.shot_view is None or not self.shot_view.winfo_exists():
            return
        shots_list = self.subject.details.screenshots
        i = self.shot_index
        shot = shots_list[i]
        self.shot_count.config(text=f"{i + 1} / {len(shots_list)}")
        self.shot_caption.config(text=shot.caption)
        img = self.shot_images.get(i)
        if img is not None:
            self.shot_view.config(image=img, text="")
        else:
            state = self.shot_state.get(i, '')
            text = t('shots.failed', error=state[6:]) if state.startswith('error:') else \
                t('shots.loading')
            self.shot_view.config(image="", text=text)

    def load_shot(self, i: int):
        if i in self.shot_images or self.shot_state.get(i) == 'loading':
            return
        store, s = self.store, self.subject
        shot = s.details.screenshots[i]
        token = self.shot_token
        self.shot_state[i] = 'loading'
        room = self.canvas.winfo_width() - store.px(40)
        width = store.px(752) if room < store.px(200) else \
            min(store.px(752), max(store.px(320), room))     # before the first layout: full

        def work():
            return shots.fetch(shot.url)

        def done(result):
            path, error = result
            if token != self.shot_token:
                return
            if path:
                img = store.icons.load(path, 0, fit_width=width)
                if img is not None:
                    self.shot_images[i] = img
                    self.shot_state[i] = 'ok'
                else:
                    self.shot_state[i] = 'error:' + t('shots.unreadable')
            else:
                self.shot_state[i] = 'error:' + error
            if i == self.shot_index:
                self.show_shot()
            if i == 0 and len(s.details.screenshots) > 1:
                self.load_shot(1)            # the next one, so the arrow is instant

        store.bg(work, done)

    # — add-ons —
    SHOWN_ADDONS = 8

    def build_addons(self):
        self._heading(t('addons.title'))
        self.addon_frame = tk.Frame(self.inner, bg=T["bg"])
        self.addon_frame.pack(fill="x")
        self.update_addons()

    def update_addons(self):
        frame = self.addon_frame
        if frame is None or not frame.winfo_exists() or self.subject is None:
            return
        store, px, s = self.store, self.store.px, self.subject
        addons = store.catalog.addons.get(s.id, [])
        scope, _job, _u = self.state()
        jobs = {a.id: store.queue.for_app(a.id) for a in addons}
        key = (scope, self.addons_all, store.installed_loaded,
               tuple((a.id, store.runtimes.get(a.id), jobs[a.id].id if jobs[a.id] else None,
                      jobs[a.id].state if jobs[a.id] else None) for a in addons))
        if key == self.addon_key:
            for addon_id, label in self.addon_status.items():
                job = jobs.get(addon_id)
                if job is not None and job.state == RUNNING and label.winfo_exists():
                    pct = f" {round(job.progress * 100)}%" if job.progress is not None else "…"
                    label.config(text=t(f'doing.{job.kind}').upper() + pct)
            return
        self.addon_key = key
        self.addon_status = {}
        clear(frame)
        note = tk.Label(frame, text=t('addons.note', name=s.name) if scope else
                        t('addons.need_app', name=s.name), font=store.font(8, False),
                        bg=T["bg"], fg=T["muted"], anchor="w", justify="left")
        note.pack(fill="x", padx=px(16), pady=(0, px(4)))
        wrap_on_resize(frame, [note], px(36), slack=px(40))
        shown = addons if self.addons_all else addons[:self.SHOWN_ADDONS]
        for addon in shown:
            self._addon_row(frame, addon, jobs.get(addon.id), scope)
        if len(addons) > len(shown):
            def more():
                self.addons_all = True
                self.update_addons()
            WolkButton(frame, t('addons.more', n=len(addons)), more, store.font(8),
                       padx=10, pady=4).pack(anchor="w", padx=px(16), pady=(px(6), 0))

    def _addon_row(self, frame, addon, job, scope):
        store, px = self.store, self.store.px
        bg = T["panel"]
        row = tk.Frame(frame, bg=bg, highlightthickness=1, highlightbackground=T["line"])
        row.pack(fill="x", padx=px(16), pady=(px(3), 0))
        right = tk.Frame(row, bg=bg)
        right.pack(side="right", padx=px(8), pady=px(6))
        col = tk.Frame(row, bg=bg)
        col.pack(side="left", fill="x", expand=True, padx=px(10), pady=px(6))
        head = tk.Frame(col, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=addon.name, font=store.font(9), bg=bg, fg=T["text"],
                 anchor="w").pack(side="left")
        if addon.proprietary:
            chip(head, t('chip.proprietary'), store.font(7), T["gold"], px=px).pack(
                side="left", padx=(px(8), 0))
        labels = []
        if addon.summary:
            summary = tk.Label(col, text=addon.summary, font=store.font(8, False), bg=bg,
                               fg=T["muted"], anchor="w", justify="left")
            summary.pack(fill="x")
            labels.append(summary)
        installed = store.runtimes.get(addon.id)
        if job is not None and job.state in (RUNNING, WAITING):
            status = tk.Label(right, text=t(f'doing.{job.kind}').upper() + "…",
                              font=store.font(8), bg=bg, fg=T["gold"])
            status.pack(side="right")
            self.addon_status[addon.id] = status
        elif installed:
            WolkButton(right, t('btn.remove'), lambda a=addon: store.remove_addon(a),
                       store.font(8), variant="danger", padx=10, pady=3).pack(side="right")
            chip(right, t('addons.installed'), store.font(7), T["accent"], True, px).pack(
                side="right", padx=(0, px(8)))
        elif scope and store.flatpak_ok:
            WolkButton(right, t('btn.install'), lambda a=addon: store.install_addon(a),
                       store.font(8), variant="primary", padx=10, pady=3).pack(side="right")
        if job is not None and job.state == FAILED:
            err = tk.Label(col, text=job.error or t('fail.unknown'), font=store.font(8, False),
                           bg=bg, fg=T["pink"], anchor="w", justify="left")
            err.pack(fill="x", pady=(px(2), 0))
            labels.append(err)
            WolkButton(right, t('btn.retry'), lambda j=job: store.retry(j), store.font(8),
                       padx=10, pady=3).pack(side="right", padx=(0, px(6)))
        wrap_on_resize(col, labels, px(4), slack=px(40))

    # — description and links —
    def build_description(self):
        store, px = self.store, self.store.px
        self._heading(t('about.title'))
        box = tk.Frame(self.inner, bg=T["bg"])
        box.pack(fill="x", padx=px(16))
        labels = []
        for kind, text in self.subject.details.description[:40]:
            if kind == 'li':
                label = tk.Label(box, text=f"–  {text}", font=store.font(9, False), bg=T["bg"],
                                 fg=T["text"], anchor="w", justify="left")
                label.pack(fill="x", padx=(px(10), 0), pady=(0, px(2)))
            else:
                label = tk.Label(box, text=text, font=store.font(9, False), bg=T["bg"],
                                 fg=T["text"], anchor="w", justify="left")
                label.pack(fill="x", pady=(px(4), px(4)))
            labels.append(label)
        wrap_on_resize(box, labels, px(16))

    def build_spark_notes(self):
        store, px, sp = self.store, self.store.px, self.subject.spark
        self._heading(t('spark.about'))
        lines = []
        if sp.installed == 'system':
            lines.append(t('spark.note_image'))
        elif sp.installed == 'user':
            lines.append(t('spark.note_user', slug=sp.slug))
        elif sp.source:
            lines.append(t('spark.note_source', folder=sp.source, slug=sp.slug))
        else:
            lines.append(t('spark.note_no_source'))
        optional = sp.needs.get('optional_commands') or sp.needs.get('optional_programs') or \
            list((sp.needs.get('optional') or {}).keys())
        if optional:
            lines.append(t('spark.optional', items=', '.join(str(o) for o in optional)))
        lines.append(t('spark.updates'))
        box = tk.Frame(self.inner, bg=T["bg"])
        box.pack(fill="x", padx=px(16))
        labels = []
        for line in lines:
            label = tk.Label(box, text=line, font=store.font(9, False), bg=T["bg"], fg=T["text"],
                             anchor="w", justify="left")
            label.pack(fill="x", pady=(0, px(4)))
            labels.append(label)
        wrap_on_resize(box, labels, px(16))

    def build_links(self):
        store, px, s = self.store, self.store.px, self.subject
        urls = dict(s.details.urls)
        if s.kind == 'spark' and s.spark.source_url:
            urls['vcs-browser'] = s.spark.source_url
        if s.kind == 'ref' and s.ref and s.ref.homepage:
            urls['homepage'] = s.ref.homepage
        if s.kind == 'repo' and s.repo and s.repo.homepage:
            urls['homepage'] = s.repo.homepage
        if s.kind == 'flathub':
            urls.setdefault('flathub', f"https://flathub.org/apps/{s.id}")
        order = [('homepage', 'link.home'), ('help', 'link.help'),
                 ('bugtracker', 'link.bugs'), ('vcs-browser', 'link.source'),
                 ('donation', 'link.donate'), ('flathub', 'link.flathub')]
        present = [(urls[k], label) for k, label in order if urls.get(k)]
        if not present:
            return
        self._heading(t('links.title'))
        row = tk.Frame(self.inner, bg=T["bg"])
        row.pack(fill="x", padx=px(14))
        for url, label in present:
            WolkButton(row, t(label), lambda u=url: self.open_url(u), store.font(8),
                       padx=10, pady=4).pack(side="left", padx=(0, px(6)))
        tk.Label(self.inner, text=t('links.note'), font=store.font(8, False), bg=T["bg"],
                 fg=T["dim"], anchor="w").pack(fill="x", padx=px(16), pady=(px(6), 0))

    def open_url(self, url: str):
        if url.startswith(('https://', 'http://')):
            try:
                webbrowser.open(url)
            except webbrowser.Error:
                pass

    def check_repo(self):
        """Whether this app source is already one of your remotes (by name or address)."""
        s = self.subject
        if s is None or s.kind != 'repo':
            return
        repo = s.repo

        def work():
            names = flatpak.remotes()
            return repo.name in names.get('user', []) or (
                repo.is_flathub and flatpak.REMOTE in names.get('user', []))

        def done(added):
            if self.subject is s:
                self.repo_added = bool(added)
                self.update_actions(force=True)

        self.store.bg(work, done)

    # — called by the window when something changed —
    def refresh(self):
        if self.subject is None:
            return
        if self.subject.kind == 'spark':
            sparkapps.refresh_state(self.subject.spark)
        self.addon_key = None
        self.update_actions()
        self.update_facts()
