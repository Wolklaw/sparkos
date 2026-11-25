"""The three panes beside the font list: Preview, Characters and Details. Each is a Frame that
the window shows one at a time; they draw through the window's Renderer (Pillow, off the UI
thread) and never block it."""

import tkinter as tk
from typing import Callable, List, Optional, Sequence, Tuple

from . import fcdata, fontfile, preview
from .core import home_short, human_size
from .text import t
from .widgets import T, WolkButton, Toggle

LIGHT = {"fg": "#10171a", "bg": "#eef6f4"}
DARK = {"fg": T["text"], "bg": T["panel"]}


class Pick(tk.Menubutton):
    """A one-of-many menu in the house style: LABEL: value."""

    def __init__(self, parent: tk.Misc, label: str, options: Sequence[Tuple[str, str]],
                 value: str, command: Callable[[str], None], font):
        super().__init__(parent, font=font, bg=T["panel"], fg=T["text"], bd=0, relief="flat",
                         activebackground=T["hover"], activeforeground=T["accent"],
                         highlightthickness=1, highlightbackground=T["line2"],
                         highlightcolor=T["accent"], padx=8, pady=3, cursor="hand2",
                         anchor="w", indicatoron=False, takefocus=1)
        self.label, self.command, self.font = label, command, font
        self.value, self.options = value, list(options)
        self.menu = tk.Menu(self, tearoff=False, bg=T["panel"], fg=T["text"],
                            activebackground=T["accent"], activeforeground=T["on_accent"],
                            bd=0, relief="flat", font=font)
        self["menu"] = self.menu
        self.set_options(self.options, value)

    def set_options(self, options: Sequence[Tuple[str, str]], value: Optional[str] = None):
        self.options = list(options)
        self.menu.delete(0, "end")
        for text, val in self.options:
            self.menu.add_command(label=text, command=lambda v=val: self.set(v, fire=True))
        self.set(value if value is not None else (self.options[0][1] if self.options else ''))

    def set(self, value: str, fire: bool = False):
        self.value = value
        shown = next((text for text, val in self.options if val == value), '')
        self.config(text=f"{self.label.upper()}: {shown}  ▾" if self.label else f"{shown}  ▾")
        if fire:
            self.command(value)


def entry(parent: tk.Misc, var: tk.StringVar, font, width: int = 20) -> tk.Entry:
    return tk.Entry(parent, textvariable=var, font=font, bg=T["panel"], fg=T["text"],
                    insertbackground=T["accent"], relief="flat", bd=0, width=width,
                    highlightthickness=1, highlightbackground=T["line2"],
                    highlightcolor=T["accent"], selectbackground=T["line2"],
                    selectforeground=T["text"])


def wheel_bind(widget: tk.Misc, canvas: tk.Canvas) -> None:
    def scroll(event):
        step = -1 if (getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0) else 1
        canvas.yview_scroll(step * 3, "units")
        return "break"
    widget.bind("<Button-4>", scroll, add="+")
    widget.bind("<Button-5>", scroll, add="+")
    widget.bind("<MouseWheel>", scroll, add="+")


# ─── Preview ─────────────────────────────────────────────────

