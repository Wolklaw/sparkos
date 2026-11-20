"""The six pages. Each one only draws and reacts; the work happens in catalog, flatpak,
windows and checks, in background threads started through App.bg."""

import os
import threading
import time
from typing import Any, Dict, List, Optional

import tkinter as tk

from . import APP_NAME, catalog as catalog_mod, checks, core, flatpak, windows
from .strings import LANG, t
from .widgets import T, GlitchPanel, GlitchText, Segmented, Strip, Toggle, WolkButton


class Scroller(tk.Frame):
    """A page that scrolls: the wheel anywhere in the window, or the thin bar on the right."""

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["bg"])
        self.app = app
        self.bar = tk.Canvas(self, width=app.px(6), bg=T["bg"], highlightthickness=0, bd=0)
        self.bar.pack(side="right", fill="y", padx=(0, app.px(4)))
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self._region())
        self.canvas.bind("<Configure>", self._resized)
        self.canvas.configure(yscrollcommand=self._yset)
        self.bar.bind("<ButtonPress-1>", self._drag)
        self.bar.bind("<B1-Motion>", self._drag)
        self.lo, self.hi = 0.0, 1.0

    def _resized(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        self._region()

    def _region(self):
        height = max(self.inner.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), height))

    def _yset(self, lo, hi):
        self.lo, self.hi = float(lo), float(hi)
        self.bar.delete("all")
        if self.hi - self.lo >= 0.999:
            return
        h = self.bar.winfo_height()
        w = int(self.bar.cget("width"))
        self.bar.create_rectangle(w // 2 - 1, 0, w // 2, h, fill=T["line"], width=0)
        self.bar.create_rectangle(0, int(self.lo * h), w, max(int(self.lo * h) + 8,
                                                              int(self.hi * h)),
                                  fill=T["line2"], width=0)

    def _drag(self, event):
        span = self.hi - self.lo
        h = max(1, self.bar.winfo_height())
        self.canvas.yview_moveto(max(0.0, min(1.0 - span, event.y / h - span / 2)))

    def scroll(self, units: int):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")

    def top(self):
        self.canvas.yview_moveto(0)


class Page(tk.Frame):
    """A page: a scrolling column with a heading. Subclasses fill build()."""

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["bg"])
        self.app = app
        self.px = app.px
        self.heading: Optional[GlitchText] = None
        self.scroller = Scroller(self, app)
        self.scroller.pack(fill="both", expand=True)
        self.col = tk.Frame(self.scroller.inner, bg=T["bg"])
        self.col.pack(fill="both", expand=True, padx=self.px(28), pady=(self.px(22), self.px(28)))
        self.wrap = self.px(660)
        self.build()

    def build(self):
        raise NotImplementedError

    def shown(self):
        """Called each time the page comes to the front."""

    def scroll(self, units: int):
        self.scroller.scroll(units)

    # building blocks
    def title(self, text: str, parent: Optional[tk.Misc] = None) -> GlitchText:
        parent = parent or self.col
        heading = GlitchText(parent, text.upper(), self.app.tkfont(17), parent.cget("bg"))
        heading.pack(anchor="w", pady=(0, self.px(10)))
        if self.heading is None:
            self.heading = heading
            self.app.glitch.add(heading)
        return heading

    def para(self, text: str, parent: Optional[tk.Misc] = None, muted: bool = False,
             size: int = 10, pady=(0, 10), colour: Optional[str] = None,
             wrap: Optional[int] = None) -> tk.Label:
        parent = parent or self.col
        label = tk.Label(parent, text=text, bg=parent.cget("bg"),
                         fg=colour or (T["muted"] if muted else T["text"]),
                         font=self.app.font(size, False), justify="left", anchor="w",
                         wraplength=wrap or self.wrap)
        label.pack(anchor="w", fill="x", pady=(self.px(pady[0]), self.px(pady[1])))
        return label

    def micro(self, text: str, parent: Optional[tk.Misc] = None, colour: str = T["dim"],
              pady=(14, 6)) -> tk.Label:
        parent = parent or self.col
        label = tk.Label(parent, text=text.upper(), bg=parent.cget("bg"), fg=colour,
                         font=self.app.font(8), anchor="w")
        label.pack(anchor="w", fill="x", pady=(self.px(pady[0]), self.px(pady[1])))
        return label

    def button(self, parent: tk.Misc, text: str, command, variant: str = "ghost",
               side: str = "left") -> WolkButton:
        btn = WolkButton(parent, text, command, self.app.font(9), variant)
        btn.pack(side=side, padx=(0, self.px(8)))
        return btn

    def row(self, parent: Optional[tk.Misc] = None, pady=(6, 0)) -> tk.Frame:
        parent = parent or self.col
        frame = tk.Frame(parent, bg=parent.cget("bg"))
        frame.pack(anchor="w", fill="x", pady=(self.px(pady[0]), self.px(pady[1])))
        return frame

    def panel(self, parent: Optional[tk.Misc] = None, pady=(0, 8)) -> GlitchPanel:
        parent = parent or self.col
        box = GlitchPanel(parent, T["panel"])
        box.pack(fill="x", pady=(self.px(pady[0]), self.px(pady[1])))
        return box

    @staticmethod
    def clear(frame: tk.Misc):
        for child in frame.winfo_children():
            child.destroy()


