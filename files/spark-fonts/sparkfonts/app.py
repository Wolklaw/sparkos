"""The Spark Fonts window: every font grouped by family, a preview, the characters, the details,
and install, remove and import from Windows."""

import os
import queue
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog
from typing import Callable, Dict, List, Optional, Tuple

from . import APP_CLASS, APP_NAME, dialogs, fcdata, fontfile, preview, store, winfonts
from .core import count, home, home_short, log, reduced_motion
from .panes import CharsPane, DetailsPane, Pick, PreviewPane, entry
from .text import EN, t
from .widgets import (T, Glitch, GlitchPanel, GlitchText, Mark, Segmented, Strip, WolkButton,
                      make_table, pick_mono, style_tables)

FAMILY_LIMIT = 6000


def launch(argv: List[str]) -> bool:
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as exc:
        log.warning("couldn't start %s: %s", argv[0], exc)
        return False


def show_in_folder_command(path: str) -> List[str]:
    spark_files = shutil.which('spark-files')
    if spark_files:
        return [spark_files, '--select', path]
    return ['xdg-open', os.path.dirname(path) or '/']


class Lock(tk.Canvas):
    """A drawn padlock (fonts can't be trusted to have the glyph)."""

    def __init__(self, parent: tk.Misc, size: int):
        super().__init__(parent, width=size, height=size, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0)
        s = size
        self.create_arc(s * .28, s * .06, s * .72, s * .62, start=0, extent=180,
                        style="arc", outline=T["gold"], width=max(2, s // 9))
        self.create_rectangle(s * .18, s * .44, s * .82, s * .92, outline=T["gold"],
                              fill=T["panel"], width=max(1, s // 12))


class App:
    def __init__(self, files: Optional[List[str]] = None,
                 opener: Callable[[List[str]], bool] = launch,
                 ask: Optional[Callable[..., bool]] = None,
                 tell: Optional[Callable[..., object]] = None,
                 warn: Optional[Callable[..., object]] = None,
                 error: Optional[Callable[..., object]] = None,
                 pick: Optional[Callable[[], List[str]]] = None,
                 windows_finder: Optional[Callable[[], Tuple[list, str]]] = None):
        # the dialogs and the file picker can be swapped (the tests answer them)
        self.opener = opener
        self.ask = ask or dialogs.askyesno
        self.tell = tell or dialogs.showinfo
        self.warn = warn or dialogs.showwarning
        self.error = error or dialogs.showerror
        self.pick = pick or self._pick_files
        self.windows_finder = windows_finder or winfonts.find_all
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=T["bg"])
        try:
            self.scale = max(1.0, self.root.winfo_fpixels('1i') / 96)
        except tk.TclError:
            self.scale = 1.0
        self.root.geometry(f"{self.px(1180)}x{self.px(760)}")
        self.root.minsize(self.px(900), self.px(580))
        family = pick_mono(self.root)
        self.f_body = tkfont.Font(root=self.root, family=family, size=9)
        self.f_small = tkfont.Font(root=self.root, family=family, size=8)
        self.f_label = tkfont.Font(root=self.root, family=family, size=7, weight="bold")
        self.f_title = tkfont.Font(root=self.root, family=family, size=11, weight="bold")
        self.f_brand = tkfont.Font(root=self.root, family=family, size=10, weight="bold")
        self.f_head = tkfont.Font(root=self.root, family=family, size=15, weight="bold")
        style_tables(self.root, self.f_body, self.f_label, self.px(22))
        self.glitch = Glitch(self.root, not reduced_motion())
        self.renderer = preview.Renderer()
        self.inbox: 'queue.Queue' = queue.Queue()
        self.closed = False

        self.faces: List[fcdata.Face] = []
        self.families: List[fcdata.Family] = []
        self.broken: List[str] = []
        self.flt = fcdata.Filter()
        self.scope = 'all'
        self.view: List[fcdata.Family] = []
        self.rows: Dict[str, object] = {}              # tree iid -> Family or a broken path
        self.family: Optional[fcdata.Family] = None
        self.face: Optional[fcdata.Face] = None
        self.broken_path: Optional[str] = None
        self.tab = 'preview'
        self.loaded = False
        self.busy = 0
        self.work_dirs: List[str] = []
        self.pending: List[store.Candidate] = []
        self.pending_families: List[fcdata.Family] = []
        self.select_after_load: Optional[str] = None
        self._select_job: Optional[str] = None
        self._search_job: Optional[str] = None

        self._header()
        self._toolbar()
        self._body()
        self._footer()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        for seq in ("<Control-q>", "<Control-w>"):
            self.root.bind(seq, lambda _e: self.close())
        self.root.bind("<Control-f>", lambda _e: (self.search_entry.focus_set(), "break")[1])
        self.root.bind("<Control-o>", lambda _e: self.install_dialog())
        self.root.bind("<F5>", lambda _e: self.reload())
        self.root.bind("<Delete>", self._delete_key)
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip, self.panel)

        from .xdnd import XDnd
        self.xdnd = XDnd(self.root, self._xdnd_over, self._xdnd_leave, self._xdnd_drop)
        self.root.after(250, lambda: self.xdnd.register(self.root))
        self._tick_job = self.root.after(40, self._tick)
        self.reload()
        if files:
            self.open_files(files)

    def px(self, v: float) -> int:
        return int(round(v * self.scale))

    # ── header and toolbar ──

    def _header(self):
        bar = tk.Frame(self.root, bg=T["bg"])
        bar.pack(fill="x", padx=self.px(14), pady=(self.px(10), self.px(6)))
        self.mark = Mark(bar, self.px(26), T["bg"])
        self.mark.pack(side="left")
        self.title = GlitchText(bar, APP_NAME.upper(), self.f_brand, T["bg"])
        self.title.pack(side="left", padx=(self.px(8), 0))
        self.status = tk.Label(bar, text="", bg=T["bg"], fg=T["accent"], font=self.f_label)
        self.status.pack(side="right")
        self.strip = Strip(self.root, height=2)
        self.strip.pack(fill="x")
        self.set_status('status.loading', T["gold"])

    def set_status(self, key: str, colour: Optional[str] = None, **kw):
        self.status.config(text="● " + t(key, **kw), fg=colour or T["accent"])
        self.status_key = key

    def event(self, *targets, strong: bool = False):
        self.glitch.now(self.title, self.strip, *targets, strong=strong)

    def _toolbar(self):
        px = self.px
        box = tk.Frame(self.root, bg=T["bg"])
        box.pack(fill="x", padx=px(14), pady=(px(8), 0))
        row1 = tk.Frame(box, bg=T["bg"])
        row1.pack(fill="x")
        self.search_var = tk.StringVar()
        self.search_entry = entry(row1, self.search_var, self.f_body, width=30)
        self.search_entry.pack(side="left", ipady=px(4), fill="x", expand=True)
        self.search_var.trace_add('write', lambda *_a: self._search_changed())
        self.placeholder = tk.Label(self.search_entry, text=t('search.placeholder'),
                                    bg=T["panel"], fg=T["dim"], font=self.f_body)
        self.placeholder.place(x=px(6), rely=0.5, anchor="w")
        self.placeholder.bind("<Button-1>", lambda _e: self.search_entry.focus_set())
        self.b_install = WolkButton(row1, t('btn.install'), self.install_dialog, self.f_label,
                                    variant="primary")
        self.b_install.pack(side="right", padx=(px(6), 0))
        self.b_windows = WolkButton(row1, t('btn.windows'), self.windows_dialog, self.f_label)
        self.b_windows.pack(side="right", padx=(px(6), 0))
        self.row2 = tk.Frame(box, bg=T["bg"])
        self.row2.pack(fill="x", pady=(px(8), 0))
        self.scope_holder = tk.Frame(self.row2, bg=T["bg"])
        self.scope_holder.pack(side="left")
        self._scope_options = ()
        self._build_scopes()
        cats = [(t('cat.any'), '')] + [(t('cat.' + c), c) for c in fcdata.CATEGORIES]
        self.cat_pick = Pick(self.row2, t('filter.style'), cats, '', self._cat_changed,
                             self.f_label)
        self.cat_pick.pack(side="left", padx=(px(8), 0))
        langs = [(t('lang.any'), '')] + [(t('lang.' + c), c) for c in fcdata.LANGUAGES]
        self.lang_pick = Pick(self.row2, t('filter.supports'), langs, '', self._lang_changed,
                              self.f_label)
        self.lang_pick.pack(side="left", padx=(px(6), 0))
        self.count_label = tk.Label(self.row2, text='', bg=T["bg"], fg=T["muted"],
                                    font=self.f_small)
        self.count_label.pack(side="right")

    def _build_scopes(self):
        wanted = ['all', 'mine', 'system']
        if self.pending_families:
            wanted.append('opened')
        if self.broken:
            wanted.append('broken')
        if tuple(wanted) == self._scope_options:
            return
        self._scope_options = tuple(wanted)
        for child in self.scope_holder.winfo_children():
            child.destroy()
        if self.scope not in wanted:
            self.scope = 'all'
            self.flt.scope = 'all'
        names = {'all': t('scope.all'), 'mine': t('scope.mine'), 'system': t('scope.system'),
                 'opened': t('scope.opened'), 'broken': t('scope.broken', n=len(self.broken))}
        self.scopes = Segmented(self.scope_holder, [(names[w], w) for w in wanted], self.scope,
                                self.set_scope, self.f_label)
        self.scopes.pack()

    def _search_changed(self):
        text = self.search_var.get()
        if text:
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=self.px(6), rely=0.5, anchor="w")
        self.flt.text = text
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(120, self.refilter)

    def set_scope(self, scope: str):
        self.scope = scope
        self.flt.scope = scope if scope in ('mine', 'system') else 'all'
        if self.scopes.value != scope:
            self.scopes.set(scope)
        self.refilter()
        self.event()

    def _cat_changed(self, value: str):
        self.flt.category = value
        self.refilter()

    def _lang_changed(self, value: str):
        self.flt.lang = value
        self.refilter()

    # ── body: the list and the panes ──

    def _body(self):
        px = self.px
        body = tk.Frame(self.root, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(14), pady=px(10))
        left = tk.Frame(body, bg=T["bg"], width=px(330))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        frame, self.tree = make_table(left, ("n", "tag"), show="tree headings")
        self.tree.heading("#0", text=t('list.family'))
        self.tree.heading("n", text=t('list.styles'))
        self.tree.heading("tag", text=t('list.where'))
        self.tree.column("#0", width=px(170), stretch=True)
        self.tree.column("n", width=px(62), stretch=False, anchor="e")
        self.tree.column("tag", width=px(70), stretch=False)
        frame.pack(fill="both", expand=True)
        self.tree.tag_configure("mine", foreground=T["accent"])
        self.tree.tag_configure("opened", foreground=T["gold"])
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._selected_soon())
        self.empty = tk.Label(frame, text='', bg=T["panel"], fg=T["muted"], font=self.f_body,
                              wraplength=px(260), justify="left")

        self.panel = GlitchPanel(body, T["bg"])
        self.panel.pack(side="left", fill="both", expand=True, padx=(px(10), 0))
        right = tk.Frame(self.panel.inner, bg=T["bg"])
        right.pack(fill="both", expand=True, padx=px(10), pady=px(8))
        head = tk.Frame(right, bg=T["bg"])
        head.pack(fill="x")
        self.name = GlitchText(head, '', self.f_title, T["bg"])
        self.name.pack(side="left")
        self.glitch.add(self.name)
        self.chip = tk.Label(head, text='', bg=T["bg"], fg=T["muted"], font=self.f_label,
                             highlightthickness=1, highlightbackground=T["line2"],
                             padx=px(5), pady=px(1))
        self.chip.pack(side="left", padx=(px(8), 0))
        self.style_pick = Pick(head, t('tab.style'), [('', '')], '', self._style_changed,
                               self.f_label)
        self.style_pick.pack(side="right")
        tabs = tk.Frame(right, bg=T["bg"])
        tabs.pack(fill="x", pady=(px(8), px(8)))
        self.tabs = Segmented(tabs, [(t('tab.preview'), 'preview'),
                                     (t('tab.chars'), 'chars'), (t('tab.details'), 'details')],
                              'preview', self.set_tab, self.f_label)
        self.tabs.pack(side="left")
        stage = tk.Frame(right, bg=T["bg"])
        stage.pack(fill="both", expand=True)
        self.pane_preview = PreviewPane(stage, self)
        self.pane_chars = CharsPane(stage, self)
        self.pane_details = DetailsPane(stage, self)
        self.panes = {'preview': self.pane_preview, 'chars': self.pane_chars,
                      'details': self.pane_details}
        self.pane_preview.pack(fill="both", expand=True)

        actions = tk.Frame(right, bg=T["bg"])
        actions.pack(fill="x", pady=(px(8), 0))
        self.lock = Lock(actions, px(18))
        self.note = tk.Label(actions, text='', bg=T["bg"], fg=T["gold"], font=self.f_small,
                             anchor="w", justify="left", wraplength=px(430))
        self.b_remove = WolkButton(actions, t('btn.remove'), self.remove_selected,
                                   self.f_label, variant="danger")
        self.b_remove.pack(side="right", padx=(px(6), 0))
        self.b_reveal = WolkButton(actions, t('btn.reveal'), self.reveal_selected, self.f_label)
        self.b_reveal.pack(side="right", padx=(px(6), 0))
        self.b_add = WolkButton(actions, t('btn.install_these'), self.install_opened,
                                self.f_label, variant="primary")
        self.note.pack(side="left", fill="x", expand=True)

    def _footer(self):
        pass

    # ── loading and filtering ──

    def post(self, fn: Callable[[], None]):
        self.inbox.put(fn)

    def _tick(self):
        if self.closed:
            return
        try:
            for _ in range(40):
                self.inbox.get_nowait()()
        except queue.Empty:
            pass
        self.renderer.poll()
        self._tick_job = self.root.after(40, self._tick)

    def reload(self, select: Optional[str] = None):
        """Read the font list again, off the window's thread."""
        if select:
            self.select_after_load = select
        self.busy += 1

        def work():
            faces = fcdata.list_faces()
            broken = fcdata.find_broken(faces)
            families = fcdata.group(faces)
            self.post(lambda: self._loaded(faces, families, broken))
        threading.Thread(target=work, daemon=True, name='spark-fonts-list').start()

    def _loaded(self, faces, families, broken):
        self.busy = max(0, self.busy - 1)
        self.faces, self.families, self.broken = faces, families, broken
        self.loaded = True
        self._build_scopes()
        self.refilter()
        if self.status_key in ('status.loading',):
            self.set_status('status.ready')
        if self.select_after_load:
            self.select_family(self.select_after_load)
            self.select_after_load = None

    def current_families(self) -> List[fcdata.Family]:
        if self.scope == 'opened':
            return self.pending_families
        return self.families

    def refilter(self):
        self._search_job = None
        self._build_scopes()
        keep = self.family.name.lower() if self.family else None
        keep_broken = self.broken_path
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        if self.scope == 'broken':
            shown = [p for p in self.broken
                     if not self.flt.text.strip() or self.flt.text.strip().lower()
                     in os.path.basename(p).lower()]
            for i, path in enumerate(shown):
                iid = f"b{i}"
                self.rows[iid] = path
                self.tree.insert('', 'end', iid=iid, text=os.path.basename(path),
                                 values=('', t('tag.broken')), tags=("off",))
            self.view = []
            self.count_label.config(text=t('count.broken', n=len(shown)))
        else:
            self.view = fcdata.apply(self.current_families(), self.flt)
            for i, fam in enumerate(self.view[:FAMILY_LIMIT]):
                iid = f"f{i}"
                self.rows[iid] = fam
                tag = t('tag.opened') if self.scope == 'opened' else (
                    t('tag.mine') if fam.mine and not fam.system else
                    t('tag.mixed') if fam.mine else t('tag.system'))
                tags = ("opened",) if self.scope == 'opened' else (("mine",) if fam.mine else ())
                self.tree.insert('', 'end', iid=iid, text=fam.name,
                                 values=(count(len(fam.faces)), tag), tags=tags)
            total = len(self.current_families())
            if len(self.view) == total:
                self.count_label.config(text=t('count.all', n=count(total),
                                               styles=count(sum(len(f.faces) for f in self.view))))
            else:
                self.count_label.config(text=t('count.some', n=count(len(self.view)),
                                               total=count(total)))
        self._empty_message()
        target = None
        for iid, row in self.rows.items():
            if (isinstance(row, fcdata.Family) and keep and row.name.lower() == keep) \
                    or (row == keep_broken and keep_broken):
                target = iid
                break
        if target is None and self.rows:
            target = next(iter(self.rows))
        if target:
            self.tree.selection_set(target)
            self.tree.see(target)
        else:
            self._select(None)

    def _empty_message(self):
        if self.rows or not self.loaded:
            self.empty.place_forget()
            return
        if self.scope == 'all' and not self.flt.text and not self.flt.category \
                and not self.flt.lang:
            msg = t('empty.none')
        elif self.scope == 'mine' and not self.flt.text and not self.flt.category \
                and not self.flt.lang:
            msg = t('empty.mine')
        else:
            msg = t('empty.filtered')
        self.empty.config(text=msg)
        self.empty.place(relx=0.5, rely=0.3, anchor="n")

    # ── selection ──

    def _selected_soon(self):
        if self._select_job is None:
            self._select_job = self.root.after_idle(self._selected)

    def _selected(self):
        self._select_job = None
        sel = self.tree.selection()
        self._select(self.rows.get(sel[0]) if sel else None)

    def select_family(self, name: str) -> bool:
        for iid, row in self.rows.items():
            if isinstance(row, fcdata.Family) and row.name.lower() == name.lower():
                self.tree.selection_set(iid)
                self.tree.see(iid)
                return True
        if self.scope != 'all' and (self.flt.text or self.flt.category or self.flt.lang
                                    or self.scope not in ('all', 'opened')):
            self.search_var.set('')
            self.flt.category = self.flt.lang = ''
            self.cat_pick.set('')
            self.lang_pick.set('')
            self.set_scope('all')
            return self.select_family(name) if name else False
        return False

    def _select(self, row):
        self.family = self.face = self.broken_path = None
        if isinstance(row, fcdata.Family):
            self.family = row
            keep = self._remembered_style(row)
            self.face = keep
        elif isinstance(row, str):
            self.broken_path = row
        self._fill_head()
        self._fill_panes()

    def _remembered_style(self, fam: fcdata.Family) -> fcdata.Face:
        """The Regular style when there is one, else the first."""
        for f in fam.faces:
            if f.style.lower() in ('regular', 'book', 'roman', 'normal'):
                return f
        return fam.faces[0]

    def _style_changed(self, value: str):
        if self.family:
            for f in self.family.faces:
                if self._face_id(f) == value:
                    self.face = f
            self._fill_panes(styles=False)

    @staticmethod
    def _face_id(f: fcdata.Face) -> str:
        return f"{f.path}\x00{f.index}\x00{f.style}"

    def _fill_head(self):
        px = self.px
        self.lock.pack_forget()
        self.b_add.pack_forget()
        self.note.pack_forget()
        fam = self.family
        if fam is None and self.broken_path is None:
            self.name.set_text('')
            self.chip.config(text='')
            self.chip.pack_forget()
            self.style_pick.pack_forget()
            self.note.config(text='')
            self.b_remove.set_enabled(False)
            self.b_reveal.set_enabled(False)
            self.note.pack(side="left", fill="x", expand=True)
            return
        if fam is None:
            self.name.set_text(os.path.basename(self.broken_path))
            self.chip.config(text=t('tag.broken'), fg=T["pink"])
            self.chip.pack(side="left", padx=(px(8), 0))
            self.style_pick.pack_forget()
            self.note.config(text=t('note.broken'), fg=T["gold"])
            self.b_remove.set_enabled(True)
            self.b_reveal.set_enabled(True)
            self.note.pack(side="left", fill="x", expand=True)
            return
        self.name.set_text(fam.name)
        if self.scope == 'opened':
            chip, colour = t('tag.opened'), T["gold"]
        elif fam.mine and fam.system:
            chip, colour = t('tag.mixed'), T["accent"]
        elif fam.mine:
            chip, colour = t('tag.mine'), T["accent"]
        else:
            chip, colour = t('tag.system'), T["muted"]
        self.chip.config(text=chip, fg=colour)
        self.chip.pack(side="left", padx=(px(8), 0))
        opts = [(self._style_label(f), self._face_id(f)) for f in fam.faces]
        self.style_pick.set_options(opts, self._face_id(self.face))
        self.style_pick.pack(side="right")
        mine = [f for f in fam.faces if fcdata.is_user_font(f.path)]
        if self.scope == 'opened':
            self.note.config(text=self._opened_note(), fg=T["gold"])
            self.b_add.pack(side="right", padx=(px(6), 0))
            self.b_add.set_enabled(any(c.installable for c in self.pending))
            self.b_remove.set_enabled(False)
        elif mine:
            self.note.config(text=t('note.mine', n=len(set(f.path for f in mine))),
                             fg=T["muted"])
            self.b_remove.set_enabled(True)
        else:
            reason = fcdata.removal_refusal(fam.faces[0].path)
            self.lock.pack(side="left", padx=(0, px(8)))
            self.note.config(text=t('why_locked.' + (reason or 'other')), fg=T["gold"])
            self.b_remove.set_enabled(False)
        self.b_reveal.set_enabled(True)
        self.note.pack(side="left", fill="x", expand=True)

    def _opened_note(self) -> str:
        refused = [c for c in self.pending if not c.installable]
        if self.pending and not any(c.installable for c in self.pending):
            return t('note.opened_view_only')
        if refused:
            return t('note.opened_some', n=len(refused))
        return t('note.opened')

    def _style_label(self, f: fcdata.Face) -> str:
        return f.style or t('style.regular')

    def _fill_panes(self, styles: bool = True):
        if self.broken_path is not None:
            self.tabs.set('details')
            self._show_tab('details')
            self.pane_details.show_broken(self.broken_path)
            return
        if self.family is None:
            self.pane_preview.show([])
            self.pane_chars.show(None)
            self.pane_details.put([('note', '', t('det.pick'))])
            return
        if styles:
            self.pane_preview.show(self.family.faces)
        self.pane_chars.show(self.face)
        self.pane_details.show_face(self.family, self.face)
        self._show_tab(self.tab)

    def set_tab(self, tab: str):
        self.tab = tab
        if self.tabs.value != tab:
            self.tabs.set(tab)
        self._show_tab(tab)
        self.event(self.panel)

    def _show_tab(self, tab: str):
        for name, pane in self.panes.items():
            if name != tab:
                pane.pack_forget()
        self.panes[tab].pack(fill="both", expand=True)

    # ── install ──

    def _pick_files(self) -> List[str]:
        picked = filedialog.askopenfilenames(
            parent=self.root, title=t('pick.title'), initialdir=home(),
            filetypes=[(t('pick.fonts'), "*.ttf *.otf *.ttc *.otc *.zip *.woff *.woff2"),
                       (t('pick.all'), "*")])
        return list(picked)

    def install_dialog(self):
        paths = self.pick()
        if paths:
            self.install_paths(paths)

    def _work_dir(self) -> str:
        path = tempfile.mkdtemp(prefix='spark-fonts-')
        self.work_dirs.append(path)
        return path

    def install_paths(self, paths: List[str]):
        """Look at what was dropped or chosen (zips unpacked, folders walked), then install."""
        self._begin('status.checking')
        work = self._work_dir()

        def job():
            try:
                cands, problems = store.plan(paths, work)
            except Exception as exc:                   # noqa: BLE001
                log.exception("planning failed")
                self.post(lambda: self._failed(str(exc)))
                return
            self.post(lambda: self._planned(cands, problems))
        threading.Thread(target=job, daemon=True, name='spark-fonts-plan').start()

    def install_candidates(self, cands: List[store.Candidate]):
        self._planned(cands, [])

    def install_opened(self):
        cands = [c for c in self.pending if c.installable]
        if cands:
            self._planned(cands, [])

    def _begin(self, key: str):
        self.busy += 1
        self.set_status(key, T["gold"])
        self.event(strong=False)

    def _end(self):
        self.busy = max(0, self.busy - 1)

    def _failed(self, why: str):
        self._end()
        self.set_status('status.error', T["pink"])
        self.event(self.panel, strong=True)
        self.error(t('error.title'), t('error.install', error=why), parent=self.root)

    def _planned(self, cands: List[store.Candidate], problems: List[Tuple[str, str]]):
        notes: List[str] = []
        for name, reason in problems:
            notes.append(f"{name}: {self.why(reason)}")
        for c in cands:
            if c.status == store.REFUSED:
                notes.append(f"{c.name}: {self.why(c.reason)}")
            elif c.status == store.SYSTEM:
                notes.append(f"{c.name}: {t('why.system', family=c.family)}")
            elif c.status == store.SAME:
                notes.append(f"{c.name}: {t('why.same', family=c.family)}")
        todo = [c for c in cands if c.status == store.NEW]
        dupes = [c for c in cands if c.status == store.DUPLICATE]
        replace = False
        if dupes:
            names = ", ".join(sorted({c.family for c in dupes}))
            replace = bool(self.ask(t('ask.replace_title'),
                                    t('ask.replace', n=len(dupes), names=names),
                                    parent=self.root))
            if replace:
                todo += dupes
            else:
                notes += [f"{c.name}: {t('why.kept_old', family=c.family)}" for c in dupes]
        if not todo:
            self._end()
            self.set_status('status.nothing', T["gold"])
            self.event(self.panel, strong=True)
            if notes:
                self.warn(t('report.title_none'), "\n".join(notes[:12]) +
                          (f"\n{t('report.more', n=len(notes) - 12)}" if len(notes) > 12
                           else ''), parent=self.root)
            return
        self.set_status('status.installing', T["gold"])

        def job():
            try:
                out = store.install(todo, replace=replace)
            except Exception as exc:                   # noqa: BLE001
                log.exception("install failed")
                self.post(lambda: self._failed(str(exc)))
                return
            self.post(lambda: self._installed(todo, out, notes))
        threading.Thread(target=job, daemon=True, name='spark-fonts-install').start()

    def _installed(self, todo, out: store.Outcome, notes: List[str]):
        self._end()
        for name, why in out.failed:
            notes.append(f"{name}: {why}")
        families = []
        for c in todo:
            if c.family and c.family not in families:
                families.append(c.family)
        n = len(out.installed)
        if n:
            self.set_status('status.installed', n=n)
            self.event(self.panel, strong=True)
            if self.pending:
                self.pending = [c for c in self.pending if c.src not in
                                {x.src for x in todo}]
                self._rebuild_pending()
            self.reload(select=families[0] if families else None)
        else:
            self.set_status('status.error', T["pink"])
            self.event(self.panel, strong=True)
        if notes:
            (self.warn if not n else self.tell)(
                t('report.title') if n else t('report.title_none'),
                "\n".join(notes[:12]), parent=self.root)

    def why(self, reason: str) -> str:
        return t('why.' + reason) if 'why.' + reason in EN else t('why.unreadable')

    # ── open files for a look ──

    def open_files(self, paths: List[str]):
        """The preview for files that aren't installed: they get their own list, with INSTALL."""
        self._begin('status.checking')
        work = self._work_dir()

        def job():
            cands, problems = store.plan(paths, work)
            faces: List[fcdata.Face] = []
            for c in cands:
                if c.status != store.REFUSED or c.reason == 'web_font':
                    faces += fcdata.query_file(c.src)
            self.post(lambda: self._opened(cands, problems, faces))
        threading.Thread(target=job, daemon=True, name='spark-fonts-open').start()

    def _opened(self, cands, problems, faces):
        self._end()
        self.pending = cands
        self.pending_families = fcdata.group(faces)
        self._rebuild_pending()
        notes = [f"{n}: {self.why(r)}" for n, r in problems]
        notes += [f"{c.name}: {self.why(c.reason)}" for c in cands
                  if c.status == store.REFUSED and c.reason != 'web_font']
        if self.pending_families:
            self.set_scope('opened')
            self.set_status('status.opened', n=len(self.pending_families))
        else:
            self.set_status('status.nothing', T["gold"])
            self.event(strong=True)
        if notes:
            self.warn(t('report.title_none'), "\n".join(notes[:12]), parent=self.root)

    def _rebuild_pending(self):
        faces = []
        for c in self.pending:
            if c.status != store.REFUSED or c.reason == 'web_font':
                faces += fcdata.query_file(c.src)
        self.pending_families = fcdata.group(faces)
        self._build_scopes()
        if self.scope == 'opened' and not self.pending_families:
            self.set_scope('all')

    # ── remove ──

    def _delete_key(self, event):
        if self.root.focus_get() in (self.tree, self.root):
            self.remove_selected()

    def remove_selected(self):
        if self.broken_path is not None:
            paths = [self.broken_path]
            title, body = t('ask.remove_broken_title'), t('ask.remove_broken',
                                                          name=os.path.basename(paths[0]))
        elif self.family is not None and self.scope != 'opened':
            paths = sorted({f.path for f in self.family.faces if fcdata.is_user_font(f.path)})
            if not paths:
                return
            title = t('ask.remove_title')
            body = t('ask.remove', name=self.family.name, n=len(paths))
        else:
            return
        if not self.ask(title, body, parent=self.root):
            return
        self.busy += 1
        self.set_status('status.removing', T["gold"])

        def job():
            done, failed = store.remove(paths)
            self.post(lambda: self._removed(done, failed))
        threading.Thread(target=job, daemon=True, name='spark-fonts-remove').start()

    def _removed(self, done: List[str], failed: List[Tuple[str, str]]):
        self._end()
        if failed:
            self.set_status('status.error', T["pink"])
            self.event(self.panel, strong=True)
            self.error(t('error.title'), "\n".join(
                f"{os.path.basename(p)}: {self.why_locked(p, why)}" for p, why in failed[:8]),
                parent=self.root)
        if done:
            self.set_status('status.removed', n=len(done))
            self.event(self.panel, strong=True)
        self.reload()

    @staticmethod
    def why_locked(path: str, reason: str) -> str:
        key = 'why_locked.' + reason
        return t(key) if key in EN else reason

    def reveal_selected(self):
        path = self.broken_path or (self.face.path if self.face else None)
        if path and not self.opener(show_in_folder_command(path)):
            self.opener(['xdg-open', os.path.dirname(path) or '/'])

    # ── Windows ──

    def windows_dialog(self):
        from .winimport import WindowsDialog
        self.event(strong=False)
        self.windows = WindowsDialog(self, self.windows_finder)

    # ── dropping files on the window ──

    def _xdnd_over(self, x: int, y: int, action: str) -> bool:
        self.set_status('status.drop', T["gold"])
        return True

    def _xdnd_leave(self) -> None:
        if self.status_key == 'status.drop':
            self.set_status('status.ready')

    def _xdnd_drop(self, paths: List[str], action: str, x: int, y: int) -> None:
        self._xdnd_leave()
        if paths:
            self.install_paths(paths)

    # ── life ──

    def run(self):
        self.root.mainloop()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.root.after_cancel(self._tick_job)
        except (tk.TclError, AttributeError):
            pass
        self.renderer.close()
        try:
            self.xdnd.close()
        except Exception:                              # noqa: BLE001
            pass
        for path in self.work_dirs:
            shutil.rmtree(path, ignore_errors=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass
