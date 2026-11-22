"""The Installed, Updates and Queue pages."""

import time
from typing import TYPE_CHECKING, Dict, Optional

import tkinter as tk

from .appstream import fold
from .core import size as fmt_size
from .jobs import CANCELLED, DONE, FAILED, RUNNING, WAITING, Job
from .pages import clear, notice, section, wrap_on_resize
from .text import t
from .ui import Card, Progress, chip, scrollable
from .widgets import T, WolkButton

if TYPE_CHECKING:
    from .app import Store


def row_card(store: 'Store', parent: tk.Misc, app_id: str, name: str, sub: str,
             icon_path: Optional[str], on_open) -> Card:
    """A one-line row: icon, name and a muted line under it; buttons go in .right."""
    px = store.px
    card = Card(parent, command=on_open)
    card.pack(fill="x", padx=px(14), pady=px(2))
    inner = card.inner
    bg = inner.cget("bg")
    icon = tk.Label(inner, bg=bg, bd=0)
    icon.pack(side="left", padx=px(10), pady=px(8))
    store.icons.put(icon, app_id, icon_path, px(32))
    card.right = tk.Frame(inner, bg=bg)
    card.right.pack(side="right", padx=(0, px(10)))
    col = tk.Frame(inner, bg=bg)
    col.pack(side="left", fill="x", expand=True)
    tk.Label(col, text=name, font=store.font(10), bg=bg, fg=T["text"], anchor="w"
             ).pack(fill="x")
    sub_label = tk.Label(col, text=sub, font=store.font(8, False), bg=bg, fg=T["muted"],
                         anchor="w", justify="left")
    sub_label.pack(fill="x")
    card.sub = sub_label
    card.col = col
    return card


def own_click(widget: tk.Misc) -> tk.Misc:
    """Mark a button inside a card so a click on it doesn't also open the card."""
    widget._own_click = True
    for child in widget.winfo_children():
        own_click(child)
    return widget


class InstalledPage:
    def __init__(self, store: 'Store'):
        self.store = store
        self.frame, self.inner, self.canvas = scrollable(store.body, T["bg"], store.px)
        self.built_for = None

    def refresh(self, force: bool = False):
        store, px = self.store, self.store.px
        key = (store.installed_stamp, store.spark_stamp, store.installed_loaded,
               len(store.catalog.apps), tuple((j.id, j.state) for j in store.queue.active()))
        if key == self.built_for and not force:
            return
        self.built_for = key
        y = self.canvas.yview()[0]
        clear(self.inner)
        spark = [s for s in store.spark if s.installed]
        section(store, self.inner, t('home.spark'), t('installed.spark_note', n=len(spark)))
        for sp in spark:
            from . import sparkapps
            where = t('spark.in_image_short') if sp.installed == 'system' else t('scope.user')
            card = row_card(store, self.inner, sp.id, sp.name,
                            f"{where}" + (f" · {sp.version}" if sp.version else ""),
                            sparkapps.icon_path(sp), lambda s=sp: store.open_app(s))
            own_click(WolkButton(card.right, t('btn.open'), lambda s=sp: store.launch_spark(s),
                                 store.font(8), padx=10, pady=4)).pack(side="right")
            card.wire()
        apps = sorted(store.installed.values(), key=lambda a: fold(a.name))
        total = sum(a.size or 0 for a in apps)
        section(store, self.inner, t('installed.flatpak'),
                t('installed.count', n=len(apps), size=fmt_size(total)) if apps else '')
        if not store.flatpak_ok:
            tk.Label(self.inner, text=t('flatpak.missing'), font=store.font(9, False),
                     bg=T["bg"], fg=T["muted"], anchor="w").pack(fill="x", padx=px(16))
        elif not store.installed_loaded:
            tk.Label(self.inner, text=t('app.checking'), font=store.font(9, False),
                     bg=T["bg"], fg=T["muted"], anchor="w").pack(fill="x", padx=px(16))
        elif not apps:
            tk.Label(self.inner, text=t('installed.none'), font=store.font(9, False),
                     bg=T["bg"], fg=T["muted"], anchor="w").pack(fill="x", padx=px(16))
        for inst in apps:
            scope = t('scope.user') if inst.scope == 'user' else t('scope.system')
            bits = [scope]
            if inst.version:
                bits.append(inst.version)
            if inst.size:
                bits.append(fmt_size(inst.size))
            job = store.queue.for_app(inst.id)
            if job is not None and job.state in (RUNNING, WAITING):
                bits.append(t(f'doing.{job.kind}') + "…")
            card = row_card(store, self.inner, inst.id, inst.name, " · ".join(bits),
                            store.installed_icon(inst.id),
                            lambda i=inst: store.open_app(i.id))
            own_click(WolkButton(card.right, t('btn.open'), lambda i=inst: store.launch_id(i.id),
                                 store.font(8), padx=10, pady=4)).pack(side="right")
            card.wire()
        if store.flatpak_ok and store.installed_loaded:
            section(store, self.inner, t('unused.title'))
            note = tk.Label(self.inner, text=t('unused.note'), font=store.font(8, False),
                            bg=T["bg"], fg=T["muted"], anchor="w", justify="left")
            note.pack(fill="x", padx=px(16))
            wrap_on_resize(self.inner, [note], px(32), slack=px(40))
            job = store.queue.for_app('unused-user')
            button = WolkButton(self.inner, t('unused.button'), store.remove_unused,
                                store.font(8))
            button.pack(anchor="w", padx=px(14), pady=(px(6), 0))
            if job is not None and job.state in (RUNNING, WAITING):
                button.set_enabled(False)
        tk.Frame(self.inner, bg=T["bg"], height=px(20)).pack()
        if y:
            self.inner.after_idle(lambda: self.canvas.yview_moveto(y))


class UpdatesPage:
    def __init__(self, store: 'Store'):
        self.store = store
        self.frame, self.inner, self.canvas = scrollable(store.body, T["bg"], store.px)
        self.built_for = None

    def refresh(self, force: bool = False):
        store, px = self.store, self.store.px
        key = (store.updates_stamp, store.updates_busy, store.installed_stamp,
               tuple((j.id, j.state) for j in store.queue.active()))
        if key == self.built_for and not force:
            return
        self.built_for = key
        clear(self.inner)
        head = tk.Frame(self.inner, bg=T["bg"])
        head.pack(fill="x")
        section(store, head, t('updates.title'), self.checked_note())
        bar = tk.Frame(self.inner, bg=T["bg"])
        bar.pack(fill="x", padx=px(16), pady=(0, px(6)))
        check = WolkButton(bar, t('updates.check'), store.check_updates, store.font(8))
        check.pack(side="left")
        if store.updates_busy:
            check.set_enabled(False)
            check.set_text(t('updates.checking'))
        if store.updates:
            WolkButton(bar, t('updates.all'), store.update_all, store.font(8),
                       variant="primary").pack(side="left", padx=(px(8), 0))
        if store.updates_error:
            notice(store, self.inner, t('updates.error_title'),
                   t('updates.error', error=store.updates_error), T["pink"])
        if not store.flatpak_ok:
            tk.Label(self.inner, text=t('flatpak.missing'), font=store.font(9, False),
                     bg=T["bg"], fg=T["muted"], anchor="w").pack(fill="x", padx=px(16))
        elif not store.updates and store.updates_checked and not store.updates_error:
            tk.Label(self.inner, text=t('updates.none'), font=store.font(9, False), bg=T["bg"],
                     fg=T["accent"], anchor="w").pack(fill="x", padx=px(16), pady=(px(6), 0))
        for up in sorted(store.updates, key=lambda u: fold(store.name_of(u.id))):
            name = store.name_of(up.id)
            inst = store.installed.get(up.id)
            bits = [t('scope.user') if up.scope == 'user' else t('scope.system')]
            if inst and inst.version and up.version and inst.version != up.version:
                bits.append(f"{inst.version} → {up.version}")
            elif up.version:
                bits.append(up.version)
            job = store.queue.for_app(up.id)
            card = row_card(store, self.inner, up.id, name, " · ".join(bits),
                            store.installed_icon(up.id), lambda u=up: store.open_app(u.id))
            if job is not None and job.state in (RUNNING, WAITING):
                tk.Label(card.right, text=t(f'doing.{job.kind}').upper() + "…",
                         font=store.font(8), bg=T["panel"], fg=T["accent"]).pack(side="right")
            else:
                own_click(WolkButton(card.right, t('btn.update'),
                                     lambda u=up: store.update(u.id, u.scope), store.font(8),
                                     padx=10, pady=4)).pack(side="right")
            card.wire()
        if store.runtime_updates:
            tk.Label(self.inner, text=t('updates.runtimes', n=store.runtime_updates),
                     font=store.font(8, False), bg=T["bg"], fg=T["muted"], anchor="w",
                     justify="left").pack(fill="x", padx=px(16), pady=(px(8), 0))
        note = tk.Label(self.inner, text=t('updates.note'), font=store.font(8, False),
                        bg=T["bg"], fg=T["dim"], anchor="w", justify="left")
        note.pack(fill="x", padx=px(16), pady=(px(12), 0))
        wrap_on_resize(self.inner, [note], px(32))
        tk.Frame(self.inner, bg=T["bg"], height=px(20)).pack()

    def checked_note(self) -> str:
        store = self.store
        if not store.updates_checked:
            return ''
        when = time.strftime('%H:%M', time.localtime(store.updates_checked))
        return t('updates.checked', time=when, n=len(store.updates))