# ─── 1. Welcome ───────────────────────────────────────────────

class WelcomePage(Page):
    def build(self):
        px = self.px
        top = tk.Frame(self.col, bg=T["bg"])
        top.pack(fill="x")
        self.bot = None
        size = 320 if self.app.scale >= 1.75 else 240 if self.app.scale >= 1.25 else 160
        image_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  'icons', f'sparkos-bot-{size}.png')
        if os.path.isfile(image_path):
            try:
                self.bot = tk.PhotoImage(master=self, file=image_path)
                tk.Label(top, image=self.bot, bg=T["bg"]).pack(side="left", anchor="n",
                                                                padx=(0, px(22)))
            except tk.TclError:
                self.bot = None
        text = tk.Frame(top, bg=T["bg"])
        text.pack(side="left", fill="both", expand=True)
        self.title(t('welcome.title'), text)
        wrap = self.px(460)
        self.para(t('welcome.intro'), text, wrap=wrap)
        self.para(t('welcome.rest'), text, wrap=wrap)
        self.micro(t('welcome.onboard'))
        for name, what in (('Soot', t('welcome.soot')), ('FreeSuite', t('welcome.freesuite')),
                           ('Spark Snip', t('welcome.snip')), ('Spark Media', t('welcome.media')),
                           ('Spark Games', t('welcome.games')), ('Spark Monitor', t('welcome.monitor')),
                           ('Spark Edit', t('welcome.edit')), ('Spark Calc', t('welcome.calc')),
                           ('Spark Archive', t('welcome.archive')), ('Spark Scan', t('welcome.scan')),
                           ('Spark Run', t('welcome.run')), ('Spark Link', t('welcome.link')),
                           ('Spark Store', t('welcome.store')), ('Spark Update', t('welcome.update'))):
            box = self.panel(pady=(0, 6))
            line = tk.Frame(box.inner, bg=T["panel"])
            line.pack(fill="x", padx=px(12), pady=px(8))
            tk.Label(line, text=name.upper(), bg=T["panel"], fg=T["accent"], font=self.app.font(9),
                     width=15, anchor="w").pack(side="left")
            tk.Label(line, text=what, bg=T["panel"], fg=T["text"], font=self.app.font(9, False),
                     anchor="w", justify="left", wraplength=px(480)).pack(side="left", fill="x")
        self.micro(t('welcome.how'))
        self.para(t('welcome.skip'), muted=True)


# ─── 2 and 3. Games and Apps ──────────────────────────────────

class Tick(Toggle):
    """A Toggle that can be locked (installed, queued)."""

    def __init__(self, parent, text, command, font):
        self.locked = False
        super().__init__(parent, text, False, command, font)

    def set(self, value: bool, fire: bool = False):
        if self.locked and fire:
            return
        super().set(value, fire)

    def lock(self, on: bool):
        self.locked = on
        self.configure(cursor="arrow" if on else "hand2", takefocus=0 if on else 1)
        if on:
            self.value = False
            self.config(text="□ " + self.text.upper(), fg=T["dim"], bg=T["panel"],
                        highlightbackground=T["line"])
        else:
            self._paint()

    def _paint(self, hover: bool = False):
        if self.locked:
            return
        super()._paint(hover)


