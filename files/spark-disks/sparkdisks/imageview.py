"""The Write image tab: an .iso or .img (or one packed as .gz, .xz, .bz2) onto a USB stick or SD
card. Only removable drives are offered, and ops.image_target refuses anything else, the system
disk and D: included."""

import os
import threading
from typing import Dict, Optional, Tuple

import tkinter as tk
from tkinter import filedialog

from . import imagewrite, safety
from .dialogs import Ask, Field, ask
from .model import Node, removable_drive
from .text import t
from .ui import make_table
from .viewkit import View, error_text, size_text
from .widgets import T, Toggle


class ImageView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        self.targets: Dict[str, Node] = {}
        self.cancel = threading.Event()
        self.progress: Tuple[str, int, int] = ('', 0, 0)
        self.writing = False
        self.verify = True
        pad = tk.Frame(self, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.heading(pad, t("image.heading")).pack(anchor="w")
        self.note(pad, t("image.note"), px(900)).pack(anchor="w", pady=(0, px(8)))

        self.heading(pad, t("image.file")).pack(anchor="w")
        row = tk.Frame(pad, bg=T["bg"])
        row.pack(fill="x", pady=(px(3), px(8)))
        self.path_var = tk.StringVar()
        self.path_var.trace_add("write", lambda *_: self._buttons())
        self.entry = tk.Entry(row, textvariable=self.path_var, bg=T["out_bg"], fg=T["text"],
                              insertbackground=T["accent"], relief="flat", highlightthickness=1,
                              highlightbackground=T["line2"], highlightcolor=T["accent"],
                              font=app.font(9, False))
        self.entry.pack(side="left", fill="x", expand=True, ipady=px(3))
        self.browse_button = self.button(row, t("btn.browse"), self.browse)
        self.browse_button.pack(side="left", padx=(px(8), 0))

        self.heading(pad, t("image.target")).pack(anchor="w")
        frame, self.tree = make_table(pad, ("size", "tag"), show="tree headings")
        self.tree.heading("#0", text=t("col.drive").upper(), anchor="w")
        self.tree.column("#0", width=px(460), anchor="w", stretch=True)
        self.tree.heading("size", text=t("col.size").upper(), anchor="e")
        self.tree.column("size", width=px(100), anchor="e", stretch=False)
        self.tree.heading("tag", text=t("col.tag").upper(), anchor="w")
        self.tree.column("tag", width=px(100), anchor="w", stretch=False)
        self.tree.configure(height=5)
        frame.pack(fill="x", pady=(px(3), 0))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._buttons())
        self.none = self.note(pad, t("image.no_stick"), px(900))

        opts = tk.Frame(pad, bg=T["bg"])
        opts.pack(fill="x", pady=(px(10), 0))
        self.verify_toggle = Toggle(opts, t("image.verify"), True, self._set_verify, app.font(8))
        self.verify_toggle.pack(side="left")

        self.bar = tk.Canvas(pad, height=px(10), bg=T["panel"], highlightthickness=1,
                             highlightbackground=T["line"], bd=0)
        self.bar.pack(fill="x", pady=(px(14), px(4)))
        self.bar.bind("<Configure>", lambda _e: self._draw())
        self.state = self.note(pad, "", px(900))
        self.state.pack(anchor="w")
        buttons = tk.Frame(pad, bg=T["bg"])
        buttons.pack(fill="x", pady=(px(8), 0))
        self.write_button = self.button(buttons, t("btn.write"), self.write, "danger")
        self.write_button.pack(side="left")
        self.stop_button = self.button(buttons, t("btn.stop"), self.stop)
        self.stop_button.pack(side="left", padx=(px(8), 0))
        self.disks_changed()

    def _set_verify(self, value: bool) -> None:
        self.verify = value

    # — choices —
    def disks_changed(self) -> None:
        keep = self.tree.selection()
        if not self.writing:
            self.tree.delete(*self.tree.get_children())
            self.targets = {}
            for disk in self.app.disks:
                if disk.kind == 'disk' and disk.path and removable_drive(disk):
                    self.targets[disk.path] = disk
                    name = disk.title or disk.path
                    tag = safety.tag_for(disk)
                    self.tree.insert("", "end", iid=disk.path, text=f"{name}  ({disk.path})",
                                     values=(size_text(disk.size), t(tag) if tag else ''))
            for iid in keep:
                if iid in self.targets:
                    self.tree.selection_set(iid)
            if self.targets:
                self.none.pack_forget()
            else:
                self.none.pack(anchor="w", pady=(self.app.px(4), 0), after=self.tree.master)
        self._buttons()

    def selected(self) -> Optional[Node]:
        picked = self.tree.selection()
        return self.targets.get(picked[0]) if picked else None

    def _buttons(self) -> None:
        ready = bool(self.path_var.get().strip()) and self.selected() is not None
        self.write_button.set_enabled(ready and not self.writing and not self.app.busy)
        self.stop_button.set_enabled(self.writing)
        self.browse_button.set_enabled(not self.writing)

    def browse(self) -> None:
        start = os.path.dirname(self.path_var.get()) or os.path.expanduser("~")
        chosen = filedialog.askopenfilename(
            parent=self.app.root, initialdir=start, title=t("image.file"),
            filetypes=[(t("image.types"), "*.iso *.img *.raw *.gz *.xz *.bz2"),
                       (t("image.all"), "*")])
        if chosen:
            self.path_var.set(chosen)

    # — writing —
    def write(self) -> None:
        app = self.app
        target, image = self.selected(), self.path_var.get().strip()
        if target is None or not image or self.writing or app.busy:
            return
        verdict = safety.check('write_image', target, app.disks)
        if not verdict.allowed:
            app.set_status(t(verdict.key, **verdict.args), T["pink"], hold_ms=10000)
            app.glitch.now(app.title, strong=True)
            return
        try:
            imagewrite.check_image(image)
        except Exception as exc:
            app.set_status(error_text(exc), T["pink"], hold_ms=10000)
            app.glitch.now(app.title, strong=True)
            return
        size = imagewrite.image_size(image)
        if size and size > target.size:
            app.set_status(t("bad.image_big", image=size_text(size), drive=size_text(target.size)),
                           T["pink"], hold_ms=10000)
            app.glitch.now(app.title, strong=True)
            return
        facts = [(t("fact.image"), os.path.basename(image)),
                 (t("fact.image_size"), size_text(size) if size else t("image.packed")),
                 (t("fact.drive"), target.title or target.path), (t("fact.device"), target.path),
                 (t("fact.size"), size_text(target.size))]
        mounted = [m for sub in target.walk() for m in sub.mounts]
        if mounted:
            facts.append((t("fact.mounted"), ', '.join(mounted)))
        spec = Ask(t("dlg.write"), t("btn.write"), facts, [t("note.write_all")], (), '')
        if ask(app, spec) is None:
            return
        self._start(target, image)

    def _start(self, target: Node, image: str) -> None:
        app, path, verify = self.app, target.path, self.verify
        self.cancel = threading.Event()
        cancel = self.cancel
        self.progress = ('write', 0, 0)
        self.writing = True
        self._buttons()

        def report(phase: str, done: int, total: int) -> None:
            self.progress = (phase, done, total)

        def job():
            return imagewrite.write_image(app.ops, app.backend, image, path, report, cancel, verify)

        def after(_value) -> None:
            self.state.config(text=t("image.done"), fg=T["accent"])

        self._poll()
        app.run_change(t("status.writing"), job, t("done.written"), after)
        self._watch()

    def _watch(self) -> None:
        """Clear the writing state once the app's change has finished."""
        if self.app.busy:
            self.after(300, self._watch)
            return
        self.writing = False
        self.progress = ('', 0, 0)
        self._draw()
        self.disks_changed()

    def _poll(self) -> None:
        if not self.writing:
            return
        self._draw()
        self.after(200, self._poll)

    def stop(self) -> None:
        if self.writing:
            self.cancel.set()
            self.state.config(text=t("image.stopping"), fg=T["gold"])

    def _draw(self) -> None:
        phase, done, total = self.progress
        self.bar.delete("all")
        width, height = max(1, self.bar.winfo_width()), max(1, self.bar.winfo_height())
        if not phase:
            return
        fraction = (done / total) if total else 0.0
        if phase == 'verify':
            colour = T["ch_b"]
        else:
            colour = T["accent"]
        if total:
            self.bar.create_rectangle(0, 0, int(width * min(1.0, fraction)), height, fill=colour,
                                      width=0)
            percent = int(fraction * 100)
            text = t(f"image.{phase}_progress", done=size_text(done), total=size_text(total),
                     percent=percent)
        else:
            step = (done // (8 * 1024 * 1024)) % 20
            self.bar.create_rectangle(int(width * step / 20), 0, int(width * (step + 2) / 20),
                                      height, fill=colour, width=0)
            text = t(f"image.{phase}_unknown", done=size_text(done))
        self.state.config(text=text, fg=T["text"])
