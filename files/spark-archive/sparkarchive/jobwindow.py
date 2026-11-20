"""The small window Dolphin's right-click menu opens: Extract here, Extract to folder,
Compress to .zip, Compress to .tar.zst. It shows progress and Cancel, asks for a password
or before overwriting, and closes by itself when everything went through cleanly. A job
that finishes within a third of a second never shows a window at all."""

import os
from typing import List, Optional

import tkinter as tk

from . import APP_NAME
from .core import show_in_file_manager
from .jobs import CompressJob, ExtractJob, Job, Result
from .text import t
from .ui import Look, Progress, home_short, middle, result_lines, version_chip
from .widgets import T, Strip

SHOW_AFTER_MS = 350
CLOSE_AFTER_MS = 900


class JobWindow(Look):
    def __init__(self, action: str, paths: List[str]):
        super().__init__()
        self.action, self.paths = action, paths
        self.results: List[Result] = []
        self.job: Optional[Job] = None
        self.index = -1
        self.exit_code = 0
        self._build()
        self.root.after(SHOW_AFTER_MS, self._show_if_busy)
        self.root.after(10, self._next)

    def _build(self) -> None:
        px, bg, root = self.px, T["bg"], self.root
        root.protocol("WM_DELETE_WINDOW", self._close_request)
        root.resizable(True, False)
        word = 'EXTRACTING' if self.action.startswith('extract') else 'COMPRESSING'
        frame = tk.Frame(root, bg=bg)
        frame.pack(fill="both", expand=True)
        self.mark, self.title, self.status, head = self.header(frame, word, size=12)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        version_chip(self, head).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(frame, height=px(2))
        self.strip.pack(fill="x")
        body = tk.Frame(frame, bg=bg)
        body.pack(fill="both", expand=True, padx=px(16), pady=px(12))
        self.body = body
        self.progress = Progress(body, self, self.cancel)
        self.progress.pack(fill="x")
        self.result_box = tk.Frame(body, bg=bg)
        root.geometry(f"{px(560)}x{px(200)}")
        root.minsize(px(420), px(160))
        root.bind('<Escape>', lambda _e: self.cancel())
        self.glitch.add(self.title, self.mark, self.strip)

    def _show_if_busy(self) -> None:
        if self.job is not None:
            self.root.deiconify()

    # ─── running ──────────────────────────────────────────────

    def _next(self) -> None:
        self.index += 1
        if self.action.startswith('compress'):
            if self.index > 0:
                return self._finished()
            fmt = 'zip' if self.action == 'compress-zip' else 'tar.zst'
            self.job = CompressJob(self.paths, fmt, asker=self.bridge.ask)
            self.what = os.path.basename(self.paths[0]) if len(self.paths) == 1 else \
                os.path.basename(os.path.dirname(os.path.abspath(self.paths[0])))
        else:
            if self.index >= len(self.paths):
                return self._finished()
            path = os.path.abspath(self.paths[self.index])
            self.job = ExtractJob(path, os.path.dirname(path),
                                  new_folder=self.action == 'extract-folder',
                                  asker=self.bridge.ask)
            self.what = os.path.basename(path)
        self.job.start()
        self._poll()

    def _title(self) -> str:
        if isinstance(self.job, CompressJob):
            name = os.path.basename(self.job.output) if self.job.output else self.what
            return t('progress.compress_title', name=middle(name, 50))
        title = t('progress.extract_title', name=middle(self.what, 50))
        if len(self.paths) > 1:
            title += f"  ({self.index + 1}/{len(self.paths)})"
        return title

    def _poll(self) -> None:
        job = self.job
        if job is None:
            return
        self.bridge.pump()
        if job.phase == 'done' and job.result is not None:
            self.results.append(job.result)
            if not job.result.ok and not job.result.cancelled:
                self.glitch.now(self.title, self.mark, strong=True)
            self.job = None
            if job.result.cancelled:
                return self._finished()
            return self._next()
        self.progress.show_job(job, self._title())
        word = 'status.reading' if job.phase == 'reading' else (
            'status.compressing' if isinstance(job, CompressJob) else 'status.extracting')
        self.status.config(text=f"● {t(word)}", fg=T["accent"])
        self.root.after(100, self._poll)

    def cancel(self) -> None:
        if self.job is not None:
            self.job.cancel()
            self.progress.cancelling()
        else:
            self.root.destroy()

    def _close_request(self) -> None:
        if self.job is not None:
            self.bridge.release()
            self.job.cancel()
            self.progress.cancelling()
            self.root.after(100, self._close_when_stopped)
        else:
            self.root.destroy()

    def _close_when_stopped(self) -> None:
        self.bridge.release()
        if self.job is not None and self.job.phase != 'done':
            self.root.after(100, self._close_when_stopped)
            return
        self.exit_code = 1
        self.root.destroy()

    # ─── the end ──────────────────────────────────────────────

    def _finished(self) -> None:
        self.job = None
        clean = all(r.ok and not r.problems and not r.skipped for r in self.results)
        cancelled = any(r.cancelled for r in self.results)
        failed = [r for r in self.results if not r.ok and not r.cancelled]
        self.exit_code = 0 if clean else (2 if cancelled else 1)
        self.progress.pack_forget()
        px, bg = self.px, T["bg"]
        kind = 'compress' if self.action.startswith('compress') else 'extract'
        if failed:
            self.status.config(text=f"● {t('status.error')}", fg=T["pink"])
        elif cancelled:
            self.status.config(text=f"● {t('status.cancelled')}", fg=T["gold"])
        else:
            self.status.config(text=f"● {t('status.done')}", fg=T["accent"])
        box = self.result_box
        box.pack(fill="both", expand=True)
        lines: List[str] = []
        heads = []
        for res in self.results:
            head, more, _err = result_lines(res, kind)
            heads.append(head)
            lines += more
        for head in heads:
            tk.Label(box, text=head, bg=bg, fg=T["text"], font=self.font(9, False),
                     anchor="w", justify="left", wraplength=px(520)).pack(anchor="w", fill="x")
        if lines:
            text = tk.Text(box, height=min(8, len(lines)), bg=T["panel"], fg=T["muted"],
                           relief="flat", font=self.font(8, False), wrap="none",
                           highlightthickness=1, highlightbackground=T["line"])
            text.insert('1.0', '\n'.join(lines))
            text.configure(state='disabled')
            text.pack(fill="both", expand=True, pady=(px(8), 0))
        buttons = tk.Frame(box, bg=bg)
        buttons.pack(fill="x", pady=(px(10), 0))
        close = self.button(buttons, t('button.close'), self.root.destroy,
                            "primary" if not clean else "ghost")
        close.pack(side="right")
        target = next((r.output for r in reversed(self.results) if r.output and r.ok), None)
        if target:
            self.button(buttons, t('button.show'),
                        lambda: (show_in_file_manager(target), self.root.destroy())).pack(
                side="right", padx=(0, px(8)))
        self.root.resizable(True, True)
        self.root.update_idletasks()
        self.root.geometry(f"{max(px(560), self.root.winfo_reqwidth())}x"
                           f"{self.root.winfo_reqheight()}")
        if clean and not self.root.winfo_viewable():
            self.root.destroy()                  # fast and clean: never shown
            return
        if clean:
            self.root.after(CLOSE_AFTER_MS, self.root.destroy)
        else:
            self.root.deiconify()
            self.glitch.now(self.title, strong=bool(failed))

    def run(self) -> int:
        self.root.mainloop()
        return self.exit_code


__all__ = ['JobWindow', 'APP_NAME', 'home_short']