class AppRow(GlitchPanel):
    """One app: tick, name, whose app it is, a line about it, and how its install is going."""

    def __init__(self, parent: tk.Misc, page: 'InstallPage', entry: catalog_mod.Entry):
        super().__init__(parent, T["panel"])
        app, px = page.app, page.px
        self.page, self.app, self.entry = page, app, entry
        body = tk.Frame(self.inner, bg=T["panel"])
        body.pack(fill="x", padx=px(10), pady=px(8))
        right = tk.Frame(body, bg=T["panel"])
        right.pack(side="right", anchor="n")
        self.state = tk.Label(right, text="", bg=T["panel"], fg=T["muted"], font=app.font(8))
        self.state.pack(side="right", anchor="n", pady=(px(4), 0))
        self.retry_btn = WolkButton(right, t('apps.retry'), lambda: app.retry(entry.id),
                                    app.font(8), "danger", padx=8, pady=2)
        left = tk.Frame(body, bg=T["panel"])
        left.pack(side="left", fill="x", expand=True)
        top = tk.Frame(left, bg=T["panel"])
        top.pack(anchor="w", fill="x")
        self.tick = Tick(top, entry.label(LANG), lambda _v: page.ticks_changed(), app.font(9))
        self.tick.pack(side="left")
        tk.Label(top, text=t('apps.by', who=entry.who(LANG)), bg=T["panel"], fg=T["dim"],
                 font=app.font(8, False)).pack(side="left", padx=(px(10), 0))
        tk.Label(left, text=entry.text(LANG), bg=T["panel"], fg=T["muted"],
                 font=app.font(9, False), anchor="w", justify="left",
                 wraplength=px(520)).pack(anchor="w", fill="x", pady=(px(4), 0))
        self.error = tk.Label(left, text="", bg=T["panel"], fg=T["pink"], font=app.font(8, False),
                              anchor="w", justify="left", wraplength=px(520))
        app.rows[entry.id] = self
        if entry.id in app.installed:
            self.set_installed()
        job = app.installer.jobs.get(entry.id)
        if job is not None:
            self.set_job(job)

    @property
    def ticked(self) -> bool:
        return self.tick.value and not self.tick.locked

    def set_installed(self):
        self.tick.lock(True)
        self.state.config(text=f"■ {t('apps.state.installed')}", fg=T["accent"])
        self.retry_btn.pack_forget()
        self.error.pack_forget()

    def set_job(self, job: flatpak.Job):
        if job.state == flatpak.DONE:
            self.set_installed()
            self.burst()
            return
        self.tick.lock(job.state in (flatpak.QUEUED, flatpak.WORKING))
        if job.state == flatpak.QUEUED:
            self.state.config(text=t('apps.state.queued'), fg=T["muted"])
        elif job.state == flatpak.WORKING:
            pct = f" {job.percent}%" if job.percent is not None else "…"
            self.state.config(text=t('apps.state.installing') + pct, fg=T["accent"])
        elif job.state in (flatpak.FAILED, flatpak.CANCELLED):
            failed = job.state == flatpak.FAILED
            self.state.config(text=t('apps.state.failed' if failed else 'apps.state.stopped'),
                              fg=T["pink"])
            self.retry_btn.pack(side="right", padx=(0, self.page.px(8)))
            if failed:
                self.error.config(text=job.error)
                self.error.pack(anchor="w", fill="x", pady=(self.page.px(4), 0))
                self.burst(True)
            self.page.ticks_changed()
            return
        self.retry_btn.pack_forget()
        self.error.pack_forget()
        self.page.ticks_changed()


