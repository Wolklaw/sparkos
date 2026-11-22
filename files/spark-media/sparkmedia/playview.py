"""The player screens. Videos: the picture and the transport bar, with their own player.
Music: cover art, the play queue and the same transport bar, driving the app's music session,
so the music keeps playing when you go back to the library."""

import os
from typing import Any, Callable, List, Optional

import tkinter as tk

from PIL import Image, ImageTk

from . import player as gst
from .core import clock, folder_cover, load_json, log, save_json
from .text import tr
from .widgets import T, IconButton, Seek

POLL_MS = 100
HIDE_CONTROLS_MS = 2500
RESUME_MIN = 180          # remember where a video was left if it runs at least this long (s)
RESUME_KEEP = 200         # how many videos to remember
SEEK_STEP, SEEK_BIG = 5, 30


def fit_text(app, text: str, width: int, size: int, bold: bool = False) -> str:
    f = app.tkfont(size, bold)
    if f.measure(text) <= width:
        return text
    while text and f.measure(text + "…") > width:
        text = text[:-1]
    return text + "…"


class Transport(tk.Frame):
    """The bar under a video or a song: time, seek bar, prev/play/next, title, volume. Screens
    put their own buttons in .extras."""

    def __init__(self, parent: tk.Misc, app, on_seek: Callable[[float], None],
                 on_drag: Callable[[float], None], on_prev, on_toggle, on_next,
                 on_volume: Callable[[float], None], on_mute):
        super().__init__(parent, bg=T["panel"])
        self.app = app
        px = app.px
        tk.Frame(self, bg=T["line"], height=1).pack(fill="x")
        seek_row = tk.Frame(self, bg=T["panel"])
        seek_row.pack(fill="x", padx=px(10), pady=(px(6), 0))
        self.time_label = tk.Label(seek_row, text="0:00", bg=T["panel"], fg=T["text"],
                                   font=app.font(8), width=8, anchor="w")
        self.time_label.pack(side="left")
        self.total_label = tk.Label(seek_row, text="--:--", bg=T["panel"], fg=T["muted"],
                                    font=app.font(8), width=8, anchor="e")
        self.total_label.pack(side="right")
        self.seek = Seek(seek_row, px(18), on_seek, on_drag)
        self.seek.pack(side="left", fill="x", expand=True)

        row = tk.Frame(self, bg=T["panel"])
        row.pack(fill="x", padx=px(10), pady=(px(2), px(8)))
        size = px(30)
        self.btn = {"prev": IconButton(row, "prev", on_prev, size, tip=tr('tip.prev')),
                    "play": IconButton(row, "pause", on_toggle, px(34), accent=True,
                                       tip=tr('tip.play')),
                    "next": IconButton(row, "next", on_next, size, tip=tr('tip.next'))}
        for name in ("prev", "play", "next"):
            self.btn[name].pack(side="left", padx=(0, px(4)))
        self.title_label = tk.Label(row, text="", bg=T["panel"], fg=T["text"], font=app.font(9),
                                    anchor="w")
        self.title_label.pack(side="left", padx=(px(10), 0))
        self.sub_label = tk.Label(row, text="", bg=T["panel"], fg=T["muted"],
                                  font=app.font(8, False), anchor="w")
        self.sub_label.pack(side="left", padx=(px(10), 0), fill="x", expand=True)
        self.extras = tk.Frame(row, bg=T["panel"])
        self.extras.pack(side="right")
        self.volume = Seek(row, px(18), on_volume, on_volume, width=px(90))
        self.volume.pack(side="right", padx=(0, px(10)))
        self.btn["mute"] = IconButton(row, "volume", on_mute, size, tip=tr('tip.mute'))
        self.btn["mute"].pack(side="right")

    def button(self, name: str, icon: str, command, tip: str = '', show: bool = True) -> IconButton:
        b = IconButton(self.extras, icon, command, self.app.px(30), tip=tip)
        if show:
            b.pack(side="right")
        self.btn[name] = b
        return b

    def set_time(self, pos: Optional[float], dur: Optional[float]) -> None:
        if pos is not None and not self.seek.dragging:
            self.time_label.config(text=clock(pos))
            if dur:
                self.seek.set(pos / dur)
        self.total_label.config(text=clock(dur) if dur else "--:--")

    def reset_time(self) -> None:
        self.seek.set(0)
        self.time_label.config(text="0:00")
        self.total_label.config(text="--:--")

    def set_playing(self, playing: bool) -> None:
        self.btn["play"].set_icon("pause" if playing else "play")

    def set_title(self, title: str, sub: str = '', colour: str = T["muted"]) -> None:
        self.title_label.config(text=fit_text(self.app, title, self.app.px(420), 9, True))
        self.sub_label.config(text=sub, fg=colour)

    def paint_mute(self, muted: bool, volume: float) -> None:
        self.btn["mute"].set_icon("mute" if muted or volume == 0 else "volume")

    def disable(self) -> None:
        self.btn["play"].set_icon("play")
        for button in self.btn.values():
            button.set_enabled(False)
        self.seek.set_enabled(False)
        self.volume.set_enabled(False)


