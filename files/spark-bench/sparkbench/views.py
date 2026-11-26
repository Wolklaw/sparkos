"""The three tabs: Setup (MangoHud check, fix, undo, alerts), Recordings (every run, its numbers,
leave out or trim) and Compare (systems side by side, export)."""

import os
from typing import Dict, List, Optional

import tkinter as tk
from . import pickdialog as filedialog

from . import core, dialogs, library, mangohud, watch
from .frames import Stats
from .text import t, tn
from .widgets import T, GlitchPanel, GlitchText, Segmented, Toggle, WolkButton


class View(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.px = app.px

    def refresh(self):
        pass

    def runs_changed(self):
        if self.winfo_ismapped():
            self.refresh()

    def stats_ready(self, run_id: str):
        pass

    def label(self, parent, text='', size=8, bold=False, fg=None, **kw):
        bg = kw.pop('bg', parent.cget('bg'))
        return tk.Label(parent, text=text, bg=bg, fg=fg or T["text"],
                        font=self.app.font(size, bold), anchor="w", justify="left", **kw)

    def micro(self, parent, text, fg=None, **kw):
        """An UPPERCASE bold micro-label."""
        return self.label(parent, text.upper(), size=7, bold=True, fg=fg or T["muted"], **kw)

    def button(self, parent, text, command, variant="ghost"):
        return WolkButton(parent, text, command, self.app.font(8), variant=variant,
                          padx=self.px(12), pady=self.px(4))


class ScrollFrame(tk.Frame):
    """A frame that scrolls with the wheel when its content is taller than the window."""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self._fit())
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(
            self._win, width=e.width), self._fit()))
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.bind_all(seq, self._wheel, add="+")

    def _fit(self):
        self.canvas.configure(scrollregion=(0, 0, self.inner.winfo_reqwidth(),
                                            self.inner.winfo_reqheight()))

    def _wheel(self, event):
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, KeyError):
            return
        while w is not None and w is not self:
            w = w.master
        if w is None or self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            return
        step = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
        self.canvas.yview_scroll(step * 3, "units")


# ─── Setup ────────────────────────────────────────────────────

