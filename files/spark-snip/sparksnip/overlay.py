"""The capture overlay: the frozen screen, dimmed, one full-screen window per monitor.

Drag a box, or click once for the whole monitor. The chip at the top switches between
TEXT, IMAGE and VIDEO (also T, I and V on the keyboard). Esc or a right-click cancels.
"""

import random
from typing import TYPE_CHECKING, Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont
from PIL import Image, ImageTk

from . import APP_NAME, MODES
from .core import Box, Monitor, bounding_box, language_short, log, screen_to_image
from .text import t
from .widgets import T

if TYPE_CHECKING:
    from .app import App

OVERLAY_MAX_SECONDS = 120   # hard ceiling on how long the overlay may cover the screen
DIM = 0.62                  # how far the frozen screen is pulled towards the background
MIN_DRAG = 5                # smaller than this is a click: the whole monitor


class Selection(NamedTuple):
    mode: str
    image: Image.Image          # the picked area, from the frozen screen, full resolution
    region: Box                 # the picked area in screen coordinates
    monitor: Monitor


class _Screen(NamedTuple):
    window: tk.Toplevel
    canvas: tk.Canvas
    monitor: Monitor
    bright: Image.Image          # this monitor's slice of the frozen screen, at display size
    photos: List[Any]            # keeps Tk's images alive
    items: Dict[str, Any]