class _Stage:
    """Messages over the picture or the cover."""

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


# ─── Videos ───────────────────────────────────────────────────

class PlayerView(tk.Frame, _Stage):
    kind = 'video'

    def __init__(self, app, path: str, playlist: List[str]):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.files = playlist
        self.index = playlist.index(path) if path in playlist else 0
        self.message: Optional[tk.Frame] = None
        app.pause_music()

        # bg "" : Tk paints nothing here, so it never draws over the frames the sink puts in
        self.stage = tk.Frame(self, bg="#000000")
        self.stage.pack(fill="both", expand=True)
        self.surface = tk.Frame(self.stage, bg="", width=app.px(640), height=app.px(360))
        self.surface.pack(fill="both", expand=True)
        self.surface.bind("<Configure>", self._surface_resized)
        self.surface.bind("<Double-Button-1>", lambda _e: self.app.toggle_fullscreen())
        self.surface.bind("<ButtonRelease-1>", lambda _e: self.toggle())

        self.bar = Transport(self, app, self._seek_to, self._seek_drag, self.prev, self.toggle,
                             self.next, self._volume_set, self.toggle_mute)
        self.bar.pack(fill="x")
        self.btn = self.bar.btn
        self.bar.button("fullscreen", "fullscreen", app.toggle_fullscreen, tr('tip.fullscreen'))
        self.bar.button("subtitles", "subtitles", self.toggle_subtitles, tr('tip.subtitles'),
                        show=False)
        self.bar.button("audio", "audio", self.next_audio, tr('tip.audio'), show=False)

        self.player: Optional[gst.Player] = None
        self.positions = load_json('positions.json')
        self._poll_id = self._hide_id = None
        self._last_drag_seek = 0.0
        problem = gst.init()
        if problem:
            self._disable()
            self._show_problem(tr('play.need_gst'), problem)
            return
        self.update_idletasks()
        try:
            self.player = gst.Player(self._on_event, window_handle=self.surface.winfo_id(),
                                     audio_sink=os.environ.get('SPARK_MEDIA_AUDIO_SINK'))
        except RuntimeError as exc:
            self._disable()
            self._show_problem(tr('play.no_start'), str(exc))
            return
        saved = app.settings.get("volume")
        self.player.volume = float(saved) if isinstance(saved, (int, float)) else 0.8
        self.player.muted = bool(app.settings.get("muted", False))
        self.bar.volume.set(self.player.volume)
        self.bar.paint_mute(self.player.muted, self.player.volume)
        if self.player.sink is None:
            self._show_problem(tr('play.no_video_out'), tr('play.no_video_out_detail'))
        self._poll_id = self.after(POLL_MS, self._poll)
        for widget in (self, self.surface, self.stage):
            widget.bind("<Motion>", self._activity, add="+")
        self.play_index(self.index)

    def _disable(self):
        self.bar.disable()
        name = os.path.splitext(os.path.basename(self.files[self.index]))[0]
        self.bar.set_title(name)

    # ── playing ──
    def play_index(self, index: int):
        if self.player is None or not self.files:
            return
        self._remember_position()
        self.index = index % len(self.files)
        path = self.files[self.index]
        start = 0.0
        saved = self.positions.get(path)
        if isinstance(saved, (int, float)) and saved > 0:
            start = float(saved)
        log.info("playing %s%s", path, f" from {clock(start)}" if start else "")
        self.player.load(path, video=True, start=start)
        self.app.set_window_title(os.path.basename(path))
        count = f"{self.index + 1} / {len(self.files)}" if len(self.files) > 1 else ""
        self.bar.set_title(os.path.splitext(os.path.basename(path))[0], count)
        self.bar.reset_time()
        self.bar.set_playing(True)
        self._hide_problem()
        self.btn["prev"].set_enabled(True)
        self.btn["next"].set_enabled(len(self.files) > 1)
        if start:
            self.app.set_status(tr('status.resumed', time=clock(start)), T["accent"])
        self.app.glitch.now(self.app.title)

    def _on_event(self, what: str, data: Any):
        if what == 'eos':
            self._ended()
        elif what == 'error':
            self.bar.set_playing(False)
            self._show_problem(tr('play.cant'), str(data))
            self.app.set_status(tr('status.play_error'), T["pink"])
            self.app.glitch.now(self.app.title, strong=True)
        elif what in ('tags', 'ready'):
            self._update_track_buttons()
            if what == 'ready':
                self.player.expose(self.surface.winfo_width(), self.surface.winfo_height())
                if not self.player.has_video():
                    self._show_problem(tr('play.no_picture'), tr('play.sound_only'), error=False)

    def _ended(self):
        self.positions.pop(self.files[self.index], None)
        last = self.index >= len(self.files) - 1
        if not last and self.app.settings.get("autoplay_next_video", False):
            self.next()
        else:
            self.bar.set_playing(False)
            self.app.set_status(tr('status.finished'), T["muted"])

    def _poll(self):
        self._poll_id = self.after(POLL_MS, self._poll)
        if self.player is None:
            return
        self.player.poll()
        self.bar.set_time(self.player.position(), self.player.duration)
        self.bar.set_playing(self.player.playing)

    def toggle(self):
        if self.player is None:
            return
        self.player.toggle()
        self.bar.set_playing(self.player.playing)
        self.app.set_status(tr('status.playing') if self.player.playing else tr('status.paused'),
                            T["accent"] if self.player.playing else T["muted"])

    def next(self):
        if len(self.files) > 1:
            self.play_index(self.index + 1)

    def prev(self):
        if self.player is None:
            return
        pos = self.player.position() or 0
        if pos > 3 or len(self.files) < 2:
            self.player.seek(0)
            return
        self.play_index(self.index - 1)

    def _seek_to(self, fraction: float):
        if self.player and self.player.duration:
            self.player.seek(fraction * self.player.duration)

    def _seek_drag(self, fraction: float):
        if self.player and self.player.duration:
            self.bar.time_label.config(text=clock(fraction * self.player.duration))
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
            self.bar.paint_mute(self.player.muted, self.player.volume)

    def change_volume(self, delta: float):
        if self.player:
            self.bar.volume.set(max(0.0, min(1.0, self.player.volume + delta)))
            self._volume_set(self.bar.volume.value)
            self.app.set_status(tr('status.volume', n=round(self.player.volume * 100)),
                                T["accent"])

    def toggle_mute(self):
        if self.player:
            self.player.muted = not self.player.muted
            self.app.settings["muted"] = self.player.muted
            self.bar.paint_mute(self.player.muted, self.player.volume)
            self.app.set_status(tr('status.muted') if self.player.muted else tr('status.sound_on'),
                                T["muted"])

    def toggle_subtitles(self):
        if self.player:
            on = self.player.toggle_subtitles()
            self.app.set_status(tr('status.subs_on') if on else tr('status.subs_off'), T["accent"])

    def next_audio(self):
        if self.player:
            index = self.player.next_audio_track()
            if index is not None:
                self.app.set_status(tr('status.audio_track', n=index + 1), T["accent"])

    def _update_track_buttons(self):
        if self.player is None:
            return
        audio, text = self.player.track_counts()
        has_sub = text > 0 or bool(self.player.playbin.get_property('suburi'))
        for name, show in (("subtitles", has_sub), ("audio", audio > 1)):
            button = self.btn[name]
            if show and not button.winfo_ismapped():
                button.pack(side="right", before=self.btn["fullscreen"])
            elif not show and button.winfo_ismapped():
                button.pack_forget()

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
        self.surface.configure(cursor="")

    def _hide_controls(self):
        self._hide_id = None
        if self.app.fullscreen and self.player and self.player.playing:
            self.bar.pack_forget()
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
        elif k in ('s', 'S', 'v', 'V'):
            self.toggle_subtitles()
        elif k in ('a', 'A'):
            self.next_audio()
        else:
            return False
        return True

    def _remember_position(self):
        if self.player is None or not self.player.path:
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


