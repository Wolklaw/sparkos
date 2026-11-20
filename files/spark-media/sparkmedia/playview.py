"""The player screen, for videos and for music: picture or cover, queue, and the transport bar."""

import os
import random
from typing import Any, List, Optional

import tkinter as tk

from PIL import Image, ImageTk

from . import player as gst
from .core import clock, folder_cover, kind_of, load_json, log, save_json
from .widgets import T, IconButton, Seek

POLL_MS = 100
HIDE_CONTROLS_MS = 2500
RESUME_MIN = 180          # remember where a video was left if it runs at least this long (s)
RESUME_KEEP = 200         # how many videos to remember
SEEK_STEP, SEEK_BIG = 5, 30


class PlayerView(tk.Frame):
    def __init__(self, app, path: str, playlist: List[str]):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.kind = kind_of(path) or 'video'
        self.files = playlist
        self.order = list(range(len(playlist)))
        self.position_in_order = self.order.index(playlist.index(path)) if path in playlist else 0
        self.shuffle = self.repeat = False
        px = app.px

        # stage: the video surface, or cover art and the queue for music
        self.stage = tk.Frame(self, bg="#000000" if self.kind == 'video' else T["bg"])
        self.stage.pack(fill="both", expand=True)
        self.surface: Optional[tk.Frame] = None
        self.cover_canvas: Optional[tk.Canvas] = None
        self.queue_list: Optional[tk.Listbox] = None
        self.message: Optional[tk.Label] = None
        if self.kind == 'video':
            # bg "" : Tk paints nothing here, so it never draws over the frames the sink puts in
            self.surface = tk.Frame(self.stage, bg="", width=px(640), height=px(360))
            self.surface.pack(fill="both", expand=True)
            self.surface.bind("<Configure>", self._surface_resized)
            self.surface.bind("<Double-Button-1>", lambda _e: self.app.toggle_fullscreen())
            self.surface.bind("<ButtonRelease-1>", lambda _e: self.toggle())
        else:
            self._build_music_stage()

        # transport bar
        self.bar = tk.Frame(self, bg=T["panel"])
        self.bar.pack(fill="x")
        tk.Frame(self.bar, bg=T["line"], height=1).pack(fill="x")
        seek_row = tk.Frame(self.bar, bg=T["panel"])
        seek_row.pack(fill="x", padx=px(10), pady=(px(6), 0))
        self.time_label = tk.Label(seek_row, text="0:00", bg=T["panel"], fg=T["text"],
                                   font=app.font(8), width=8, anchor="w")
        self.time_label.pack(side="left")
        self.total_label = tk.Label(seek_row, text="--:--", bg=T["panel"], fg=T["muted"],
                                    font=app.font(8), width=8, anchor="e")
        self.total_label.pack(side="right")
        self.seek = Seek(seek_row, px(18), self._seek_to, self._seek_drag)
        self.seek.pack(side="left", fill="x", expand=True)

        row = tk.Frame(self.bar, bg=T["panel"])
        row.pack(fill="x", padx=px(10), pady=(px(2), px(8)))
        size = px(30)
        self.btn = {}
        self.btn["prev"] = IconButton(row, "prev", self.prev, size)
        self.btn["play"] = IconButton(row, "pause", self.toggle, px(34), accent=True)
        self.btn["next"] = IconButton(row, "next", self.next, size)
        for name in ("prev", "play", "next"):
            self.btn[name].pack(side="left", padx=(0, px(4)))
        self.title_label = tk.Label(row, text="", bg=T["panel"], fg=T["text"], font=app.font(9),
                                    anchor="w")
        self.title_label.pack(side="left", padx=(px(10), 0))
        self.sub_label = tk.Label(row, text="", bg=T["panel"], fg=T["muted"],
                                  font=app.font(8, False), anchor="w")
        self.sub_label.pack(side="left", padx=(px(10), 0), fill="x", expand=True)

        if self.kind == 'video':
            self.btn["fullscreen"] = IconButton(row, "fullscreen", app.toggle_fullscreen, size)
            self.btn["fullscreen"].pack(side="right")
            self.btn["subtitles"] = IconButton(row, "subtitles", self.toggle_subtitles, size)
            self.btn["audio"] = IconButton(row, "audio", self.next_audio, size)
        else:
            self.btn["repeat"] = IconButton(row, "repeat", self.toggle_repeat, size)
            self.btn["repeat"].pack(side="right")
            self.btn["shuffle"] = IconButton(row, "shuffle", self.toggle_shuffle, size)
            self.btn["shuffle"].pack(side="right")
        self.volume = Seek(row, px(18), self._volume_set, self._volume_set, width=px(90))
        self.volume.pack(side="right", padx=(0, px(10)))
        self.btn["mute"] = IconButton(row, "volume", self.toggle_mute, size)
        self.btn["mute"].pack(side="right")

        # the player
        self.player: Optional[gst.Player] = None
        self.positions = load_json('positions.json') if self.kind == 'video' else {}
        self._poll_id = self._hide_id = None
        self._last_drag_seek = 0.0
        self._cover_image: Optional[ImageTk.PhotoImage] = None
        self._cover_source: Optional[Image.Image] = None
        problem = gst.init()
        if problem:
            self._disable()
            self._show_problem("VIDEO AND MUSIC NEED GSTREAMER", problem)
            return
        self.update_idletasks()
        handle = self.surface.winfo_id() if self.surface is not None else None
        try:
            self.player = gst.Player(self._on_event, window_handle=handle)
        except RuntimeError as exc:
            self._disable()
            self._show_problem("THE PLAYER COULD NOT START", str(exc))
            return
        saved = app.settings.get("volume")
        self.player.volume = float(saved) if isinstance(saved, (int, float)) else 0.8
        self.player.muted = bool(app.settings.get("muted", False))
        self.volume.set(self.player.volume)
        self._paint_mute()
        if self.kind == 'video' and self.player.sink is None:
            self._show_problem("NO VIDEO OUTPUT", "None of glimagesink, xvimagesink or "
                               "ximagesink is installed. Sound will still play.")
        self._poll_id = self.after(POLL_MS, self._poll)
        if self.surface is not None:
            for widget in (self, self.surface, self.stage):
                widget.bind("<Motion>", self._activity, add="+")
        self.play_index(self.order[self.position_in_order])

    def _disable(self):
        """Nothing can play: grey the controls out instead of offering them."""
        self.btn["play"].set_icon("play")
        for button in self.btn.values():
            button.set_enabled(False)
        self.seek.set_enabled(False)
        self.volume.set_enabled(False)
        name = os.path.splitext(os.path.basename(self.files[self.order[self.position_in_order]]))[0]
        self.title_label.config(text=self._fit(name, self.app.px(420), 9))

    # ── music stage ──
    def _build_music_stage(self):
        px = self.app.px
        wrap = tk.Frame(self.stage, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=px(16), pady=px(16))
        left = tk.Frame(wrap, bg=T["bg"])
        left.pack(side="left", fill="both", expand=True)
        self.cover_canvas = tk.Canvas(left, bg=T["bg"], highlightthickness=0, bd=0)
        self.cover_canvas.pack(fill="both", expand=True)
        self.cover_canvas.bind("<Configure>", lambda _e: self._draw_cover())
        right = tk.Frame(wrap, bg=T["bg"], width=px(320))
        right.pack(side="right", fill="y", padx=(px(16), 0))
        right.pack_propagate(False)
        tk.Label(right, text="UP NEXT", bg=T["bg"], fg=T["dim"], font=self.app.font(7),
                 anchor="w").pack(fill="x", pady=(0, px(6)))
        edge = tk.Frame(right, bg=T["line"], padx=1, pady=1)
        edge.pack(fill="both", expand=True)
        self.queue_list = tk.Listbox(
            edge, bg=T["panel"], fg=T["text"], font=self.app.font(8, False), bd=0,
            highlightthickness=0, activestyle="none", selectbackground=T["accent"],
            selectforeground=T["on_accent"], exportselection=False, takefocus=1)
        self.queue_list.pack(fill="both", expand=True)
        for path in self.files:
            self.queue_list.insert("end", "  " + os.path.splitext(os.path.basename(path))[0])
        self.queue_list.bind("<Double-Button-1>", self._queue_pick)
        self.queue_list.bind("<Return>", self._queue_pick)

    def _queue_pick(self, _event=None):
        sel = self.queue_list.curselection()
        if sel:
            index = sel[0]
            self.position_in_order = self.order.index(index)
            self.play_index(index)
        return "break"

    def _draw_cover(self):
        c = self.cover_canvas
        if c is None:
            return
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        px = self.app.px
        text_h = px(84)
        side = max(px(60), min(w, h - text_h, px(520)))
        x0, y0 = (w - side) / 2, max(0, (h - text_h - side) / 2)
        if self._cover_source is not None:
            image = self._cover_source.copy()
            image.thumbnail((side, side), Image.Resampling.LANCZOS)
            self._cover_image = ImageTk.PhotoImage(image)
            c.create_image(w / 2, y0 + side / 2, image=self._cover_image)
        else:
            c.create_rectangle(x0, y0, x0 + side, y0 + side, fill=T["tile"], outline=T["line2"])
            # no cover: a small note, split into the channels
            k = min(side, px(240)) / 48
            cx, cy = w / 2, y0 + side / 2
            for dx, colour in ((-1.5, T["ch_a"]), (1.5, T["ch_b"]), (0, T["accent"])):
                c.create_line(cx - 3 * k + dx, cy + 6 * k, cx - 3 * k + dx, cy - 7 * k,
                              cx + 6 * k + dx, cy - 9 * k, cx + 6 * k + dx, cy + 4 * k,
                              fill=colour, width=max(2, round(1.2 * k)))
                c.create_rectangle(cx - 7 * k + dx, cy + 4 * k, cx - 2.4 * k + dx, cy + 8 * k,
                                   fill=colour, outline="")
                c.create_rectangle(cx + 1.6 * k + dx, cy + 2 * k, cx + 6.6 * k + dx, cy + 6 * k,
                                   fill=colour, outline="")
        tags = self.player.tags if self.player else None
        path = self.files[self.order[self.position_in_order]]
        title = (tags.title if tags and tags.title else
                 os.path.splitext(os.path.basename(path))[0])
        line2 = " · ".join(x for x in ((tags.artist if tags else None),
                                       (tags.album if tags else None)) if x)
        ty = y0 + side + px(14)
        c.create_text(w / 2, ty, text=self._fit(title, w, 13), fill=T["text"],
                      font=self.app.font(13), anchor="n")
        if line2:
            c.create_text(w / 2, ty + px(30), text=self._fit(line2, w, 9), fill=T["muted"],
                          font=self.app.font(9, False), anchor="n")

    def _fit(self, text: str, width: int, size: int) -> str:
        f = self.app.tkfont(size, size >= 13)
        if f.measure(text) <= width:
            return text
        while text and f.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def _load_cover(self):
        tags = self.player.tags if self.player else None
        source = tags.cover if tags and tags.cover is not None else None
        if source is None:
            path = folder_cover(self.files[self.order[self.position_in_order]])
            if path:
                try:
                    source = Image.open(path)
                    source.load()
                    source = source.convert('RGB')
                except Exception:      # noqa: BLE001
                    source = None
        self._cover_source = source
        self._draw_cover()

    # ── playing ──
    def play_index(self, index: int):
        if self.player is None or not self.files:
            return
        self._remember_position()
        path = self.files[index]
        start = 0.0
        if self.kind == 'video':
            saved = self.positions.get(path)
            if isinstance(saved, (int, float)) and saved > 0:
                start = float(saved)
        log.info("playing %s%s", path, f" from {clock(start)}" if start else "")
        self.player.load(path, video=self.kind == 'video', start=start)
        self.app.set_window_title(os.path.basename(path))
        name = os.path.splitext(os.path.basename(path))[0]
        self.title_label.config(text=self._fit(name, self.app.px(420), 9))
        count = f"{index + 1} / {len(self.files)}" if len(self.files) > 1 else ""
        self.sub_label.config(text=count, fg=T["muted"])
        self.seek.set(0)
        self.time_label.config(text="0:00")
        self.total_label.config(text="--:--")
        self.btn["play"].set_icon("pause")
        self._hide_problem()
        many = len(self.files) > 1
        self.btn["prev"].set_enabled(True)
        self.btn["next"].set_enabled(many)
        if self.queue_list is not None:
            self.queue_list.selection_clear(0, "end")
            self.queue_list.selection_set(index)
            self.queue_list.see(index)
            self._load_cover()
        if start:
            self.app.set_status(f"RESUMED AT {clock(start)} · HOME STARTS OVER", T["accent"])
        self.app.glitch.now(self.app.title)

    def _on_event(self, what: str, data: Any):
        if what == 'eos':
            self._ended()
        elif what == 'error':
            self.btn["play"].set_icon("play")
            self._show_problem("CAN'T PLAY THIS FILE", str(data))
            self.app.set_status("PLAYBACK ERROR", T["pink"])
            self.app.glitch.now(self.app.title, strong=True)
        elif what == 'tags':
            if self.kind == 'music':
                self._load_cover()
            self._update_track_buttons()
        elif what == 'ready':
            self._update_track_buttons()
            if self.surface is not None:
                self.player.expose(self.surface.winfo_width(), self.surface.winfo_height())
                if not self.player.has_video():
                    self._show_problem("NO PICTURE", "This file has sound only.", error=False)

    def _ended(self):
        path = self.files[self.order[self.position_in_order]]
        self.positions.pop(path, None)
        last = self.position_in_order >= len(self.order) - 1
        if self.kind == 'music' and (not last or self.repeat):
            self.next()
        elif self.kind == 'video' and not last and len(self.files) > 1 and \
                self.app.settings.get("autoplay_next_video", False):
            self.next()
        else:
            self.btn["play"].set_icon("play")
            self.app.set_status("FINISHED", T["muted"])

    def _poll(self):
        self._poll_id = self.after(POLL_MS, self._poll)
        if self.player is None:
            return
        self.player.poll()
        pos, dur = self.player.position(), self.player.duration
        if pos is not None and not self.seek.dragging:
            self.time_label.config(text=clock(pos))
            if dur:
                self.seek.set(pos / dur)
        self.total_label.config(text=clock(dur) if dur else "--:--")
        self.btn["play"].set_icon("pause" if self.player.playing else "play")

    def toggle(self):
        if self.player is None:
            return
        self.player.toggle()
        self.btn["play"].set_icon("pause" if self.player.playing else "play")
        self.app.set_status("PLAYING" if self.player.playing else "PAUSED",
                            T["accent"] if self.player.playing else T["muted"])

    def next(self):
        if len(self.order) < 2:
            return
        self.position_in_order = (self.position_in_order + 1) % len(self.order)
        self.play_index(self.order[self.position_in_order])

    def prev(self):
        if self.player is None:
            return
        pos = self.player.position() or 0
        if pos > 3 or len(self.order) < 2:
            self.player.seek(0)
            return
        self.position_in_order = (self.position_in_order - 1) % len(self.order)
        self.play_index(self.order[self.position_in_order])

    def _seek_to(self, fraction: float):
        if self.player and self.player.duration:
            self.player.seek(fraction * self.player.duration)

    def _seek_drag(self, fraction: float):
        if self.player and self.player.duration:
            self.time_label.config(text=clock(fraction * self.player.duration))
            now = self.tk.call('clock', 'milliseconds')
            if now - self._last_drag_seek > 120:
                self._last_drag_seek = now
                self.player.seek(fraction * self.player.duration, accurate=False)

    def _volume_set(self, value: float):
        if self.player:
            self.player.volume = value
            if self.player.muted and value > 0:
                self.player.muted = False
            self.app.settings["volume"] = round(value, 3)
            self.app.settings["muted"] = self.player.muted
            self._paint_mute()

    def change_volume(self, delta: float):
        if self.player:
            self.volume.set(max(0.0, min(1.0, self.player.volume + delta)))
            self._volume_set(self.volume.value)
            self.app.set_status(f"VOLUME {round(self.player.volume * 100)}%", T["accent"])

    def toggle_mute(self):
        if self.player:
            self.player.muted = not self.player.muted
            self.app.settings["muted"] = self.player.muted
            self._paint_mute()
            self.app.set_status("MUTED" if self.player.muted else "SOUND ON", T["muted"])

    def _paint_mute(self):
        if self.player:
            self.btn["mute"].set_icon("mute" if self.player.muted or self.player.volume == 0
                                      else "volume")

    def toggle_subtitles(self):
        if self.player:
            on = self.player.toggle_subtitles()
            self.app.set_status("SUBTITLES ON" if on else "SUBTITLES OFF", T["accent"])

    def next_audio(self):
        if self.player:
            index = self.player.next_audio_track()
            if index is not None:
                self.app.set_status(f"AUDIO TRACK {index + 1}", T["accent"])

    def _update_track_buttons(self):
        if self.player is None or self.kind != 'video':
            return
        audio, text = self.player.track_counts()
        has_sub = text > 0 or bool(self.player.playbin.get_property('suburi'))
        for name, show in (("subtitles", has_sub), ("audio", audio > 1)):
            button = self.btn[name]
            if show and not button.winfo_ismapped():
                button.pack(side="right", before=self.btn["fullscreen"])
            elif not show and button.winfo_ismapped():
                button.pack_forget()

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        current = self.order[self.position_in_order]
        rest = [i for i in range(len(self.files)) if i != current]
        if self.shuffle:
            random.shuffle(rest)
            self.order = [current] + rest
        else:
            self.order = list(range(len(self.files)))
        self.position_in_order = self.order.index(current)
        self.btn["shuffle"].accent = self.shuffle
        self.btn["shuffle"].draw()
        self.app.set_status("SHUFFLE ON" if self.shuffle else "SHUFFLE OFF", T["accent"])

    def toggle_repeat(self):
        self.repeat = not self.repeat
        self.btn["repeat"].accent = self.repeat
        self.btn["repeat"].draw()
        self.app.set_status("REPEAT ON" if self.repeat else "REPEAT OFF", T["accent"])

    # ── messages over the stage ──
    def _show_problem(self, title: str, detail: str, error: bool = True):
        self._hide_problem()
        px = self.app.px
        box = tk.Frame(self.stage, bg=T["panel"], highlightthickness=1,
                       highlightbackground=T["pink"] if error else T["line2"])
        tk.Label(box, text=title, bg=T["panel"], fg=T["pink"] if error else T["text"],
                 font=self.app.font(10)).pack(padx=px(18), pady=(px(12), px(4)))
        tk.Label(box, text=detail, bg=T["panel"], fg=T["muted"], font=self.app.font(8, False),
                 wraplength=px(460), justify="center").pack(padx=px(18), pady=(0, px(12)))
        box.place(relx=0.5, rely=0.5, anchor="center")
        self.message = box

    def _hide_problem(self):
        if self.message is not None:
            self.message.destroy()
            self.message = None

    # ── window ──
    def _surface_resized(self, event):
        if self.player is not None:
            self.player.expose(event.width, event.height)

    def fullscreen_changed(self, on: bool):
        if not on:
            self._show_controls()
            if self._hide_id:
                self.after_cancel(self._hide_id)
                self._hide_id = None
        else:
            self._activity()

    def _activity(self, _event=None):
        if not self.app.fullscreen:
            return
        self._show_controls()
        if self._hide_id:
            self.after_cancel(self._hide_id)
        self._hide_id = self.after(HIDE_CONTROLS_MS, self._hide_controls)

    def _show_controls(self):
        if not self.bar.winfo_ismapped():
            self.bar.pack(fill="x")
        self.configure(cursor="")
        if self.surface is not None:
            self.surface.configure(cursor="")

    def _hide_controls(self):
        self._hide_id = None
        if self.app.fullscreen and self.kind == 'video' and self.player and self.player.playing:
            self.bar.pack_forget()
            if self.surface is not None:
                self.surface.configure(cursor="none")

    def key(self, event) -> bool:
        k = event.keysym
        shift = bool(event.state & 0x1)
        self._activity()
        if k in ('space', 'k', 'K', 'p', 'P', 'XF86AudioPlay'):
            self.toggle()
        elif k in ('Right', 'l', 'L'):
            self.player and self.player.step(SEEK_BIG if shift else SEEK_STEP)
        elif k in ('Left', 'j', 'J'):
            self.player and self.player.step(-(SEEK_BIG if shift else SEEK_STEP))
        elif k == 'Up':
            self.change_volume(0.05)
        elif k == 'Down':
            self.change_volume(-0.05)
        elif k in ('m', 'M'):
            self.toggle_mute()
        elif k in ('Next', 'n', 'N', 'XF86AudioNext'):
            self.next()
        elif k in ('Prior', 'XF86AudioPrev'):
            self.prev()
        elif k == 'Home':
            self.player and self.player.seek(0)
        elif k in ('s', 'S', 'v', 'V') and self.kind == 'video':
            self.toggle_subtitles()
        elif k in ('a', 'A') and self.kind == 'video':
            self.next_audio()
        else:
            return False
        return True

    def _remember_position(self):
        if self.player is None or self.kind != 'video' or not self.player.path:
            return
        pos, dur = self.player.position(), self.player.duration
        path = self.player.path
        if pos is None or not dur or dur < RESUME_MIN:
            return
        if 30 < pos < dur - 30:
            self.positions.pop(path, None)
            self.positions[path] = round(pos, 1)
            while len(self.positions) > RESUME_KEEP:
                self.positions.pop(next(iter(self.positions)))
        else:
            self.positions.pop(path, None)
        save_json('positions.json', self.positions)

    def destroy(self):
        for job in (self._poll_id, self._hide_id):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        if self.player is not None:
            self._remember_position()
            # stop before the window it draws into goes away
            self.player.close()
            self.player = None
        super().destroy()
