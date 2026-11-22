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
            "hline": canvas.create_line(0, 0, w, 0, fill=T["line2"], dash=(4, 4), state="hidden"),
            "vline": canvas.create_line(0, 0, 0, h, fill=T["line2"], dash=(4, 4), state="hidden"),
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

        canvas.bind("<Motion>", lambda e: self.motion(screen, e.x, e.y))
        canvas.bind("<ButtonPress-1>", lambda e: self.press(screen, e.x, e.y))
        canvas.bind("<B1-Motion>", lambda e: self.drag(screen, e.x, e.y))
        canvas.bind("<ButtonRelease-1>", lambda e: self.release(screen, e.x, e.y))
        canvas.bind("<ButtonPress-3>", lambda _e: self.cancel())
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
        except tk.TclError:
            log.warning("overlay could not take focus; right-click still cancels")

    # input
    def _on_hint(self, screen: _Screen, x: int, y: int) -> bool:
        box = screen.items["hint_box"]
        return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def motion(self, screen: _Screen, x: int, y: int):
        if self.start is not None or self.finished:
            return
        c, w, h = screen.canvas, screen.monitor.w, screen.monitor.h
        for other in self.screens:
            if other is not screen:
                other.canvas.itemconfigure(other.items["hline"], state="hidden")
                other.canvas.itemconfigure(other.items["vline"], state="hidden")
        c.coords(screen.items["hline"], 0, y, w, y)
        c.coords(screen.items["vline"], x, 0, x, h)
        c.itemconfigure(screen.items["hline"], state="normal")
        c.itemconfigure(screen.items["vline"], state="normal")

    def press(self, screen: _Screen, x: int, y: int):
        if self.finished or self._on_hint(screen, x, y):
            return
        self.active, self.start, self.current = screen, (x, y), (x, y)
        screen.canvas.itemconfigure(screen.items["hline"], state="hidden")
        screen.canvas.itemconfigure(screen.items["vline"], state="hidden")

    def drag(self, screen: _Screen, x: int, y: int):
        if self.start is None or screen is not self.active or self.finished:
            return
        w, h = screen.monitor.w, screen.monitor.h
        self.current = (max(0, min(w, x)), max(0, min(h, y)))
        if self._pending is None:           # redraw at most once per frame
            self._pending = self.app.root.after(16, self._redraw)

    def _selection(self) -> Optional[Box]:
        if self.start is None or self.current is None:
            return None
        (x1, y1), (x2, y2) = self.start, self.current
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def _redraw(self, jitter: float = 0.0, sel: Optional[Box] = None):
        self._pending = None
        screen, sel = self.active, sel or self._selection()
        if screen is None or sel is None or self.finished:
            return
        c, items = screen.canvas, screen.items
        x0, y0, x1, y1 = sel
        if x1 - x0 >= 1 and y1 - y0 >= 1:
            photo = ImageTk.PhotoImage(screen.bright.crop((x0, y0, x1, y1)), master=screen.window)
            screen.photos[1:] = [photo]
            c.itemconfigure(items["bright"], image=photo, state="normal")
            c.coords(items["bright"], x0, y0)
        split = 2 + abs(jitter)
        c.coords(items["ghost_a"], x0 - split, y0, x1 - split, y1)
        c.coords(items["ghost_b"], x0 + split, y0, x1 + split, y1)
        c.coords(items["frame"], x0, y0, x1, y1)
        arm = min(self.app.px(14), (x1 - x0) // 2, (y1 - y0) // 2)
        for item, (cx, cy, dx, dy) in zip(items["corners"],
                                          ((x0, y0, 1, 1), (x1, y0, -1, 1),
                                           (x0, y1, 1, -1), (x1, y1, -1, -1))):
            c.coords(item, cx, cy + dy * arm, cx, cy, cx + dx * arm, cy)
        for item in (items["ghost_a"], items["ghost_b"], items["frame"], *items["corners"]):
            c.itemconfigure(item, state="normal")
        # size readout, in real screenshot pixels
        box = self._image_box(screen, sel)
        label = f"{box[2] - box[0]} × {box[3] - box[1]}"
        pad = self.app.px(5)
        tw = self.size_font.measure(label)
        th = self.size_font.metrics("linespace")
        lx = max(2, min(x1 - tw - 2 * pad, screen.monitor.w - tw - 2 * pad - 2))
        ly = y1 + pad if y1 + th + 3 * pad < screen.monitor.h else y0 + pad
        c.coords(items["size_bg"], lx, ly, lx + tw + 2 * pad, ly + th + 2 * pad)
        c.coords(items["size"], lx + pad, ly + pad)
        c.itemconfigure(items["size"], text=label, state="normal")
        c.itemconfigure(items["size_bg"], state="normal")
        c.tag_raise("hint")

    def release(self, screen: _Screen, x: int, y: int):
        if self.finished:
            return
        if self.start is None or screen is not self.active:
            return                          # a release on the chip, or with no press
        self.drag(screen, x, y)
        if self._pending is not None:
            self.app.root.after_cancel(self._pending)
            self._pending = None
        sel = self._selection()
        if sel is None or sel[2] - sel[0] < MIN_DRAG or sel[3] - sel[1] < MIN_DRAG:
            sel = (0, 0, screen.monitor.w, screen.monitor.h)      # a click: whole monitor
        self._redraw(sel=sel)
        m = screen.monitor
        region = (m.x + sel[0], m.y + sel[1], m.x + sel[2], m.y + sel[3])
        image = self.shot.crop(self._image_box(screen, sel))
        log.info("%s: picked %s on %s", self.mode, region, m.name)
        result = Selection(self.mode, image, region, m)
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

    def _image_box(self, screen: _Screen, sel: Box) -> Box:
        x, y = screen.monitor.x, screen.monitor.y
        return screen_to_image((x + sel[0], y + sel[1], x + sel[2], y + sel[3]),
                               self.desktop, self.shot.size)

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