# ─── Music ────────────────────────────────────────────────────

def draw_note(c: tk.Canvas, cx: float, cy: float, k: float):
    """The no-cover mark: a note split into the two channels."""
    for dx, colour in ((-1.5, T["ch_a"]), (1.5, T["ch_b"]), (0, T["accent"])):
        c.create_line(cx - 3 * k + dx, cy + 6 * k, cx - 3 * k + dx, cy - 7 * k,
                      cx + 6 * k + dx, cy - 9 * k, cx + 6 * k + dx, cy + 4 * k,
                      fill=colour, width=max(2, round(1.2 * k)))
        c.create_rectangle(cx - 7 * k + dx, cy + 4 * k, cx - 2.4 * k + dx, cy + 8 * k,
                           fill=colour, outline="")
        c.create_rectangle(cx + 1.6 * k + dx, cy + 2 * k, cx + 6.6 * k + dx, cy + 6 * k,
                           fill=colour, outline="")


class MusicPlayerView(tk.Frame, _Stage):
    """Now playing: the cover, the queue, and the transport bar for the app's music session."""
    kind = 'music'

    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.session = app.music
        self.message: Optional[tk.Frame] = None
        self._cover_image: Optional[ImageTk.PhotoImage] = None
        self._cover_source: Optional[Image.Image] = None
        self._cover_for: Optional[str] = None
        self._last_drag_seek = 0.0
        self._rows: List[int] = []
        px = app.px

        self.stage = tk.Frame(self, bg=T["bg"])
        self.stage.pack(fill="both", expand=True)
        wrap = tk.Frame(self.stage, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=px(16), pady=px(16))
        left = tk.Frame(wrap, bg=T["bg"])
        left.pack(side="left", fill="both", expand=True)
        self.cover_canvas = tk.Canvas(left, bg=T["bg"], highlightthickness=0, bd=0)
        self.cover_canvas.pack(fill="both", expand=True)
        self.cover_canvas.bind("<Configure>", lambda _e: self._draw_cover())
        right = tk.Frame(wrap, bg=T["bg"], width=px(340))
        right.pack(side="right", fill="y", padx=(px(16), 0))
        right.pack_propagate(False)
        head = tk.Frame(right, bg=T["bg"])
        head.pack(fill="x", pady=(0, px(6)))
        tk.Label(head, text=tr('music.up_next'), bg=T["bg"], fg=T["dim"], font=app.font(7),
                 anchor="w").pack(side="left")
        from .widgets import WolkButton
        WolkButton(head, tr('music.clear'), self._clear, app.font(7), padx=px(6),
                   pady=px(1)).pack(side="right")
        WolkButton(head, tr('music.save_queue'), self._save_queue, app.font(7), padx=px(6),
                   pady=px(1)).pack(side="right", padx=(0, px(4)))
        edge = tk.Frame(right, bg=T["line"], padx=1, pady=1)
        edge.pack(fill="both", expand=True)
        self.queue_list = tk.Listbox(
            edge, bg=T["panel"], fg=T["text"], font=app.font(8, False), bd=0,
            highlightthickness=0, activestyle="none", selectbackground=T["hover"],
            selectforeground=T["text"], exportselection=False, takefocus=1)
        self.queue_list.pack(fill="both", expand=True)
        self.queue_list.bind("<Double-Button-1>", self._queue_pick)
        self.queue_list.bind("<Return>", self._queue_pick)
        self.queue_list.bind("<Button-3>", self._queue_menu)
        self.queue_list.bind("<Delete>", lambda _e: self._remove_selected())

        self.bar = Transport(self, app, self._seek_to, self._seek_drag, self.session.prev,
                             self.session.toggle, self.session.next, self._volume_set,
                             self.toggle_mute)
        self.bar.pack(fill="x")
        self.btn = self.bar.btn
        self.bar.button("repeat", "repeat", self.toggle_repeat, tr('tip.repeat'))
        self.bar.button("shuffle", "shuffle", self.toggle_shuffle, tr('tip.shuffle'))

        player = self.session.player
        if self.session.problem or player is None:
            self.bar.disable()
            self._show_problem(tr('play.need_gst'), self.session.problem or '')
        else:
            self.bar.volume.set(player.volume)
            self.bar.paint_mute(player.muted, player.volume)
        self._paint_modes()
        self.session.listen(self._on_session)
        self._refresh_queue()
        self._refresh_track()
        self.session._ensure_poll()

    @property
    def player(self) -> Optional[gst.Player]:
        return self.session.player

    # ── session events ──
    def _on_session(self, what: str, data: Any):
        if what == 'tick':
            p = self.session.player
            if p is not None:
                self.bar.set_time(p.position(), p.duration)
                self.bar.set_playing(p.playing)
        elif what == 'track':
            self._hide_problem()
            self._refresh_track()
            self._refresh_queue()
            self.app.glitch.now(self.app.title)
        elif what == 'queue':
            self._refresh_queue()
        elif what == 'tags':
            self._refresh_track(cover_only=False)
        elif what == 'state':
            self.bar.set_playing(self.session.playing)
            self._paint_modes()
        elif what == 'finished':
            self.bar.set_playing(False)
            self.app.set_status(tr('status.finished'), T["muted"])
        elif what == 'error':
            self.bar.set_playing(False)
            self._show_problem(tr('play.cant'), str(data))
            self.app.set_status(tr('status.play_error'), T["pink"])
            self.app.glitch.now(self.app.title, strong=True)

    def _refresh_track(self, cover_only: bool = False):
        path = self.session.current
        if path is None:
            self.bar.set_title(tr('music.nothing'), '')
            self.bar.reset_time()
            self.bar.set_playing(False)
            self._cover_source, self._cover_for = None, None
            self._draw_cover()
            return
        info = self.session.info()
        q = self.session.queue
        count = f"{q.pos + 1} / {len(q)}" if len(q) > 1 else ""
        self.bar.set_title(info['title'], count)
        self.bar.set_playing(self.session.playing)
        self.app.set_window_title(info['title'])
        self._load_cover(path)

    def _load_cover(self, path: str):
        tags = self.player.tags if self.player is not None and self.player.path == path else None
        source = tags.cover if tags is not None and tags.cover is not None else None
        if source is None:
            source = self.app.album_cover(path)
        if source is None:
            cover = folder_cover(path)
            if cover:
                try:
                    with Image.open(cover) as image:
                        image.draft('RGB', (1024, 1024))
                        source = image.convert('RGB')
                except Exception:      # noqa: BLE001
                    source = None
        self._cover_source, self._cover_for = source, path
        self._draw_cover()

    def _refresh_queue(self):
        q = self.session.queue
        lb = self.queue_list
        lb.delete(0, "end")
        start = max(0, q.pos)
        self._rows = q.order[start:]
        lines = []
        for n, item in enumerate(self._rows):
            info = self.session.info(q.items[item]) if n < 400 else None
            if info is None:      # past the first few hundred: the file name is enough
                name = os.path.splitext(os.path.basename(q.items[item]))[0]
            else:
                name = info['title'] + (f" — {info['artist']}" if info['artist'] else "")
            lines.append(("▶ " if n == 0 and q.pos >= 0 else "  ") + name)
        if lines:
            lb.insert("end", *lines)
            if q.pos >= 0:
                lb.itemconfig(0, fg=T["accent"])

    def _draw_cover(self):
        c = self.cover_canvas
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
            draw_note(c, w / 2, y0 + side / 2, min(side, px(240)) / 48)
        if self.session.current is None:
            return
        info = self.session.info()
        line2 = " · ".join(x for x in (info['artist'], info['album']) if x)
        ty = y0 + side + px(14)
        c.create_text(w / 2, ty, text=fit_text(self.app, info['title'], w, 13, True),
                      fill=T["text"], font=self.app.font(13), anchor="n")
        if line2:
            c.create_text(w / 2, ty + px(30), text=fit_text(self.app, line2, w, 9),
                          fill=T["muted"], font=self.app.font(9, False), anchor="n")

    # ── queue ──
    def _selected(self) -> Optional[int]:
        sel = self.queue_list.curselection()
        if sel and sel[0] < len(self._rows):
            return self._rows[sel[0]]
        return None

    def _queue_pick(self, _event=None):
        item = self._selected()
        if item is not None:
            self.session.jump(item)
        return "break"

    def _remove_selected(self):
        item = self._selected()
        if item is not None:
            self.session.remove(item)
        return "break"

    def _queue_menu(self, event):
        index = self.queue_list.nearest(event.y)
        if index < 0 or index >= len(self._rows):
            return
        self.queue_list.selection_clear(0, "end")
        self.queue_list.selection_set(index)
        item = self._rows[index]
        menu = self.app.menu()
        menu.add_command(label=tr('menu.play'), command=lambda: self.session.jump(item))
        menu.add_command(label=tr('menu.move_up'), command=lambda: self.session.move(item, -1))
        menu.add_command(label=tr('menu.move_down'), command=lambda: self.session.move(item, 1))
        menu.add_separator()
        menu.add_command(label=tr('menu.remove_queue'), command=lambda: self.session.remove(item))
        menu.tk_popup(event.x_root, event.y_root)

    def _clear(self):
        self.session.clear()

    def _save_queue(self):
        q = self.session.queue
        items = [q.items[i] for i in q.order]
        if items:
            self.app.save_as_playlist(items)

    # ── transport ──
    def _seek_to(self, fraction: float):
        p = self.session.player
        if p and p.duration:
            self.session.seek(fraction * p.duration)

    def _seek_drag(self, fraction: float):
        p = self.session.player
        if p and p.duration:
            self.bar.time_label.config(text=clock(fraction * p.duration))
            now = self.tk.call('clock', 'milliseconds')
            if now - self._last_drag_seek > 120:
                self._last_drag_seek = now
                self.session.seek(fraction * p.duration, accurate=False)

    def _volume_set(self, value: float):
        self.session.set_volume(value)
        p = self.session.player
        if p:
            self.bar.paint_mute(p.muted, p.volume)

    def change_volume(self, delta: float):
        p = self.session.player
        if p:
            self.bar.volume.set(max(0.0, min(1.0, p.volume + delta)))
            self._volume_set(self.bar.volume.value)
            self.app.set_status(tr('status.volume', n=round(p.volume * 100)), T["accent"])

    def toggle_mute(self):
        p = self.session.player
        if p:
            self.session.set_muted(not p.muted)
            self.bar.paint_mute(p.muted, p.volume)
            self.app.set_status(tr('status.muted') if p.muted else tr('status.sound_on'),
                                T["muted"])

    def toggle_shuffle(self):
        self.session.set_shuffle(not self.session.queue.shuffle)
        self._paint_modes()
        self.app.set_status(tr('status.shuffle_on') if self.session.queue.shuffle
                            else tr('status.shuffle_off'), T["accent"])

    def toggle_repeat(self):
        self.session.set_repeat(not self.session.queue.repeat)
        self._paint_modes()
        self.app.set_status(tr('status.repeat_on') if self.session.queue.repeat
                            else tr('status.repeat_off'), T["accent"])

    def _paint_modes(self):
        for name, on in (("shuffle", self.session.queue.shuffle),
                         ("repeat", self.session.queue.repeat)):
            self.btn[name].accent = on
            self.btn[name].draw()

    def fullscreen_changed(self, on: bool):
        pass

    def key(self, event) -> bool:
        k = event.keysym
        shift = bool(event.state & 0x1)
        p = self.session.player
        if k in ('space', 'k', 'K', 'p', 'P', 'XF86AudioPlay'):
            self.session.toggle()
        elif k in ('Right', 'l', 'L'):
            p and p.step(SEEK_BIG if shift else SEEK_STEP)
        elif k in ('Left', 'j', 'J'):
            p and p.step(-(SEEK_BIG if shift else SEEK_STEP))
        elif k == 'Up' and event.widget is not self.queue_list:
            self.change_volume(0.05)
        elif k == 'Down' and event.widget is not self.queue_list:
            self.change_volume(-0.05)
        elif k in ('m', 'M'):
            self.toggle_mute()
        elif k in ('Next', 'n', 'N', 'XF86AudioNext'):
            self.session.next()
        elif k in ('Prior', 'XF86AudioPrev'):
            self.session.prev()
        elif k == 'Home':
            self.session.seek(0)
        else:
            return False
        return True

    def destroy(self):
        self.session.unlisten(self._on_session)
        super().destroy()
