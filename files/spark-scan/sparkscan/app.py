"""The window: the scanner and its settings on the left, the preview or a page in the middle,
the pages of the document on the right. Everything slow (finding scanners, asking a scanner
what it offers, scanning, saving, OCR) runs in a worker thread; the window only polls for
results while one is running, so it uses no CPU when idle."""

import base64
import io
import os
import queue
import re
import shutil
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from PIL import Image

from . import (APP_CLASS, APP_ID, APP_NAME, APP_SLUG, DPI_CHOICES, FORMATS, MODES, VERSION)
from . import adjust
from .core import (Tesseract, language_label, load_config, log, new_session_dir, open_folder,
                   page_paths, reduced_motion, save_config, scan_name, scans_dir, short_path,
                   unique_path)
from .document import Cancelled, Page, SaveError, save_images, save_ocr_pdf, save_pdf
from .scanner import Caps, Device, Request, ScanError, list_devices, query_caps
from .text import decimal, pages_word, t
from .widgets import (T, Glitch, GlitchPanel, GlitchText, IconButton, Mark, Segmented, Slider,
                      Strip, Toggle, WolkButton, pick_mono)
from .work import THUMB_SIZE, Session, edited_view, prepare, straighten, view_image, whiten

try:
    from PIL import ImageTk
except ImportError:          # python3-pillow-tk missing: Tk reads PNG data itself
    ImageTk = None

POLL_MS = 60
HANDLE = 7                   # crop corner handle, px before scaling


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_SCAN_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    if os.name != 'nt' and shutil.which('xrdb'):
        try:
            out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True,
                                 timeout=3).stdout
            match = re.search(r'^Xft\.dpi:\s*([0-9.]+)', out, re.M)
            if match:
                return max(1.0, min(4.0, float(match.group(1)) / 96))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    try:
        return max(1.0, min(4.0, root.winfo_fpixels('1i') / 96))
    except tk.TclError:
        return 1.0


def load_icon(root: tk.Misc) -> Optional[tk.PhotoImage]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (os.path.join(here, 'icons', f'{APP_SLUG}-256.png'),
                 f'/usr/share/icons/hicolor/256x256/apps/{APP_ID}.png'):
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                log.exception("could not load %s", path)
    return None


def to_photo(root: tk.Misc, image: Image.Image):
    if ImageTk is not None:
        return ImageTk.PhotoImage(image, master=root)
    buf = io.BytesIO()
    image.save(buf, format='PNG', compress_level=1)
    return tk.PhotoImage(master=root, data=base64.b64encode(buf.getvalue()).decode('ascii'))