class QueuePage:
    def __init__(self, store: 'Store'):
        self.store = store
        self.frame, self.inner, self.canvas = scrollable(store.body, T["bg"], store.px)
        self.built_for = None
        self.rows: Dict[int, tuple] = {}

    def refresh(self, force: bool = False):
        store, px = self.store, self.store.px
        jobs = list(store.queue.jobs)
        key = tuple((j.id, j.state) for j in jobs)
        if key == self.built_for and not force:
            self.update_progress()
            return
        self.built_for = key
        for _card, bar, *_rest in self.rows.values():
            if bar is not None:
                bar.stop()
        self.rows.clear()
        clear(self.inner)
        section(store, self.inner, t('queue.title'), t('queue.note'))
        if not jobs:
            tk.Label(self.inner, text=t('queue.empty'), font=store.font(9, False), bg=T["bg"],
                     fg=T["muted"], anchor="w").pack(fill="x", padx=px(16))
        for job in jobs:
            self.row(job)
        if any(j.finished for j in jobs):
            bar = tk.Frame(self.inner, bg=T["bg"])
            bar.pack(fill="x", padx=px(16), pady=(px(10), 0))
            WolkButton(bar, t('queue.clear'), store.clear_finished, store.font(8)).pack(
                side="left")
        tk.Frame(self.inner, bg=T["bg"], height=px(20)).pack()
        self.update_progress()

    def row(self, job: Job):
        store, px = self.store, self.store.px
        verb = t(f'verb.{job.kind}')
        card = row_card(store, self.inner, job.app_id, f"{verb} {job.title}", "",
                        store.icon_for_id(job.app_id),
                        lambda j=job: store.open_app(j.app_id) if j.kind != 'catalog' else None)
        state_colour = {DONE: T["accent"], FAILED: T["pink"], CANCELLED: T["muted"],
                        RUNNING: T["accent"], WAITING: T["muted"]}[job.state]
        chip(card.right, t(f'state.{job.state}'), store.font(7), state_colour,
             job.state == RUNNING, px).pack(side="right", padx=(px(8), 0))
        bar = None
        if job.state in (RUNNING, WAITING):
            own_click(WolkButton(card.right, t('btn.cancel'), lambda j=job: store.queue.cancel(j),
                                 store.font(8), padx=10, pady=4)).pack(side="right")
        if job.state == FAILED:
            own_click(WolkButton(card.right, t('btn.retry'), lambda j=job: store.retry(j),
                                 store.font(8), variant="primary", padx=10, pady=4)
                      ).pack(side="right")
        if job.state == RUNNING:
            bar = Progress(card.col, height=px(5))
            bar.pack(fill="x", pady=(px(4), px(6)), padx=(0, px(10)))
        if job.state == FAILED and job.error:
            err = tk.Label(card.col, text=job.error, font=store.font(8, False),
                           bg=T["panel"], fg=T["pink"], anchor="w", justify="left")
            err.pack(fill="x", pady=(px(2), px(6)))
            wrap_on_resize(card.col, [err], px(10))
        card.wire()
        self.rows[job.id] = (card, bar, job)

    def update_progress(self):
        for card, bar, job in self.rows.values():
            if not card.winfo_exists():
                continue
            if job.state == RUNNING:
                pct = f"{round(job.progress * 100)}% · " if job.progress is not None else ""
                text = pct + (job.line[:120] if job.line else t('job.started'))
                if bar is not None:
                    bar.set(job.progress)
            elif job.state == WAITING:
                ahead = self.store.queue_position(job)
                text = t('job.waiting', n=ahead) if ahead else t('job.next')
            elif job.state == DONE:
                took = max(1, round(job.ended - job.started))
                text = t('job.done', secs=took)
            elif job.state == CANCELLED:
                text = t('job.cancelled')
            else:
                text = t('job.failed')
            if card.sub.cget("text") != text:
                card.sub.config(text=text)