class PreviewPane(tk.Frame):
    MAX_STYLES = 60

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["bg"])
        self.app = app
        px = app.px
        self.faces: List[fcdata.Face] = []
        self.light = False
        self.blocks: List[Tuple[tk.Label, tk.Label]] = []
        self._later: Optional[str] = None

        ctl = tk.Frame(self, bg=T["bg"])
        ctl.pack(fill="x", pady=(0, px(6)))
        tk.Label(ctl, text=t('prev.sample'), bg=T["bg"], fg=T["muted"],
                 font=app.f_label).grid(row=0, column=0, sticky="w")
        self.var = tk.StringVar(value='')
        self.entry = entry(ctl, self.var, app.f_body)
        self.entry.grid(row=1, column=0, sticky="we", ipady=px(3), padx=(0, px(10)))
        self.var.trace_add('write', lambda *_a: self.later())
        tk.Label(ctl, text=t('prev.size'), bg=T["bg"], fg=T["muted"],
                 font=app.f_label).grid(row=0, column=1, sticky="w")
        row = tk.Frame(ctl, bg=T["bg"])
        row.grid(row=1, column=1, sticky="w")
        self.size = tk.Scale(row, from_=8, to=96, orient="horizontal", showvalue=False,
                             length=px(150), bg=T["bg"], troughcolor=T["panel2"],
                             activebackground=T["accent"], highlightthickness=0, bd=0,
                             sliderrelief="flat", sliderlength=px(14), width=px(10),
                             command=lambda _v: self._size_changed())
        self.size.set(36)
        self.size.pack(side="left")
        self.size_label = tk.Label(row, text="36", bg=T["bg"], fg=T["text"], font=app.f_body,
                                   width=3, anchor="e")
        self.size_label.pack(side="left")
        self.toggle = Toggle(ctl, t('prev.light'), False, self._set_light, app.f_label)
        self.toggle.grid(row=1, column=2, padx=(px(10), 0))
        ctl.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
        from tkinter import ttk
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                 style="Spark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resized)
        for w in (self.canvas, self.inner):
            wheel_bind(w, self.canvas)
        self.empty = tk.Label(self.inner, text=t('prev.none'), bg=T["bg"], fg=T["muted"],
                              font=app.f_body, anchor="w")

    def colours(self) -> dict:
        return LIGHT if self.light else DARK

    def sample(self) -> str:
        return self.var.get() or t('prev.pangram')

    def later(self, ms: int = 140):
        if self._later is not None:
            try:
                self.after_cancel(self._later)
            except tk.TclError:
                pass
        self._later = self.after(ms, self.refresh)

    def _size_changed(self):
        self.size_label.config(text=str(self.size.get()))
        self.later(100)

    def _set_light(self, on: bool):
        self.light = on
        self.refresh()

    def _resized(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        self.later(200)

    def show(self, faces: List[fcdata.Face]):
        self.faces = faces[:self.MAX_STYLES]
        for a, b in self.blocks:
            a.destroy()
            b.destroy()
        self.blocks = []
        self.empty.pack_forget()
        px = self.app.px
        if not faces:
            self.empty.pack(fill="x")
            return
        for face in self.faces:
            head = tk.Label(self.inner, text=face.style.upper() or face.family.upper(),
                            bg=T["bg"], fg=T["muted"], font=self.app.f_label, anchor="w")
            head.pack(fill="x", pady=(px(8), 0))
            body = tk.Label(self.inner, text='', bg=self.colours()["bg"], anchor="w",
                            bd=0, padx=0, pady=0)
            body.pack(fill="x", pady=(px(2), 0))
            for w in (head, body):
                wheel_bind(w, self.canvas)
            self.blocks.append((head, body))
        if len(faces) > self.MAX_STYLES:
            more = tk.Label(self.inner, text=t('prev.more', n=len(faces) - self.MAX_STYLES),
                            bg=T["bg"], fg=T["muted"], font=self.app.f_small, anchor="w")
            more.pack(fill="x", pady=(px(8), 0))
            self.blocks.append((more, more))
        self.canvas.yview_moveto(0)
        self.refresh()

    def refresh(self):
        self._later = None
        width = max(160, self.canvas.winfo_width() - self.app.px(6))
        size, text, colours = self.size.get(), self.sample(), self.colours()
        for i, face in enumerate(self.faces):
            head, body = self.blocks[i]
            body.config(bg=colours["bg"])

            def draw(face=face):
                return preview.draw_text(face, text, size, width, colours["fg"], colours["bg"])

            def done(result, body=body):
                if not body.winfo_exists():
                    return
                if result is None:
                    body.config(image='', text=t('prev.cant'), fg=T["pink"], bg=T["bg"],
                                font=self.app.f_small, height=1)
                    body.image = None
                    return
                png, _h = result
                body.image = tk.PhotoImage(data=png)
                body.config(image=body.image, text='')
            key = (face.path, face.index, size, text, colours["fg"], colours["bg"], width)
            self.app.renderer.request(f'prev{i}', key, draw, done)


# ─── Characters ──────────────────────────────────────────────

class CharsPane(tk.Frame):
    COLS = 16
    PAGE = 256

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["bg"])
        self.app = app
        px = app.px
        self.face: Optional[fcdata.Face] = None
        self.chars: List[int] = []
        self.page = 0
        self.mark: Optional[int] = None
        self.cell = px(34)
        self.image = None
        self._token = 0

        top = tk.Frame(self, bg=T["bg"])
        top.pack(fill="x", pady=(0, px(6)))
        tk.Label(top, text=t('chars.find'), bg=T["bg"], fg=T["muted"],
                 font=app.f_label).pack(side="left")
        self.var = tk.StringVar()
        self.entry = entry(top, self.var, app.f_body, width=14)
        self.entry.pack(side="left", padx=(px(8), px(6)), ipady=px(3))
        self.entry.bind("<Return>", lambda _e: self.find())
        WolkButton(top, t('chars.go'), self.find, app.f_label).pack(side="left")
        self.count = tk.Label(top, text='', bg=T["bg"], fg=T["muted"], font=app.f_small)
        self.count.pack(side="right")

        pager = tk.Frame(self, bg=T["bg"])
        pager.pack(fill="x", pady=(0, px(6)))
        self.prev = WolkButton(pager, t('chars.prev'), lambda: self.go(self.page - 1),
                               app.f_label, padx=10, pady=3)
        self.prev.pack(side="left")
        self.next = WolkButton(pager, t('chars.next'), lambda: self.go(self.page + 1),
                               app.f_label, padx=10, pady=3)
        self.next.pack(side="left", padx=(px(6), 0))
        self.range = tk.Label(pager, text='', bg=T["bg"], fg=T["text"], font=app.f_body)
        self.range.pack(side="left", padx=(px(10), 0))

        self.canvas = tk.Canvas(self, bg=T["panel"], highlightthickness=1,
                                highlightbackground=T["line"], bd=0,
                                width=self.cell * self.COLS + 1, height=self.cell * 4)
        self.canvas.pack(anchor="nw")
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda _e: self.info.config(text=self._default_info()))
        self.canvas.bind("<ButtonRelease-1>", self._click)
        self.info = tk.Label(self, text='', bg=T["bg"], fg=T["text"], font=app.f_body,
                             anchor="w")
        self.info.pack(fill="x", pady=(px(8), 0))
        self.hint = tk.Label(self, text=t('chars.hint'), bg=T["bg"], fg=T["muted"],
                             font=app.f_small, anchor="w", justify="left",
                             wraplength=px(520))
        self.hint.pack(fill="x")

    def _default_info(self) -> str:
        return t('chars.none') if not self.chars else ''

    def show(self, face: Optional[fcdata.Face]):
        if face is not None and self.face is not None and \
                (face.path, face.index) == (self.face.path, self.face.index):
            self.face = face
            return
        self.face, self.chars, self.page, self.mark = face, [], 0, None
        self.canvas.delete("all")
        self.count.config(text='')
        self.range.config(text='')
        self.info.config(text='')
        self._buttons()
        if face is None:
            return
        self._token += 1
        token = self._token

        def done(result):
            if token != self._token:
                return
            self.chars = result or []
            self.count.config(text=t('chars.count', n=len(self.chars)))
            self.info.config(text=self._default_info())
            self.draw()
        self.app.renderer.request('chars', ('chars', face.path, face.index),
                                  lambda: preview.charset(face.path, face.index), done)

    def pages(self) -> int:
        return max(1, -(-len(self.chars) // self.PAGE))

    def _buttons(self):
        self.prev.set_enabled(self.page > 0)
        self.next.set_enabled(self.page < self.pages() - 1)

    def go(self, page: int):
        page = max(0, min(self.pages() - 1, page))
        if page != self.page:
            self.page = page
            self.draw()

    def chunk(self) -> List[int]:
        return self.chars[self.page * self.PAGE:(self.page + 1) * self.PAGE]

    def draw(self):
        self._buttons()
        chunk = self.chunk()
        if not chunk or self.face is None:
            self.canvas.delete("all")
            self.range.config(text='')
            return
        self.range.config(text=f"U+{chunk[0]:04X} - U+{chunk[-1]:04X}   "
                          f"{self.page + 1}/{self.pages()}")
        face, cell, mark = self.face, self.cell, self.mark
        self._token += 1
        token = self._token
        page = self.page

        def draw():
            return preview.grid_image(face, chunk, cell, self.COLS, T["text"], T["panel"],
                                      T["line"], mark)

        def done(result):
            if token != self._token or page != self.page:
                return
            self.canvas.delete("all")
            if result is None:
                self.info.config(text=t('prev.cant'))
                return
            png, w, h = result
            self.image = tk.PhotoImage(data=png)
            self.canvas.config(width=w, height=h)
            self.canvas.create_image(0, 0, image=self.image, anchor="nw")
        self.app.renderer.request('grid', ('grid', face.path, face.index, tuple(chunk), cell,
                                           mark), draw, done)

    def _char_at(self, event) -> Optional[int]:
        col, row = event.x // self.cell, event.y // self.cell
        if not 0 <= col < self.COLS or row < 0:
            return None
        i = row * self.COLS + col
        chunk = self.chunk()
        return chunk[i] if i < len(chunk) else None

    def _hover(self, event):
        c = self._char_at(event)
        if c is None:
            self.info.config(text=self._default_info())
        else:
            self.info.config(text=f"U+{c:04X}  {preview.char_name(c)}")

    def _click(self, event):
        c = self._char_at(event)
        if c is not None:
            self.clipboard_clear()
            self.clipboard_append(chr(c))
            self.app.set_status('status.copied')
            self.app.event()

    def find(self):
        c = preview.parse_char_query(self.var.get())
        if c is None:
            self.info.config(text=t('chars.bad_query'))
            return
        if c not in self.chars:
            self.info.config(text=t('chars.missing', code=f"U+{c:04X}"))
            return
        self.mark = c
        self.page = self.chars.index(c) // self.PAGE
        self.info.config(text=f"U+{c:04X}  {preview.char_name(c)}")
        self.draw()


# ─── Details ─────────────────────────────────────────────────

class DetailsPane(tk.Frame):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["bg"])
        self.app = app
        from tkinter import ttk
        self.text = tk.Text(self, bg=T["panel"], fg=T["text"], font=app.f_body, wrap="word",
                            relief="flat", bd=0, highlightthickness=1,
                            highlightbackground=T["line"], padx=app.px(12), pady=app.px(10),
                            cursor="arrow", state="disabled", spacing3=app.px(3),
                            selectbackground=T["line2"], inactiveselectbackground=T["line2"])
        bar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview,
                            style="Spark.Vertical.TScrollbar")
        self.text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("key", foreground=T["muted"], font=app.f_label)
        self.text.tag_configure("val", foreground=T["text"])
        self.text.tag_configure("warn", foreground=T["gold"])
        self.text.tag_configure("head", foreground=T["accent"], font=app.f_label,
                                spacing1=app.px(8))
        self.text.tag_configure("small", foreground=T["muted"], font=app.f_small)

    def put(self, rows: List[Tuple[str, str, str]]):
        """rows: (kind, label, value); kind is 'row', 'head', 'note' or 'long'."""
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        for kind, label, value in rows:
            if kind == 'head':
                self.text.insert("end", label.upper() + "\n", "head")
            elif kind == 'note':
                self.text.insert("end", value + "\n", "warn")
            elif kind == 'long':
                self.text.insert("end", value + "\n", "small")
            else:
                self.text.insert("end", label.upper() + "  ", "key")
                self.text.insert("end", value + "\n", "val")
        self.text.config(state="disabled")
        self.text.yview_moveto(0)

    def plain(self) -> str:
        return self.text.get("1.0", "end")

    def show_face(self, family: fcdata.Family, face: fcdata.Face):
        self.put(describe(family, face))

    def show_broken(self, path: str):
        try:
            size = human_size(__import__('os').path.getsize(path))
        except OSError:
            size = '?'
        self.put([('head', t('det.broken_head'), ''),
                  ('row', t('det.file'), home_short(path)),
                  ('row', t('det.size'), size),
                  ('note', '', t('det.broken_why'))])