class SetupView(View):
    def __init__(self, app):
        super().__init__(app)
        px = self.px
        self.scroll = ScrollFrame(self, T["bg"])
        self.scroll.pack(fill="both", expand=True)
        root = self.scroll.inner
        pad = dict(padx=px(18))

        self.heading = GlitchText(root, t('setup.title').upper(), app.tkfont(11), T["bg"])
        self.heading.pack(anchor="w", pady=(px(14), 0), padx=px(14))
        self.label(root, t('setup.intro'), size=8, fg=T["muted"],
                   wraplength=px(900)).pack(fill="x", pady=(px(4), px(10)), **pad)

        self.panel = GlitchPanel(root, T["panel"])
        self.panel.pack(fill="x", **pad)
        self.checks = tk.Frame(self.panel.inner, bg=T["panel"])
        self.checks.pack(fill="x", padx=px(14), pady=px(12))
        app.glitch.add(self.heading)

        # what the fix writes
        form = tk.Frame(root, bg=T["bg"])
        form.pack(fill="x", pady=(px(14), 0), **pad)
        self.micro(form, t('setup.hotkey'), bg=T["bg"]).grid(row=0, column=0, sticky="w")
        self.micro(form, t('setup.duration'), bg=T["bg"]).grid(row=0, column=1, sticky="w",
                                                                padx=(px(18), 0))
        self.micro(form, t('setup.folder'), bg=T["bg"]).grid(row=0, column=2, sticky="w",
                                                              padx=(px(18), 0))
        entry = dict(bg=T["panel"], fg=T["text"], insertbackground=T["accent"], relief="flat",
                     highlightthickness=1, highlightbackground=T["line"],
                     highlightcolor=T["accent"], font=app.font(9, False))
        self.hotkey = tk.StringVar(value=app.settings['hotkey'])
        e = tk.Entry(form, textvariable=self.hotkey, width=16, **entry)
        e.grid(row=1, column=0, sticky="w", pady=(px(3), 0), ipady=px(3))
        e.bind("<Return>", lambda _e: self._save_form())
        e.bind("<FocusOut>", lambda _e: self._save_form())
        self.duration = tk.StringVar(value=str(app.settings['duration']))
        sp = tk.Spinbox(form, from_=10, to=3600, increment=10, textvariable=self.duration,
                        width=6, buttonbackground=T["panel2"], command=self._save_form,
                        **entry)
        sp.grid(row=1, column=1, sticky="w", padx=(px(18), 0), pady=(px(3), 0), ipady=px(3))
        sp.bind("<Return>", lambda _e: self._save_form())
        sp.bind("<FocusOut>", lambda _e: self._save_form())
        frow = tk.Frame(form, bg=T["bg"])
        frow.grid(row=1, column=2, sticky="w", padx=(px(18), 0), pady=(px(3), 0))
        self.folder_label = self.label(frow, '', size=9, bg=T["bg"])
        self.folder_label.pack(side="left")
        self.button(frow, t('setup.change'), self._pick_folder).pack(side="left",
                                                                      padx=(px(10), 0))
        self.label(root, t('setup.hotkey_help'), size=7, fg=T["dim"],
                   wraplength=px(900)).pack(fill="x", pady=(px(4), 0), **pad)

        row = tk.Frame(root, bg=T["bg"])
        row.pack(fill="x", pady=(px(14), 0), **pad)
        self.fix_button = self.button(row, t('setup.fix'), self.fix, "primary")
        self.fix_button.pack(side="left")
        self.undo_button = self.button(row, t('setup.undo'), self.undo)
        self.undo_button.pack(side="left", padx=(px(8), 0))
        self.button(row, t('setup.check'), app.refresh_all).pack(side="left", padx=(px(8), 0))
        self.result = self.label(root, '', size=8, fg=T["muted"], wraplength=px(900))
        self.result.pack(fill="x", pady=(px(8), 0), **pad)

        # alerts
        GlitchText(root, t('alerts.title').upper(), app.tkfont(11), T["bg"]).pack(
            anchor="w", pady=(px(18), 0), padx=px(14))
        self.label(root, t('alerts.intro'), size=8, fg=T["muted"],
                   wraplength=px(900)).pack(fill="x", pady=(px(4), px(8)), **pad)
        arow = tk.Frame(root, bg=T["bg"])
        arow.pack(fill="x", **pad)
        self.sound = Toggle(arow, t('alerts.sound'), bool(app.settings.get('sound', True)),
                            self._sound, app.font(8))
        self.sound.pack(side="left")
        self.background = Toggle(arow, t('alerts.background'), False, self._background,
                                 app.font(8))
        self.background.pack(side="left", padx=(px(8), 0))
        self.button(arow, t('alerts.try'), self._try).pack(side="left", padx=(px(8), 0))
        self.bg_note = self.label(root, t('alerts.background_help'), size=7, fg=T["dim"],
                                  wraplength=px(900))
        self.bg_note.pack(fill="x", pady=(px(6), px(18)), **pad)
        app.submit('background', lambda: ('state', watch.background_on(app.systemctl), ''))

    # — the checks —
    def refresh(self):
        r = self.app.report
        for w in self.checks.winfo_children():
            w.destroy()
        if r is None:
            self.label(self.checks, t('setup.checking'), size=9, fg=T["muted"],
                       bg=T["panel"]).pack(anchor="w")
            self.fix_button.set_enabled(False)
            self.undo_button.set_enabled(False)
            return
        rows = []
        rows.append((r.host_mangohud, t('check.host'),
                     t('check.host_ok') if r.host_mangohud else t('check.host_missing'), None))
        if r.steam_flatpak:
            rows.append((True, t('check.steam'), t('check.steam_ok', branch=r.steam_branch
                                                   or '?'), None))
            have = ', '.join(r.layer_branches) or t('check.none')
            rows.append((r.layer_ok, t('check.layer'),
                         t('check.layer_ok', branch=r.steam_branch or have) if r.layer_ok else
                         t('check.layer_missing', branch=r.steam_branch or '?', have=have),
                         None if r.layer_ok else (t('check.install_layer'), self.install_layer)))
            if r.env_enabled:
                detail = t('check.env_ok_system') if r.env_where == 'system' else t('check.env_ok')
            else:
                detail = t('check.env_missing')
            rows.append((r.env_enabled, t('check.env'), detail, None))
        else:
            rows.append((None, t('check.steam'), t('check.steam_missing') if r.flatpak
                         else t('check.no_flatpak'), None))
        for c in r.configs:
            name = t('check.config_steam') if c.target == 'steam' else t('check.config_host')
            if c.missing:
                detail = t('check.config_missing', path=core.short_path(c.path),
                           lines=', '.join(c.missing))
            else:
                folder = c.values.get('output_folder') or r.output_folder
                detail = t('check.config_ok', path=core.short_path(c.path),
                           key=mangohud.pretty_key(c.values.get('toggle_logging', '')),
                           s=c.values.get('log_duration', '?'),
                           folder=core.short_path(os.path.expanduser(folder)))
            rows.append((not c.missing, name, detail, None))
        if not r.configs:
            rows.append((False, t('check.config_none'), t('check.config_none_help'), None))
        if r.host_mangohud:
            rows.append((None, t('check.native'), t('check.native_help'), None))
        px = self.px
        for i, (ok, title, detail, action) in enumerate(rows):
            colour = T["dim"] if ok is None else (T["accent"] if ok else T["pink"])
            mark = "○" if ok is None else ("●" if ok else "■")
            self.label(self.checks, mark, size=9, bold=True, fg=colour, bg=T["panel"]).grid(
                row=i, column=0, sticky="nw", pady=px(3))
            self.label(self.checks, title.upper(), size=7, bold=True,
                       fg=T["text"] if ok is not None else T["muted"], bg=T["panel"]).grid(
                row=i, column=1, sticky="nw", padx=(px(8), px(14)), pady=(px(5), px(3)))
            self.label(self.checks, detail, size=8, fg=T["muted"], bg=T["panel"],
                       wraplength=px(520)).grid(row=i, column=2, sticky="nw", pady=px(3))
            if action:
                self.button(self.checks, action[0], action[1]).grid(row=i, column=3, sticky="ne",
                                                                   padx=(px(10), 0))
        self.checks.grid_columnconfigure(2, weight=1)
        self.panel.set_slip(not r.ready)
        self.folder_label.config(text=core.short_path(r.output_folder))
        self.fix_button.set_enabled(r.fixable)
        self.undo_button.set_enabled(r.undo_available)

    # — the form —
    def _save_form(self):
        s = self.app.settings
        hotkey = self.hotkey.get().strip().replace(' ', '')
        try:
            duration = max(1, min(3600, int(float(self.duration.get()))))
        except ValueError:
            duration = s['duration']
        if hotkey and (hotkey, duration) != (s['hotkey'], s['duration']):
            s['hotkey'], s['duration'] = hotkey, duration
            self.app.save_settings()
            self.app.check_setup()
        self.hotkey.set(s['hotkey'])
        self.duration.set(str(s['duration']))

    def _pick_folder(self):
        r = self.app.report
        start = r.output_folder if r and os.path.isdir(r.output_folder) else core.home()
        path = filedialog.askdirectory(parent=self, initialdir=start,
                                       title=t('setup.folder_pick'))
        if path:
            self.app.settings['output_folder'] = path
            self.app.save_settings()
            self.app.check_setup()

    # — fix and undo —
    def fix(self):
        r = self.app.report
        if r is None:
            return
        changes = mangohud.plan(r, self.app.settings)
        if not changes:
            self.result.config(text=t('fix.nothing'), fg=T["muted"])
            return
        lines = []
        for ch in changes:
            if ch.kind == 'file':
                lines.append(t('fix.file', path=core.short_path(ch.path)))
                lines += ['    ' + line for line in ch.lines]
            elif ch.kind == 'folder':
                lines.append(t('fix.folder', path=core.short_path(ch.path)))
            elif ch.kind == 'override':
                lines.append(t('fix.override'))
                lines += ['    ' + line for line in ch.lines]
        if not dialogs.askokcancel(t('fix.title'), '\n'.join(lines), parent=self,
                                   detail=t('fix.detail')):
            return
        self._pending_override = any(ch.kind == 'override' for ch in changes)
        self.fix_button.set_enabled(False)
        self.app.submit('fix', mangohud.apply, changes, self.app.runner)

    def undo(self):
        lines = mangohud.undo_summary()
        if not lines:
            return
        detail = t('undo.detail') + ('\n' + t('undo.changed') if any('(*)' in x for x in lines)
                                     else '')
        if not dialogs.askokcancel(t('undo.title'), '\n'.join(lines), parent=self,
                                   detail=detail):
            return
        self.undo_button.set_enabled(False)
        self.app.submit('undo', mangohud.undo, self.app.runner)

    def install_layer(self):
        r = self.app.report
        ref = mangohud.layer_ref(r)
        if not dialogs.askokcancel(t('layer.title'), t('layer.body', ref=ref), parent=self,
                                   detail=t('layer.detail')):
            return
        self.result.config(text=t('layer.working'), fg=T["muted"])
        self.app.submit('layer', mangohud.install_layer, r, self.app.runner)

    def action_done(self, tag, result, error):
        app = self.app
        if tag == 'background':
            action, ok, out = result if result else ('error', False, str(error))
            if action == 'state':
                self.background.set(bool(ok))
                return
            if not ok:
                self.background.set(action == 'off')
                self.result.config(text=t('alerts.background_failed', error=(out or '').strip()
                                          or '?'), fg=T["pink"])
                app.glitch.now(self.heading, strong=True)
            else:
                self.background.set(action == 'on')
                self.result.config(text=t('alerts.background_' + action), fg=T["accent"])
            return
        if tag == 'layer':
            ok, out = result if result else (False, str(error))
            if ok:
                self.result.config(text=t('layer.done'), fg=T["accent"])
            else:
                self.result.config(text=t('layer.failed', error=out.strip()[-300:] or '?'),
                                   fg=T["pink"])
                app.glitch.now(self.heading, strong=True)
            app.check_setup()
            return
        errors = result if error is None else [str(error)]
        if errors:
            self.result.config(text=t(tag + '.failed', error='\n'.join(errors)), fg=T["pink"])
            app.glitch.now(self.heading, self.panel, strong=True)
        else:
            text = t(tag + '.done')
            if tag == 'fix' and getattr(self, '_pending_override', False):
                text += ' ' + t('fix.restart_steam')
            self.result.config(text=text, fg=T["accent"])
            app.set_status(t('status.' + tag + '_done'))
            app.glitch.now(self.heading, self.panel)
        app.check_setup()

    # — alerts —
    def _sound(self, on: bool):
        self.app.settings['sound'] = on
        self.app.save_settings()

    def _background(self, on: bool):
        sc = self.app.systemctl
        if on:
            self.app.submit('background', lambda: ('on',) + watch.enable_background(sc))
        else:
            self.app.submit('background', lambda: ('off',) + watch.disable_background(sc))

    def _try(self):
        kind = watch.STARTED
        self.app.alerter(kind, *watch.message(kind, int(self.app.settings['duration'])))


