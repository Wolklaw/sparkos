"""The photo viewer: fit, zoom around the pointer, pan, rotate in view, slideshow, Trash."""

import os
import threading
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk

from .core import (Photo, PhotoError, clamp_center, fit_scale, flatten, human_size, log,
                   move_to_trash, visible_region)
from .widgets import T, IconButton

ZOOM_STEPS = (0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0,
              6.0, 8.0, 12.0, 16.0, 24.0, 32.0)
SLIDE_MS = 4000
SHARPEN_MS = 140          # after the view settles, redraw with the slower, sharper filter
CACHE = 5


class PhotoView(tk.Frame):
    def __init__(self, app, path: str, playlist: List[str], slideshow: bool = False):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.files = playlist
        self.index = playlist.index(path) if path in playlist else 0
        px = app.px
        self.canvas = tk.Canvas(self, bg=T["out_bg"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.bar = tk.Frame(self, bg=T["panel"])
        self.bar.pack(fill="x")
        tk.Frame(self.bar, bg=T["line"], height=1).pack(fill="x", side="top")
        inner = tk.Frame(self.bar, bg=T["panel"])
        inner.pack(fill="x", padx=px(10), pady=px(6))
        size = px(30)
        self.buttons: Dict[str, IconButton] = {}
        for name, cmd in (("prev", self.prev), ("next", self.next)):
            self.buttons[name] = IconButton(inner, name, cmd, size)
            self.buttons[name].pack(side="left")
        self.info = tk.Label(inner, text="", bg=T["panel"], fg=T["text"], font=app.font(8),
                             anchor="w")
        self.info.pack(side="left", padx=(px(10), 0))
        self.facts = tk.Label(inner, text="", bg=T["panel"], fg=T["muted"],
                              font=app.font(7, False), anchor="w")
        self.facts.pack(side="left", padx=(px(10), 0), fill="x", expand=True)
        for name, cmd in (("fullscreen", app.toggle_fullscreen), ("trash", self.trash),
                          ("slideshow", self.toggle_slideshow), ("rotate", self.rotate),
                          ("zoom_in", lambda: self.zoom_step(1)), ("fit", self.fit),
                          ("zoom_out", lambda: self.zoom_step(-1))):
            self.buttons[name] = IconButton(inner, name, cmd, size)
            self.buttons[name].pack(side="right")
        self.zoom_label = tk.Label(inner, text="", bg=T["panel"], fg=T["accent"],
                                   font=app.font(8), width=6, anchor="e")
        self.zoom_label.pack(side="right", padx=(0, px(6)))

        self.photo: Optional[Photo] = None
        self.error: Optional[str] = None
        self.cache: Dict[str, Photo] = {}
        self._ready: Dict[str, Photo] = {}        # preloaded by a worker thread
        self.rotation = 0
        self.scale = 1.0
        self.fitted = True
        self.center = (0.0, 0.0)
        self.frame_index = 0
        self.tkimage: Optional[ImageTk.PhotoImage] = None
        self._sharpen_id = self._anim_id = self._slide_id = None
        self._drag: Optional[Tuple[int, int, Tuple[float, float]]] = None
        self._rotated: Dict[int, Image.Image] = {}

        c = self.canvas
        c.bind("<Configure>", lambda _e: self.render())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._move)
        c.bind("<ButtonRelease-1>", lambda _e: self._end_drag())
        c.bind("<Double-Button-1>", lambda _e: self.app.toggle_fullscreen())
        c.bind("<Button-3>", lambda _e: self.toggle_actual())
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            c.bind(seq, self._wheel)
        self.show(self.index)
        if slideshow:
            self.toggle_slideshow()

    # ── loading ──
    def _load(self, path: str) -> Photo:
        photo = self.cache.get(path) or self._ready.pop(path, None)
        if photo is None:
            photo = Photo(path)
            self.cache[path] = photo
            while len(self.cache) > CACHE:
                self.cache.pop(next(iter(self.cache)))
        return photo

    def _preload(self, index: int):
        if not (0 <= index < len(self.files)):
            return
        if self.files[index] in self.cache or self.files[index] in self._ready:
            return
        path = self.files[index]

        def work():
            # no Tk calls here: the photo is only handed over, and _load picks it up
            try:
                self._ready[path] = Photo(path)
            except PhotoError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def show(self, index: int):
        if not self.files:
            return
        self.index = index % len(self.files)
        path = self.files[self.index]
        self._stop_animation()
        self.rotation, self.fitted, self.frame_index = 0, True, 0
        self._rotated.clear()
        try:
            self.photo = self._load(path)
            self.error = None
        except PhotoError as exc:
            self.photo, self.error = None, str(exc)
            log.warning("cannot show %s: %s", path, exc)
            self.app.glitch.now(self.app.title, strong=True)
        self.app.set_window_title(os.path.basename(path))
        self._update_info()
        self.render()
        if self.photo is not None and self.photo.animated:
            self._anim_id = self.after(self.photo.durations[0], self._animate)
        many = len(self.files) > 1
        self.buttons["prev"].set_enabled(many)
        self.buttons["next"].set_enabled(many)
        self._preload(self.index + 1)
        self._preload(self.index - 1)

    def _update_info(self):
        path = self.files[self.index]
        count = f"  {self.index + 1} / {len(self.files)}" if len(self.files) > 1 else ""
        self.info.config(text=os.path.basename(path) + count)
        if self.photo is None:
            self.facts.config(text="UNREADABLE", fg=T["pink"])
            return
        w, h = self._image().size
        parts = [f"{w} × {h}", self.photo.format, human_size(self.photo.bytes)]
        if self.photo.taken:
            parts.append(self.photo.taken)
        if self.photo.animated:
            parts.append(f"{len(self.photo.frames)} FRAMES")
        if self.rotation:
            parts.append("ROTATED IN VIEW ONLY")
        self.facts.config(text="  ·  ".join(parts), fg=T["muted"])

    def _image(self) -> Image.Image:
        base = self.photo.frames[self.frame_index] if self.photo.animated else self.photo.image
        if not self.rotation:
            return base
        if self.photo.animated:
            return base.rotate(-self.rotation, expand=True)
        if self.rotation not in self._rotated:
            self._rotated[self.rotation] = base.rotate(-self.rotation, expand=True)
        return self._rotated[self.rotation]

    # ── drawing ──
    def _view(self) -> Tuple[int, int]:
        return max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())

    def render(self, quick: bool = False):
        c = self.canvas
        c.delete("all")
        vw, vh = self._view()
        if self.photo is None:
            if self.error:
                c.create_text(vw / 2, vh / 2 - self.app.px(12), text="CAN'T SHOW THIS PHOTO",
                              fill=T["pink"], font=self.app.font(11))
                c.create_text(vw / 2, vh / 2 + self.app.px(14), text=self.error,
                              fill=T["muted"], font=self.app.font(8, False))
            return
        image = self._image()
        if self.fitted:
            self.scale = fit_scale(image.size, (vw, vh))
            self.center = (image.width / 2, image.height / 2)
        self.center = clamp_center(image.size, (vw, vh), self.scale, self.center)
        box, (ox, oy) = visible_region(image.size, (vw, vh), self.scale, self.center)
        crop = image.crop(box)
        target = (max(1, round(crop.width * self.scale)), max(1, round(crop.height * self.scale)))
        if target != crop.size:
            if quick or self.scale > 1.0:
                # nearest neighbour above 100% keeps pixels sharp, like every viewer
                method = Image.Resampling.NEAREST if self.scale >= 2 else Image.Resampling.BILINEAR
                crop = crop.resize(target, method)
            else:
                crop = crop.resize(target, Image.Resampling.LANCZOS, reducing_gap=3.0)
        self.tkimage = ImageTk.PhotoImage(flatten(crop, T["out_bg"]))
        c.create_image(ox, oy, image=self.tkimage, anchor="nw")
        self.zoom_label.config(text=f"{self.scale * 100:.0f}%")
        if quick:
            if self._sharpen_id:
                self.after_cancel(self._sharpen_id)
            self._sharpen_id = self.after(SHARPEN_MS, self._sharpen)

    def _sharpen(self):
        self._sharpen_id = None
        self.render()

    def _animate(self):
        if self.photo is None or not self.photo.animated:
            return
        self.frame_index = (self.frame_index + 1) % len(self.photo.frames)
        self.render(quick=True)
        self._anim_id = self.after(self.photo.durations[self.frame_index], self._animate)

    def _stop_animation(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    # ── zoom and pan ──
    def zoom_to(self, scale: float, anchor: Optional[Tuple[int, int]] = None):
        if self.photo is None:
            return
        scale = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], scale))
        vw, vh = self._view()
        ax, ay = anchor if anchor else (vw / 2, vh / 2)
        # keep the image point under the anchor where it is
        ix = self.center[0] + (ax - vw / 2) / self.scale
        iy = self.center[1] + (ay - vh / 2) / self.scale
        self.scale, self.fitted = scale, False
        self.center = (ix - (ax - vw / 2) / scale, iy - (ay - vh / 2) / scale)
        self.render(quick=True)

    def zoom_step(self, direction: int, anchor: Optional[Tuple[int, int]] = None):
        if direction > 0:
            nxt = next((z for z in ZOOM_STEPS if z > self.scale * 1.01), ZOOM_STEPS[-1])
        else:
            nxt = next((z for z in reversed(ZOOM_STEPS) if z < self.scale * 0.99), ZOOM_STEPS[0])
        self.zoom_to(nxt, anchor)

    def fit(self):
        self.fitted = True
        self.render()

    def toggle_actual(self, anchor: Optional[Tuple[int, int]] = None):
        if self.fitted or abs(self.scale - 1.0) > 0.001:
            self.zoom_to(1.0, anchor)
        else:
            self.fit()

    def _wheel(self, event):
        up = getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0
        if event.state & 0x4 or not len(self.files) > 1 or not self.fitted:
            self.zoom_step(1 if up else -1, (event.x, event.y))      # Ctrl+wheel, or zoomed
        else:
            self.prev() if up else self.next()

    def _press(self, event):
        self.canvas.focus_set()
        self._drag = (event.x, event.y, self.center)
        self.canvas.configure(cursor="fleur")

    def _move(self, event):
        if self._drag is None or self.fitted:
            return
        x, y, (cx, cy) = self._drag
        self.center = (cx - (event.x - x) / self.scale, cy - (event.y - y) / self.scale)
        self.render(quick=True)

    def _end_drag(self):
        self._drag = None
        self.canvas.configure(cursor="")

    # ── actions ──
    def next(self):
        self.show(self.index + 1)

    def prev(self):
        self.show(self.index - 1)

    def rotate(self):
        if self.photo is None:
            return
        self.rotation = (self.rotation + 90) % 360
        self.fitted = True
        self._update_info()
        self.render()

    def toggle_slideshow(self):
        if self._slide_id:
            self.after_cancel(self._slide_id)
            self._slide_id = None
            self.buttons["slideshow"].set_icon("slideshow")
            self.app.set_status("SLIDESHOW OFF", T["muted"])
        elif len(self.files) > 1:
            self._slide_id = self.after(SLIDE_MS, self._slide)
            self.buttons["slideshow"].set_icon("pause")
            self.app.set_status("SLIDESHOW", T["accent"])

    def _slide(self):
        self.next()
        self._slide_id = self.after(SLIDE_MS, self._slide)

    def trash(self):
        if not self.files:
            return
        path = self.files[self.index]
        if not messagebox.askyesno("Move to Trash",
                                   f"Move {os.path.basename(path)} to the Trash?\n\n"
                                   "You can restore it from the Trash in the file manager.",
                                   parent=self):
            return
        problem = move_to_trash(path)
        if problem:
            self.app.set_status("COULD NOT MOVE TO TRASH", T["pink"])
            self.app.glitch.now(self.app.title, strong=True)
            messagebox.showerror("Move to Trash", problem, parent=self)
            return
        log.info("moved to trash: %s", path)
        self.cache.pop(path, None)
        del self.files[self.index]
        self.app.set_status("MOVED TO TRASH", T["accent"])
        if not self.files:
            self.app.show_home('photo')
        else:
            self.show(min(self.index, len(self.files) - 1))

    def fullscreen_changed(self, on: bool):
        if on:
            self.bar.pack_forget()
        else:
            self.bar.pack(fill="x")

    def key(self, event) -> bool:
        k = event.keysym
        ctrl = bool(event.state & 0x4)
        if k in ('Right', 'Next', 'space', 'Down') and not ctrl:
            if not self.fitted and k in ('Right', 'Down'):
                return self._nudge(k)
            self.next()
        elif k in ('Left', 'Prior', 'BackSpace', 'Up') and not ctrl:
            if not self.fitted and k in ('Left', 'Up'):
                return self._nudge(k)
            self.prev()
        elif k == 'Home':
            self.show(0)
        elif k == 'End':
            self.show(len(self.files) - 1)
        elif k in ('plus', 'equal', 'KP_Add'):
            self.zoom_step(1)
        elif k in ('minus', 'KP_Subtract'):
            self.zoom_step(-1)
        elif k in ('0', 'KP_0'):
            self.fit()
        elif k in ('1', 'KP_1'):
            self.zoom_to(1.0)
        elif k in ('r', 'R'):
            self.rotate()
        elif k in ('s', 'S'):
            self.toggle_slideshow()
        elif k == 'Delete':
            self.trash()
        else:
            return False
        return True

    def _nudge(self, k: str) -> bool:
        step = 80 / self.scale
        dx = {'Left': -step, 'Right': step}.get(k, 0)
        dy = {'Up': -step, 'Down': step}.get(k, 0)
        self.center = (self.center[0] + dx, self.center[1] + dy)
        self.render(quick=True)
        return True

    def destroy(self):
        for job in (self._sharpen_id, self._anim_id, self._slide_id):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        super().destroy()