class InstallPage(Page):
    """Shared by Games and Apps: rows of apps and an Install button."""

    rows: List[AppRow]

    def add_rows(self, entries: List[catalog_mod.Entry]):
        for entry in entries:
            row = AppRow(self.col, self, entry)
            row.pack(fill="x", pady=(0, self.px(6)))
            self.rows.append(row)

    def install_bar(self) -> tk.Frame:
        """Pinned under the list, so Install is in reach wherever the list is scrolled."""
        holder = tk.Frame(self, bg=T["bg"], highlightthickness=0)
        holder.pack(side="bottom", fill="x", before=self.scroller)
        tk.Frame(holder, bg=T["line"], height=1).pack(fill="x")
        bar = tk.Frame(holder, bg=T["bg"])
        bar.pack(fill="x", padx=self.px(28), pady=self.px(10))
        self.install_btn = self.button(bar, t('apps.install_none'), self.install, "primary")
        self.install_btn.set_enabled(False)
        return bar

    def ticks_changed(self):
        n = sum(1 for r in self.rows if r.ticked)
        self.install_btn.set_text(t('apps.install', n=n) if n else t('apps.install_none'))
        self.install_btn.set_enabled(n > 0)

    def install(self):
        chosen = [r for r in self.rows if r.ticked]
        if not chosen:
            return
        for r in chosen:
            r.tick.set(False)
        self.app.install([r.entry for r in chosen])
        self.ticks_changed()


class GamesPage(InstallPage):
    def build(self):
        self.rows = []
        self.title(t('games.title'))
        self.para(t('games.intro'))
        self.micro(t('games.launchers'))
        self.add_rows(self.app.catalog.launchers)
        self.install_bar()
        if core.app_installed('dev.wolklaw.SparkGames', 'spark-games'):
            self.para(t('games.spark_games'), muted=True, pady=(12, 0))
        self.micro(t('games.anticheat.label'), colour=T["gold"], pady=(22, 6))
        box = self.panel()
        inner = tk.Frame(box.inner, bg=T["panel"])
        inner.pack(fill="x", padx=self.px(12), pady=self.px(10))
        self.para(t('games.anticheat'), inner, size=9, pady=(0, 8), wrap=self.px(620))
        self.button(inner, t('games.anticheat.button'), lambda: self.app.action('anticheat'))
        self.para(t('games.later'), muted=True, pady=(14, 0))


class AppsPage(InstallPage):
    def build(self):
        self.rows = []
        self.title(t('apps.title'))
        self.para(t('apps.intro'))
        for cat in self.app.catalog.categories:
            self.micro(cat.label(LANG))
            self.add_rows(cat.apps)
        bar = self.install_bar()
        self.button(bar, t('apps.store'), lambda: self.app.action('store'))
        self.para(t('apps.flathub'), muted=True, pady=(14, 0))


# ─── 4. Files from Windows ────────────────────────────────────