class SnipOverlay:
    """Every exit path funnels through _finish(), which is idempotent, destroys every window
    and calls back once. An overlay that cannot be dismissed looks like a frozen desktop."""

    def __init__(self, app: "App", shot: Image.Image, layout: List[Monitor], mode: str,
                 on_done: Callable[[Optional[Selection]], None]):
        self.app, self.shot, self.on_done, self.mode = app, shot, on_done, mode
        self.desktop = bounding_box(layout)
        self.finished = False
        self.start: Optional[Tuple[int, int]] = None
        self.current: Optional[Tuple[int, int]] = None
        self.active: Optional[_Screen] = None
        self._pending: Optional[str] = None
        self.hint_font = tkfont.Font(app.root, family=app.mono, size=11, weight="bold")
        self.size_font = tkfont.Font(app.root, family=app.mono, size=9, weight="bold")
        px, py = app.root.winfo_pointerxy()
        under = [m for m in layout if m.contains(px, py)]
        self.hint_on = under[0] if under else layout[0]
        self.screens = [self._make_screen(m) for m in layout]
        self._deadline = app.root.after(OVERLAY_MAX_SECONDS * 1000, self.cancel)
        focus = next(s for s in self.screens if s.monitor == self.hint_on)
        app.root.after(60, lambda: self._focus(focus))
        if app.glitch.enabled:
            app.root.after(450, lambda: self._tear_hint(focus))

    # building
    @staticmethod
    def _cross_line(win: tk.Toplevel, w: int, h: int) -> tk.Canvas:
        line = tk.Canvas(win, width=w, height=h, bg=T["bg"], highlightthickness=0, bd=0,
                         cursor="crosshair")
        line.create_line(0, 0, w if w > 1 else 0, h if h > 1 else 0, fill=T["line2"],
                         dash=(4, 4))
        return line

    def _make_screen(self, monitor: Monitor) -> _Screen:
        x, y, w, h = monitor.x, monitor.y, monitor.w, monitor.h
        win = tk.Toplevel(self.app.root)
        win.withdraw()
        win.title(f"{APP_NAME} capture")
        win.configure(bg=T["bg"])
        win.geometry(f"{w}x{h}+{x}+{y}")
        box = screen_to_image(monitor.box, self.desktop, self.shot.size)
        bright = self.shot.crop(box)
        if bright.size != (w, h):
            bright = bright.resize((w, h), Image.Resampling.BILINEAR)
        dim = Image.blend(bright, Image.new('RGB', bright.size, T["bg"]), DIM)
        canvas = tk.Canvas(win, width=w, height=h, bg=T["bg"], highlightthickness=0, bd=0,
                           cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        dim_photo = ImageTk.PhotoImage(dim, master=win)
        canvas.create_image(0, 0, anchor="nw", image=dim_photo)
        items: Dict[str, Any] = {
            # The crosshair lines are 1 px child windows, not canvas items: the canvas keeps one
            # redraw box, so moving two full-length lines repainted the whole screenshot on
            # every mouse event and the lines trailed the pointer. A moved window only
            # repaints the strip it uncovers.
            "hline": self._cross_line(win, w, 1),
            "vline": self._cross_line(win, 1, h),
            "bright": canvas.create_image(0, 0, anchor="nw", state="hidden"),
            "ghost_a": canvas.create_rectangle(0, 0, 0, 0, outline=T["ch_a"], state="hidden"),
            "ghost_b": canvas.create_rectangle(0, 0, 0, 0, outline=T["ch_b"], state="hidden"),
            "frame": canvas.create_rectangle(0, 0, 0, 0, outline=T["accent"], state="hidden"),
            "corners": [canvas.create_line(0, 0, 0, 0, fill=T["accent"], width=3,
                                           capstyle="projecting", state="hidden")
                        for _ in range(4)],
            "size_bg": canvas.create_rectangle(0, 0, 0, 0, fill=T["panel"], outline=T["line2"],
                                               state="hidden"),
            "size": canvas.create_text(0, 0, anchor="nw", font=self.size_font, fill=T["text"],
                                       state="hidden"),
            "hint_box": None,
        }
        screen = _Screen(win, canvas, monitor, bright, [dim_photo], items)
        if monitor == self.hint_on:
            self._draw_hint(screen)

        def at(e):          # the pointer sits on a crosshair line most of the time
            if e.widget is canvas:
                return e.x, e.y
            return e.widget.winfo_x() + e.x, e.widget.winfo_y() + e.y
        for widget in (canvas, items["hline"], items["vline"]):
            widget.bind("<Motion>", lambda e: self.motion(screen, *at(e)))
            widget.bind("<ButtonPress-1>", lambda e: self.press(screen, *at(e)))
            widget.bind("<B1-Motion>", lambda e: self.drag(screen, *at(e)))
            widget.bind("<ButtonRelease-1>", lambda e: self.release(screen, *at(e)))
            widget.bind("<ButtonPress-3>", lambda _e: self.cancel())
        # the compositor tells a new window where a still pointer is with an Enter, no Motion
        canvas.bind("<Enter>", lambda e: self.motion(screen, e.x, e.y))
        win.bind("<Escape>", lambda _e: self.cancel())
        win.bind("<Key>", self._on_key)
        win.bind("<Destroy>", lambda e: self.cancel() if e.widget is win else None)
        win.protocol("WM_DELETE_WINDOW", self.cancel)
        try:
            win.attributes('-fullscreen', True)
            win.attributes('-topmost', True)
        except tk.TclError:
            log.warning("could not make the overlay full screen")
        win.deiconify()
        # Map this window before building the next one: Tk maps every new toplevel in one
        # idle pass otherwise, and with -fullscreen on the Spark compositor that pass waits
        # out Tk's 2 s window-manager timeout before the other monitors get their overlay.
        win.update_idletasks()
        return screen

    def _instructions(self) -> str:
        if self.mode == "text":
            return t('overlay.text', lang=language_short(self.app.ocr.lang))
        if self.mode == "image":
            return t('overlay.image')
        mic = t('on') if self.app.config.get("mic") else t('off')
        sound = t('on') if self.app.config.get("sound", True) else t('off')
        return t('overlay.video', mic=mic, sound=sound)

    def _draw_hint(self, screen: _Screen):
        c, w = screen.canvas, screen.monitor.w
        c.delete("hint")
        font, px = self.hint_font, self.app.px
        title, rest = "SPARK SNIP", self._instructions()
        pad_x, pad_y, gap, seg_pad = px(16), px(10), px(14), px(10)
        line_h = font.metrics("linespace")
        seg_w = [font.measure(t(f'mode.{m}').upper()) + 2 * seg_pad for m in MODES]
        width = (font.measure(title) + gap + sum(seg_w) + gap + font.measure(rest) + 2 * pad_x)
        height = line_h + 2 * pad_y
        x0, y0 = max(px(8), (w - width) // 2), px(28)
        cy = y0 + height / 2
        c.create_rectangle(x0, y0, x0 + width, y0 + height, fill=T["panel"], outline=T["line2"],
                           tags=("hint",))
        x = x0 + pad_x
        ghosts = [c.create_text(x + dx, cy, text=title, anchor="w", font=font, fill=colour,
                                tags=("hint",))
                  for dx, colour in ((-2, T["ch_a"]), (2, T["ch_b"]))]
        main = c.create_text(x, cy, text=title, anchor="w", font=font, fill=T["text"],
                             tags=("hint",))
        screen.items["hint"] = (ghosts, main, x, cy)
        x += font.measure(title) + gap
        for mode, sw in zip(MODES, seg_w):
            on = mode == self.mode
            tag = f"mode-{mode}"
            c.create_rectangle(x, y0 + px(5), x + sw, y0 + height - px(5),
                               fill=T["accent"] if on else T["panel2"],
                               outline=T["accent"] if on else T["line2"], tags=("hint", tag))
            c.create_text(x + sw / 2, cy, text=t(f'mode.{mode}').upper(), font=font,
                          fill=T["on_accent"] if on else T["muted"], tags=("hint", tag))
            c.tag_bind(tag, "<ButtonRelease-1>", lambda _e, m=mode: self.set_mode(m))
            c.tag_bind(tag, "<Enter>", lambda _e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda _e: c.configure(cursor="crosshair"))
            x += sw
        x += gap
        c.create_text(x, cy, text=rest, anchor="w", font=font, fill=T["muted"], tags=("hint",))
        screen.items["hint_box"] = (x0, y0, x0 + width, y0 + height)

    def set_mode(self, mode: str):
        if mode == self.mode or self.finished:
            return
        self.mode = mode
        self.app.remember_mode(mode)
        for screen in self.screens:
            if screen.items["hint_box"]:
                self._draw_hint(screen)
                if self.app.glitch.enabled:
                    self._tear_hint(screen)

    def _on_key(self, event):
        key = (event.keysym or '').lower()
        if key in ('t', 'i', 'v'):
            self.set_mode({'t': 'text', 'i': 'image', 'v': 'video'}[key])
        elif self.mode == 'video' and key in ('m', 's'):
            name, default = ('mic', False) if key == 'm' else ('sound', True)
            self.app.set_option(name, not self.app.config.get(name, default))
            for screen in self.screens:
                if screen.items["hint_box"]:
                    self._draw_hint(screen)

    def _tear_hint(self, screen: _Screen, i: int = 0):
        if self.finished or "hint" not in screen.items:
            return
        ghosts, main, x, y = screen.items["hint"]
        c = screen.canvas
        try:
            if i < 6:
                jitter = random.uniform(-5, 5)
                c.coords(ghosts[0], x - 2 - abs(jitter), y + random.choice((0, -1, 1)))
                c.coords(ghosts[1], x + 2 + abs(jitter), y)
                c.coords(main, x + jitter / 2, y)
                self.app.root.after(45, lambda: self._tear_hint(screen, i + 1))
            else:
                c.coords(ghosts[0], x - 2, y)
                c.coords(ghosts[1], x + 2, y)
                c.coords(main, x, y)
        except tk.TclError:
            pass

    def _focus(self, screen: _Screen):
        if self.finished:
            return
        try:
            screen.window.focus_force()
            screen.canvas.focus_set()
            # show the crosshair where the pointer already is, not after the first move
            px, py = self.app.root.winfo_pointerxy()
            for other in self.screens:
                if other.monitor.contains(px, py):
                    self.motion(other, px - other.monitor.x, py - other.monitor.y)
        except tk.TclError:
            log.warning("overlay could not take focus; right-click still cancels")

    # input
    def _on_hint(self, screen: _Screen, x: int, y: int) -> bool:
        box = screen.items["hint_box"]
        return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def motion(self, screen: _Screen, x: int, y: int):
        if self.start is not None or self.finished:
            return
        w, h = screen.monitor.w, screen.monitor.h
        for other in self.screens:
            if other is not screen:
                other.items["hline"].place_forget()
                other.items["vline"].place_forget()
        if self._on_hint(screen, x, y):     # the mode buttons need the clicks, not the lines
            screen.items["hline"].place_forget()
            screen.items["vline"].place_forget()
            return
        screen.items["hline"].place(x=0, y=max(0, min(h - 1, y)))
        screen.items["vline"].place(x=max(0, min(w - 1, x)), y=0)

    # The selection lives in desktop coordinates, so a box can start on one monitor and end
    # on another (or reach a panel at the far edge). Every monitor draws its own slice of it.
    def _global(self, screen: _Screen, x: int, y: int) -> Tuple[int, int]:
        return screen.monitor.x + x, screen.monitor.y + y

    def _bounds(self) -> Box:
        """Where the drag may go: the whole desktop, or for a video the monitor it started
        on (a recording is of one screen)."""
        if self.mode == "video" and self.active is not None:
            return self.active.monitor.box
        return self.desktop

    def press(self, screen: _Screen, x: int, y: int):
        if self.finished or self._on_hint(screen, x, y):
            return
        g = self._global(screen, x, y)
        self.active, self.start, self.current = screen, g, g
        for other in self.screens:
            other.items["hline"].place_forget()
            other.items["vline"].place_forget()

    def drag(self, screen: _Screen, x: int, y: int):
        if self.start is None or self.finished:
            return
        gx, gy = self._global(screen, x, y)
        bx0, by0, bx1, by1 = self._bounds()
        self.current = (max(bx0, min(bx1, gx)), max(by0, min(by1, gy)))
        if self._pending is None:           # redraw at most once per frame
            self._pending = self.app.root.after(16, self._redraw)

    def _selection(self) -> Optional[Box]:
        if self.start is None or self.current is None:
            return None
        (x1, y1), (x2, y2) = self.start, self.current
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    @staticmethod
    def _hide_selection(screen: _Screen):
        items = screen.items
        for item in (items["bright"], items["ghost_a"], items["ghost_b"], items["frame"],
                     *items["corners"], items["size"], items["size_bg"]):
            screen.canvas.itemconfigure(item, state="hidden")

    def _redraw(self, jitter: float = 0.0, sel: Optional[Box] = None):
        self._pending = None
        sel = sel or self._selection()
        if sel is None or self.finished:
            return
        gx0, gy0, gx1, gy1 = sel
        # the size readout goes on the monitor under the moving corner
        cx, cy = self.current or (gx1, gy1)
        label_on = next((sc for sc in self.screens if sc.monitor.contains(cx, cy)), self.active)
        for screen in self.screens:
            m = screen.monitor
            x0, y0 = max(gx0, m.x) - m.x, max(gy0, m.y) - m.y
            x1, y1 = min(gx1, m.x + m.w) - m.x, min(gy1, m.y + m.h) - m.y
            if x1 <= x0 or y1 <= y0:
                self._hide_selection(screen)
                continue
            self._draw_slice(screen, (x0, y0, x1, y1), (gx0 - m.x, gy0 - m.y, gx1 - m.x,
                                                         gy1 - m.y), jitter,
                             sel if screen is label_on else None)

    def _draw_slice(self, screen: _Screen, part: Box, whole: Box, jitter: float,
                    label_sel: Optional[Box]):
        """Draw this monitor's part of the selection. `whole` is the full box in this monitor's
        coordinates (it may run off the edges); the frame is drawn around it, the canvas
        clips what is outside."""
        c, items = screen.canvas, screen.items
        x0, y0, x1, y1 = part
        if x1 - x0 >= 1 and y1 - y0 >= 1:
            photo = ImageTk.PhotoImage(screen.bright.crop((x0, y0, x1, y1)), master=screen.window)
            screen.photos[1:] = [photo]
            c.itemconfigure(items["bright"], image=photo, state="normal")
            c.coords(items["bright"], x0, y0)
        wx0, wy0, wx1, wy1 = whole
        split = 2 + abs(jitter)
        c.coords(items["ghost_a"], wx0 - split, wy0, wx1 - split, wy1)
        c.coords(items["ghost_b"], wx0 + split, wy0, wx1 + split, wy1)
        c.coords(items["frame"], wx0, wy0, wx1, wy1)
        arm = min(self.app.px(14), (wx1 - wx0) // 2, (wy1 - wy0) // 2)
        for item, (cx, cy, dx, dy) in zip(items["corners"],
                                          ((wx0, wy0, 1, 1), (wx1, wy0, -1, 1),
                                           (wx0, wy1, 1, -1), (wx1, wy1, -1, -1))):
            c.coords(item, cx, cy + dy * arm, cx, cy, cx + dx * arm, cy)
        for item in (items["ghost_a"], items["ghost_b"], items["frame"], *items["corners"]):
            c.itemconfigure(item, state="normal")
        if label_sel is None:
            c.itemconfigure(items["size"], state="hidden")
            c.itemconfigure(items["size_bg"], state="hidden")
            c.tag_raise("hint")
            return
        # size readout, in real screenshot pixels, kept on this monitor
        box = self._image_box(label_sel)
        label = f"{box[2] - box[0]} × {box[3] - box[1]}"
        pad = self.app.px(5)
        tw = self.size_font.measure(label)
        th = self.size_font.metrics("linespace")
        mw, mh = screen.monitor.w, screen.monitor.h
        lx = max(2, min(x1 - tw - 2 * pad, mw - tw - 2 * pad - 2))
        ly = y1 + pad if y1 + th + 3 * pad < mh else max(2, y1 - th - 3 * pad)
        c.coords(items["size_bg"], lx, ly, lx + tw + 2 * pad, ly + th + 2 * pad)
        c.coords(items["size"], lx + pad, ly + pad)
        c.itemconfigure(items["size"], text=label, state="normal")
        c.itemconfigure(items["size_bg"], state="normal")
        c.tag_raise("hint")

    def release(self, screen: _Screen, x: int, y: int):
        if self.finished:
            return
        if self.start is None or self.active is None:
            return                          # a release on the chip, or with no press
        self.drag(screen, x, y)
        if self._pending is not None:
            self.app.root.after_cancel(self._pending)
            self._pending = None
        sel = self._selection()
        if sel is None or sel[2] - sel[0] < MIN_DRAG or sel[3] - sel[1] < MIN_DRAG:
            sel = self.active.monitor.box   # a click: the whole monitor it was on
            self.current = (sel[2], sel[3])
        self._redraw(sel=sel)
        # the monitor holding most of the box gets the popup (and, for a video, the recording)
        def overlap(m):
            return (max(0, min(sel[2], m.x + m.w) - max(sel[0], m.x)) *
                    max(0, min(sel[3], m.y + m.h) - max(sel[1], m.y)))
        m = max((sc.monitor for sc in self.screens), key=overlap)
        image = self.shot.crop(self._image_box(sel))
        log.info("%s: picked %s on %s", self.mode, sel, m.name)
        result = Selection(self.mode, image, sel, m)
        if self.app.glitch.enabled:
            self._tear_selection(sel, lambda: self._finish(result))
        else:
            self._finish(result)

    def _tear_selection(self, sel: Box, then: Callable[[], None], i: int = 0):
        if self.finished:
            return
        if i < 3:
            self._redraw(jitter=random.uniform(2, 6), sel=sel)
            self.app.root.after(40, lambda: self._tear_selection(sel, then, i + 1))
        else:
            then()

    def _image_box(self, sel: Box) -> Box:
        """A box in desktop coordinates, in the screenshot's pixels."""
        return screen_to_image(sel, self.desktop, self.shot.size)

    def cancel(self):
        self._finish(None)

    def _finish(self, result: Optional[Selection]):
        if self.finished:
            return
        self.finished = True
        try:
            self.app.root.after_cancel(self._deadline)
        except (tk.TclError, ValueError):
            pass
        for screen in self.screens:
            try:
                screen.window.destroy()
            except tk.TclError:
                pass
        # give the compositor a moment to take the overlay off screen before anything
        # records or screenshots it
        self.app.root.after(60, lambda: self.on_done(result))