# ─── Recordings ───────────────────────────────────────────────

class RecordingsView(View):
    COLUMNS = ('system', 'avg', 'low1', 'low01', 'note')

    def __init__(self, app):
        super().__init__(app)
        px = self.px
        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.heading = GlitchText(bar, t('runs.title').upper(), app.tkfont(11), T["bg"])
        self.heading.pack(side="left")
        self.button(bar, t('runs.add_folder'), self.add_folder).pack(side="right")
        self.button(bar, t('runs.import'), self.import_files, "primary").pack(
            side="right", padx=(0, px(8)))
        app.glitch.add(self.heading)

        main = tk.Frame(self, bg=T["bg"])
        main.pack(fill="both", expand=True, padx=px(14), pady=(0, px(12)))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        from tkinter import ttk
        frame = tk.Frame(main, bg=T["line"], padx=1, pady=1)
        frame.grid(row=0, column=0, sticky="nsew")
        self.tree = ttk.Treeview(frame, columns=self.COLUMNS, style="Spark.Treeview",
                                 selectmode="browse")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview,
                           style="Spark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        heads = {'#0': t('runs.col_run'), 'system': t('runs.col_system'),
                 'avg': t('runs.col_avg'), 'low1': t('runs.col_low1'),
                 'low01': t('runs.col_low01'), 'note': t('runs.col_note')}
        font = app.tkfont(7)
        for col, title in heads.items():
            self.tree.heading(col, text=title.upper(), anchor="w")
            need = font.measure(title.upper()) + px(20)
            base = {'#0': 210, 'system': 90, 'note': 110}.get(col, 70)
            self.tree.column(col, width=max(px(base), need), minwidth=need,
                             stretch=col in ('#0', 'note'), anchor="w")
        self.tree.tag_configure("game", foreground=T["accent"], background=T["panel2"])
        self.tree.tag_configure("off", foreground=T["dim"])
        self.tree.tag_configure("busy", foreground=T["gold"])
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_detail())
        self.empty = self.label(main, t('runs.empty'), size=9, fg=T["muted"], bg=T["panel"],
                                wraplength=px(460), padx=px(16), pady=px(14))

        self.side = GlitchPanel(main, T["panel"])
        self.side.grid(row=0, column=1, sticky="ns", padx=(px(12), 0))
        self.detail = tk.Frame(self.side.inner, bg=T["panel"], width=px(380))
        self.detail.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.detail.pack_propagate(False)
        self.selected: Optional[str] = None
        self.items: Dict[str, library.Run] = {}
        self.game_items: Dict[str, str] = {}

    def refresh(self):
        lib = self.app.library
        open_games = {g for g, iid in self.game_items.items() if self.tree.item(iid, 'open')}
        first = not self.game_items
        self.tree.delete(*self.tree.get_children())
        self.items, self.game_items = {}, {}
        for game, runs in lib.groups():
            gid = self.tree.insert('', 'end', text=game, tags=("game",),
                                   values=('', '', '', '', tn('runs.count', len(runs))),
                                   open=first or game in open_games)
            self.game_items[game] = gid
            for run in runs:
                iid = self.tree.insert(gid, 'end', text=core.day_clock(run.when),
                                       values=self._values(run), tags=self._tags(run))
                self.items[iid] = run
        if self.game_items:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.4, anchor="center")
        if self.selected:
            for iid, run in self.items.items():
                if run.id == self.selected:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    break
        self.show_detail()

    def _values(self, run):
        s = self.app.stats.get(run.id)
        mark = self.app.library.mark(run.id)
        if run.recording_now:
            note = t('runs.recording')
        elif isinstance(s, str):
            note = t('runs.unreadable')
        elif s is None:
            note = t('runs.reading')
        elif mark['excluded']:
            note = t('runs.left_out')
        elif mark['trim_start'] or mark['trim_end']:
            note = t('runs.trimmed')
        else:
            note = ''
        if isinstance(s, Stats):
            return (run.system, core.num(s.avg_fps), core.num(s.low1), core.num(s.low01), note)
        return (run.system, '', '', '', note)

    def _tags(self, run):
        if run.recording_now or self.app.stats.get(run.id) is None:
            return ("busy",)
        return ("off",) if self.app.library.mark(run.id)['excluded'] else ()

    def stats_ready(self, run_id: str):
        for iid, run in self.items.items():
            if run.id == run_id:
                self.tree.item(iid, values=self._values(run), tags=self._tags(run))
                if run_id == self.selected:
                    self.show_detail()

    def selected_run(self) -> Optional[library.Run]:
        sel = self.tree.selection()
        return self.items.get(sel[0]) if sel else None

    def selected_game(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            return None
        for game, iid in self.game_items.items():
            if iid == sel[0]:
                return game
        run = self.items.get(sel[0])
        return self.app.library.game_name(run.key) if run else None

    # — the side panel —
    def show_detail(self):
        for w in self.detail.winfo_children():
            w.destroy()
        px, d = self.px, self.detail
        run = self.selected_run()
        game = self.selected_game()
        if run is None and game is None:
            self.label(d, t('runs.pick'), size=8, fg=T["muted"], wraplength=px(340)).pack(
                anchor="w")
            return
        if run is None:
            self.selected = None
            self._game_panel(game)
            return
        self.selected = run.id
        lib, s = self.app.library, self.app.stats.get(run.id)
        mark = lib.mark(run.id)
        self.micro(d, f"{run.system} · {core.day_clock(run.when)}").pack(anchor="w")
        self.label(d, game, size=11, bold=True).pack(anchor="w", pady=(px(2), 0))
        self.label(d, run.id, size=7, fg=T["dim"], wraplength=px(340)).pack(anchor="w")
        if run.recording_now:
            self.label(d, t('runs.recording_help'), size=8, fg=T["gold"],
                       wraplength=px(340)).pack(anchor="w", pady=(px(10), 0))
            return
        if isinstance(s, str) or s is None:
            self.label(d, t('runs.unreadable_help', error=s) if s else t('runs.reading'),
                       size=8, fg=T["pink"] if s else T["muted"], wraplength=px(340)).pack(
                anchor="w", pady=(px(10), 0))
            return
        grid = tk.Frame(d, bg=T["panel"])
        grid.pack(fill="x", pady=(px(10), 0))
        cells = [(t('stat.avg'), core.num(s.avg_fps)), (t('stat.low1'), core.num(s.low1)),
                 (t('stat.low01'), core.num(s.low01)),
                 (t('stat.duration'), core.seconds(s.seconds)),
                 (t('stat.frames'), f"{s.frames}"),
                 (t('stat.worst'), t('stat.worst_value', ms=core.num(s.worst_ms)))]
        for i, (name, value) in enumerate(cells):
            cell = tk.Frame(grid, bg=T["panel"])
            cell.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, px(14)), pady=(0, px(6)))
            self.micro(cell, name).pack(anchor="w")
            self.label(cell, value, size=12 if i < 3 else 9, bold=True,
                       fg=T["accent"] if i < 3 else T["text"]).pack(anchor="w")
        self.micro(d, t('runs.per_second')).pack(anchor="w", pady=(px(6), px(3)))
        self._strip(d, run, s, mark)

        trim = tk.Frame(d, bg=T["panel"])
        trim.pack(fill="x", pady=(px(10), 0))
        self.micro(trim, t('runs.trim')).grid(row=0, column=0, columnspan=4, sticky="w")
        entry = dict(bg=T["panel2"], fg=T["text"], insertbackground=T["accent"], relief="flat",
                     highlightthickness=1, highlightbackground=T["line"],
                     highlightcolor=T["accent"], font=self.app.font(9, False),
                     buttonbackground=T["panel2"], width=5, from_=0,
                     to=max(0, int(s.total_seconds) - 1), increment=1)
        self.trim_start = tk.StringVar(value=f"{mark['trim_start']:g}")
        self.trim_end = tk.StringVar(value=f"{mark['trim_end']:g}")
        for col, (text, var) in enumerate(((t('runs.trim_start'), self.trim_start),
                                           (t('runs.trim_end'), self.trim_end))):
            self.label(trim, text, size=8, fg=T["muted"]).grid(row=1, column=col * 2,
                                                               sticky="w", padx=(0, px(6)))
            sp = tk.Spinbox(trim, textvariable=var, command=lambda r=run: self._trim(r),
                            **entry)
            sp.grid(row=1, column=col * 2 + 1, sticky="w", padx=(0, px(14)), pady=px(3))
            sp.bind("<Return>", lambda _e, r=run: self._trim(r))
            sp.bind("<FocusOut>", lambda _e, r=run: self._trim(r))
        self.label(d, t('runs.trim_help', total=core.seconds(s.total_seconds)), size=7,
                   fg=T["dim"], wraplength=px(340)).pack(anchor="w", pady=(px(2), 0))

        row = tk.Frame(d, bg=T["panel"])
        row.pack(fill="x", pady=(px(10), 0))
        Toggle(row, t('runs.counted'), not mark['excluded'],
               lambda on, r=run: self._count(r, on), self.app.font(8)).pack(side="left")
        self.button(row, t('runs.open_folder'),
                    lambda p=run.path: open_folder(os.path.dirname(p))).pack(side="left",
                                                                             padx=(px(8), 0))
        self._rename(d, run.key, game)

    def _strip(self, parent, run, s: Stats, mark):
        """Bars, one per second of the whole recording; trimmed seconds dim."""
        from . import frames
        px = self.px
        width, height = px(340), px(70)
        c = tk.Canvas(parent, width=width, height=height, bg=T["out_bg"], highlightthickness=1,
                      highlightbackground=T["line"])
        c.pack(anchor="w")
        try:
            whole = frames.per_second(self.app.library.recording(run).frametimes)
        except Exception:                     # noqa: BLE001 - the file went away
            whole = s.per_second
        if not whole:
            return
        top = max(whole) or 1
        n = len(whole)
        bar = width / n
        for i, fps in enumerate(whole):
            cut = i < mark['trim_start'] or i >= n - mark['trim_end']
            h = (height - px(14)) * fps / top
            c.create_rectangle(i * bar, height - h, (i + 1) * bar - (1 if bar > 3 else 0),
                               height, fill=T["dim"] if cut else T["accent"], width=0)
        avg_y = height - (height - px(14)) * s.avg_fps / top
        c.create_line(0, avg_y, width, avg_y, fill=T["gold"], dash=(3, 3))
        c.create_text(px(4), px(2), anchor="nw", fill=T["muted"], font=self.app.font(7),
                      text=t('runs.strip_top', fps=core.num(top, 0)))

    def _game_panel(self, game: str):
        d, px, lib = self.detail, self.px, self.app.library
        runs = dict(lib.groups()).get(game, [])
        self.micro(d, t('runs.game')).pack(anchor="w")
        self.label(d, game, size=11, bold=True).pack(anchor="w", pady=(px(2), px(8)))
        for system in sorted({r.system for r in runs}):
            n = sum(1 for r in runs if r.system == system)
            counted = sum(1 for r in runs if r.system == system
                          and not lib.mark(r.id)['excluded'])
            self.label(d, t('runs.game_line', system=system, n=n, counted=counted), size=8,
                       fg=T["muted"]).pack(anchor="w")
        keys = list(dict.fromkeys(r.key for r in runs))
        programs = sorted({r.program for r in runs})
        self.label(d, t('runs.programs', names=', '.join(programs)), size=7, fg=T["dim"],
                   wraplength=px(340)).pack(anchor="w", pady=(px(6), 0))
        self._rename(d, keys, game)

    def _rename(self, d, keys, game: str):
        px = self.px
        keys = [keys] if isinstance(keys, str) else keys
        box = tk.Frame(d, bg=T["panel"])
        box.pack(fill="x", pady=(px(14), 0))
        self.micro(box, t('runs.rename')).pack(anchor="w")
        row = tk.Frame(box, bg=T["panel"])
        row.pack(fill="x", pady=(px(3), 0))
        var = tk.StringVar(value=game)
        e = tk.Entry(row, textvariable=var, width=22, bg=T["panel2"], fg=T["text"],
                     insertbackground=T["accent"], relief="flat", highlightthickness=1,
                     highlightbackground=T["line"], highlightcolor=T["accent"],
                     font=self.app.font(9, False))
        e.pack(side="left", ipady=px(3))

        def apply(_e=None):
            name = var.get().strip()
            if name and name != game:
                for key in keys:
                    self.app.library.rename_game(key, name)
                self.refresh()
                self.app.views['compare'].runs_changed()
        e.bind("<Return>", apply)
        self.button(row, t('runs.rename_button'), apply).pack(side="left", padx=(px(8), 0))
        self.label(box, t('runs.rename_help'), size=7, fg=T["dim"], wraplength=px(340)).pack(
            anchor="w", pady=(px(3), 0))

    def _trim(self, run):
        try:
            start = max(0.0, float(self.trim_start.get().replace(',', '.')))
            end = max(0.0, float(self.trim_end.get().replace(',', '.')))
        except ValueError:
            return
        mark = self.app.library.mark(run.id)
        s = self.app.stats.get(run.id)
        if isinstance(s, Stats) and start + end > s.total_seconds - 1:
            # at least one second has to stay
            self.trim_start.set(f"{mark['trim_start']:g}")
            self.trim_end.set(f"{mark['trim_end']:g}")
            return
        if (start, end) == (mark['trim_start'], mark['trim_end']):
            return
        self.app.library.set_mark(run.id, trim_start=start, trim_end=end)
        self.app.restat(run)
        self.stats_ready(run.id)

    def _count(self, run, on: bool):
        self.app.library.set_mark(run.id, excluded=not on)
        self.stats_ready(run.id)
        self.app.glitch.now(self.side)

    # — bringing recordings in —
    def import_files(self):
        paths = filedialog.askopenfilenames(parent=self, title=t('runs.import_title'),
                                            filetypes=[(t('runs.csv_files'), '*.csv *.CSV'),
                                                       (t('runs.all_files'), '*')])
        if not paths:
            return
        copied, refused = self.app.library.import_files(list(paths))
        if refused:
            dialogs.showwarning(t('runs.refused_title'),
                                t('runs.refused', names=', '.join(refused)), parent=self)
            self.app.glitch.now(self.heading, strong=True)
        if copied:
            self.app.set_status(tn('status.imported', copied))
            self.app.glitch.now(self.heading)
        self.app.rescan()

    def add_folder(self):
        path = filedialog.askdirectory(parent=self, title=t('runs.folder_title'),
                                       initialdir=core.home())
        if path:
            self.app.library.add_folder(path)
            self.app.rescan()