class WindowsPage(Page):
    def build(self):
        self.title(t('win.title'))
        self.para(t('win.intro'))
        self.para(t('win.safe'), muted=True)
        bar = self.row(pady=(4, 0))
        self.scan_btn = self.button(bar, t('win.scan'), self.scan)
        self.drives = tk.Frame(self.col, bg=T["bg"])
        self.drives.pack(fill="x", pady=(self.px(10), 0))
        self.area = tk.Frame(self.col, bg=T["bg"])
        self.area.pack(fill="x")
        self.scanned = False
        self.cancel = threading.Event()
        self.copying = False
        self.users: List[windows.WindowsUser] = []
        self.user: Optional[windows.WindowsUser] = None
        self.ticks: Dict[str, Toggle] = {}
        self.sizes: Dict[str, tk.Label] = {}

    def shown(self):
        if not self.scanned:
            self.scan()

    def stop(self):
        self.cancel.set()

    # drives
    def scan(self):
        if self.copying:
            return
        self.scanned = True
        self.clear(self.drives)
        self.clear(self.area)
        self.para(t('win.scanning'), self.drives, muted=True)
        self.app.bg(windows.list_partitions, self._scanned)

    def _scanned(self, result):
        self.clear(self.drives)
        if isinstance(result, Exception):
            result = ([], str(result))
        parts, problem = result
        if problem:
            self.para(t('win.lsblk_failed', error=problem), self.drives, colour=T["pink"])
            self.app.event(error=True)
            return
        if not parts:
            self.para(t('win.none'), self.drives, muted=True)
            return
        self.micro(t('win.drives'), self.drives, pady=(4, 6))
        for part in parts:
            box = self.panel(self.drives, pady=(0, 6))
            line = tk.Frame(box.inner, bg=T["panel"])
            line.pack(fill="x", padx=self.px(12), pady=self.px(8))
            name = part.label or part.name
            tk.Label(line, text=f"{name}  ·  {core.human_size(part.size)}  ·  {part.path}",
                     bg=T["panel"], fg=T["text"], font=self.app.font(9),
                     anchor="w").pack(side="left")
            if part.locked:
                tk.Label(line, text=t('win.locked'), bg=T["panel"], fg=T["gold"],
                         font=self.app.font(8)).pack(side="right")
            else:
                WolkButton(line, t('win.open'), lambda p=part: self.mount(p), self.app.font(8),
                           padx=8, pady=2).pack(side="right")
        self.app.event()

    def mount(self, part: windows.Partition):
        if self.copying:
            return
        self.clear(self.area)
        self.para(t('win.mounting', name=part.label or part.name), self.area, muted=True,
                  pady=(12, 0))

        def work():
            point, problem = windows.mount_read_only(part)
            users = windows.find_users(point) if point else []
            return point, problem, users

        self.app.bg(work, self._mounted)

    def _mounted(self, result):
        self.clear(self.area)
        if isinstance(result, Exception):
            result = (None, str(result), [])
        point, problem, users = result
        if not point:
            self.para(problem, self.area, colour=T["pink"], pady=(12, 0))
            self.app.event(error=True)
            return
        if not users:
            self.para(t('win.no_users', where=point), self.area, muted=True, pady=(12, 0))
            self.app.event()
            return
        self.users = users
        self.micro(t('win.account'), self.area, pady=(16, 6))
        if len(users) > 1:
            pick = Segmented(self.area, [(u.name, u.name) for u in users], users[0].name,
                             self.pick_user, self.app.font(8))
            pick.pack(anchor="w", pady=(0, self.px(8)))
        else:
            self.para(users[0].name, self.area, pady=(0, 4))
        self.folders = tk.Frame(self.area, bg=T["bg"])
        self.folders.pack(fill="x")
        self.pick_user(users[0].name)
        self.app.event()

    def pick_user(self, name: str):
        if self.copying:
            return
        self.user = next(u for u in self.users if u.name == name)
        self.clear(self.folders)
        self.ticks, self.sizes = {}, {}
        for folder in self.user.folders:
            box = self.panel(self.folders, pady=(0, 6))
            line = tk.Frame(box.inner, bg=T["panel"])
            line.pack(fill="x", padx=self.px(12), pady=self.px(7))
            tick = Toggle(line, folder.key, folder.key != 'Downloads', lambda _v: None,
                          self.app.font(9))
            tick.pack(side="left")
            self.ticks[folder.key] = tick
            size = tk.Label(line, text=t('win.measuring'), bg=T["panel"], fg=T["dim"],
                            font=self.app.font(8, False))
            size.pack(side="left", padx=(self.px(10), 0))
            self.sizes[folder.key] = size
            tk.Label(line, text=f"→ {windows.destination(folder)}", bg=T["panel"], fg=T["muted"],
                     font=self.app.font(8, False)).pack(side="right")
        bar = self.row(self.folders, pady=(10, 0))
        self.copy_btn = self.button(bar, t('win.copy'), self.copy, "primary")
        self.cancel_btn = WolkButton(bar, t('win.cancel'), self.cancel.set, self.app.font(9),
                                     "danger")
        self.progress_label = tk.Label(self.folders, text="", bg=T["bg"], fg=T["muted"],
                                       font=self.app.font(8), anchor="w")
        self.progress = Strip(self.folders, height=self.px(3))
        self.result = tk.Frame(self.folders, bg=T["bg"])
        self.result.pack(fill="x")
        user = self.user

        def work():
            for folder in user.folders:
                if self.cancel.is_set():
                    return
                folder.size, folder.files = windows.measure(folder.path, self.cancel)
                self.app.post(self._measured, user, folder)

        self.app.bg(work)

    def _measured(self, user, folder):
        label = self.sizes.get(folder.key)
        if user is self.user and label is not None and label.winfo_exists():
            label.config(text=t('win.size' if folder.files != 1 else 'win.size.one',
                                size=core.human_size(folder.size or 0), files=folder.files or 0))

    def copy(self):
        if self.copying or self.user is None:
            return
        chosen = [f for f in self.user.folders if self.ticks[f.key].value]
        if not chosen:
            self.app.set_status(t('win.tick_one'), T["gold"])
            return
        self.copying = True
        self.cancel.clear()
        self.copy_btn.set_enabled(False)
        self.scan_btn.set_enabled(False)
        self.cancel_btn.pack(side="left")
        self.clear(self.result)
        self.progress_label.config(text=t('win.planning'), fg=T["muted"])
        self.progress_label.pack(fill="x", pady=(self.px(12), self.px(4)), before=self.result)
        self.progress.pack(fill="x", before=self.result)
        self.progress.draw(fraction=0)
        last = [0.0]

        def progress(done, total, name):
            now = time.monotonic()
            if now - last[0] > 0.12 or not name:
                last[0] = now
                self.app.post(self._progress, done, total, name)

        def work():
            plan, claimed = windows.Plan(), set()
            for folder in chosen:
                plan.extend(windows.plan_copy(folder.path, windows.destination(folder), claimed))
                if self.cancel.is_set():
                    return windows.Summary(cancelled=True)
            return windows.copy_plan(plan, progress, self.cancel)

        self.app.bg(work, self._copied)
        self.app.event()

    def _progress(self, done, total, name):
        if not self.progress.winfo_exists():
            return
        self.progress.draw(fraction=done / total if total else 1.0)
        self.progress_label.config(text=t('win.copying', name=name or '…',
                                          done=core.human_size(done),
                                          total=core.human_size(total)), fg=T["accent"])

    def _copied(self, summary):
        self.copying = False
        self.scan_btn.set_enabled(True)
        if not self.copy_btn.winfo_exists():
            return
        self.copy_btn.set_enabled(True)
        self.cancel_btn.pack_forget()
        self.progress.pack_forget()
        self.progress_label.pack_forget()
        self.clear(self.result)
        if isinstance(summary, Exception):
            self.para(t('win.copy_failed', error=summary), self.result, colour=T["pink"],
                      pady=(12, 0))
            self.app.event(error=True)
            return
        box = self.panel(self.result, pady=(12, 0))
        inner = tk.Frame(box.inner, bg=T["panel"])
        inner.pack(fill="x", padx=self.px(12), pady=self.px(10))
        head = 'win.done.cancelled' if summary.cancelled else 'win.done'
        self.micro(t(head), inner, colour=T["gold"] if summary.cancelled else T["accent"],
                   pady=(0, 6))
        lines = [t('win.done.copied', n=summary.copied,
                   size=core.human_size(summary.copied_bytes))]
        if summary.skipped:
            lines.append(t('win.done.skipped', n=summary.skipped))
        if summary.renamed:
            lines.append(t('win.done.renamed', n=summary.renamed))
        if summary.failed:
            lines.append(t('win.done.failed', n=len(summary.failed)))
        self.para('\n'.join(lines), inner, size=9, pady=(0, 4))
        for path, error in summary.failed[:6]:
            self.para(f"{path}: {error}", inner, size=8, colour=T["pink"], pady=(0, 2))
        if len(summary.failed) > 6:
            self.para(t('win.done.more', n=len(summary.failed) - 6), inner, size=8,
                      colour=T["pink"])
        box.burst(bool(summary.failed))
        self.app.event(error=bool(summary.failed))


