"""The Spark Clips window: what the replay service is doing, a button to save a clip now, the
clips you have, and the settings. The service (daemon.py) does the recording; this only talks
to it over the control socket, so closing the window never stops the replay."""

import os
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable, Dict, List, Optional

from . import APP_CLASS, APP_NAME, buffer, clipfile, dialogs, ipc, library, servicectl, shortcut, trash
from .core import (BITRATES, FRAME_RATES, LENGTHS, SIZES, buffer_dir, clean_name, clips_dir,
                   duration_text, file_when, human_size, load_settings, log, reduced_motion,
                   save_settings)
from .text import t
from .widgets import (T, Choice, Glitch, GlitchPanel, GlitchText, Mark, Segmented, Strip, Toggle,
                      WolkButton, pick_mono)

TICK_MS = 100
STATUS_EVERY = 1.0
LIBRARY_EVERY = 3.0
CARD_W = 188
THUMB_W = 168
MIN_TRIM = 0.5


def launch(argv: List[str]) -> bool:
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as exc:
        log.warning("couldn't start %s: %s", argv[0], exc)
        return False


def time_text(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def problem_text(status: Dict[str, Any]) -> str:
    """The sentence for what is wrong, from the service's problem key."""
    key = status.get('problem')
    if not key:
        return ''
    return t('problem.' + key, detail=status.get('detail') or '')


class App:
    def __init__(self, opener: Callable[[List[str]], bool] = launch,
                 ask: Optional[Callable[..., bool]] = None,
                 tell: Optional[Callable[..., object]] = None,
                 warn: Optional[Callable[..., object]] = None,
                 error: Optional[Callable[..., object]] = None,
                 name: Optional[Callable[..., Optional[str]]] = None,
                 root_folder: Optional[str] = None, poll: bool = True):
        # the dialogs can be swapped (the tests answer them; nothing modal blocks a test)
        self.opener = opener
        self.ask = ask or dialogs.askyesno
        self.tell = tell or dialogs.showinfo
        self.warn = warn or dialogs.showwarning
        self.error = error or dialogs.showerror
        self.askname = name or dialogs.askname
        self.folder = root_folder
        self.settings = load_settings()
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=T["bg"])
        try:
            self.scale = max(1.0, self.root.winfo_fpixels('1i') / 96)
        except tk.TclError:
            self.scale = 1.0
        self.root.geometry(f"{self.px(1120)}x{self.px(760)}")
        self.root.minsize(self.px(900), self.px(600))
        family = pick_mono(self.root)
        self.f_body = tkfont.Font(root=self.root, family=family, size=9)
        self.f_small = tkfont.Font(root=self.root, family=family, size=8)
        self.f_label = tkfont.Font(root=self.root, family=family, size=7, weight="bold")
        self.f_title = tkfont.Font(root=self.root, family=family, size=11, weight="bold")
        self.f_brand = tkfont.Font(root=self.root, family=family, size=10, weight="bold")
        self.f_big = tkfont.Font(root=self.root, family=family, size=20, weight="bold")
        self.glitch = Glitch(self.root, not reduced_motion())
        self.closed = False
        self.inbox: 'queue.Queue[Callable[[], None]]' = queue.Queue()
        self.jobs: 'queue.Queue[Optional[library.Clip]]' = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.poll = poll
        self.service: Optional[Dict[str, Any]] = None      # the last status; None = no service
        self.asking = False
        self.next_status = 0.0
        self.next_library = 0.0
        self.starting_service = False
        self.clips: List[library.Clip] = []
        self.signature: tuple = ()
        self.selected: Optional[str] = None
        self.cards: Dict[str, tk.Frame] = {}
        self.images: Dict[str, Any] = {}
        self.infos: Dict[str, Dict[str, Any]] = {}
        self.queued: set = set()
        self.columns = 0
        self.shortcut_owner: Optional[str] = None
        self.trim_window: Optional[tk.Toplevel] = None

        self._header()
        body = tk.Frame(self.root, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=self.px(14), pady=self.px(10))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self._main(body)
        self._side(body)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        for seq in ("<Control-q>", "<Control-w>"):
            self.root.bind(seq, lambda _e: self.close())
        self.root.bind("<F5>", lambda _e: self.refresh_library(force=True))
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        self.refresh_library(force=True)
        self.apply_status(None)
        if poll:
            threading.Thread(target=self._find_shortcut_owner, daemon=True).start()
        self.tick_job = self.root.after(TICK_MS, self._tick)

    def px(self, v: float) -> int:
        return int(round(v * self.scale))

    # ── layout ──

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

    def set_status(self, key: str, colour: Optional[str] = None, **kw):
        self.status.config(text="● " + t(key, **kw), fg=colour or T["accent"])

    def event(self, *targets, strong: bool = False):
        self.glitch.now(self.title, self.strip, *targets, strong=strong)

    def _main(self, body: tk.Frame):
        px = self.px
        main = tk.Frame(body, bg=T["bg"])
        main.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        self.live = GlitchPanel(main, T["panel"])
        self.live.grid(row=0, column=0, sticky="ew")
        inner = self.live.inner
        inner.columnconfigure(0, weight=1)
        self.state_label = tk.Label(inner, text="", bg=T["panel"], fg=T["text"], font=self.f_big,
                                    anchor="w", justify="left")
        self.state_label.grid(row=0, column=0, sticky="ew", padx=px(14), pady=(px(12), px(2)))
        self.detail_label = tk.Label(inner, text="", bg=T["panel"], fg=T["muted"], font=self.f_body,
                                     anchor="w", justify="left")
        self.detail_label.grid(row=1, column=0, sticky="ew", padx=px(14))
        self.problem_label = tk.Label(inner, text="", bg=T["panel"], fg=T["gold"], font=self.f_body,
                                      anchor="w", justify="left")
        self.problem_label.grid(row=2, column=0, sticky="ew", padx=px(14), pady=(px(4), 0))
        row = tk.Frame(inner, bg=T["panel"])
        row.grid(row=3, column=0, sticky="w", padx=px(14), pady=px(12))
        self.save_button = WolkButton(row, t('button.save'), self.save_clip, self.f_label,
                                      variant="primary", padx=px(16), pady=px(8))
        self.save_button.pack(side="left")
        self.keep_toggle = Toggle(row, t('toggle.keep'), self.settings['keep'], self.set_keep,
                                  self.f_label)
        self.keep_toggle.pack(side="left", padx=(px(14), 0))
        self.setup_button = WolkButton(row, t('button.setup'), self.setup_screen, self.f_label)
        self.service_button = WolkButton(row, t('button.service'), self.start_service, self.f_label)
        self.shortcut_label = tk.Label(inner, text="", bg=T["panel"], fg=T["muted"],
                                       font=self.f_small, anchor="w", justify="left")
        self.shortcut_label.grid(row=4, column=0, sticky="ew", padx=px(14), pady=(0, px(10)))
        self.live.bind("<Configure>", self._wrap_live)

        head = tk.Frame(main, bg=T["bg"])
        head.grid(row=1, column=0, sticky="ew", pady=(px(14), px(6)))
        tk.Label(head, text=t('clips.title').upper(), bg=T["bg"], fg=T["muted"],
                 font=self.f_label).pack(side="left")
        self.tools: Dict[str, WolkButton] = {}
        for key, command in (('folder', self.open_folder), ('copy', self.copy_file),
                             ('delete', self.delete), ('rename', self.rename),
                             ('trim', self.trim), ('play', self.play)):
            button = WolkButton(head, t('tool.' + key), command, self.f_label,
                                variant="danger" if key == 'delete' else "ghost",
                                padx=px(8), pady=px(3))
            button.pack(side="right", padx=(px(4), 0))
            self.tools[key] = button

        shelf = tk.Frame(main, bg=T["panel"], highlightthickness=1, highlightbackground=T["line"])
        shelf.grid(row=2, column=0, sticky="nsew")
        self.canvas = tk.Canvas(shelf, bg=T["panel"], highlightthickness=0, bd=0)
        bar = tk.Scrollbar(shelf, orient="vertical", command=self.canvas.yview, bg=T["panel2"],
                           troughcolor=T["panel"], activebackground=T["hover"], bd=0,
                           highlightthickness=0)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.grid_frame = tk.Frame(self.canvas, bg=T["panel"])
        self.window_id = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.empty = tk.Label(self.canvas, text=t('clips.empty'), bg=T["panel"], fg=T["muted"],
                              font=self.f_body, justify="left", anchor="nw")
        self.canvas.bind("<Configure>", self._shelf_resized)
        self.grid_frame.bind("<Configure>",
                             lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        for widget in (self.canvas, self.grid_frame):
            widget.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-2, "units"))
            widget.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(2, "units"))

    def _wrap_live(self, event=None):
        width = max(200, self.live.winfo_width() - self.px(40))
        for label in (self.detail_label, self.problem_label, self.shortcut_label,
                      self.state_label):
            label.config(wraplength=width)

    def _side(self, body: tk.Frame):
        px = self.px
        side = GlitchPanel(body, T["panel"])
        side.grid(row=0, column=1, sticky="ns")
        self.side = side
        inner = side.inner
        pad = tk.Frame(inner, bg=T["panel"])
        pad.pack(fill="both", expand=True, padx=px(12), pady=px(10))
        pad.configure(width=px(290))
        self.side_pad = pad

        def row(label: str) -> tk.Frame:
            tk.Label(pad, text=label.upper(), bg=T["panel"], fg=T["muted"], font=self.f_label,
                     anchor="w").pack(fill="x", pady=(px(10), px(3)))
            frame = tk.Frame(pad, bg=T["panel"])
            frame.pack(fill="x")
            return frame

        s = self.settings
        self.length = Segmented(row(t('side.length')),
                                [(self.length_text(n), str(n)) for n in LENGTHS],
                                str(s['seconds']), lambda v: self.change(seconds=int(v)),
                                self.f_label)
        self.length.pack(anchor="w")
        box = row(t('side.record'))
        self.only_game = Toggle(box, t('toggle.only_game'), s['only_in_game'],
                                lambda v: self.change(only_in_game=v), self.f_label)
        self.only_game.pack(anchor="w")
        self.sound = Toggle(box, t('toggle.sound'), s['sound'],
                            lambda v: self.change(sound=v), self.f_label)
        self.sound.pack(anchor="w")
        self.mic = Toggle(box, t('toggle.mic'), s['mic'], lambda v: self.change(mic=v),
                          self.f_label)
        self.mic.pack(anchor="w")
        self.codec = Segmented(row(t('side.codec')), [(t('codec.h264'), 'h264'),
                                                      (t('codec.hevc'), 'hevc')],
                               s['codec'], lambda v: self.change(codec=v), self.f_label)
        self.codec.pack(anchor="w")
        self.fps = Segmented(row(t('side.fps')), [(t('fps.native') if v == 'native' else v, v)
                                                  for v in FRAME_RATES],
                             s['fps'], lambda v: self.change(fps=v), self.f_label)
        self.fps.pack(anchor="w")
        self.bitrate = Choice(row(t('side.bitrate')), self.f_body,
                              lambda v: self.change(bitrate=int(v)), width=22)
        self.bitrate.set_items([(t('bitrate.value', n=n), str(n)) for n in BITRATES],
                               str(s['bitrate']))
        self.bitrate.pack(fill="x")
        self.size = Choice(row(t('side.size')), self.f_body, lambda v: self.change(size=v),
                           width=22)
        self.size.set_items([(t('size.' + v), v) for v in SIZES], s['size'])
        self.size.pack(fill="x")
        self.memory = tk.Label(pad, text="", bg=T["panel"], fg=T["muted"], font=self.f_small,
                               anchor="w", justify="left", wraplength=px(270))
        self.memory.pack(fill="x", pady=(px(14), 0))
        self.encoder = tk.Label(pad, text="", bg=T["panel"], fg=T["muted"], font=self.f_small,
                                anchor="w", justify="left", wraplength=px(270))
        self.encoder.pack(fill="x", pady=(px(6), 0))
        self.show_memory()

    @staticmethod
    def length_text(seconds: int) -> str:
        return t('length.minutes', n=seconds // 60) if seconds >= 60 else t('length.seconds', n=seconds)

    # ── settings ──

    def change(self, **values) -> None:
        self.settings.update(values)
        save_settings(self.settings)
        self.show_memory()
        self.event(self.side)
        self._to_service('reload')

    def set_keep(self, value: bool) -> None:
        self.change(keep=value)

    def show_memory(self) -> None:
        s = self.settings
        estimate = buffer.estimate_bytes(s['seconds'], s['bitrate'], 2 if s['mic'] else 1)
        free = buffer.free_bytes(buffer_dir(False))
        text = t('memory.estimate', size=human_size(estimate))
        if free is not None:
            text += ' ' + t('memory.free', size=human_size(free))
        big = buffer.too_big(estimate, free)
        if big:
            text += ' ' + t('memory.too_big')
        self.memory.config(text=text, fg=T["gold"] if big else T["muted"])

    def _find_shortcut_owner(self) -> None:
        owner = shortcut.owner()
        self.inbox.put(lambda: self._set_owner(owner))

    def _set_owner(self, owner: Optional[str]) -> None:
        self.shortcut_owner = owner
        self.show_shortcut()

    def show_shortcut(self) -> None:
        if self.shortcut_owner:
            self.shortcut_label.config(text=t('shortcut.taken', keys=shortcut.KEYS,
                                              name=self.shortcut_owner), fg=T["gold"])
        else:
            self.shortcut_label.config(text=t('shortcut.line', keys=shortcut.KEYS), fg=T["muted"])

    # ── the service ──

    def _to_service(self, command: str, timeout: float = 5.0, then: Optional[Callable] = None,
                    **args) -> None:
        """Ask the service on a thread; `then(reply)` runs on the window's thread."""
        def work():
            reply = ipc.ask(command, timeout, **args)
            self.inbox.put(lambda: then(reply) if then else self.apply_status(reply))
        threading.Thread(target=work, daemon=True).start()

    def apply_status(self, reply: Optional[Dict[str, Any]]) -> None:
        self.asking = False
        self.service = reply if reply and reply.get('ok') else None
        st = self.service
        for button in (self.setup_button, self.service_button):
            button.pack_forget()
        if st is None:
            state_text, colour = t('state.service_off'), T["muted"]
            detail = t('detail.service_off')
            problem = ''
            self.service_button.pack(side="left", padx=(self.px(14), 0))
            self.save_button.set_enabled(False)
            head = t('status.service_off')
            head_colour = T["muted"]
        else:
            state = st.get('state', 'off')
            state_text = t('state.' + state)
            colour = {'recording': T["accent"], 'error': T["pink"],
                      'needs_setup': T["gold"]}.get(state, T["text"])
            problem = problem_text(st)
            detail = self.detail_text(st)
            self.save_button.set_enabled(state == 'recording')
            head = {'recording': 'status.recording', 'error': 'status.error',
                    'needs_setup': 'status.needs_setup', 'starting': 'status.starting',
                    'off': 'status.off'}.get(state, 'status.waiting')
            head_colour = {'recording': T["accent"], 'error': T["pink"],
                           'needs_setup': T["gold"]}.get(state, T["muted"])
            if state == 'needs_setup' or st.get('problem') == 'portal':
                self.setup_button.pack(side="left", padx=(self.px(14), 0))
        self.state_label.config(text=state_text.upper(), fg=colour)
        self.detail_label.config(text=detail)
        self.problem_label.config(text=problem)
        if self.keep_toggle.value != (st['keep'] if st else self.settings['keep']):
            self.keep_toggle.set(st['keep'] if st else self.settings['keep'])
        self.set_status(head, head_colour)
        if st and st.get('last_clip'):
            self.note_clip(st['last_clip'])
        self.show_shortcut()
        encoder = (st or {}).get('encoder')
        self.encoder.config(text=t('encoder.line', name=encoder) if encoder
                            else t('encoder.none'))

    def detail_text(self, st: Dict[str, Any]) -> str:
        bits = []
        if st.get('game'):
            bits.append(t('detail.game', name=st['game']))
        if st.get('state') == 'recording':
            bits.append(t('detail.held', held=duration_text(st.get('held', 0)),
                          keep=duration_text(st.get('seconds', 0))))
            if st.get('tracks'):
                bits.append(t('detail.tracks', n=st['tracks']))
        elif st.get('state') == 'waiting':
            bits.append(t('detail.waiting') if st.get('only_in_game') else t('detail.waiting_any'))
        return '  ·  '.join(bits)

    last_seen: Optional[str] = None

    def note_clip(self, clip: Dict[str, Any]) -> None:
        """A clip saved by the shortcut while the window is open: show it in the list."""
        mark = f"{clip.get('path')}|{clip.get('at')}"
        if mark != self.last_seen:
            first = self.last_seen is None
            self.last_seen = mark
            if not first:
                self.event(self.live, strong=True)
                self.refresh_library(force=True)

    def save_clip(self) -> None:
        if self.service is None or self.service.get('state') != 'recording':
            return
        self.save_button.set_enabled(False)
        self.set_status('status.saving')
        self._to_service('save', timeout=120.0, then=self._saved)

    def _saved(self, reply: Optional[Dict[str, Any]]) -> None:
        if reply and reply.get('ok'):
            self.last_seen = f"{reply.get('path')}|{reply.get('at')}"
            self.event(self.live, strong=True)
            self.set_status('status.saved', name=os.path.basename(reply['path']))
            self.refresh_library(force=True)
            self.selected = reply['path']
            self.mark_selected()
        elif reply is None:
            self.fail('error.save_title', t('error.no_service'), self.live)
        else:
            text = t('problem.' + reply.get('problem', 'save_failed'),
                     detail=reply.get('detail') or '')
            self.fail('error.save_title', text, self.live)
        self._to_service('status')

    def setup_screen(self) -> None:
        self.set_status('status.starting')
        self._to_service('setup', timeout=180.0)

    def start_service(self) -> None:
        if self.starting_service:
            return
        self.starting_service = True
        self.set_status('status.starting')

        def work():
            ok, why = servicectl.start()
            self.inbox.put(lambda: self._service_started(ok, why))
        threading.Thread(target=work, daemon=True).start()

    def _service_started(self, ok: bool, why: Optional[str]) -> None:
        self.starting_service = False
        if not ok:
            self.fail('error.service_title', t('error.service', error=why or ''), self.live)
        self.next_status = 0.0

    # ── the clip list ──

    def clips_folder(self) -> str:
        return self.folder or clips_dir()

    def refresh_library(self, force: bool = False) -> None:
        clips = library.list_clips(self.clips_folder())
        signature = tuple((c.path, c.mtime, c.size) for c in clips)
        if signature == self.signature and not force:
            return
        self.signature = signature
        self.clips = clips
        if self.selected and not any(c.path == self.selected for c in clips):
            self.selected = None
        try:
            library.prune_thumbs(clips)
        except OSError:
            pass
        self.build_cards()

    def build_cards(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.cards = {}
        if not self.clips:
            self.empty.place(x=self.px(14), y=self.px(12), width=max(200, self.canvas.winfo_width() - self.px(28)))
            self.empty.config(wraplength=max(200, self.canvas.winfo_width() - self.px(28)))
        else:
            self.empty.place_forget()
        cols = max(1, (self.canvas.winfo_width() or self.px(600)) // self.px(CARD_W + 12))
        self.columns = cols
        for index, clip in enumerate(self.clips):
            card = self.make_card(clip)
            card.grid(row=index // cols, column=index % cols, padx=self.px(6), pady=self.px(6),
                      sticky="n")
            self.cards[clip.path] = card
            if clip.path not in self.queued:
                self.queued.add(clip.path)
                self.jobs.put(clip)
        self.start_worker()
        self.mark_selected()
        self.set_tools()

    def make_card(self, clip: library.Clip) -> tk.Frame:
        px = self.px
        card = tk.Frame(self.grid_frame, bg=T["panel2"], highlightthickness=1,
                        highlightbackground=T["line"], width=px(CARD_W))
        picture = tk.Label(card, bg=T["tile"], width=px(THUMB_W), height=px(94), bd=0,
                           image=self._blank(), compound="center")
        picture.pack(padx=px(8), pady=(px(8), px(4)))
        title = tk.Label(card, text=clip.name, bg=T["panel2"], fg=T["text"], font=self.f_small,
                         anchor="w", justify="left", wraplength=px(THUMB_W))
        title.pack(fill="x", padx=px(8))
        info = self.infos.get(clip.path)
        meta = tk.Label(card, text=self.meta_text(clip, info), bg=T["panel2"], fg=T["muted"],
                        font=self.f_label, anchor="w", justify="left", wraplength=px(THUMB_W))
        meta.pack(fill="x", padx=px(8), pady=(px(2), px(8)))
        card.picture, card.meta = picture, meta
        thumb = self.images.get(clip.path)
        if thumb is not None:
            picture.config(image=thumb, width=thumb.width(), height=thumb.height())
        for widget in (card, picture, title, meta):
            widget.bind("<Button-1>", lambda _e, p=clip.path: self.select(p))
            widget.bind("<Double-Button-1>", lambda _e, p=clip.path: (self.select(p), self.play()))
            widget.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-2, "units"))
            widget.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(2, "units"))
        return card

    _blank_image: Optional[tk.PhotoImage] = None

    def _blank(self) -> tk.PhotoImage:
        if self._blank_image is None:
            self._blank_image = tk.PhotoImage(master=self.root, width=1, height=1)
        return self._blank_image

    def meta_text(self, clip: library.Clip, info: Optional[Dict[str, Any]]) -> str:
        parts = []
        if info and info.get('duration'):
            parts.append(duration_text(info['duration']))
        parts += [human_size(clip.size), file_when(clip.mtime)]
        return '\n'.join(['  ·  '.join(parts[:-1]), parts[-1]]) if len(parts) > 1 else parts[0]

    def _shelf_resized(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)
        cols = max(1, event.width // self.px(CARD_W + 12))
        if cols != self.columns and self.clips:
            self.build_cards()
        elif not self.clips:
            self.empty.place(x=self.px(14), y=self.px(12), width=max(200, event.width - self.px(28)))
            self.empty.config(wraplength=max(200, event.width - self.px(28)))

    def select(self, path: str) -> None:
        self.selected = path
        self.mark_selected()
        self.set_tools()

    def mark_selected(self) -> None:
        for path, card in self.cards.items():
            on = path == self.selected
            card.config(highlightbackground=T["accent"] if on else T["line"],
                        highlightthickness=2 if on else 1)

    def set_tools(self) -> None:
        for key in ('play', 'trim', 'rename', 'delete', 'copy'):
            self.tools[key].set_enabled(self.selected is not None)

    # ── thumbnails (a thread; the window only receives the results) ──

    def start_worker(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._thumbs, daemon=True, name='clips-thumbs')
            self.worker.start()

    def _thumbs(self) -> None:
        while True:
            clip = self.jobs.get()                 # waits; close() sends None to end it
            if clip is None or self.closed:
                return
            thumb = library.thumb_path(clip)
            if not os.path.isfile(thumb):
                clipfile.thumbnail(clip.path, thumb, THUMB_W)
            info = clipfile.probe(clip.path)
            self.inbox.put(lambda c=clip, th=thumb, i=info: self._thumb_ready(c, th, i))

    def _thumb_ready(self, clip: library.Clip, thumb: str, info: Dict[str, Any]) -> None:
        self.queued.discard(clip.path)
        self.infos[clip.path] = info
        photo = None
        if os.path.isfile(thumb):
            try:
                from PIL import Image, ImageTk
                photo = ImageTk.PhotoImage(Image.open(thumb), master=self.root)
            except Exception:                      # noqa: BLE001 - no ImageTk, a bad JPEG
                photo = None
        if photo is not None:
            self.images[clip.path] = photo
        card = self.cards.get(clip.path)
        if card is not None and card.winfo_exists():
            if photo is not None:
                card.picture.config(image=photo, width=photo.width(), height=photo.height())
            card.meta.config(text=self.meta_text(clip, info))

    # ── the toolbar ──

    def current(self) -> Optional[library.Clip]:
        return next((c for c in self.clips if c.path == self.selected), None)

    def play(self) -> None:
        clip = self.current()
        if clip is None:
            return
        player = shutil.which('spark-media')
        if not self.opener([player, clip.path] if player else ['xdg-open', clip.path]):
            self.error(t('error.open_title'), t('error.open', path=clip.path), parent=self.root)

    def open_folder(self) -> None:
        clip = self.current()
        folder = os.path.dirname(clip.path) if clip else self.clips_folder()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass
        files = shutil.which('spark-files')
        if not self.opener([files, folder] if files else ['xdg-open', folder]):
            self.error(t('error.open_title'), t('error.open', path=folder), parent=self.root)

    def copy_file(self) -> None:
        """Put the file on the clipboard the way file managers do, so it can be pasted into a
        chat or a folder."""
        clip = self.current()
        if clip is None:
            return
        uri = library.path_to_uri(clip.path)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(uri + '\r\n', type='text/uri-list')
            self.root.clipboard_append('copy\n' + uri, type='x-special/gnome-copied-files')
            self.root.clipboard_append(clip.path, type='STRING')
            self.root.update()
        except tk.TclError as exc:
            self.fail('error.copy_title', t('error.copy', error=str(exc)))
            return
        self.set_status('status.copied', name=os.path.basename(clip.path))

    def rename(self) -> None:
        clip = self.current()
        if clip is None:
            return
        wanted = self.askname(t('rename.title'), t('rename.message'), initial=clip.name,
                              parent=self.root)
        if wanted is None:
            return
        ext = os.path.splitext(clip.path)[1]
        wanted = clean_name(wanted)
        if wanted.lower().endswith(ext.lower()):
            wanted = wanted[:-len(ext)]
        if not wanted or wanted == clip.name:
            return
        target = os.path.join(os.path.dirname(clip.path), wanted + ext)
        if os.path.exists(target):
            self.fail('error.rename_title', t('error.exists', name=os.path.basename(target)))
            return
        try:
            os.rename(clip.path, target)
        except OSError as exc:
            self.fail('error.rename_title', t('error.rename', name=clip.name,
                                              error=exc.strerror or str(exc)))
            return
        log.info("renamed %s to %s", clip.path, target)
        self.selected = target
        self.event(self.live)
        self.refresh_library(force=True)

    def delete(self) -> None:
        clip = self.current()
        if clip is None:
            return
        if not self.ask(t('delete.title'), t('delete.message', name=os.path.basename(clip.path)),
                        parent=self.root):
            return
        try:
            trash.trash(clip.path)
        except (OSError, trash.NoTrash) as exc:
            # never delete for good: if the trash can't take it, the file stays
            self.fail('error.delete_title', t('error.delete', name=clip.name,
                                              error=getattr(exc, 'strerror', None) or str(exc)))
            return
        log.info("moved to the trash: %s", clip.path)
        self.set_status('status.trashed', name=clip.name)
        self.selected = None
        self.refresh_library(force=True)

    # ── trim ──

    def trim(self) -> None:
        clip = self.current()
        if clip is None or (self.trim_window is not None and self.trim_window.winfo_exists()):
            return
        info = clipfile.probe(clip.path)
        length = float(info.get('duration') or 0)
        if length < MIN_TRIM * 2:
            self.fail('error.trim_title', t('error.trim_unreadable', name=clip.name))
            return
        px = self.px
        win = tk.Toplevel(self.root)
        self.trim_window = win
        win.title(t('trim.title'))
        win.configure(bg=T["bg"])
        win.transient(self.root)
        tk.Label(win, text=clip.name, bg=T["bg"], fg=T["text"], font=self.f_title, anchor="w",
                 wraplength=px(480), justify="left").pack(fill="x", padx=px(16), pady=(px(14), px(8)))
        start = tk.DoubleVar(value=0.0)
        end = tk.DoubleVar(value=round(length, 1))
        summary = tk.Label(win, text="", bg=T["bg"], fg=T["accent"], font=self.f_body, anchor="w")

        def refresh(_v=None):
            s, e = start.get(), end.get()
            summary.config(text=t('trim.summary', start=time_text(s), end=time_text(e),
                                  length=duration_text(max(0.0, e - s))),
                           fg=T["accent"] if e - s >= MIN_TRIM else T["pink"])

        for label, var in ((t('trim.start'), start), (t('trim.end'), end)):
            tk.Label(win, text=label.upper(), bg=T["bg"], fg=T["muted"], font=self.f_label,
                     anchor="w").pack(fill="x", padx=px(16), pady=(px(6), 0))
            tk.Scale(win, variable=var, from_=0.0, to=round(length, 1), resolution=0.1,
                     orient="horizontal", length=px(480), showvalue=False, command=refresh,
                     bg=T["bg"], fg=T["text"], troughcolor=T["panel2"],
                     activebackground=T["accent"], highlightthickness=0, bd=0,
                     sliderrelief="flat").pack(padx=px(16))
        summary.pack(fill="x", padx=px(16), pady=(px(8), 0))
        tk.Label(win, text=t('trim.note'), bg=T["bg"], fg=T["muted"], font=self.f_small,
                 anchor="w", justify="left", wraplength=px(480)).pack(fill="x", padx=px(16),
                                                                       pady=(px(4), px(10)))
        row = tk.Frame(win, bg=T["bg"])
        row.pack(fill="x", padx=px(16), pady=(0, px(14)))

        def go():
            s, e = start.get(), end.get()
            if e - s < MIN_TRIM:
                refresh()
                return
            win.destroy()
            self.do_trim(clip, s, e)

        WolkButton(row, t('trim.save'), go, self.f_label, variant="primary").pack(side="left")
        WolkButton(row, t('button.cancel'), win.destroy, self.f_label).pack(side="left",
                                                                            padx=(px(8), 0))
        refresh()
        self.trim_start, self.trim_end = start, end

    def do_trim(self, clip: library.Clip, start: float, end: float) -> None:
        """Cut without re-encoding, on a thread; the result is a new file next to the clip."""
        dst = library.trimmed_name(os.path.dirname(clip.path), clip.name)
        self.set_status('status.trimming')

        def work():
            try:
                clipfile.trim_clip(clip.path, dst, start, end)
                error = None
            except (clipfile.ClipError, OSError) as exc:
                error = str(exc)
            self.inbox.put(lambda: self._trimmed(dst, error))
        threading.Thread(target=work, daemon=True).start()

    def _trimmed(self, dst: str, error: Optional[str]) -> None:
        if error:
            try:
                os.remove(dst)
            except OSError:
                pass
            self.fail('error.trim_title', t('error.trim', error=error))
            return
        self.event(self.live, strong=True)
        self.set_status('status.saved', name=os.path.basename(dst))
        self.selected = dst
        self.refresh_library(force=True)

    # ── errors, timer, closing ──

    def fail(self, title_key: str, message: str, *targets) -> None:
        self.set_status('status.error', T["pink"])
        self.event(*targets, strong=True)
        self.error(t(title_key), message, parent=self.root)

    def _tick(self):
        if self.closed:
            return
        try:
            while True:
                try:
                    job = self.inbox.get_nowait()
                except queue.Empty:
                    break
                job()
            now = time.monotonic()
            if self.poll and not self.asking and now >= self.next_status:
                self.asking = True
                self.next_status = now + STATUS_EVERY
                self._to_service('status', timeout=3.0)
            if now >= self.next_library:
                self.next_library = now + LIBRARY_EVERY
                self.refresh_library()
        except tk.TclError:
            pass
        except Exception:                          # noqa: BLE001 - keep the window alive
            log.exception("tick failed")
        self.tick_job = self.root.after(TICK_MS, self._tick)

    def run(self):
        self.root.mainloop()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.jobs.put(None)
        try:
            self.root.after_cancel(self.tick_job)
        except (tk.TclError, AttributeError):
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