class App:
    def __init__(self, device: Optional[str] = None):
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.icon = load_icon(self.root)
        if self.icon is not None:
            self.root.iconphoto(True, self.icon)

        cfg = load_config()
        self.cfg = cfg
        self.dpi = cfg.get('dpi') if cfg.get('dpi') in DPI_CHOICES else 300
        self.mode = cfg.get('mode') if cfg.get('mode') in MODES else 'color'
        self.fmt = cfg.get('format') if cfg.get('format') in FORMATS else 'pdf'
        self.source = cfg.get('source') if cfg.get('source') in ('glass', 'feeder',
                                                                  'duplex') else 'glass'
        self.ocr_on = bool(cfg.get('ocr', False))
        self.tesseract = Tesseract()
        self.ocr_choices: List[str] = []
        self.ocr_lang = cfg.get('ocr_lang') if isinstance(cfg.get('ocr_lang'), str) else ''
        # Straighten and Whiten paper, as last set: new pages get them too
        self.straighten_new = cfg.get('straighten') is True
        self.whiten_new = cfg.get('whiten') is True

        self.devices: List[Device] = []
        self.device: Optional[str] = device or (cfg.get('device') if isinstance(
            cfg.get('device'), str) else None)
        self.device_label: str = cfg.get('device_label') if isinstance(
            cfg.get('device_label'), str) else ''
        self.caps: Dict[str, Caps] = {}
        self.listing = False
        self.asking = False

        self.session = Session(new_session_dir())
        self.pages: List[Page] = []
        self.thumbs: Dict[str, Any] = {}
        self.selected: Optional[int] = None
        self.dirty = False
        self.preview: Optional[Image.Image] = None
        self.crop: Optional[Tuple[float, float, float, float]] = None
        self.showing = 'preview'                  # or 'page'
        self.shown: Optional[Image.Image] = None  # what the view canvas shows, unscaled
        self._photo = None
        self._dim_photo = None
        self._crop_photo = None
        self._scaled: Optional[Image.Image] = None
        self._base: Optional[int] = None
        self._img_box = (0, 0, 1, 1)              # where the image sits on the canvas
        self._page_fit: Optional[Image.Image] = None   # the page turned, straightened, scaled
        self._measuring: set = set()              # pages whose angle is being measured
        self._drag: Optional[Tuple[str, Any]] = None
        self.busy: Optional[str] = None           # 'preview', 'scan', 'save'
        self.cancel_event: Optional[threading.Event] = None
        self.last_saved: Optional[str] = None
        self._queue: "queue.Queue[Tuple[Callable, tuple]]" = queue.Queue()
        self._polling = False
        self._threads = 0
        self._status_id: Optional[str] = None
        self._resize_id: Optional[str] = None
        self.closed = False

        self.glitch = Glitch(self.root, enabled=not reduced_motion()
                             and cfg.get('glitch', True) is not False)
        self._build()
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        self.root.after_idle(self._start)

    # ─── look helpers ─────────────────────────────────────────

    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size: int, bold: bool = True) -> Tuple[str, int, str]:
        return (self.mono, size, "bold" if bold else "normal")

    def tkfont(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def micro(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(parent, text=text.upper(), bg=parent.cget('bg'), fg=T["muted"],
                        font=self.font(7), anchor='w')

    # ─── building the window ──────────────────────────────────

    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.minsize(px(860), px(560))

        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK SCAN", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text=f"● {t('status.ready')}", bg=bg, fg=T["accent"],
                               font=self.font(7))
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")

        body = tk.Frame(root, bg=bg)
        body.pack(fill="both", expand=True, padx=px(12), pady=px(12))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.left = tk.Frame(body, bg=T["panel"], highlightthickness=1,
                             highlightbackground=T["line"], width=px(270))
        self.left.grid(row=0, column=0, sticky="ns")
        self.left.grid_propagate(False)
        self.left.pack_propagate(False)
        self._build_controls(self.left)

        self.middle = GlitchPanel(body, T["out_bg"])
        self.middle.grid(row=0, column=1, sticky="nsew", padx=px(10))
        self.caption = tk.Label(self.middle.inner, text="", bg=T["out_bg"], fg=T["muted"],
                                font=self.font(7), anchor="w")
        self.caption.pack(fill="x", padx=px(10), pady=(px(6), 0))
        self.view = tk.Canvas(self.middle.inner, bg=T["out_bg"], highlightthickness=0, bd=0,
                              cursor="crosshair")
        self.view.pack(fill="both", expand=True, padx=px(8), pady=px(8))
        self._build_edit_bar(self.middle.inner)
        self.view.bind("<Configure>", self._on_view_resize)
        self.view.bind("<ButtonPress-1>", self._press)
        self.view.bind("<B1-Motion>", self._motion)
        self.view.bind("<ButtonRelease-1>", self._release)
        self.view.bind("<Motion>", self._hover_cursor)

        self.right = tk.Frame(body, bg=T["panel"], highlightthickness=1,
                              highlightbackground=T["line"], width=px(200))
        self.right.grid(row=0, column=2, sticky="ns")
        self.right.grid_propagate(False)
        self.right.pack_propagate(False)
        self._build_pages(self.right)

        root.bind("<KeyPress>", self._key)
        geometry = self.cfg.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w, h = min(px(1180), int(sw * 0.85)), min(px(800), int(sh * 0.85))
            root.geometry(f"{w}x{h}")

    def _build_controls(self, box: tk.Frame):
        px, pbg = self.px, T["panel"]
        pad = dict(padx=px(14))

        self.micro(box, t('label.scanner')).pack(fill="x", pady=(px(12), px(4)), **pad)
        row = tk.Frame(box, bg=pbg)
        row.pack(fill="x", **pad)
        self.device_button = tk.Label(row, text="…", bg=T["panel2"], fg=T["text"],
                                      font=self.font(9), anchor="w", padx=px(8), pady=px(5),
                                      cursor="hand2", highlightthickness=1,
                                      highlightbackground=T["line2"], takefocus=1)
        self.device_button.pack(side="left", fill="x", expand=True)
        self.device_button.bind("<ButtonRelease-1>", lambda _e: self._device_menu())
        self.device_button.bind("<Return>", lambda _e: self._device_menu())
        self.device_button.bind("<space>", lambda _e: self._device_menu())
        self.refresh = IconButton(row, "refresh", self.look_again, px(28),
                                  tip=t('tip.look_again'))
        self.refresh.pack(side="left", padx=(px(6), 0))
        self.device_note = tk.Label(box, text="", bg=pbg, fg=T["muted"], font=self.font(8, False),
                                    justify="left", anchor="w", wraplength=px(238))
        self.device_note.pack(fill="x", pady=(px(4), 0), **pad)

        self.source_box = tk.Frame(box, bg=pbg)
        self.source_box.pack(fill="x", **pad)
        self.source_switch: Optional[Segmented] = None

        self.micro(box, t('label.resolution')).pack(fill="x", pady=(px(12), px(4)), **pad)
        self.dpi_switch = Segmented(box, [(f"{d}", str(d)) for d in DPI_CHOICES], str(self.dpi),
                                    self._set_dpi, self.font(8))
        self.dpi_switch.pack(anchor="w", **pad)
        self.micro(box, t('label.colour')).pack(fill="x", pady=(px(12), px(4)), **pad)
        self.mode_switch = Segmented(box, [(t(f'mode.{m}').upper(), m) for m in MODES],
                                     self.mode, self._set_mode, self.font(8))
        self.mode_switch.pack(anchor="w", **pad)

        self.micro(box, t('label.area')).pack(fill="x", pady=(px(12), px(4)), **pad)
        arow = tk.Frame(box, bg=pbg)
        arow.pack(fill="x", **pad)
        self.area_label = tk.Label(arow, text=t('area.whole'), bg=pbg, fg=T["text"],
                                   font=self.font(8), anchor="w")
        self.area_label.pack(side="left")
        self.whole = IconButton(arow, "crop", self.clear_crop, px(22), tip=t('button.whole'))

        brow = tk.Frame(box, bg=pbg)
        brow.pack(fill="x", pady=(px(14), 0), **pad)
        self.preview_button = WolkButton(brow, t('button.preview'), self.start_preview,
                                         self.font(9), "ghost", padx=px(10))
        self.preview_button.pack(side="left")
        self.scan_button = WolkButton(brow, t('button.scan'), self.start_scan, self.font(9),
                                      "primary", padx=px(12))
        self.scan_button.pack(side="left", padx=(px(6), 0))
        self.cancel_button = WolkButton(brow, t('button.cancel'), self.cancel, self.font(9),
                                        "danger", padx=px(12))
        self.progress = Strip(box, height=px(3))
        self.progress.configure(bg=pbg)
        self.progress_text = tk.Label(box, text="", bg=pbg, fg=T["accent"], font=self.font(8),
                                      anchor="w")
        self.message = tk.Label(box, text="", bg=pbg, fg=T["muted"], font=self.font(8, False),
                                justify="left", anchor="w", wraplength=px(238))
        self.message.pack(fill="x", pady=(px(8), 0), **pad)

        # saving, at the bottom
        save = tk.Frame(box, bg=pbg)
        save.pack(side="bottom", fill="x", pady=(0, px(12)), **pad)
        tk.Frame(save, bg=T["line"], height=1).pack(fill="x", pady=(0, px(10)))
        self.micro(save, t('label.save_as')).pack(fill="x", pady=(0, px(4)))
        self.format_switch = Segmented(save, [(f.upper(), f) for f in FORMATS], self.fmt,
                                       self._set_format, self.font(8))
        self.format_switch.pack(anchor="w")
        self.ocr_row = tk.Frame(save, bg=pbg)
        self.ocr_row.pack(fill="x", pady=(px(8), 0))
        self.ocr_toggle = Toggle(self.ocr_row, t('ocr.toggle'), self.ocr_on, self._set_ocr,
                                 self.font(8))
        self.ocr_toggle.pack(side="left")
        self.ocr_lang_box = tk.Frame(self.ocr_row, bg=pbg)
        self.ocr_lang_box.pack(side="left", padx=(px(6), 0))
        self.ocr_note = tk.Label(save, text="", bg=pbg, fg=T["dim"], font=self.font(7, False),
                                 justify="left", anchor="w", wraplength=px(238))
        self.ocr_note.pack(fill="x")
        self.save_button = WolkButton(save, t('button.save'), self.start_save, self.font(9),
                                      "primary", padx=px(12))
        self.save_button.pack(anchor="w", pady=(px(10), px(4)))
        folder_row = tk.Frame(save, bg=pbg)
        folder_row.pack(fill="x")
        self.folder_label = tk.Label(folder_row, text=t('save.to',
                                                        folder=short_path(scans_dir())),
                                     bg=pbg, fg=T["muted"], font=self.font(7, False),
                                     anchor="w", cursor="hand2")
        self.folder_label.pack(side="left")
        self.folder_label.bind("<ButtonRelease-1>", lambda _e: self.open_scans())
        self._refresh_ocr()

    def _build_pages(self, box: tk.Frame):
        px, pbg = self.px, T["panel"]
        top = tk.Frame(box, bg=pbg)
        top.pack(fill="x", padx=px(12), pady=(px(12), px(6)))
        self.pages_label = self.micro(top, t('label.pages'))
        self.pages_label.pack(side="left")
        self.clear_button = tk.Label(top, text=t('button.clear').upper(), bg=pbg,
                                     fg=T["dim"], font=self.font(7), cursor="hand2")
        self.clear_button.pack(side="right")
        self.clear_button.bind("<ButtonRelease-1>", lambda _e: self.clear_pages())

        tools = tk.Frame(box, bg=pbg)
        tools.pack(side="bottom", fill="x", padx=px(10), pady=(px(6), px(10)))
        self.up_button = IconButton(tools, "up", lambda: self.move_page(-1), px(26),
                                    tip=t('tip.up'))
        self.down_button = IconButton(tools, "down", lambda: self.move_page(1), px(26),
                                      tip=t('tip.down'))
        self.delete_button = IconButton(tools, "trash", self.delete_page, px(26),
                                        tip=t('tip.delete'))
        self.rotate_all_button = IconButton(tools, "rotate_all", self.turn_all, px(26),
                                            tip=t('tip.rotate_all'))
        for b in (self.up_button, self.down_button, self.delete_button):
            b.pack(side="left", padx=(0, px(4)))
        self.rotate_all_button.pack(side="right")

        wrap = tk.Frame(box, bg=pbg)
        wrap.pack(fill="both", expand=True, padx=(px(10), px(4)))
        self.list = tk.Canvas(wrap, bg=pbg, highlightthickness=0, bd=0)
        self.list.pack(side="left", fill="both", expand=True)
        self.list.bind("<Configure>", lambda _e: self._draw_pages())
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.list.bind(seq, self._scroll_pages)
        self.list.bind("<ButtonRelease-1>", self._click_pages)
        self._draw_pages()

    def _build_edit_bar(self, parent: tk.Frame):
        """Under the page: turn it, straighten it, whiten its paper, brightness and
        contrast. Shown while a page is shown."""
        px, pbg = self.px, T["panel"]
        bar = self.edit_bar = tk.Frame(parent, bg=pbg)
        tk.Frame(bar, bg=T["line"], height=1).pack(fill="x")
        row = tk.Frame(bar, bg=pbg)
        row.pack(fill="x", padx=px(10), pady=(px(8), 0))
        self.turn_left_button = IconButton(row, "rotate_left", lambda: self.turn(-1), px(26),
                                           tip=t('tip.rotate_left'))
        self.turn_right_button = IconButton(row, "rotate_right", lambda: self.turn(1), px(26),
                                            tip=t('tip.rotate_right'))
        self.turn_180_button = IconButton(row, "rotate_180", lambda: self.turn(2), px(26),
                                          tip=t('tip.rotate_180'))
        for b in (self.turn_left_button, self.turn_right_button, self.turn_180_button):
            b.pack(side="left", padx=(0, px(4)))
        self.straighten_toggle = Toggle(row, t('edit.straighten'), False,
                                        self.set_straighten, self.font(8))
        self.straighten_toggle.pack(side="left", padx=(px(10), 0))
        self.whiten_toggle = Toggle(row, t('edit.whiten'), False, self.set_whiten,
                                    self.font(8))
        self.whiten_toggle.pack(side="left", padx=(px(6), 0))

        tone = tk.Frame(bar, bg=pbg)
        tone.pack(fill="x", padx=px(10), pady=(px(8), 0))
        self.sliders: Dict[str, Slider] = {}
        for i, key in enumerate(('brightness', 'contrast')):
            box = tk.Frame(tone, bg=pbg)
            box.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else px(14), 0))
            self.micro(box, t(f'edit.{key}')).pack(fill="x")
            slider = Slider(box, lambda v, k=key: self.set_tone(k, v), px(150), px(20),
                            self.font(8), on_release=self._edited_thumb)
            slider.pack(fill="x")
            self.sliders[key] = slider
        foot = tk.Frame(bar, bg=pbg)
        foot.pack(fill="x", padx=px(10), pady=(px(4), px(8)))
        self.reset_button = tk.Label(foot, text=t('edit.reset').upper(), bg=pbg, fg=T["dim"],
                                     font=self.font(7), cursor="hand2")
        self.reset_button.pack(side="right", anchor="n")
        self.reset_button.bind("<ButtonRelease-1>", lambda _e: self.reset_edits())
        self.edit_note = tk.Label(foot, text="", bg=pbg, fg=T["muted"], font=self.font(7, False),
                                  anchor="w", justify="left")
        self.edit_note.pack(side="left", fill="x", expand=True)
        self.edit_note.bind("<Configure>", lambda e: self.edit_note.configure(
            wraplength=max(100, e.width - 4)))

    # ─── threads ──────────────────────────────────────────────

    def post(self, fn: Callable, *args) -> None:
        """Run fn(*args) on the Tk thread (callable from any thread)."""
        self._queue.put((fn, args))

    def spawn(self, target: Callable[[], None]) -> None:
        def run():
            try:
                target()
            except Exception as exc:          # noqa: BLE001 - shown, not swallowed
                log.exception("worker failed")
                self.post(self._unexpected, exc)
            finally:
                self.post(self._thread_done)

        self._threads += 1
        threading.Thread(target=run, daemon=True).start()
        if not self._polling:
            self._polling = True
            self.root.after(POLL_MS, self._pump)

    def _thread_done(self):
        self._threads -= 1

    def _pump(self):
        try:
            while True:
                fn, args = self._queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        if self._threads > 0 or not self._queue.empty():
            self.root.after(POLL_MS, self._pump)
        else:
            self._polling = False

    def _unexpected(self, exc: BaseException):
        self._end_busy()
        self.show_error(t('error.unexpected', detail=exc))

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.show_error(t('error.unexpected', detail=exc_value))

    # ─── status and messages ──────────────────────────────────

    def set_status(self, text: str, colour: str = T["accent"], hold_ms: int = 0):
        self.status.config(text=f"● {text}", fg=colour)
        if self._status_id:
            self.root.after_cancel(self._status_id)
            self._status_id = None
        if hold_ms:
            self._status_id = self.root.after(hold_ms, self._status_idle)

    def _status_idle(self):
        self._status_id = None
        if not self.busy:
            self.status.config(text=f"● {t('status.ready')}", fg=T["accent"])

    def say(self, text: str, colour: str = T["muted"]):
        self.message.config(text=text, fg=colour)

    def show_error(self, text: str):
        self.say(text, T["pink"])
        self.set_status(t('status.error'), T["pink"], hold_ms=5000)
        self.glitch.now(self.title, self.middle, self.mark, strong=True)

    # ─── scanners ─────────────────────────────────────────────

    def _start(self):
        self._show_device()
        self._show_view()
        if self.device:
            self._ask_caps(self.device)       # the last one: often there, and quicker
        self.look_again()

    def look_again(self):
        if self.listing:
            return
        self.listing = True
        self.refresh.set_enabled(False)
        if not self.busy:
            self.set_status(t('status.looking'))
        if not self.device or self.device not in self.caps:
            self.device_note.config(text=t('scanner.looking'), fg=T["muted"])

        def work():
            try:
                found = list_devices()
                self.post(self._got_devices, found, None)
            except ScanError as exc:
                self.post(self._got_devices, [], exc)

        self.spawn(work)

    def _got_devices(self, found: List[Device], error: Optional[ScanError]):
        self.listing = False
        self.refresh.set_enabled(True)
        self.devices = found
        if not self.busy:
            self._status_idle()
        if error is not None:
            key = {'no_scanimage': 'scanner.no_sane', 'list_timeout': 'scanner.list_timeout'
                   }.get(error.kind, 'scanner.list_failed')
            if not (self.device and self.device in self.caps):
                self.device_note.config(text=t(key, detail=error.detail or error.kind),
                                        fg=T["pink"])
                self.glitch.now(self.title, strong=True)
            return
        names = [d.name for d in found]
        if self.device in names or (self.device and self.device in self.caps):
            self._show_device()
            if self.device not in self.caps:
                self._ask_caps(self.device)
            return
        if found:
            self.choose(found[0].name)
        else:
            if self.device and not self.asking:
                self.device_note.config(text=t('scanner.not_found', name=self.device_label
                                               or self.device), fg=T["pink"])
            else:
                self.device_note.config(text=t('scanner.none'), fg=T["gold"])
            if not self.device:
                self.set_status(t('status.no_scanner'), T["gold"], hold_ms=4000)
            self._show_device()
            self._refresh_buttons()
            self._show_view()

    def _device_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=T["panel2"], fg=T["text"],
                       activebackground=T["hover"], activeforeground=T["accent"],
                       font=self.font(9, False), bd=1, relief="flat")
        if not self.devices:
            menu.add_command(label=t('scanner.none').split('.')[0] + '.', state="disabled")
        for d in self.devices:
            mark = "■ " if d.name == self.device else "  "
            menu.add_command(label=f"{mark}{d.label}   [{d.backend}]",
                             command=lambda n=d.name: self.choose(n))
        menu.add_separator()
        menu.add_command(label=t('tip.look_again'), command=self.look_again)
        x = self.device_button.winfo_rootx()
        y = self.device_button.winfo_rooty() + self.device_button.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def choose(self, name: str):
        if name != self.device:
            self.preview = None
            self.crop = None
        self.device = name
        dev = next((d for d in self.devices if d.name == name), None)
        if dev:
            self.device_label = dev.label
        self.cfg['device'], self.cfg['device_label'] = name, self.device_label
        save_config(self._settings())
        self._show_device()
        self._show_view()
        if name not in self.caps:
            self._ask_caps(name)
        else:
            self._caps_ready()

    def _ask_caps(self, name: str):
        self.asking = True
        self._refresh_buttons()
        if not self.busy:
            self.set_status(t('status.connecting'))

        def work():
            try:
                caps = query_caps(name)
                self.post(self._got_caps, name, caps, None)
            except ScanError as exc:
                self.post(self._got_caps, name, None, exc)

        self.spawn(work)

    def _got_caps(self, name: str, caps: Optional[Caps], error: Optional[ScanError]):
        self.asking = False
        if caps is not None:
            self.caps[name] = caps
        if name != self.device:
            return
        if not self.busy:
            self._status_idle()
        if error is not None:
            if not self.listing:
                self.device_note.config(text=t('scanner.not_found', name=self.device_label
                                               or name), fg=T["pink"])
                self.glitch.now(self.title, strong=True)
            log.info("%s: %s %s", name, error.kind, error.detail)
            self._refresh_buttons()
            return
        self._caps_ready()

    def _caps_ready(self):
        caps = self.caps.get(self.device or '')
        self.device_note.config(text=self._device_kind(), fg=T["dim"])
        for child in self.source_box.winfo_children():
            child.destroy()
        self.source_switch = None
        if caps and len(caps.sources) > 1:
            if self.source not in caps.sources:
                self.source = caps.source_default if caps.source_default in caps.sources \
                    else next(iter(caps.sources))
            self.micro(self.source_box, t('label.source')).pack(fill="x", pady=(self.px(12),
                                                                              self.px(4)))
            order = [s for s in ('glass', 'feeder', 'duplex') if s in caps.sources]
            self.source_switch = Segmented(self.source_box,
                                           [(t(f'source.{s}').upper(), s) for s in order],
                                           self.source, self._set_source, self.font(8))
            self.source_switch.pack(anchor="w")
        self._refresh_buttons()
        self._show_area()
        self._show_view()

    def _device_kind(self) -> str:
        dev = next((d for d in self.devices if d.name == self.device), None)
        backend = (self.device or '').split(':', 1)[0]
        kind = dev.kind if dev and dev.kind else ''
        how = t('scanner.network') if backend in ('airscan', 'escl', 'net') or \
            'network' in kind.lower() or re.search(r'\d+\.\d+\.\d+\.\d+|bjnp|_IP', self.device
                                                   or '') else ''
        return ' · '.join(p for p in (backend, how) if p)

    def _show_device(self):
        if self.device:
            dev = next((d for d in self.devices if d.name == self.device), None)
            label = dev.label if dev else (self.device_label or self.device)
        else:
            label = t('scanner.pick')
        self.device_button.config(text=f"{label}  ▾")

    def current_caps(self) -> Optional[Caps]:
        return self.caps.get(self.device or '')

    def feeder(self) -> bool:
        caps = self.current_caps()
        return bool(caps and self.source in ('feeder', 'duplex') and self.source in caps.sources)

    # ─── settings ─────────────────────────────────────────────

    def _set_dpi(self, value: str):
        self.dpi = int(value)
        save_config(self._settings())

    def _set_mode(self, value: str):
        self.mode = value
        save_config(self._settings())

    def _set_source(self, value: str):
        self.source = value
        save_config(self._settings())
        self._refresh_buttons()
        self._show_area()
        self._show_view()

    def _set_format(self, value: str):
        self.fmt = value
        save_config(self._settings())
        self._refresh_ocr()

    def _set_ocr(self, on: bool):
        self.ocr_on = on
        save_config(self._settings())
        self._refresh_ocr()

    def _set_ocr_lang(self, value: str):
        self.ocr_lang = value
        save_config(self._settings())

    def _refresh_ocr(self):
        for child in self.ocr_lang_box.winfo_children():
            child.destroy()
        if not self.tesseract.found:
            self.ocr_toggle.set(False)
            self.ocr_toggle.pack_forget()
            self.ocr_note.config(text=t('ocr.missing'))
            return
        self.ocr_choices = self.tesseract.language_choices()
        if not self.ocr_choices:
            self.ocr_toggle.pack_forget()
            self.ocr_note.config(text=t('ocr.no_lang'))
            return
        if self.ocr_lang not in self.ocr_choices:
            self.ocr_lang = self.ocr_choices[0]
        if not self.ocr_toggle.winfo_manager():
            self.ocr_toggle.pack(side="left", before=self.ocr_lang_box)
        if self.fmt != 'pdf':
            self.ocr_toggle.set(False)
            self.ocr_note.config(text=t('ocr.pdf_only'))
            return
        self.ocr_toggle.set(self.ocr_on)
        self.ocr_note.config(text="")
        if self.ocr_on and len(self.ocr_choices) > 1:
            Segmented(self.ocr_lang_box, [(language_label(c), c) for c in self.ocr_choices],
                      self.ocr_lang, self._set_ocr_lang, self.font(7)).pack(side="left")

    def _settings(self) -> Dict[str, Any]:
        self.cfg.update(dpi=self.dpi, mode=self.mode, format=self.fmt, source=self.source,
                        ocr=self.ocr_on, ocr_lang=self.ocr_lang, straighten=self.straighten_new,
                        whiten=self.whiten_new, version=VERSION)
        if self.device:
            self.cfg.update(device=self.device, device_label=self.device_label)
        return self.cfg

    # ─── buttons ──────────────────────────────────────────────

    def _refresh_buttons(self):
        ready = self.current_caps() is not None and not self.busy
        self.scan_button.set_enabled(ready)
        self.scan_button.set_text(t('button.scan_feeder') if self.feeder() else t('button.scan'))
        self.preview_button.set_enabled(ready and not self.feeder())
        has_pages = bool(self.pages) and not self.busy
        self.save_button.set_enabled(has_pages)
        self.save_button.set_text(t('button.save_n', n=len(self.pages)) if len(self.pages) > 1
                                  else t('button.save'))
        sel = self.selected is not None and not self.busy
        self.up_button.set_enabled(sel and self.selected > 0)
        self.down_button.set_enabled(sel and self.selected < len(self.pages) - 1)
        self.delete_button.set_enabled(sel)
        self.rotate_all_button.set_enabled(has_pages)
        self._sync_edit_bar()
        self.clear_button.config(fg=T["muted"] if has_pages else T["dim"])
        self.pages_label.config(text=(t('label.pages') + (f"  {len(self.pages)}" if self.pages
                                                          else '')).upper())

    def _begin_busy(self, kind: str):
        self.busy = kind
        self.cancel_event = threading.Event()
        self.preview_button.pack_forget()
        self.scan_button.pack_forget()
        self.cancel_button.pack(side="left")
        self.cancel_button.set_enabled(True)
        self.progress.pack(fill="x", padx=self.px(14), pady=(self.px(10), 0),
                           before=self.message)
        self.progress_text.pack(fill="x", padx=self.px(14), pady=(self.px(4), 0),
                                before=self.message)
        self.progress.draw(fraction=0.0)
        self.say("")
        self._refresh_buttons()

    def _end_busy(self):
        self.busy = None
        self.cancel_event = None
        self.cancel_button.pack_forget()
        self.preview_button.pack(side="left")
        self.scan_button.pack(side="left", padx=(self.px(6), 0))
        self.progress.pack_forget()
        self.progress_text.pack_forget()
        self._refresh_buttons()

    def _progress(self, fraction: float, text: str):
        self.progress.draw(fraction=fraction)
        self.progress_text.config(text=text)
        self.set_status(text)

    def cancel(self):
        if not self.busy:
            return
        if self.cancel_event:
            self.cancel_event.set()
        self.session.cancel()
        self.cancel_button.set_enabled(False)
        self.set_status(t('status.cancelling'), T["gold"])

    # ─── preview and scan ─────────────────────────────────────

    def start_preview(self):
        caps = self.current_caps()
        if not caps or self.busy or self.feeder():
            return
        self._begin_busy('preview')
        self._progress(0.0, t('status.previewing', pct=''))
        mode = 'color' if 'color' in caps.modes else 'gray'

        def on_progress(fraction: float, _page: int):
            self.post(self._progress, fraction, t('status.previewing',
                                                  pct=f"{int(fraction * 100)}%"))

        def work():
            try:
                image = self.session.preview(caps, mode, on_progress)
                self.post(self._preview_done, image, None)
            except ScanError as exc:
                self.post(self._preview_done, None, exc)

        self.spawn(work)

    def _preview_done(self, image: Optional[Image.Image], error: Optional[ScanError]):
        self._end_busy()
        if error is not None:
            self.scan_failed(error)
            return
        if image is None:
            self.say(t('done.cancelled'))
            self._status_idle()
            return
        self.preview = image
        self.showing = 'preview'
        self.selected = None
        self._show_view()
        self._draw_pages()
        self._refresh_buttons()
        self.set_status(t('status.ready'))
        self.glitch.now(self.middle)

    def start_scan(self):
        caps = self.current_caps()
        if not caps or self.busy or not self.device:
            return
        feeder = self.feeder()
        req = Request(self.device, self.dpi, self.mode,
                      area=None if feeder else self.crop,
                      source=self.source if self.source in caps.sources else
                      ('glass' if 'glass' in caps.sources else ''))
        self._begin_busy('scan')
        self._progress(0.0, t('status.scanning', pct=''))
        before = len(self.pages)

        def on_progress(fraction: float, page: int):
            text = t('status.scanning_page', n=before + page, pct=f"{int(fraction * 100)}%") \
                if feeder else t('status.scanning', pct=f"{int(fraction * 100)}%")
            self.post(self._progress, fraction, text)

        straighten_new, whiten_new = self.straighten_new, self.whiten_new

        def on_page(page: Page):
            prepare(page, straighten_new, whiten_new)
            thumb = self._make_thumb(page)
            self.post(self._add_page, page, thumb)

        def work():
            try:
                pages = self.session.scan(caps, req, on_progress, on_page)
                self.post(self._scan_done, pages, None, feeder)
            except ScanError as exc:
                self.post(self._scan_done, [], exc, feeder)

        self.spawn(work)

    @staticmethod
    def _make_thumb(page: Page) -> Image.Image:
        image = edited_view(page)
        image.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
        return image

    def _add_page(self, page: Page, thumb: Image.Image):
        self.pages.append(page)
        self.thumbs[page.path] = to_photo(self.root, thumb)
        self.dirty = True
        self.selected = len(self.pages) - 1
        self.showing = 'page'
        self._show_view()
        self._draw_pages(scroll_to_end=True)
        self._refresh_buttons()

    def _scan_done(self, pages: List[Page], error: Optional[ScanError], feeder: bool):
        cancelled = bool(self.cancel_event and self.cancel_event.is_set())
        self._end_busy()
        if error is not None:
            self.scan_failed(error)
            return
        if cancelled:
            self.say(t('done.feeder_partial', n=len(pages)) if pages else t('done.cancelled'))
            self._status_idle()
            return
        if not pages:
            self._status_idle()
            return
        self.say(t('done.page', n=len(self.pages)) if len(pages) == 1
                 else t('done.pages', n=len(pages)), T["accent"])
        self.set_status(t('status.ready'))
        self.glitch.now(self.middle, self.strip)

    def scan_failed(self, error: ScanError):
        key = f"error.{error.kind}"
        text = t(key) if t(key) != key else t('error.failed')
        if error.detail and error.kind in ('failed', 'io', 'open_failed', 'list_failed'):
            text += "\n" + t('error.detail', detail=error.detail)
        log.warning("scan failed: %s %s", error.kind, error.detail)
        self.show_error(text)

    # ─── pages ────────────────────────────────────────────────

    def _draw_pages(self, scroll_to_end: bool = False):
        c = self.list
        c.delete("all")
        px = self.px
        width = max(1, c.winfo_width())
        if not self.pages:
            c.create_text(px(4), px(8), text=t('pages.none'), anchor="nw", fill=T["dim"],
                          font=self.font(8, False))
            c.configure(scrollregion=(0, 0, width, 1))
            return
        y = px(4)
        self._rows: List[Tuple[int, int]] = []
        for i, page in enumerate(self.pages):
            photo = self.thumbs.get(page.path)
            h = photo.height() if photo else px(100)
            w = photo.width() if photo else px(80)
            top = y
            sel = i == self.selected and self.showing == 'page'
            x = px(22) + max(0, (width - px(26) - w) // 2)
            if sel:
                c.create_rectangle(x - 4, top - 2, x + w + 2, top + h + 2, outline=T["ch_a"],
                                   width=1)
                c.create_rectangle(x - 2, top - 2, x + w + 4, top + h + 2, outline=T["ch_b"],
                                   width=1)
                c.create_rectangle(x - 3, top - 3, x + w + 3, top + h + 3, outline=T["accent"],
                                   width=2)
            if photo:
                c.create_image(x, top, image=photo, anchor="nw")
            else:
                c.create_rectangle(x, top, x + w, top + h, outline=T["line2"])
            c.create_text(px(2), top, text=f"{i + 1}", anchor="nw",
                          fill=T["accent"] if sel else T["muted"], font=self.font(8))
            y = top + h + px(12)
            self._rows.append((top, y))
        c.configure(scrollregion=(0, 0, width, y))
        if scroll_to_end:
            c.yview_moveto(1.0)

    def _scroll_pages(self, event):
        if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0:
            self.list.yview_scroll(-1, "units")
        else:
            self.list.yview_scroll(1, "units")

    def _click_pages(self, event):
        y = self.list.canvasy(event.y)
        for i, (top, bottom) in enumerate(getattr(self, '_rows', [])):
            if top <= y < bottom:
                self.select_page(i)
                return

    def select_page(self, i: Optional[int]):
        if i is None or not (0 <= i < len(self.pages)):
            self.selected = None
            self.showing = 'preview'
        else:
            self.selected = i
            self.showing = 'page'
        self._show_view()
        self._draw_pages()
        self._refresh_buttons()

    def move_page(self, step: int):
        i = self.selected
        if i is None or self.busy:
            return
        j = i + step
        if not 0 <= j < len(self.pages):
            return
        self.pages[i], self.pages[j] = self.pages[j], self.pages[i]
        self.selected = j
        self.dirty = True
        self._draw_pages()
        self._show_view()
        self._refresh_buttons()

    def delete_page(self):
        i = self.selected
        if i is None or self.busy:
            return
        page = self.pages.pop(i)
        self.thumbs.pop(page.path, None)
        page.discard()
        self.dirty = bool(self.pages)
        if self.pages:
            self.selected = min(i, len(self.pages) - 1)
        else:
            self.selected = None
            self.showing = 'preview'
        self._draw_pages()
        self._show_view()
        self._refresh_buttons()
        self.glitch.now(self.middle)

    def clear_pages(self, ask: bool = True):
        if not self.pages or self.busy:
            return
        if ask and self.dirty and not messagebox.askyesno(
                t('clear.title'), t('clear.confirm', pages=pages_word(len(self.pages))),
                parent=self.root):
            return
        for page in self.pages:
            page.discard()
        self.pages.clear()
        self.thumbs.clear()
        self.selected = None
        self.showing = 'preview'
        self.dirty = False
        self._draw_pages()
        self._show_view()
        self._refresh_buttons()
        self.glitch.now(self.middle)

    # ─── changing a page ──────────────────────────────────────

    def current_page(self) -> Optional[Page]:
        if self.showing == 'page' and self.selected is not None and \
                self.selected < len(self.pages):
            return self.pages[self.selected]
        return None

    def _can_edit(self) -> bool:
        # while saving, the pages are being read in the background
        return self.busy != 'save'

    def turn(self, quarters: int):
        """Turn the shown page: 1 right, -1 left, 2 upside down."""
        page = self.current_page()
        if page is None or not self._can_edit():
            return
        page.edits.turn = (page.edits.turn + quarters) % 4
        self._edited(page, geometry=True)

    def turn_all(self):
        """Turn every page a quarter turn right (twice for pages that came out upside
        down)."""
        if not self.pages or not self._can_edit():
            return
        for page in self.pages:
            page.edits.turn = (page.edits.turn + 1) % 4
            self._refresh_thumb(page, draw=False)
        self.dirty = True
        self._draw_pages()
        if self.current_page() is not None:
            self._show_view()
        self.say(t('done.turned_all', pages=pages_word(len(self.pages))), T["accent"])
        self.glitch.now(self.middle)

    def set_straighten(self, on: bool):
        page = self.current_page()
        self.straighten_new = on
        if page is None or not self._can_edit():
            self._sync_edit_bar()
            return
        if on and not page.measured:
            # measuring takes about 0.2 s on a big page: not on the Tk thread
            key = id(page)
            if key in self._measuring:
                return
            self._measuring.add(key)
            self._sync_edit_bar()

            def work():
                try:
                    straighten(page, True)
                finally:
                    self.post(self._measured, page)

            self.spawn(work)
            return
        straighten(page, on)
        self._edited(page, geometry=True)

    def _measured(self, page: Page):
        self._measuring.discard(id(page))
        if self.closed or not any(p is page for p in self.pages):
            return
        # it may have been turned off again while it was measuring
        straighten(page, self.straighten_new)
        self._edited(page, geometry=True)

    def set_whiten(self, on: bool):
        page = self.current_page()
        self.whiten_new = on
        if page is None or not self._can_edit() or page.mode == 'bw':
            self._sync_edit_bar()
            return
        whiten(page, on)
        self._edited(page)

    def set_tone(self, key: str, value: int):
        """A brightness or contrast slider moved: only the tone of the shown page is redone,
        on the copy already scaled to the view, so it follows the drag."""
        page = self.current_page()
        if page is None or not self._can_edit() or page.mode == 'bw':
            return
        setattr(page.edits, key, int(value))
        self.dirty = True
        self._retone()
        self.reset_button.config(fg=T["muted"] if page.edits.any() else T["dim"])

    def reset_edits(self):
        page = self.current_page()
        if page is None or not self._can_edit() or not page.edits.any():
            return
        page.edits = adjust.Edits(angle=page.skew or 0.0)
        self._edited(page, geometry=True)

    def _edited(self, page: Page, geometry: bool = False):
        self.dirty = True
        self._refresh_thumb(page)
        if page is self.current_page():
            if geometry:
                self._show_view()
            else:
                self._retone()
        self._sync_edit_bar()

    def _edited_thumb(self):
        page = self.current_page()
        if page is not None:
            self._refresh_thumb(page)

    def _refresh_thumb(self, page: Page, draw: bool = True):
        try:
            self.thumbs[page.path] = to_photo(self.root, self._make_thumb(page))
        except OSError:
            log.exception("could not redraw the thumbnail of %s", page.path)
        if draw:
            self._draw_pages()

    def _retone(self):
        page = self.current_page()
        if page is None or self._page_fit is None or self._base is None:
            return
        self._scaled = adjust.apply_tone(self._page_fit, page.edits)
        self._photo = to_photo(self.root, self._scaled)
        self.view.itemconfigure(self._base, image=self._photo)

    def _sync_edit_bar(self):
        """Show the shown page's edits in the bar."""
        page = self.current_page()
        if page is None:
            return
        editable = self._can_edit()
        bw = page.mode == 'bw'
        for b in (self.turn_left_button, self.turn_right_button, self.turn_180_button):
            b.set_enabled(editable)
        self.straighten_toggle.set(page.edits.straighten)
        self.whiten_toggle.set(bool(page.edits.levels))
        for key, slider in self.sliders.items():
            slider.set(getattr(page.edits, key))
            slider.set_enabled(editable and not bw)
        self.reset_button.config(fg=T["muted"] if page.edits.any() and editable else T["dim"])
        if id(page) in self._measuring:
            note = t('edit.measuring')
        elif page.edits.straighten and abs(page.skew or 0.0) >= 0.05:
            note = t('edit.straightened', angle=decimal(abs(page.skew or 0.0)))
        elif page.edits.straighten:
            note = t('edit.straight')
        elif page.measured and page.skew is None and self.straighten_new:
            note = t('edit.no_lines')
        elif bw:
            note = t('edit.bw')
        else:
            note = ''
        self.edit_note.config(text=note)

    # ─── the middle: preview with crop, or a page ─────────────

    def _show_area(self):
        if self.feeder():
            self.area_label.config(text=t('area.feeder'))
            self.whole.pack_forget()
            return
        caps = self.current_caps()
        if self.crop and caps and caps.area:
            width, height = caps.area['x'][1], caps.area['y'][1]
            if caps.area_unit == 'mm':
                w = round((self.crop[2] - self.crop[0]) * width)
                h = round((self.crop[3] - self.crop[1]) * height)
                self.area_label.config(text=t('area.part', w=w, h=h))
            else:
                self.area_label.config(text=f"{round((self.crop[2] - self.crop[0]) * 100)} × "
                                            f"{round((self.crop[3] - self.crop[1]) * 100)} %")
        elif self.crop:
            self.area_label.config(text=f"{round((self.crop[2] - self.crop[0]) * 100)} × "
                                        f"{round((self.crop[3] - self.crop[1]) * 100)} %")
        else:
            self.area_label.config(text=t('area.whole'))
        if self.crop:
            if not self.whole.winfo_ismapped():
                self.whole.pack(side="left", padx=(self.px(8), 0))
        else:
            self.whole.pack_forget()

    def clear_crop(self):
        self.crop = None
        self._show_area()
        self._draw_view()

    def _on_view_resize(self, _event=None):
        if self.closed:
            return
        if self._resize_id:
            self.root.after_cancel(self._resize_id)
        self._resize_id = self.root.after(90, self._draw_view)

    def _show_view(self):
        """Decide what the middle shows, and load it."""
        if self.showing == 'page' and self.selected is not None and self.selected < len(
                self.pages):
            page = self.pages[self.selected]
            try:
                self.shown = view_image(page)
            except OSError:
                log.exception("could not show %s", page.path)
                self.shown = None
            w_mm, h_mm = page.size_mm
            self.caption.config(text=t('view.page', n=self.selected + 1, count=len(self.pages),
                                       dpi=round(page.dpi), w=round(w_mm), h=round(h_mm)),
                                fg=T["muted"])
            self.view.configure(cursor="arrow")
            if not self.edit_bar.winfo_ismapped():
                self.edit_bar.pack(side="bottom", fill="x", before=self.view)
            self._sync_edit_bar()
        else:
            self.showing = 'preview'
            self.edit_bar.pack_forget()
            self.shown = self.preview
            if self.preview is not None:
                self.caption.config(text=t('view.preview_crop') if self.crop else
                                    t('view.preview'), fg=T["muted"])
            else:
                self.caption.config(text="")
            self.view.configure(cursor="crosshair" if self.preview is not None else "arrow")
        self._draw_view()

    def _draw_view(self):
        self._resize_id = None
        c = self.view
        c.delete("all")
        cw, ch = max(1, c.winfo_width()), max(1, c.winfo_height())
        if self.shown is None:
            if self.feeder():
                text = t('view.feeder')
            elif self.current_caps() is None:
                text = ''
            else:
                text = t('view.empty')
            c.create_text(cw // 2, ch // 2, text=text, fill=T["dim"], font=self.font(9, False),
                          justify="center", width=max(100, cw - self.px(40)))
            self._photo = self._dim_photo = self._crop_photo = None
            self._base = None
            return
        page = self.current_page()
        if page is not None:
            # turned and straightened on the screen-sized copy, then toned after scaling
            self._page_fit = adjust.fit(adjust.apply_geometry(self.shown, page.edits,
                                                              fast=True), (cw, ch))
            self._scaled = adjust.apply_tone(self._page_fit, page.edits)
            w, h = self._scaled.size
        else:
            self._page_fit = None
            iw, ih = self.shown.size
            k = min(cw / iw, ch / ih)
            w, h = max(1, int(iw * k)), max(1, int(ih * k))
            self._scaled = self.shown.resize((w, h), Image.Resampling.BILINEAR if k < 1 else
                                             Image.Resampling.NEAREST).convert('RGB')
        x0, y0 = (cw - w) // 2, (ch - h) // 2
        self._photo = to_photo(self.root, self._scaled)
        self._dim_photo = None
        self._base = c.create_image(x0, y0, image=self._photo, anchor="nw")
        c.create_rectangle(x0 - 1, y0 - 1, x0 + w, y0 + h, outline=T["line2"])
        self._img_box = (x0, y0, w, h)
        if self.showing == 'preview':
            self._draw_crop()

    def _draw_crop(self):
        """The part to scan at full brightness, the rest dimmed, and its edge slipped into
        the two channels."""
        c = self.view
        c.delete("crop")
        if self.shown is None or self._base is None:
            return
        if not self.crop:
            c.itemconfigure(self._base, image=self._photo)
            return
        if self._dim_photo is None:
            dim = Image.blend(self._scaled, Image.new('RGB', self._scaled.size, T["bg"]), 0.62)
            self._dim_photo = to_photo(self.root, dim)
        c.itemconfigure(self._base, image=self._dim_photo)
        x0, y0, w, h = self._img_box
        a = self.crop
        box = (int(a[0] * w), int(a[1] * h), max(int(a[0] * w) + 1, int(a[2] * w)),
               max(int(a[1] * h) + 1, int(a[3] * h)))
        self._crop_photo = to_photo(self.root, self._scaled.crop(box))
        c.create_image(x0 + box[0], y0 + box[1], image=self._crop_photo, anchor="nw",
                       tags="crop")
        l, tp, r, b = x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]
        c.create_rectangle(l - 3, tp, r - 3, b, outline=T["ch_a"], width=1, tags="crop")
        c.create_rectangle(l + 3, tp, r + 3, b, outline=T["ch_b"], width=1, tags="crop")
        c.create_rectangle(l, tp, r, b, outline=T["accent"], width=2, tags="crop")
        hs = self.px(HANDLE) / 2
        for cx, cy in ((l, tp), (r, tp), (l, b), (r, b)):
            c.create_rectangle(cx - hs, cy - hs, cx + hs, cy + hs, fill=T["accent"],
                               outline=T["on_accent"], tags="crop")

    def _frac(self, x: float, y: float) -> Tuple[float, float]:
        x0, y0, w, h = self._img_box
        return (max(0.0, min(1.0, (x - x0) / w)), max(0.0, min(1.0, (y - y0) / h)))

    def _corner_at(self, x: float, y: float) -> Optional[Tuple[float, float]]:
        """The opposite corner (as fractions) if (x, y) is on a crop corner handle."""
        if not self.crop:
            return None
        x0, y0, w, h = self._img_box
        a = self.crop
        reach = self.px(HANDLE) + 3
        for cx, cy, ox, oy in ((a[0], a[1], a[2], a[3]), (a[2], a[1], a[0], a[3]),
                               (a[0], a[3], a[2], a[1]), (a[2], a[3], a[0], a[1])):
            if abs(x0 + cx * w - x) <= reach and abs(y0 + cy * h - y) <= reach:
                return (ox, oy)
        return None

    def _inside_crop(self, x: float, y: float) -> bool:
        if not self.crop:
            return False
        fx, fy = self._frac(x, y)
        return self.crop[0] < fx < self.crop[2] and self.crop[1] < fy < self.crop[3]

    def _hover_cursor(self, event):
        if self.showing != 'preview' or self.preview is None:
            return
        if self._corner_at(event.x, event.y):
            cursor = "sizing"
        elif self._inside_crop(event.x, event.y):
            cursor = "fleur"
        else:
            cursor = "crosshair"
        if str(self.view.cget("cursor")) != cursor:
            self.view.configure(cursor=cursor)

    def _press(self, event):
        if self.showing != 'preview' or self.preview is None or self.busy:
            self._drag = None
            return
        corner = self._corner_at(event.x, event.y)
        if corner:
            self._drag = ('resize', corner)
        elif self._inside_crop(event.x, event.y):
            self._drag = ('move', (self._frac(event.x, event.y), self.crop))
        else:
            self._drag = ('new', self._frac(event.x, event.y))

    def _motion(self, event):
        if not self._drag:
            return
        kind, data = self._drag
        fx, fy = self._frac(event.x, event.y)
        if kind in ('new', 'resize'):
            ax, ay = data
            self.crop = (min(ax, fx), min(ay, fy), max(ax, fx), max(ay, fy))
        else:
            (sx, sy), start = data
            w, h = start[2] - start[0], start[3] - start[1]
            nx = max(0.0, min(1.0 - w, start[0] + fx - sx))
            ny = max(0.0, min(1.0 - h, start[1] + fy - sy))
            self.crop = (nx, ny, nx + w, ny + h)
        self._draw_crop()
        self._show_area()

    def _release(self, _event):
        if not self._drag:
            return
        self._drag = None
        if self.crop:
            _x0, _y0, w, h = self._img_box
            if (self.crop[2] - self.crop[0]) * w < self.px(10) or \
                    (self.crop[3] - self.crop[1]) * h < self.px(10):
                self.crop = None             # a click, not a drag: the whole glass
        self._draw_view()
        self._show_area()
        self.caption.config(text=t('view.preview_crop') if self.crop else t('view.preview'))

    # ─── saving ───────────────────────────────────────────────

    def start_save(self):
        if not self.pages or self.busy:
            return
        pages = list(self.pages)
        folder = scans_dir()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            self.show_error(t('error.save', detail=exc))
            return
        stem = scan_name(t('file.scan'))
        ocr = self.fmt == 'pdf' and self.ocr_on and self.tesseract.found and \
            bool(self.ocr_choices)
        lang = self.ocr_lang or 'eng'
        fmt = self.fmt
        self._begin_busy('save')
        self._progress(0.0, t('status.reading' if ocr else 'status.saving', pages=''))
        cancel = self.cancel_event

        def progress(fraction: float, which: str):
            self.post(self._progress, fraction,
                      t('status.reading' if ocr else 'status.saving', pages=which))

        def work():
            try:
                if fmt == 'pdf':
                    path = unique_path(folder, stem, 'pdf')
                    if ocr:
                        save_ocr_pdf(pages, path, lang, self.tesseract, self.session.folder,
                                     progress, cancel)
                    else:
                        save_pdf(pages, path, os.path.splitext(os.path.basename(path))[0],
                                 progress, cancel)
                    done = [path]
                else:
                    paths = page_paths(folder, stem, fmt, len(pages), t('file.page'))
                    done = save_images(pages, paths, fmt, progress, cancel)
                self.post(self._save_done, done, None)
            except Cancelled:
                self.post(self._save_done, [], None)
            except (OSError, SaveError) as exc:
                self.post(self._save_done, [], exc)

        self.spawn(work)

    def _save_done(self, paths: List[str], error: Optional[BaseException]):
        self._end_busy()
        if error is not None:
            log.error("save failed: %s", error)
            self.show_error(t('error.save', detail=error))
            return
        if not paths:
            self.say(t('done.cancelled'))
            self._status_idle()
            return
        self.dirty = False
        self.last_saved = paths[0]
        name = os.path.basename(paths[0])
        log.info("saved %s", ', '.join(paths))
        self.say(t('done.saved', name=name) if len(paths) == 1 else
                 t('done.saved_n', n=len(paths), name=name), T["accent"])
        self.set_status(t('status.saved'), hold_ms=4000)
        self.folder_label.config(text=t('button.open_folder').upper() + " →  " +
                                 short_path(os.path.dirname(paths[0])), fg=T["accent"])
        self.glitch.now(self.title, self.middle, self.strip)

    def open_scans(self):
        folder = os.path.dirname(self.last_saved) if self.last_saved else scans_dir()
        os.makedirs(folder, exist_ok=True)
        problem = open_folder(folder)
        if problem:
            self.show_error(problem)

    # ─── keys, closing ────────────────────────────────────────

    def _key(self, event):
        k = event.keysym
        ctrl = bool(event.state & 0x4)
        alt = bool(event.state & 0x8) or bool(event.state & 0x80)
        if ctrl and k in ('Return', 'KP_Enter'):
            self.start_scan()
        elif ctrl and k.lower() == 's':
            self.start_save()
        elif ctrl and k.lower() == 'p':
            self.start_preview()
        elif ctrl and k.lower() == 'r' and event.state & 0x1:
            self.turn_all()
        elif ctrl and k.lower() in ('r', 'l'):
            self.turn(1 if k.lower() == 'r' else -1)
        elif ctrl and k.lower() in ('w', 'q'):
            self._on_close()
        elif k == 'Escape':
            if self.busy:
                self.cancel()
            elif self.crop:
                self.clear_crop()
            elif self.showing == 'page':
                self.select_page(None)
        elif k == 'Delete' and self.selected is not None:
            self.delete_page()
        elif alt and k in ('Up', 'Down'):
            self.move_page(-1 if k == 'Up' else 1)
        elif k in ('Up', 'Down') and self.pages and not isinstance(event.widget, tk.Entry):
            i = self.selected if self.selected is not None else -1
            self.select_page(max(0, min(len(self.pages) - 1, i + (-1 if k == 'Up' else 1))))
        else:
            return None
        return "break"

    def _on_close(self):
        if self.pages and self.dirty and not messagebox.askyesno(
                t('close.title'), t('close.unsaved', pages=pages_word(len(self.pages))),
                parent=self.root):
            return
        self.close()

    def close(self):
        self.closed = True
        if self.busy:
            self.cancel()
        try:
            if self.root.state() == 'normal':
                self.cfg["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        save_config(self._settings())
        for pending in (self._resize_id, self._status_id):
            if pending:
                self.root.after_cancel(pending)
        self.session.clear()
        log.info("--- shutting down ---")
        # let go of the Tk images here, on the Tk thread: a garbage collection that happens
        # to run in a worker thread later must not be the one to delete them
        self.thumbs.clear()
        self._photo = self._dim_photo = self._crop_photo = self.icon = None
        self.root.destroy()

    def run(self):
        self.root.mainloop()