# ─── 5. Check this PC ─────────────────────────────────────────

class ChecksPage(Page):
    def build(self):
        self.title(t('checks.title'))
        self.para(t('checks.intro'))
        bar = self.row(pady=(0, 6))
        self.again = self.button(bar, t('checks.again'), self.run)
        self.list = tk.Frame(self.col, bg=T["bg"])
        self.list.pack(fill="x", pady=(self.px(8), 0))
        self.running = False
        self.ran = False
        self.boxes: Dict[str, GlitchPanel] = {}

    def shown(self):
        if not self.ran:
            self.run()

    def run(self):
        if self.running:
            return
        self.running = True
        self.ran = True
        self.again.set_enabled(False)
        self.clear(self.list)
        self.boxes = {}
        for fn in checks.CHECKS:
            key = fn.__name__[6:]
            box = self.panel(self.list, pady=(0, 6))
            self.boxes[key] = box
            line = tk.Frame(box.inner, bg=T["panel"])
            line.pack(fill="x", padx=self.px(12), pady=self.px(9))
            tk.Label(line, text=f"○ {t('check.' + key).upper()}", bg=T["panel"], fg=T["dim"],
                     font=self.app.font(9)).pack(side="left")
            tk.Label(line, text=t('checks.checking'), bg=T["panel"], fg=T["dim"],
                     font=self.app.font(8, False)).pack(side="right")

        def work():
            for fn in checks.CHECKS:
                key = fn.__name__[6:]
                try:
                    result = fn()
                except Exception as exc:     # noqa: BLE001
                    result = checks.Check(key, t('check.' + key), checks.WARN,
                                          t('check.crashed'), str(exc))
                self.app.post(self._show, result)

        self.app.bg(work, self._done)

    def _show(self, check: checks.Check):
        box = self.boxes.get(check.key)
        if box is None or not box.winfo_exists():
            return
        self.clear(box.inner)
        ok = check.status == checks.OK
        colour = T["accent"] if ok else T["gold"]
        inner = tk.Frame(box.inner, bg=T["panel"])
        inner.pack(fill="x", padx=self.px(12), pady=self.px(9))
        top = tk.Frame(inner, bg=T["panel"])
        top.pack(fill="x")
        tk.Label(top, text=f"● {check.title.upper()}", bg=T["panel"], fg=colour,
                 font=self.app.font(9)).pack(side="left")
        tk.Label(top, text=t('checks.ok') if ok else t('checks.look'), bg=T["panel"], fg=colour,
                 font=self.app.font(8)).pack(side="right")
        self.para(check.summary, inner, size=9, pady=(5, 0), wrap=self.px(620))
        if check.detail:
            self.para(check.detail, inner, size=8, muted=True, pady=(3, 0), wrap=self.px(620))
        if check.fixes:
            bar = tk.Frame(inner, bg=T["panel"])
            bar.pack(anchor="w", pady=(self.px(8), 0))
            for label, key in check.fixes:
                WolkButton(bar, label, lambda k=key: self.app.action(k), self.app.font(8),
                           padx=8, pady=2).pack(side="left", padx=(0, self.px(6)))
        box.burst(not ok)

    def _done(self, _result):
        self.running = False
        self.again.set_enabled(True)
        self.app.event()