def open_folder(path: str) -> None:
    import shutil
    import subprocess
    exe = shutil.which('xdg-open')
    if exe and os.path.isdir(path):
        subprocess.Popen([exe, path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


# ─── Compare ──────────────────────────────────────────────────

class CompareView(View):
    def __init__(self, app):
        super().__init__(app)
        px = self.px
        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.heading = GlitchText(bar, t('compare.title').upper(), app.tkfont(11), T["bg"])
        self.heading.pack(side="left")
        self.button(bar, t('compare.export'), self.export, "primary").pack(side="right")
        self.base_row = tk.Frame(bar, bg=T["bg"])
        self.base_row.pack(side="right", padx=(0, px(14)))
        app.glitch.add(self.heading)
        self.scroll = ScrollFrame(self, T["bg"])
        self.scroll.pack(fill="both", expand=True, padx=px(14), pady=(0, px(12)))
        self._pending: Optional[str] = None
        self._systems: List[str] = []

    def baseline(self) -> str:
        systems = self.app.library.systems()
        base = self.app.settings.get('baseline') or ''
        if base in systems:
            return base
        return 'Windows' if 'Windows' in systems else (systems[0] if systems else '')

    def _set_base(self, value: str):
        self.app.settings['baseline'] = value
        self.app.save_settings()
        self.refresh()
        self.app.glitch.now(self.heading)

    def stats_ready(self, run_id: str):
        if self._pending is None:
            self._pending = self.after(150, self._later)

    def _later(self):
        self._pending = None
        self.refresh()

    def refresh(self):
        px = self.px
        systems = self.app.library.systems()
        base = self.baseline()
        if systems != self._systems:
            self._systems = systems
            for w in self.base_row.winfo_children():
                w.destroy()
            if len(systems) > 1:
                self.micro(self.base_row, t('compare.baseline'), bg=T["bg"]).pack(
                    side="left", padx=(0, px(8)))
                Segmented(self.base_row, [(s.upper(), s) for s in systems], base,
                          self._set_base, self.app.font(8)).pack(side="left")
        inner = self.scroll.inner
        for w in inner.winfo_children():
            w.destroy()
        stats = {k: v for k, v in self.app.stats.items() if isinstance(v, Stats)}
        table = library.comparison(self.app.library, stats)
        waiting = sum(1 for r in self.app.library.runs
                      if r.id not in self.app.stats and not r.recording_now)
        if waiting:
            self.label(inner, t('compare.reading', n=waiting), size=8, fg=T["gold"],
                       bg=T["bg"]).pack(anchor="w", pady=(0, px(8)))
        if not table:
            self.label(inner, t('compare.empty'), size=9, fg=T["muted"], bg=T["bg"],
                       wraplength=px(700)).pack(anchor="w", pady=px(10))
            return
        for game, averages in table:
            panel = GlitchPanel(inner, T["panel"])
            panel.pack(fill="x", pady=(0, px(10)))
            box = tk.Frame(panel.inner, bg=T["panel"])
            box.pack(fill="x", padx=px(14), pady=px(10))
            self.label(box, game, size=11, bold=True).grid(row=0, column=0, columnspan=9,
                                                           sticky="w", pady=(0, px(6)))
            order = [s for s in systems if s in averages]
            if base in order:
                order.remove(base)
                order.insert(0, base)
            self.micro(box, '').grid(row=1, column=0)
            for j, system in enumerate(order):
                a = averages[system]
                head = system.upper() + (' · ' + t('compare.base_tag') if system == base and
                                         len(order) > 1 else '')
                self.micro(box, head, fg=T["text"]).grid(row=1, column=1 + j * 2, sticky="w",
                                                         padx=(px(18), 0))
                self.micro(box, tn('compare.runs', a.runs)).grid(
                    row=2, column=1 + j * 2, sticky="w", padx=(px(18), 0))
            for i, (metric, title) in enumerate((('avg_fps', t('stat.avg')),
                                                 ('low1', t('stat.low1')),
                                                 ('low01', t('stat.low01')))):
                self.micro(box, title).grid(row=3 + i, column=0, sticky="w", pady=px(2))
                base_avg = averages.get(base)
                for j, system in enumerate(order):
                    value = getattr(averages[system], metric)
                    self.label(box, core.num(value), size=12, bold=True,
                               fg=T["accent"] if j == 0 else T["text"]).grid(
                        row=3 + i, column=1 + j * 2, sticky="w", padx=(px(18), 0))
                    if system != base and base_avg is not None:
                        diff = library.difference(value, getattr(base_avg, metric))
                        colour = T["muted"] if diff is None or abs(diff) < 0.05 else \
                            (T["accent"] if diff > 0 else T["pink"])
                        self.label(box, core.pct(diff), size=9, bold=True, fg=colour).grid(
                            row=3 + i, column=2 + j * 2, sticky="w", padx=(px(6), 0))
            if base not in averages and len(systems) > 1:
                self.label(box, t('compare.no_base', system=base), size=8,
                           fg=T["muted"]).grid(row=6, column=0, columnspan=9, sticky="w",
                                               pady=(px(4), 0))
        self.label(inner, t('compare.method'), size=7, fg=T["dim"], bg=T["bg"],
                   wraplength=px(860)).pack(anchor="w", pady=(px(4), 0))

    def export(self):
        stats = {k: v for k, v in self.app.stats.items() if isinstance(v, Stats)}
        if not stats:
            dialogs.showinfo(t('compare.export'), t('compare.empty'), parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title=t('compare.export_title'),
                                            defaultextension='.csv',
                                            initialfile='spark-bench-summary.csv',
                                            initialdir=core.home(),
                                            filetypes=[(t('runs.csv_files'), '*.csv')])
        if not path:
            return
        try:
            core.write_text(path, library.summary_csv(self.app.library, stats, self.baseline()))
        except OSError as exc:
            dialogs.showerror(t('compare.export'), str(exc), parent=self)
            self.app.glitch.now(self.heading, strong=True)
            return
        self.app.set_status(t('status.exported', name=os.path.basename(path)))
        self.app.glitch.now(self.heading)
