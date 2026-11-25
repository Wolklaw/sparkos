"""The annotate window: a toolbar, the picture, Copy and Save. The drawing itself lives in
annotate.py; this file only turns mouse moves into Items and shows the result."""

import tkinter as tk
from tkinter import colorchooser
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageTk

from . import APP_NAME, dialogs
from .annotate import (PRESET_COLOURS, SHAPE_TOOLS, STROKE_TOOLS, Document, Item, default_width,
                       normalise, render_item, text_size)
from .core import Monitor
from .text import t
from .widgets import T, Strip, WolkButton

if TYPE_CHECKING:
    from .app import App

TOOL_KEYS = ("arrow", "rect", "ellipse", "pen", "highlight", "text", "step", "pixelate", "crop")
SCREEN_SHARE = 0.84          # the picture may fill this much of the monitor


class EditorWindow(tk.Toplevel):
    """on_done(image, action) gets the annotated picture and 'copy' or 'save'; on_cancel() when
    the person backs out."""

    def __init__(self, app: "App", image: Image.Image, near: Monitor,
                 on_done: Callable[[Image.Image, str], None], on_cancel: Callable[[], None]):
        super().__init__(app.root)
        self.app, self.on_done, self.on_cancel = app, on_done, on_cancel
        self.withdraw()
        self.doc = Document(image)
        self.near = near
        self.tool = "arrow"
        self.colour = PRESET_COLOURS[0]
        self.width = default_width(image.size)
        self.closed = False
        self._drag: Optional[List[Tuple[float, float]]] = None
        self._preview_ids: List[int] = []
        self._entry: Optional[tk.Entry] = None
        self._entry_at: Tuple[float, float] = (0, 0)
        self._photo = None
        self._base_render: Optional[Image.Image] = None
        self.view = 1.0
        self.tool_buttons: Dict[str, WolkButton] = {}
        self.swatches: Dict[str, tk.Frame] = {}

        self.title(f"{APP_NAME}: {t('ed.title')}")
        self.configure(bg=T["bg"])
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        if app.icon is not None:
            self.iconphoto(False, app.icon)
        self._build()
        self._bind_keys()
        self.set_colour(self.colour)
        self._rebuild()
        self.deiconify()
        self.lift()
        self.after(10, lambda: self.closed or self.focus_force())

    # layout
    def _build(self):
        app, bg = self.app, T["bg"]
        px, small = app.px, app.font(8)
        self.strip = Strip(self, height=px(2))
        self.strip.pack(side="top", fill="x")
        self.strip.draw(fraction=0)

        bar = tk.Frame(self, bg=bg)
        bar.pack(side="top", fill="x", padx=px(12), pady=(px(10), px(4)))
        for key in TOOL_KEYS:
            button = WolkButton(bar, t(f'ed.tool.{key}'), lambda k=key: self.set_tool(k), small,
                                variant="ghost", padx=px(8), pady=px(4))
            button.pack(side="left", padx=(0, px(2)))
            self.tool_buttons[key] = button

        opts = tk.Frame(self, bg=bg)
        opts.pack(side="top", fill="x", padx=px(14), pady=(px(2), px(6)))
        tk.Label(opts, text=t('ed.colour'), bg=bg, fg=T["dim"], font=app.font(7)).pack(side="left")
        for colour in PRESET_COLOURS:
            self._swatch(opts, colour)
        custom = WolkButton(opts, t('ed.custom'), self.pick_custom_colour, small, variant="ghost",
                            padx=px(6), pady=px(1))
        custom.pack(side="left", padx=(px(4), 0))
        tk.Label(opts, text=t('ed.width'), bg=bg, fg=T["dim"], font=app.font(7)).pack(
            side="left", padx=(px(18), px(6)))
        self.scale = tk.Scale(opts, from_=1, to=40, orient="horizontal", showvalue=True,
                              length=px(150), bg=bg, fg=T["text"], troughcolor=T["panel2"],
                              highlightthickness=0, bd=0, sliderrelief="flat",
                              activebackground=T["accent"], font=app.font(7),
                              command=self._on_width)
        self.scale.set(self.width)
        self.scale.pack(side="left")
        self.redo_btn = WolkButton(opts, t('ed.redo'), self.redo, small, variant="ghost",
                                   padx=px(8), pady=px(4))
        self.redo_btn.pack(side="right")
        self.undo_btn = WolkButton(opts, t('ed.undo'), self.undo, small, variant="ghost",
                                   padx=px(8), pady=px(4))
        self.undo_btn.pack(side="right", padx=(0, px(2)))

        foot = tk.Frame(self, bg=bg)
        foot.pack(side="bottom", fill="x", padx=px(12), pady=(px(6), px(12)))
        self.hint = tk.Label(foot, text="", bg=bg, fg=T["dim"], font=app.font(7), anchor="w")
        self.hint.pack(side="left")
        WolkButton(foot, t('ed.save'), self.save, small, variant="ghost", padx=px(10)).pack(
            side="right")
        WolkButton(foot, t('ed.copy'), self.copy, small, variant="primary", padx=px(14)).pack(
            side="right", padx=px(4))
        WolkButton(foot, t('ed.cancel'), self.cancel, small, variant="danger", padx=px(10)).pack(
            side="right", padx=(0, px(10)))
        self.size_label = tk.Label(foot, text="", bg=bg, fg=T["muted"], font=app.font(7))
        self.size_label.pack(side="right", padx=px(12))

        frame = tk.Frame(self, bg=T["line2"])
        frame.pack(side="top", padx=px(14), pady=px(4))
        self.canvas = tk.Canvas(frame, bg=T["out_bg"], highlightthickness=0, bd=0,
                                cursor="crosshair")
        self.canvas.pack(padx=1, pady=1)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.set_tool("arrow")

    def _swatch(self, parent: tk.Misc, colour: str):
        px = self.app.px
        box = tk.Frame(parent, bg=T["bg"], padx=2, pady=2)
        box.pack(side="left", padx=px(2))
        chip = tk.Frame(box, bg=colour, width=px(18), height=px(18), cursor="hand2")
        chip.pack()
        chip.bind("<ButtonRelease-1>", lambda _e, c=colour: self.set_colour(c))
        self.swatches[colour] = box

    def _bind_keys(self):
        for seq, fn in (("<Control-z>", self.undo), ("<Control-y>", self.redo),
                        ("<Control-Z>", self.redo), ("<Control-c>", self.copy),
                        ("<Control-s>", self.save)):
            self.bind(seq, lambda _e, f=fn: self._shortcut(f))
        self.bind("<Escape>", lambda _e: self._escape())

    def _shortcut(self, fn: Callable[[], None]):
        if self._entry is not None and fn in (self.undo, self.redo, self.copy):
            return "break"          # the text box owns its own keys while it is open
        fn()
        return "break"

    # settings
    def set_tool(self, tool: str):
        self._drop_entry()
        self.tool = tool
        for key, button in self.tool_buttons.items():
            self._style(button, "primary" if key == tool else "ghost")
        self.hint.config(text=t('ed.hint.crop') if tool == "crop" else t('ed.hint'))
        if hasattr(self, "canvas"):
            self.canvas.configure(cursor="crosshair")

    def _style(self, button: WolkButton, variant: str):
        button.variant = variant
        button.bg_idle, button.fg_idle, button.border_idle, button.bg_hover = \
            WolkButton.STYLES[variant]
        button.label.config(bg=button.bg_idle, fg=button.fg_idle)
        button.box.config(bg=button.border_idle)

    def set_colour(self, colour: str):
        self.colour = colour
        for key, box in self.swatches.items():
            box.config(bg=T["accent"] if key == colour else T["bg"])

    def pick_custom_colour(self):
        _rgb, chosen = colorchooser.askcolor(color=self.colour, parent=self,
                                             title=t('ed.pick_colour'))
        if chosen:
            self.set_colour(chosen.lower())

    def _on_width(self, value: str):
        self.width = float(value)

    # history
    def undo(self):
        if self.doc.undo():
            self._after_history()

    def redo(self):
        if self.doc.redo():
            self._after_history()

    def _after_history(self):
        self._drop_entry()
        self._rebuild()

    # the picture
    def _fit(self):
        sw, sh = self.near.w, self.near.h
        iw, ih = self.doc.size
        self.view = min(1.0, sw * SCREEN_SHARE / iw, (sh * SCREEN_SHARE - self.app.px(170)) / ih)
        self.view = max(self.view, 0.05)

    def _rebuild(self):
        """Redraw from scratch: after undo, redo and crop."""
        self._fit()
        self._base_render = self.doc.base.convert("RGBA")
        for item in self.doc.items:
            render_item(self._base_render, item)
        self._show()
        self.undo_btn.set_enabled(self.doc.can_undo())
        self.redo_btn.set_enabled(self.doc.can_redo())
        self.size_label.config(text=t('ed.size', w=self.doc.size[0], h=self.doc.size[1]))

    def _show(self):
        iw, ih = self.doc.size
        vw, vh = max(1, int(iw * self.view)), max(1, int(ih * self.view))
        shown = self._base_render.convert("RGB")
        if (vw, vh) != (iw, ih):
            shown = shown.resize((vw, vh), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(shown, master=self)
        self.canvas.configure(width=vw, height=vh)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self._preview_ids = []
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        left = self.near.x + max(0, (self.near.w - w) // 2)
        top = self.near.y + max(0, (self.near.h - h) // 2)
        self.geometry(f"+{left}+{top}")

    def _to_image(self, x: float, y: float) -> Tuple[float, float]:
        iw, ih = self.doc.size
        return (min(max(x / self.view, 0), iw), min(max(y / self.view, 0), ih))

    # mouse
    def _press(self, event):
        self.canvas.focus_set()
        if self._entry is not None:
            self._commit_text()
        point = self._to_image(event.x, event.y)
        if self.tool == "text":
            self._open_entry(point, event.x, event.y)
            return
        if self.tool == "step":
            item = Item("step", (point,), self.colour, self.width,
                        str(self.doc.next_step_number()))
            self._add(item)
            return
        self._drag = [point]

    def _motion(self, event):
        if self._drag is None:
            return
        point = self._to_image(event.x, event.y)
        if self.tool in STROKE_TOOLS:
            if (abs(point[0] - self._drag[-1][0]) + abs(point[1] - self._drag[-1][1])
                    >= 1 / self.view):
                self._drag.append(point)
        else:
            self._drag = [self._drag[0], point]
        self._draw_preview()

    def _release(self, event):
        if self._drag is None:
            return
        self._motion(event)
        points, self._drag = self._drag, None
        self._clear_preview()
        if self.tool == "crop":
            if len(points) > 1 and self.doc.crop(normalise(points[0], points[-1])):
                self._rebuild()
            return
        if self.tool in SHAPE_TOOLS:
            if len(points) < 2:
                return
            points = [points[0], points[-1]]
        self._add(Item(self.tool, tuple(points), self.colour, self.width))

    def _add(self, item: Item):
        if not self.doc.add(item):
            return
        render_item(self._base_render, item)
        self._show()
        self.undo_btn.set_enabled(True)
        self.redo_btn.set_enabled(False)

    # live outline while dragging (cheap canvas shapes, not the real render)
    def _clear_preview(self):
        for ident in self._preview_ids:
            self.canvas.delete(ident)
        self._preview_ids = []

    def _draw_preview(self):
        self._clear_preview()
        v = self.view
        pts = [(x * v, y * v) for x, y in self._drag]
        w = max(1, int(self.width * v))
        c = self.canvas
        if self.tool in STROKE_TOOLS:
            if len(pts) >= 2:
                ident = c.create_line(*[n for p in pts for n in p], fill=self.colour,
                                      width=w, capstyle="round", joinstyle="round")
                self._preview_ids.append(ident)
            return
        if len(pts) < 2:
            return
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        if self.tool == "arrow":
            ident = c.create_line(x0, y0, x1, y1, fill=self.colour, width=w, arrow="last",
                                  arrowshape=(w * 3, w * 3.5, w * 1.5))
        elif self.tool == "ellipse":
            ident = c.create_oval(x0, y0, x1, y1, outline=self.colour, width=w)
        elif self.tool == "rect":
            ident = c.create_rectangle(x0, y0, x1, y1, outline=self.colour, width=w)
        else:                          # pixelate and crop: a dashed frame in the two channels
            ident = c.create_rectangle(x0, y0, x1, y1, outline=T["ch_b"], dash=(5, 4), width=2)
            self._preview_ids.append(c.create_rectangle(
                x0 + 1, y0 + 1, x1 + 1, y1 + 1, outline=T["ch_a"], dash=(5, 4)))
        self._preview_ids.append(ident)

    # text
    def _open_entry(self, point: Tuple[float, float], cx: float, cy: float):
        size = text_size(Item("text", (point,), self.colour, self.width))
        family = self.app.mono
        self._entry_at = point
        self._entry = tk.Entry(self.canvas, bg=T["bg"], fg=self.colour, relief="flat", bd=1,
                               insertbackground=self.colour, highlightthickness=1,
                               highlightbackground=T["ch_b"], highlightcolor=T["ch_a"],
                               font=(family, max(8, int(size * self.view * 0.75))), width=22)
        self.canvas.create_window(cx, cy, window=self._entry, anchor="nw", tags="entry")
        self.hint.config(text=t('ed.hint.text'))
        self._entry.bind("<Return>", lambda _e: self._commit_text())
        self._entry.bind("<Escape>", lambda _e: (self._drop_entry(), "break")[1])
        self._entry.focus_set()

    def _commit_text(self):
        entry, self._entry = self._entry, None
        if entry is None:
            return
        text = entry.get()
        entry.destroy()
        self.canvas.delete("entry")
        self.hint.config(text=t('ed.hint'))
        if text.strip():
            self._add(Item("text", (self._entry_at,), self.colour, self.width, text))

    def _drop_entry(self):
        entry, self._entry = self._entry, None
        if entry is not None:
            entry.destroy()
            self.canvas.delete("entry")
            self.hint.config(text=t('ed.hint'))

    # leaving
    def _escape(self):
        if self._entry is not None:
            self._drop_entry()
            return
        self.cancel()

    def copy(self):
        self._finish("copy")

    def save(self):
        self._finish("save")

    def _finish(self, action: str):
        if self.closed:
            return
        if self._entry is not None:
            self._commit_text()
        image = self.doc.result()
        self._close()
        self.on_done(image, action)

    def cancel(self):
        if self.closed:
            return
        if self._entry is not None:
            self._drop_entry()
        if self.doc.dirty and not dialogs.askyesno(t('ed.discard.title'), t('ed.discard.body'),
                                                  parent=self):
            return
        self._close()
        self.on_cancel()

    def _close(self):
        self.closed = True
        try:
            self.destroy()
        except tk.TclError:
            pass