# ─── 6. Done ──────────────────────────────────────────────────

class DonePage(Page):
    def build(self):
        self.title(t('done.title'))
        self.para(t('done.intro'))
        for key, button, action in (('store', 'done.store.button', 'store'),
                                    ('snip', 'done.snip.button', 'snip'),
                                    ('settings', 'done.settings.button', 'settings')):
            box = self.panel(pady=(0, 8))
            inner = tk.Frame(box.inner, bg=T["panel"])
            inner.pack(fill="x", padx=self.px(12), pady=self.px(10))
            self.micro(t(f'done.{key}.title'), inner, colour=T["accent"], pady=(0, 4))
            self.para(t(f'done.{key}'), inner, size=9, pady=(0, 8), wrap=self.px(620))
            WolkButton(inner, t(button), lambda a=action: self.app.action(a),
                       self.app.font(8), padx=8, pady=2).pack(anchor="w")
        bar = self.row(pady=(16, 0))
        self.show_again = Toggle(bar, t('done.show_again'), self.app.show_again,
                                 self.app.set_show_again, self.app.font(9))
        self.show_again.pack(side="left")
        self.para(t('done.menu', name=APP_NAME), muted=True, pady=(12, 0))
        self.busy = self.para('', colour=T["gold"], pady=(8, 0))

    def shown(self):
        if self.app.installer.busy():
            self.busy.config(text=t('done.still_installing'))
        else:
            self.busy.config(text='')


PAGE_CLASSES: Dict[str, Any] = {
    'welcome': WelcomePage, 'games': GamesPage, 'apps': AppsPage,
    'windows': WindowsPage, 'checks': ChecksPage, 'done': DonePage,
}