def describe(family: fcdata.Family, face: fcdata.Face) -> List[Tuple[str, str, str]]:
    import os
    try:
        d = fontfile.read_details(face.path, face.face_index)
    except fontfile.FontError:
        d = fontfile.Details()
    rows: List[Tuple[str, str, str]] = [('head', t('det.font'), '')]

    def row(label, value):
        if value:
            rows.append(('row', label, str(value)))
    row(t('det.family'), family.name)
    row(t('det.style'), face.style)
    row(t('det.fullname'), d.get(fontfile.N_FULL) or face.fullname)
    row(t('det.version'), (d.get(fontfile.N_VERSION) or face.version_text).replace(
        'Version ', ''))
    row(t('det.designer'), d.get(fontfile.N_DESIGNER))
    row(t('det.foundry'), d.get(fontfile.N_FOUNDRY))
    row(t('det.copyright'), d.get(fontfile.N_COPYRIGHT))
    rows.append(('head', t('det.file_head'), ''))
    row(t('det.file'), home_short(face.path))
    try:
        row(t('det.size'), human_size(os.path.getsize(face.path)))
    except OSError:
        pass
    row(t('det.format'), face.format)
    if d.faces > 1:
        row(t('det.in_collection'), t('det.face_of', n=face.face_index + 1, total=d.faces))
    if fcdata.is_user_font(face.path):
        row(t('det.where'), t('det.mine'))
    else:
        row(t('det.where'), t('det.system'))
    rows.append(('head', t('det.features'), ''))
    if face.variable or d.axes:
        axes = ", ".join(f"{a.tag.strip()} {a.low:g}-{a.high:g} ({t('det.default')} {a.default:g})"
                         for a in d.axes)
        row(t('det.variable'), axes or t('det.yes'))
    else:
        row(t('det.variable'), t('det.no'))
    row(t('det.spacing'), t('det.mono') if face.spacing in (90, 100) else t('det.proportional'))
    names = [t('lang.' + code) for code in fcdata.LANGUAGES if code in face.langs]
    row(t('det.languages'), t('det.lang_count', n=len(face.langs)) +
        (" (" + ", ".join(names) + ")" if names else ''))
    lic, url = d.get(fontfile.N_LICENSE), d.get(fontfile.N_LICENSE_URL)
    rows.append(('head', t('det.license'), ''))
    if lic or url:
        if lic:
            rows.append(('long', '', lic))
        row(t('det.license_url'), url)
    else:
        rows.append(('note', '', t('det.no_license')))
    return rows
