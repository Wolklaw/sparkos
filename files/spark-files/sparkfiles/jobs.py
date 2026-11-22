"""The long jobs' panel at the bottom of the window (progress, speed, time left, pause and
cancel), the question about a name that's already taken, and the report when some files
couldn't be copied, moved or deleted."""

import os
from typing import Dict, Optional

import tkinter as tk

from .core import full_date, home_short, human_size
from .ops import CANCEL, KEEP_BOTH, REPLACE, SKIP, Job
from .text import t
from .ui import Check, Dialog, Progress, Timers
from .widgets import T, IconButton


def job_title(job: Job) -> str:
    n = len(job.sources)
    where = home_short(job.dest) if job.dest else ''
    if where:
        where = os.path.basename(job.dest.rstrip('/')) or job.dest
    return t(f'job.{job.kind}', n=n, where=where)


def duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return ''
    seconds = int(seconds)
    if seconds < 60:
        return t('time.seconds', n=max(1, seconds))
    if seconds < 3600:
        return t('time.minutes', n=(seconds + 30) // 60)
    return t('time.hours', h=seconds // 3600, m=(seconds % 3600) // 60)


class JobRow(tk.Frame):
    def __init__(self, parent: tk.Misc, app, job: Job):
        super().__init__(parent, bg=T["panel"])
        self.app, self.job = app, job
        px = app.px
        top = tk.Frame(self, bg=T["panel"])
        top.pack(fill='x')
        self.title = tk.Label(top, text=job_title(job), font=app.font(9, True),
                              bg=T["panel"], fg=T["text"], anchor='w')
        self.title.pack(side='left')
        self.cancel_b = IconButton(top, 'close', self.cancel, px(20))
        self.cancel_b.pack(side='right')
        app.tooltip.attach(self.cancel_b, t('job.cancel'))
        self.pause_b = IconButton(top, 'pause', self.toggle, px(20))
        self.pause_b.pack(side='right', padx=(0, px(2)))
        app.tooltip.attach(self.pause_b, lambda: t('job.resume') if job.state == 'paused'
                           else t('job.pause'))
        self.bar = Progress(self, height=max(4, px(5)), bg=T["panel"])
        self.bar.pack(fill='x', pady=(px(3), px(2)))
        self.detail = tk.Label(self, text='', font=app.font(8, False), bg=T["panel"],
                               fg=T["muted"], anchor='w')
        self.detail.pack(fill='x')

    def toggle(self) -> None:
        if self.job.state == 'paused':
            self.job.resume()
        else:
            self.job.pause()
        self.update_row()

    def cancel(self) -> None:
        self.job.cancel()
        self.update_row()

    def update_row(self) -> None:
        job = self.job
        paused = job.state == 'paused'
        self.pause_b.set_icon('play' if paused else 'pause')
        self.bar.set(job.fraction, T["gold"] if paused else
                     (T["pink"] if job.errors else T["accent"]))
        if job.state == 'scanning':
            text = t('job.counting', n=job.total_files)
        elif job.waiting_for_answer:
            text = t('job.waiting')
        elif paused:
            text = t('job.paused')
        elif job.kind in ('copy', 'move') and job.total_bytes:
            text = t('job.bytes', done=human_size(job.done_bytes),
                     total=human_size(job.total_bytes))
            speed = job.speed()
            if speed > 0:
                text += f" · {human_size(speed)}/s"
                left = job.eta()
                if left is not None and left > 2:
                    text += ' · ' + t('job.left', time=duration(left))
        else:
            text = t('job.files', done=job.done_files, total=job.total_files)
        if job.current and job.state == 'running':
            name = os.path.basename(job.current)
            if len(name) > 40:
                name = name[:39] + '…'
            text += ' · ' + name
        self.detail.configure(text=text)


class JobsPanel(Timers, tk.Frame):
    """Shown while something runs; one row per job. Updates five times a second while there
    is a job, never when there isn't."""

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["panel"], highlightthickness=1,
                         highlightbackground=T["line"])
        self.app = app
        self.rows: Dict[int, JobRow] = {}
        self._tick_id: Optional[str] = None
        self.inner = tk.Frame(self, bg=T["panel"], padx=app.px(10), pady=app.px(6))
        self.inner.pack(fill='both', expand=True)

    def add(self, job: Job) -> None:
        if id(job) in self.rows or not job.active:
            return
        row = JobRow(self.inner, self.app, job)
        row.pack(fill='x', pady=(0, self.app.px(4)))
        self.rows[id(job)] = row
        self.show()
        self._tick()

    def remove(self, job: Job) -> None:
        row = self.rows.pop(id(job), None)
        if row is not None:
            row.destroy()
        if not self.rows:
            self.hide()

    def show(self) -> None:
        if not self.winfo_ismapped():
            self.master.show_jobs(self)

    def hide(self) -> None:
        self.master.hide_jobs(self)

    def _tick(self) -> None:
        if self._tick_id is not None:
            return

        def tick():
            self._tick_id = None
            if not self.winfo_exists() or not self.rows:
                return
            for row in list(self.rows.values()):
                row.update_row()
            self._tick_id = self.after(200, tick)
        self._tick_id = self.after(200, tick)


class ClashDialog(Dialog):
    """A name is taken: replace, skip, keep both, or cancel the whole job; optionally the
    same answer for every clash left in this job."""

    def __init__(self, app, parent: tk.Misc, job: Job, src: str, target: str):
        super().__init__(app, parent, t('clash.title'))
        self.job = job
        px = app.px
        f9 = app.font(9, False)
        is_dir = os.path.isdir(target)
        name = os.path.basename(target)
        folder = home_short(os.path.dirname(target))
        tk.Label(self.content, text=t('clash.folder_text' if is_dir else 'clash.text',
                                      name=name, folder=folder),
                 font=app.font(10, False), bg=T["panel"], fg=T["text"], justify='left',
                 wraplength=px(460), anchor='w').pack(anchor='w')
        grid = tk.Frame(self.content, bg=T["panel"])
        grid.pack(anchor='w', pady=(px(10), 0))
        for row, (label, path) in enumerate(((t('clash.existing'), target),
                                             (t('clash.new'), src))):
            try:
                st = os.stat(path)
                info = f"{human_size(st.st_size) if not os.path.isdir(path) else ''}  " \
                       f"{full_date(st.st_mtime)}"
            except OSError:
                info = '?'
            tk.Label(grid, text=label.upper(), font=app.font(8, True), bg=T["panel"],
                     fg=T["muted"], anchor='w').grid(row=row, column=0, sticky='w',
                                                     padx=(0, px(12)))
            tk.Label(grid, text=info.strip(), font=f9, bg=T["panel"], fg=T["text"],
                     anchor='w').grid(row=row, column=1, sticky='w')
        self.all = Check(self.content, t('clash.all'), False, f9)
        self.all.pack(anchor='w', pady=(px(12), 0))
        self.button(t('clash.cancel'), lambda: self.answer(CANCEL))
        self.button(t('clash.skip'), lambda: self.answer(SKIP))
        self.button(t('clash.keep_both'), lambda: self.answer(KEEP_BOTH))
        b = self.button(t('clash.replace'), lambda: self.answer(REPLACE), 'primary')
        self.bind('<Return>', lambda _e: self.answer(REPLACE))
        self.focus_first = lambda: b.label.focus_set()

    def answer(self, choice: str) -> None:
        self.job.answer(choice, self.all.value)
        self.destroy()

    def cancel(self) -> None:
        self.answer(CANCEL)


def show_errors(app, parent: tk.Misc, job: Job) -> None:
    d = Dialog(app, parent, t('errors.title'))
    px = app.px
    tk.Label(d.content, text=t('errors.text', n=len(job.errors)), font=app.font(10, False),
             bg=T["panel"], fg=T["text"], anchor='w', justify='left',
             wraplength=px(520)).pack(anchor='w', pady=(0, px(8)))
    box = tk.Text(d.content, height=min(12, len(job.errors) + 1), width=72,
                  font=app.font(9, False), bg=T["out_bg"], fg=T["text"], relief='flat',
                  highlightthickness=1, highlightbackground=T["line"], wrap='none')
    for path, why in job.errors[:500]:
        text = t(why) if why.startswith(('error.',)) else why
        box.insert('end', f"{home_short(path) if path else '—'}: {text}\n")
    box.configure(state='disabled')
    box.pack(fill='both', expand=True)
    d.button(t('button.close'), d.cancel, 'primary')
    d.place_and_show()
