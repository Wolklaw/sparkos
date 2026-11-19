"""The result window, the recording bar, and the frame drawn around a recording."""

import os
from datetime import datetime
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

import tkinter as tk
from PIL import Image, ImageTk

from . import APP_NAME
from .core import (CONF_WARN, Box, Monitor, OCRResult, clock, human_size, language_label, log,
                   open_folder, screenshots_dir, short_path)
from .widgets import T, GlitchPanel, GlitchText, Mark, Strip, WolkButton

if TYPE_CHECKING:
    from .app import App

POPUP_SECONDS = 12
Action = Tuple[str, Callable[[], None], str, bool]          # label, command, variant, enabled


class ResultWindow(tk.Toplevel):
    """Shows what was captured and what happened to it, with the next useful actions.

    Once something is on the clipboard it closes itself after POPUP_SECONDS. The countdown
    pauses while the pointer is over the window and stops for good once you click or type.
    """

    TICK_MS = 50

    def __init__(self, app: "App", image: Optional[Image.Image], near: Monitor,
                 on_close: Callable[[], None]):
        super().__init__(app.root)
        self.app, self.image, self.on_close = app, image, on_close
        self.withdraw()
        self.title(APP_NAME)
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<ButtonPress>", self._interacted, add="+")
        self.bind("<Key>", self._interacted, add="+")
        if app.icon is not None:
            self.iconphoto(False, app.icon)
        try:
            self.attributes('-topmost', True)
        except tk.TclError:
            pass

        px, bg = app.px, T["bg"]
        self.width = px(520)
        self.copied_text = ""
        self.video_path = ""
        self.timer = "off"                  # off, running or stopped
        self.elapsed = 0.0
        self.closed = False
        self._scan: Optional[str] = None
        self._photo = None
        self._thumb_box = (0, 0, 0, 0)
        self._scan_lines: List[int] = []

        self.strip = Strip(self, height=px(2))
        self.strip.pack(side="bottom", fill="x")
        self.strip.draw(fraction=0)
        tk.Frame(self, bg=bg, width=self.width, height=0).pack()    # fixes the width

        head = tk.Frame(self, bg=bg)
        head.pack(fill="x", padx=px(18), pady=(px(16), px(6)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left", anchor="n", pady=(px(2), 0))
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", fill="x", padx=(px(12), 0))
        self.dot = tk.Label(col, text="● WORKING", bg=bg, fg=T["gold"], font=app.font(7))
        self.dot.pack(anchor="w")
        self.headline = GlitchText(col, "ONE MOMENT", app.tkfont(15), bg)
        self.headline.pack(anchor="w")

        self.sub = tk.Label(self, text="", bg=bg, fg=T["muted"], font=app.font(9, bold=False),
                            anchor="w", justify="left", wraplength=self.width - px(40))
        self.sub.pack(fill="x", padx=px(18))

        self.panel = GlitchPanel(self, T["out_bg"])
        self.panel.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        self.thumb = tk.Canvas(self.panel.inner, bg=T["out_bg"], highlightthickness=0, bd=0)
        self.text = tk.Text(self.panel.inner, bg=T["out_bg"], fg=T["text"],
                            font=app.font(10, False), relief="flat", bd=0, wrap="word",
                            width=1, height=3, padx=px(12), pady=px(10),
                            insertbackground=T["accent"], selectbackground=T["accent"],
                            selectforeground=T["on_accent"], highlightthickness=0, undo=True)
        self.text.bind("<KeyRelease>", self._on_edit)

        self.meta = tk.Label(self, text="", bg=bg, fg=T["dim"], font=app.font(7), anchor="w")
        self.meta.pack(fill="x", padx=px(18))
        self.row = tk.Frame(self, bg=bg)
        self.row.pack(fill="x", padx=px(15), pady=(px(12), px(6)))
        self.status = tk.Label(self, text="", bg=bg, fg=T["muted"], font=app.font(7), anchor="w",
                               justify="left", wraplength=self.width - px(40))
        self.status.pack(fill="x", padx=px(18), pady=(px(4), px(14)))

        if image is not None:
            self._show_thumb()
        else:
            self.panel.pack_forget()
        self.set_actions([])
        app.glitch.add(self.mark, self.headline)
        self._place(near)
        self.deiconify()
        self.lift()
        self.app.root.after(10, lambda: self.closed or self.focus_force())
        self.app.root.after(self.TICK_MS, self._tick)

    # layout
    def _place(self, near: Monitor):
        self.update_idletasks()
        height = self.winfo_reqheight()
        left = near.x + max(0, (near.w - self.width) // 2)
        top = near.y + max(0, int(near.h * 0.42) - height // 2)
        self.geometry(f"+{left}+{top}")

    def set_actions(self, actions: List[Action]):
        for child in self.row.winfo_children():
            child.destroy()
        small, px = self.app.font(8), self.app.px
        for label, command, variant, enabled in actions:
            button = WolkButton(self.row, label, command, small, variant=variant, padx=px(10))
            button.pack(side="left")
            button.set_enabled(enabled)
        done = WolkButton(self.row, "Done", self.close, small, variant="primary", padx=px(14))
        done.pack(side="right")

    def _show_thumb(self, scanning: bool = False):
        px = self.app.px
        self.text.pack_forget()
        self.thumb.pack(fill="x")
        avail_w = self.width - px(36)
        img = self.image
        ratio = min(avail_w / img.width, px(170) / img.height, 2.0)
        tw, th = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
        self._photo = ImageTk.PhotoImage(img.resize((tw, th), Image.Resampling.LANCZOS),
                                         master=self)
        height = max(th + px(20), px(56))
        self.thumb.configure(width=avail_w, height=height)
        self.thumb.delete("all")
        self.thumb.create_image(avail_w // 2, height // 2, image=self._photo)
        self._thumb_box = ((avail_w - tw) // 2, (height - th) // 2,
                           (avail_w + tw) // 2, (height + th) // 2)
        if not scanning:
            return
        if self.app.glitch.enabled:
            x0, _, x1, _ = self._thumb_box
            self._scan_lines = [self.thumb.create_line(x0, 0, x1, 0, fill=colour, width=w)
                                for colour, w in ((T["ch_a"], 1), (T["ch_b"], 1),
                                                  (T["accent"], 2))]
            self._scan_step(self._thumb_box[1], 1)
        else:
            self.thumb.create_text(avail_w // 2, height // 2, text="READING…",
                                   font=self.app.font(9), fill=T["accent"])

    def _scan_step(self, y: float, direction: int):
        if self.closed or not self.winfo_exists():
            return
        x0, top, x1, bottom = self._thumb_box
        y += direction * max(2, (bottom - top) / 40)
        if y >= bottom or y <= top:
            direction = -direction
            y = max(top, min(bottom, y))
        a, b, main = self._scan_lines
        self.thumb.coords(a, x0, y - 3, x1, y - 3)
        self.thumb.coords(b, x0, y + 3, x1, y + 3)
        self.thumb.coords(main, x0, y, x1, y)
        self._scan = self.app.root.after(24, lambda: self._scan_step(y, direction))

    def _stop_scan(self):
        if self._scan is not None:
            try:
                self.app.root.after_cancel(self._scan)
            except (tk.TclError, ValueError):
                pass
            self._scan = None

    def _state(self, dot: str, colour: str, headline: str, sub: str):
        self.dot.config(text=f"● {dot}", fg=colour)
        self.headline.set_text(headline)
        self.sub.config(text=sub)

    def say(self, message: str, colour: str = T["muted"]):
        self.status.config(text=message, fg=colour)

    def _start_countdown(self):
        self.timer, self.elapsed = "running", 0.0
        self.strip.draw(fraction=1)

    def _image_actions(self, read_text: bool) -> List[Action]:
        can = self.app.clipboard.can_copy_binary()
        actions: List[Action] = []
        if read_text:
            actions.append(("Read text", self.read_text, "ghost", True))
        else:
            actions.append(("Copy text", self.copy_text, "ghost", True))
        actions += [("Copy image", self.copy_image, "ghost", can),
                    ("Save image", self.save_image, "ghost", True)]
        return actions

    # states
    def reading(self):
        self._state("READING", T["gold"], "READING TEXT",
                    "Tesseract is reading the area you picked.")
        if self.image is not None:
            self._show_thumb(scanning=True)
        self.set_actions([])

    def show_text(self, result: OCRResult, copy_error: Optional[str]):
        self._stop_scan()
        self.thumb.pack_forget()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", result.text)
        self.text.edit_reset()
        lines = result.text.count("\n") + 1
        self.text.configure(height=max(2, min(9, lines + 1)))
        self.text.pack(fill="x")
        self.set_actions(self._image_actions(read_text=False))
        words = len(result.text.split())
        self.meta.config(text=f"{words} WORD{'S' if words != 1 else ''}  ·  "
                              f"{result.confidence:.0f}% SURE  ·  "
                              f"{language_label(self.app.ocr.lang).upper()}")
        if copy_error:
            self._state("NOT COPIED", T["pink"], "COULD NOT COPY",
                        f"The clipboard refused the text ({copy_error}). "
                        "Select it below and copy it by hand.")
            self.app.glitch.now(self.headline, self.panel, strong=True)
            return
        self.copied_text = result.text
        if result.confidence < CONF_WARN:
            self._state("CHECK IT", T["gold"], "COPIED. CHECK IT",
                        f"Tesseract is only {result.confidence:.0f}% sure of this read. "
                        "Fix it below, then press COPY TEXT.")
        else:
            self._state("COPIED", T["accent"], "TEXT COPIED",
                        "It's on the clipboard. Paste it anywhere with Ctrl+V.")
        self.app.glitch.now(self.headline, self.panel, self.mark)
        self._start_countdown()

    def show_image(self, copy_error: Optional[str]):
        self._show_thumb()
        self.set_actions(self._image_actions(read_text=True))
        self.meta.config(text=f"{self.image.width} × {self.image.height} PX  ·  PNG")
        if copy_error:
            self._state("NOT COPIED", T["pink"], "COULD NOT COPY",
                        f"The screenshot isn't on the clipboard ({copy_error}). "
                        "Save it instead.")
            self.app.glitch.now(self.headline, self.panel, strong=True)
            return
        self._state("COPIED", T["accent"], "SCREENSHOT COPIED",
                    "It's on the clipboard. Paste it anywhere with Ctrl+V.")
        self.app.glitch.now(self.headline, self.panel, self.mark)
        self._start_countdown()

    def show_empty(self):
        self._stop_scan()
        if self.image is not None:
            self._show_thumb()
        self.set_actions(self._image_actions(read_text=False)[1:])
        self._state("NO TEXT", T["pink"], "NO TEXT FOUND",
                    "Nothing readable in that area. Try a bigger box or another language, "
                    "or keep the image instead.")
        self.app.glitch.now(self.headline, self.panel, strong=True)

    def show_error(self, title: str, message: str):
        self._stop_scan()
        if self.image is not None:
            self._show_thumb()
            self.set_actions([("Save image", self.save_image, "ghost", True)])
        else:
            self.set_actions([])
        self._state("ERROR", T["pink"], title, message)
        self.app.glitch.now(self.headline, self.panel, strong=True)

    def show_video(self, path: str, duration: float, size: Tuple[int, int], codec: str,
                   audio: str):
        self.video_path = path
        if self.image is not None:
            self._show_thumb()
        try:
            weight = human_size(os.path.getsize(path))
        except OSError:
            weight = "?"
        self.meta.config(text=f"{clock(duration)}  ·  {weight}  ·  {size[0]} × {size[1]}  ·  "
                              f"{codec}  ·  {audio}")
        self._state("SAVED", T["accent"], "RECORDING SAVED", short_path(path))
        can = self.app.clipboard.can_copy_binary()
        self.set_actions([("Open folder", self.open_video_folder, "ghost", True),
                          ("Copy file", self.copy_video, "ghost", can)])
        self.app.glitch.now(self.headline, self.panel, self.mark)
        self._start_countdown()

    # actions
    def read_text(self):
        self.app.read_text(self.image, self)

    def copy_text(self):
        text = self.text.get("1.0", "end-1c")
        error = self.app.clipboard.copy_text(text)
        if error:
            self.say(f"COULD NOT COPY: {error}", T["pink"])
            self.app.glitch.now(self.panel, strong=True)
            return
        self.copied_text = text
        self.say("TEXT COPIED", T["accent"])
        self.app.glitch.now(self.panel)

    def copy_image(self):
        error = self.app.clipboard.copy_image(self.image)
        if error:
            self.say(f"COULD NOT COPY THE IMAGE: {error}", T["pink"])
            self.app.glitch.now(self.panel, strong=True)
            return
        self.copied_text = ""
        self.say("IMAGE COPIED", T["accent"])
        self.app.glitch.now(self.panel)

    def save_image(self):
        folder = screenshots_dir()
        path = os.path.join(folder, datetime.now().strftime("SparkSnip_%Y-%m-%d_%H-%M-%S.png"))
        try:
            os.makedirs(folder, exist_ok=True)
            self.image.save(path)
        except (OSError, ValueError) as exc:
            log.exception("could not save the image")
            self.say(f"COULD NOT SAVE: {exc}", T["pink"])
            self.app.glitch.now(self.panel, strong=True)
            return
        log.info("saved %s", path)
        self.say(f"SAVED TO {short_path(path)}", T["accent"])
        self.app.glitch.now(self.panel)

    def open_video_folder(self):
        error = open_folder(os.path.dirname(self.video_path))
        if error:
            self.say(f"COULD NOT OPEN THE FOLDER: {error}", T["pink"])
        else:
            self.say("OPENED IN THE FILE MANAGER", T["accent"])

    def copy_video(self):
        error = self.app.clipboard.copy_file(self.video_path)
        if error:
            self.say(f"COULD NOT COPY: {error}", T["pink"])
            self.app.glitch.now(self.panel, strong=True)
            return
        self.say("FILE COPIED. PASTE IT INTO A CHAT OR A FOLDER.", T["accent"])
        self.app.glitch.now(self.panel)

    def _on_edit(self, _event=None):
        if self.copied_text and self.text.get("1.0", "end-1c") != self.copied_text:
            self.say("EDITED. PRESS COPY TEXT TO PUT THIS VERSION ON THE CLIPBOARD.", T["gold"])

    # countdown
    def _interacted(self, _event=None):
        if self.timer == "running":
            self.timer = "stopped"
            self.strip.draw(fraction=0)

    def _pointer_inside(self) -> bool:
        x, y = self.winfo_pointerxy()
        return (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())

    def _tick(self):
        try:
            if self.closed or not self.winfo_exists():
                return
            if self.timer == "running":
                if not self._pointer_inside():
                    self.elapsed += self.TICK_MS / 1000
                if self.elapsed >= POPUP_SECONDS:
                    self.close()
                    return
                self.strip.draw(fraction=1 - self.elapsed / POPUP_SECONDS)
            self.app.root.after(self.TICK_MS, self._tick)
        except tk.TclError:
            pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._stop_scan()
        try:
            self.destroy()
        except tk.TclError:
            pass
        self.on_close()


class RecordFrame:
    """Four thin windows drawn just outside the recorded area, so they stay out of the video."""

    THICK = 2

    def __init__(self, root: tk.Misc, region: Box):
        x0, y0, x1, y1 = region
        t = self.THICK
        self.windows = []
        for x, y, w, h, colour in ((x0 - t, y0 - t, x1 - x0 + 2 * t, t, T["ch_a"]),
                                   (x0 - t, y1, x1 - x0 + 2 * t, t, T["ch_b"]),
                                   (x0 - t, y0, t, y1 - y0, T["ch_a"]),
                                   (x1, y0, t, y1 - y0, T["ch_b"])):
            win = tk.Toplevel(root)
            win.overrideredirect(True)
            win.configure(bg=colour)
            win.geometry(f"{max(1, w)}x{max(1, h)}+{x}+{y}")
            try:
                win.attributes('-topmost', True)
            except tk.TclError:
                pass
            self.windows.append(win)

    def close(self):
        for win in self.windows:
            try:
                win.destroy()
            except tk.TclError:
                pass


class RecordBar(tk.Toplevel):
    """● REC 00:12 · SOUND · MIC OFF [STOP], placed just outside the recorded area."""

    def __init__(self, app: "App", region: Box, monitor: Monitor, audio: str,
                 on_stop: Callable[[], None]):
        super().__init__(app.root)
        self.app = app
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=T["line2"])
        try:
            self.attributes('-topmost', True)
        except tk.TclError:
            pass
        px, bg = app.px, T["panel"]
        body = tk.Frame(self, bg=bg, padx=px(10), pady=px(6))
        body.pack(fill="both", expand=True, padx=1, pady=1)
        self.dot = tk.Label(body, text="● WAITING", bg=bg, fg=T["gold"], font=app.font(9))
        self.dot.pack(side="left")
        self.clock = tk.Label(body, text="", bg=bg, fg=T["text"], font=app.font(9))
        self.clock.pack(side="left", padx=(px(10), 0))
        self.info = tk.Label(body, text=audio, bg=bg, fg=T["dim"], font=app.font(7))
        self.info.pack(side="left", padx=(px(12), px(12)))
        self.button = WolkButton(body, "Cancel", on_stop, app.font(8), variant="danger",
                                 padx=px(10), pady=px(3))
        self.button.pack(side="left")
        self._blink = True
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x0, y0, x1, y1 = region
        gap = px(10)
        x = max(monitor.x + gap, min(x1 - w, monitor.x + monitor.w - w - gap))
        if y0 - h - gap >= monitor.y:
            y = y0 - h - gap                       # above the area
        elif y1 + h + gap <= monitor.y + monitor.h:
            y = y1 + gap                           # below it
        else:
            y = monitor.y + gap                    # full screen: top right, and in the video
        self.geometry(f"+{x}+{y}")
        self.deiconify()

    def waiting(self):
        self.dot.config(text="● CHOOSE THE SCREEN IN THE SHARE DIALOG", fg=T["gold"])

    def recording(self, seconds: float):
        if self.button.label.cget("text") != "STOP":
            self.button.set_text("Stop")
        self._blink = not self._blink if self.app.glitch.enabled else True
        self.dot.config(text="● REC", fg=T["pink"] if self._blink else T["dim"])
        self.clock.config(text=clock(seconds))

    def finishing(self):
        self.dot.config(text="● SAVING", fg=T["gold"])
        self.button.set_enabled(False)

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass
