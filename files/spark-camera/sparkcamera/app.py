"""The Spark Camera window: a Camera tab (preview, photos, video, a gallery of what you took)
and a Voice tab (the voice recorder and its recordings)."""

import os
import random
import re
import shutil
import subprocess
import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Dict, List, Optional, Tuple

from . import APP_CLASS, APP_NAME, dialogs, media, trash
from .core import (duration_text, home_short, human_size, load_settings, log,
                   photos_dir, recordings_dir, reduced_motion, save_settings, stamp, unique_path,
                   videos_dir)
from .text import t
from .widgets import (T, Choice, Glitch, GlitchPanel, GlitchText, IconButton, Mark, Segmented,
                      Strip, Toggle, WolkButton, make_table, mix, pick_mono, style_tables)

PHOTO_EXT = ('.jpg', '.jpeg', '.png')
VIDEO_EXT = ('.webm', '.mp4', '.mkv')
AUDIO_EXT = ('.opus', '.flac', '.ogg', '.wav', '.mp3', '.m4a')
TICK_MS = 40
NO_PICTURE_AFTER = 8.0           # seconds without a first frame before the window says so
GALLERY_MAX = 14


def launch(argv: List[str]) -> bool:
    """Start a program without waiting for it."""
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as exc:
        log.warning("couldn't start %s: %s", argv[0], exc)
        return False


def gallery_items(limit: int = GALLERY_MAX) -> List[Tuple[str, str, float]]:
    """The newest photos and videos Spark Camera saved: (path, 'photo' or 'video', mtime)."""
    found: List[Tuple[str, str, float]] = []
    for folder, kind, exts in ((photos_dir(), 'photo', PHOTO_EXT), (videos_dir(), 'video', VIDEO_EXT)):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if name.lower().endswith(exts):
                path = os.path.join(folder, name)
                try:
                    found.append((path, kind, os.stat(path).st_mtime))
                except OSError:
                    pass
    found.sort(key=lambda item: -item[2])
    return found[:limit]


def recording_files() -> List[Tuple[str, float, int]]:
    """Voice recordings, newest first: (path, mtime, bytes)."""
    out = []
    try:
        names = os.listdir(recordings_dir())
    except OSError:
        return out
    for name in names:
        if name.lower().endswith(AUDIO_EXT):
            path = os.path.join(recordings_dir(), name)
            try:
                st = os.stat(path)
                out.append((path, st.st_mtime, st.st_size))
            except OSError:
                pass
    out.sort(key=lambda item: -item[1])
    return out


def clean_name(text: str) -> str:
    """A file name someone typed, made safe: no folders, no leading dots, no control marks."""
    text = re.sub(r'[\x00-\x1f/\\]', ' ', text or '').lstrip(' .').rstrip(' .')
    return re.sub(r'\s+', ' ', text)[:120]


def file_when(mtime: float) -> str:
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))


class App:
    def __init__(self, tab: str = 'camera',
                 opener: Callable[[List[str]], bool] = launch,
                 ask: Optional[Callable[..., bool]] = None,
                 tell: Optional[Callable[..., object]] = None,
                 warn: Optional[Callable[..., object]] = None,
                 error: Optional[Callable[..., object]] = None,
                 name: Optional[Callable[..., Optional[str]]] = None):
        # the dialogs can be swapped (the tests answer them; nothing modal blocks a test)
        self.opener = opener
        self.ask = ask or dialogs.askyesno
        self.tell = tell or dialogs.showinfo
        self.warn = warn or dialogs.showwarning
        self.error = error or dialogs.showerror
        self.askname = name or dialogs.askname
        self.settings = load_settings()
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=T["bg"])
        try:
            self.scale = max(1.0, self.root.winfo_fpixels('1i') / 96)
        except tk.TclError:
            self.scale = 1.0
        self.root.geometry(f"{self.px(1120)}x{self.px(780)}")
        self.root.minsize(self.px(900), self.px(640))
        family = pick_mono(self.root)
        self.f_body = tkfont.Font(root=self.root, family=family, size=9)
        self.f_small = tkfont.Font(root=self.root, family=family, size=8)
        self.f_label = tkfont.Font(root=self.root, family=family, size=7, weight="bold")
        self.f_title = tkfont.Font(root=self.root, family=family, size=11, weight="bold")
        self.f_head = tkfont.Font(root=self.root, family=family, size=15, weight="bold")
        self.f_brand = tkfont.Font(root=self.root, family=family, size=10, weight="bold")
        self.f_big = tkfont.Font(root=self.root, family=family, size=34, weight="bold")
        self.f_count = tkfont.Font(root=self.root, family=family, size=72, weight="bold")
        style_tables(self.root, self.f_body, self.f_label, self.px(24))
        self.glitch = Glitch(self.root, not reduced_motion())
        self.closed = False
        self.cameras: List[media.Source] = []
        self.mics: List[media.Source] = []
        self.video_formats: List[media.VideoFormat] = []
        self.voice_formats: List[media.VoiceFormat] = []
        self.scan_devices()

        self._header(tab)
        self.body = tk.Frame(self.root, bg=T["bg"])
        self.body.pack(fill="both", expand=True)
        self.cam = CameraScreen(self)
        self.voice = VoiceScreen(self)
        self.screen: Optional[tk.Frame] = None
        self.tab = ''
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        for seq in ("<Control-q>", "<Control-w>"):
            self.root.bind(seq, lambda _e: self.close())
        self.root.bind("<Control-Key-1>", lambda _e: self.pick_tab('camera'))
        self.root.bind("<Control-Key-2>", lambda _e: self.pick_tab('voice'))
        self.root.bind("<F5>", lambda _e: self.refresh_devices())
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        self.pick_tab(tab if tab in ('camera', 'voice') else 'camera')
        self.tick_job = self.root.after(TICK_MS, self._tick)

    def px(self, v: float) -> int:
        return int(round(v * self.scale))

    # ── header ──

    def _header(self, tab: str):
        bar = tk.Frame(self.root, bg=T["bg"])
        bar.pack(fill="x", padx=self.px(14), pady=(self.px(10), self.px(6)))
        self.mark = Mark(bar, self.px(26), T["bg"])
        self.mark.pack(side="left")
        self.title = GlitchText(bar, APP_NAME.upper(), self.f_brand, T["bg"])
        self.title.pack(side="left", padx=(self.px(8), 0))
        self.tabs = Segmented(bar, [(t('tab.camera'), 'camera'), (t('tab.voice'), 'voice')],
                              tab, self.pick_tab, self.f_label)
        self.tabs.pack(side="left", padx=(self.px(24), 0))
        self.status = tk.Label(bar, text="", bg=T["bg"], fg=T["accent"], font=self.f_label)
        self.status.pack(side="right")
        self.strip = Strip(self.root, height=2)
        self.strip.pack(fill="x")
        self.set_status('status.ready')

    def set_status(self, key: str, colour: Optional[str] = None, **kw):
        self.status.config(text="● " + t(key, **kw), fg=colour or T["accent"])

    def event(self, *targets, strong: bool = False):
        """Something happened: the house fault on the header and whatever else is named."""
        self.glitch.now(self.title, self.strip, *targets, strong=strong)

    def save(self, **values) -> None:
        self.settings.update(values)
        save_settings(self.settings)

    # ── devices ──

    def scan_devices(self) -> None:
        if media.init():
            self.cameras, self.mics, self.video_formats, self.voice_formats = [], [], [], []
            return
        self.cameras = media.list_cameras()
        self.mics = media.list_mics()
        self.video_formats = media.video_formats()
        self.voice_formats = media.voice_formats()
        log.info("found %d camera(s), %d microphone(s)", len(self.cameras), len(self.mics))

    def refresh_devices(self) -> None:
        if self.cam.busy() or self.voice.busy():
            return
        self.scan_devices()
        self.cam.devices_changed()
        self.voice.devices_changed()
        if self.tab == 'camera':
            self.cam.open_camera()
        else:
            self.voice.start_monitor()

    # ── tabs ──

    def pick_tab(self, tab: str) -> None:
        if tab == self.tab:
            return
        if self.cam.busy() or self.voice.busy():
            self.tabs.set(self.tab)
            self.set_status('status.finish_first', T["gold"])
            return
        if self.screen is not None:
            self.screen.pack_forget()
        # leave the camera and the microphone free for other programs
        if tab == 'camera':
            self.voice.release()
            self.screen = self.cam
            self.tab = tab
            self.cam.pack(fill="both", expand=True)
            self.cam.open_camera()
        else:
            self.cam.release()
            self.screen = self.voice
            self.tab = tab
            self.voice.pack(fill="both", expand=True)
            self.voice.start_monitor()
        self.tabs.set(tab)
        self.event(self.screen.panel, strong=False)

    # ── actions ──

    def open_path(self, path: str) -> None:
        if not self.opener(['xdg-open', path]):
            self.error(t('error.open_title'), t('error.open', path=path), parent=self.root)

    def open_folder(self, folder: str) -> None:
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass
        spark_files = shutil.which('spark-files')
        if not self.opener([spark_files, folder] if spark_files else ['xdg-open', folder]):
            self.error(t('error.open_title'), t('error.open', path=folder), parent=self.root)

    def fail(self, title_key: str, message: str, *targets) -> None:
        """An error: the status turns pink, the window tears, and a box says what happened."""
        self.set_status('status.error', T["pink"])
        self.event(*targets, strong=True)
        self.error(t(title_key), message, parent=self.root)

    # ── the timer ──

    def _tick(self):
        if self.closed:
            return
        try:
            if self.tab == 'camera':
                self.cam.tick()
            else:
                self.voice.tick()
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
        try:
            self.root.after_cancel(self.tick_job)
        except (tk.TclError, AttributeError):
            pass
        for screen in (self.cam, self.voice):
            try:
                screen.shutdown()
            except Exception:                      # noqa: BLE001
                log.exception("closing %s failed", screen)
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ─── Small helpers shared by both tabs ────────────────────────────────

def micro_label(parent: tk.Misc, app: App, text: str, bg: str = T["panel"]) -> tk.Label:
    return tk.Label(parent, text=text.upper(), bg=bg, fg=T["muted"], font=app.f_label, anchor="w")


def side_row(parent: tk.Misc, app: App, label: str) -> tk.Frame:
    micro_label(parent, app, label).pack(fill="x", pady=(app.px(10), app.px(3)))
    frame = tk.Frame(parent, bg=T["panel"])
    frame.pack(fill="x")
    return frame


def finish_wait(session, poll: Callable[[], list], seconds: float = 6.0) -> list:
    """Wait (for a short while) for a stopping recording to close its file; the events."""
    out: list = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        out += poll()
        if out:
            break
        time.sleep(0.05)
    return out


# ─── Camera tab ───────────────────────────────────────────────────────

class CameraScreen(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        self.session: Optional[media.CameraSession] = None
        self.state = 'idle'                    # idle, counting, recording
        self.count_left = 0
        self.count_job: Optional[str] = None
        self.after_count = ''                  # what to do when the countdown ends
        self.got_frame = False
        self.opened_at = 0.0
        self.message = ''
        self.sub = ''
        self.photo_ref = None
        self.tear_until = 0.0
        self.rec_path = ''
        self.thumbs: Dict[Tuple[str, float], object] = {}
        self.gallery_key: Tuple = ()
        self.last_size = (0, 0)
        self.mode_kind = 'photo'

        main = tk.Frame(self, bg=T["bg"])
        main.pack(fill="both", expand=True, padx=px(14), pady=(px(10), px(4)))

        # the picture
        left = tk.Frame(main, bg=T["bg"])
        left.pack(side="left", fill="both", expand=True)
        self.panel = GlitchPanel(left, T["out_bg"])
        self.panel.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.panel.inner, bg=T["out_bg"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw_message())

        shutter = tk.Frame(left, bg=T["bg"])
        shutter.pack(fill="x", pady=(px(8), 0))
        self.kind = Segmented(shutter, [(t('mode.photo'), 'photo'), (t('mode.video'), 'video')],
                              'photo', self.set_kind, app.f_label)
        self.kind.pack(side="left")
        self.go = WolkButton(shutter, t('shutter.photo'), self.shutter, app.f_title,
                             variant="primary", padx=px(22), pady=px(7))
        self.go.pack(side="left", padx=(px(12), 0))
        self.stop = WolkButton(shutter, t('shutter.stop'), self.shutter, app.f_title,
                               variant="danger", padx=px(22), pady=px(7))
        self.timer = tk.Label(shutter, text="", bg=T["bg"], fg=T["pink"], font=app.f_title)
        self.timer.pack(side="left", padx=(px(14), 0))
        self.hint = tk.Label(shutter, text="", bg=T["bg"], fg=T["muted"], font=app.f_small)
        self.hint.pack(side="right")

        # the settings
        side = GlitchPanel(main, T["panel"])
        side.pack(side="left", fill="y", padx=(px(12), 0))
        inner = tk.Frame(side.inner, bg=T["panel"], width=px(270))
        inner.pack(fill="both", expand=True, padx=px(14), pady=px(10))
        row = side_row(inner, app, t('side.camera'))
        self.camera_pick = Choice(row, app.f_small, self.pick_camera, width=24)
        self.camera_pick.pack(side="left", fill="x", expand=True)
        IconButton(row, "refresh", app.refresh_devices, px(26), accent=False).pack(
            side="left", padx=(px(6), 0))
        row = side_row(inner, app, t('side.size'))
        self.size_pick = Choice(row, app.f_small, self.pick_size, width=24)
        self.size_pick.pack(side="left", fill="x", expand=True)
        row = side_row(inner, app, t('side.mic'))
        self.mic_pick = Choice(row, app.f_small, self.pick_mic, width=24)
        self.mic_pick.pack(side="left", fill="x", expand=True)
        row = side_row(inner, app, t('side.format'))
        self.format_pick = Choice(row, app.f_small, self.pick_format, width=24)
        self.format_pick.pack(side="left", fill="x", expand=True)
        row = side_row(inner, app, t('side.options'))
        self.sound = Toggle(row, t('toggle.sound'), app.settings['sound'], self.set_sound,
                            app.f_label)
        self.sound.pack(side="left")
        self.mirror = Toggle(row, t('toggle.mirror'), app.settings['mirror'], self.set_mirror,
                             app.f_label)
        self.mirror.pack(side="left", padx=(px(6), 0))
        row = side_row(inner, app, t('side.countdown'))
        self.countdown = Segmented(
            row, [(t('countdown.off'), '0'), ("3", '3'), ("5", '5'), ("10", '10')],
            str(app.settings['countdown']), self.set_countdown, app.f_label)
        self.countdown.pack(side="left")
        tk.Frame(inner, bg=T["line"], height=1).pack(fill="x", pady=(px(14), px(8)))
        micro_label(inner, app, t('side.saved_to')).pack(fill="x")
        self.where = tk.Label(inner, text="", bg=T["panel"], fg=T["muted"], font=app.f_small,
                              anchor="w", justify="left", wraplength=px(250))
        self.where.pack(fill="x", pady=(px(3), 0))

        # the gallery
        gal = tk.Frame(self, bg=T["bg"])
        gal.pack(fill="x", padx=px(14), pady=(px(4), px(10)))
        head = tk.Frame(gal, bg=T["bg"])
        head.pack(fill="x")
        micro_label(head, app, t('gallery.title'), T["bg"]).pack(side="left")
        WolkButton(head, t('gallery.videos_folder'),
                   lambda: app.open_folder(videos_dir()), app.f_label,
                   padx=px(8), pady=px(2)).pack(side="right")
        WolkButton(head, t('gallery.photos_folder'),
                   lambda: app.open_folder(photos_dir()), app.f_label,
                   padx=px(8), pady=px(2)).pack(side="right", padx=(0, px(6)))
        self.strip_frame = tk.Frame(gal, bg=T["bg"], height=px(92))
        self.strip_frame.pack(fill="x", pady=(px(4), 0))
        self.strip_frame.pack_propagate(False)
        self.strip_frame.bind("<Configure>", lambda _e: self.fill_gallery())

        self.devices_changed()
        app.glitch.add(self.panel)

    # ── state ──

    def busy(self) -> bool:
        return self.state != 'idle'

    def video_format(self) -> Optional[media.VideoFormat]:
        return media.pick_by_key(self.app.video_formats, self.app.settings['video_format'])

    def devices_changed(self) -> None:
        app = self.app
        s = app.settings
        self.camera_pick.set_items([(c.name, c.id) for c in app.cameras], s['camera'])
        self.mic_pick.set_items([(m.name, m.id) for m in app.mics], s['mic'])
        self.format_pick.set_items([(f.label, f.key) for f in app.video_formats],
                                   s['video_format'])
        self.fill_sizes()
        self.sound.set(bool(s['sound']) and bool(app.mics))
        self.where.config(text=f"{t('where.photos')}  {home_short(photos_dir())}\n"
                               f"{t('where.videos')}  {home_short(videos_dir())}")
        self.update_buttons()

    def camera(self) -> Optional[media.Source]:
        return next((c for c in self.app.cameras if c.id == self.camera_pick.value), None)

    def mic(self) -> Optional[media.Source]:
        return next((m for m in self.app.mics if m.id == self.mic_pick.value), None)

    def fill_sizes(self) -> None:
        cam = self.camera()
        modes = cam.modes if cam else []
        mode = media.pick_mode(modes, self.app.settings['mode'])
        self.size_pick.set_items([(m.label(), m.key) for m in modes], mode.key if mode else '')

    def update_buttons(self) -> None:
        idle = self.state == 'idle'
        have_camera = self.session is not None and self.session.running
        self.go.set_enabled(have_camera and (self.mode_kind == 'photo'
                                             or self.video_format() is not None))
        for pick in (self.camera_pick, self.size_pick, self.mic_pick, self.format_pick):
            pick.set_enabled(idle and bool(pick.items))
        self.camera_pick.set_enabled(idle and bool(self.camera_pick.items))
        self.countdown.config(cursor="hand2" if idle else "arrow")
        if self.state == 'idle':
            self.stop.pack_forget()
            self.go.pack(side="left", padx=(self.app.px(12), 0), before=self.timer)
        else:
            self.go.pack_forget()
            self.stop.set_text(t('shutter.cancel') if self.state == 'counting'
                               else t('shutter.stop'))
            self.stop.pack(side="left", padx=(self.app.px(12), 0), before=self.timer)
        self.go.set_text(t('shutter.photo') if self.mode_kind == 'photo' else t('shutter.record'))
        if self.mode_kind == 'video' and not self.app.video_formats:
            self.hint.config(text=t('hint.no_encoder'), fg=T["gold"])
        elif self.mode_kind == 'video' and self.sound.value:
            self.hint.config(text=t('hint.with_sound'), fg=T["muted"])
        else:
            self.hint.config(text="")

    # ── choices ──

    def set_kind(self, kind: str) -> None:
        if self.busy():
            self.kind.set(self.mode_kind)
            return
        self.mode_kind = kind
        self.update_buttons()

    def pick_camera(self, cam_id: str) -> None:
        self.app.save(camera=cam_id, mode='')
        self.fill_sizes()
        self.open_camera()

    def pick_size(self, key: str) -> None:
        self.app.save(mode=key)
        self.open_camera()

    def pick_mic(self, mic_id: str) -> None:
        self.app.save(mic=mic_id)

    def pick_format(self, key: str) -> None:
        self.app.save(video_format=key)

    def set_sound(self, on: bool) -> None:
        if on and not self.app.mics:
            self.sound.set(False)
            return
        self.app.save(sound=on)
        self.update_buttons()

    def set_mirror(self, on: bool) -> None:
        self.app.save(mirror=on)

    def set_countdown(self, value: str) -> None:
        if self.busy():
            self.countdown.set(str(self.app.settings['countdown']))
            return
        self.app.save(countdown=int(value))

    # ── the camera ──

    def release(self) -> None:
        """Close the camera so other programs can have it."""
        if self.session is not None:
            try:
                self.session.stop()
            except Exception:                      # noqa: BLE001
                log.exception("closing the camera failed")
            self.session = None
        self.photo_ref = None
        self.canvas.delete("all")

    def open_camera(self) -> None:
        self.release()
        self.got_frame = False
        self.last_size = (0, 0)
        cam = self.camera()
        if media.init():
            self.show_message(t('cam.no_gstreamer'), t('cam.no_gstreamer_hint'))
            self.update_buttons()
            return
        if cam is None:
            self.show_message(t('cam.none'), t('cam.none_hint'))
            self.update_buttons()
            return
        mode = media.pick_mode(cam.modes, self.app.settings['mode'])
        if mode is None:
            self.show_message(t('cam.none'), t('cam.none_hint'))
            self.update_buttons()
            return
        self.show_message(t('cam.starting'), cam.name)
        try:
            session = media.CameraSession(cam, mode)
            session.start()
        except Exception as exc:                   # noqa: BLE001 - GStreamer's own words
            log.warning("couldn't open %s: %s", cam.name, exc)
            self.show_message(t('cam.failed'), str(exc))
            self.app.set_status('status.error', T["pink"])
            self.app.event(self.panel, strong=True)
            self.tear()
            self.update_buttons()
            return
        self.session = session
        self.opened_at = time.monotonic()
        self.app.set_status('status.live', cam=cam.name)
        self.update_buttons()

    # ── drawing ──

    def show_message(self, text: str, sub: str = '') -> None:
        self.message, self.sub = text, sub
        self.photo_ref = None
        self.redraw_message()

    def redraw_message(self) -> None:
        if not self.message:
            return
        c = self.canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        cx, cy = w // 2, h // 2 - self.app.px(10)
        for colour, dx in ((T["ch_a"], -2), (T["ch_b"], 2), (T["text"], 0)):
            c.create_text(cx + dx, cy, text=self.message.upper(), fill=colour,
                          font=self.app.f_head)
        if self.sub:
            c.create_text(cx, cy + self.app.px(30), text=self.sub, fill=T["muted"],
                          font=self.app.f_body, width=max(100, w - self.app.px(80)),
                          justify="center")

    def tear(self) -> None:
        if self.app.glitch.enabled:
            self.tear_until = time.monotonic() + 0.22

    def draw_frame(self, frame: Tuple[int, int, bytes]) -> None:
        from PIL import Image, ImageTk
        w, h, data = frame
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(cw / w, ch / h)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        image = media.rgb_to_image(w, h, data).resize(size, Image.Resampling.BILINEAR)
        if self.mirror.value:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        self.photo_ref = ImageTk.PhotoImage(image)
        c = self.canvas
        c.delete("all")
        shift = 0
        if time.monotonic() < self.tear_until:
            shift = random.choice([-8, -4, 4, 8])
            for colour, dx in ((T["ch_a"], -3), (T["ch_b"], 3)):
                c.create_rectangle((cw - size[0]) // 2 + dx, (ch - size[1]) // 2,
                                   (cw + size[0]) // 2 + dx, (ch + size[1]) // 2,
                                   outline=colour, width=2)
        c.create_image(cw // 2 + shift, ch // 2, image=self.photo_ref, tags="img")
        if time.monotonic() < self.tear_until:
            for _ in range(random.randint(2, 4)):
                y = random.randint(0, max(1, ch - 6))
                c.create_rectangle(0, y, cw, y + random.randint(2, 5),
                                   fill=random.choice([T["ch_a"], T["ch_b"]]),
                                   stipple="gray50", width=0)
        self.overlay()

    def overlay(self) -> None:
        c = self.canvas
        c.delete("ov")
        px = self.app.px
        if self.state == 'recording' and self.session is not None:
            c.create_oval(px(14), px(14), px(26), px(26), fill=T["pink"], outline="", tags="ov")
            c.create_text(px(34), px(20), anchor="w", tags="ov", fill=T["text"],
                          font=self.app.f_title,
                          text="REC  " + duration_text(self.session.record_seconds()))
        if self.state == 'counting' and self.count_left > 0:
            cx, cy = c.winfo_width() // 2, c.winfo_height() // 2
            for colour, dx in ((T["ch_a"], -4), (T["ch_b"], 4), (T["text"], 0)):
                c.create_text(cx + dx, cy, text=str(self.count_left), fill=colour,
                              font=self.app.f_count, tags="ov")

    # ── the timer ──

    def tick(self) -> None:
        session = self.session
        if session is None:
            return
        for kind, value in session.poll():
            if kind == 'error':
                self.on_camera_error(value)
            elif kind == 'recorded':
                self.on_recorded(*value)
        if self.session is None:
            return
        frame = session.new_preview()
        if frame is not None:
            self.got_frame = True
            self.message = ''
            self.draw_frame(frame)
        elif self.got_frame:
            if self.state != 'idle' or time.monotonic() < self.tear_until:
                last = session.last_preview()
                if last is not None:
                    self.draw_frame(last)
        elif time.monotonic() - self.opened_at > NO_PICTURE_AFTER and \
                self.message != t('cam.no_picture'):
            self.show_message(t('cam.no_picture'), t('cam.no_picture_hint'))
            self.app.set_status('status.error', T["pink"])
        if self.state == 'recording':
            self.timer.config(text="● " + duration_text(session.record_seconds()))

    def on_camera_error(self, text: str) -> None:
        log.warning("camera error: %s", text)
        if self.state == 'recording':
            # the session closed the recording itself and reports 'recorded' next
            self.app.set_status('status.error', T["pink"])
            self.app.event(self.panel, strong=True)
            self.tear()
            return
        self.cancel_count()
        self.release()
        self.show_message(t('cam.stopped'), text)
        self.app.set_status('status.error', T["pink"])
        self.app.event(self.panel, strong=True)
        self.update_buttons()

    # ── the shutter ──

    def shutter(self) -> None:
        if self.session is None or not self.session.running:
            return
        if self.state == 'counting':
            self.cancel_count()
            return
        if self.state == 'recording':
            self.stop_recording()
            return
        if self.mode_kind == 'video' and self.video_format() is None:
            return
        seconds = int(self.app.settings['countdown'])
        if seconds > 0:
            self.state = 'counting'
            self.count_left = seconds
            self.update_buttons()
            self.count_job = self.after(1000, self.count_step)
            self.overlay()
        else:
            self.fire()

    def count_step(self) -> None:
        self.count_job = None
        if self.state != 'counting':
            return
        self.count_left -= 1
        if self.count_left <= 0:
            self.state = 'idle'
            self.fire()
            return
        self.count_job = self.after(1000, self.count_step)
        self.overlay()

    def cancel_count(self) -> None:
        if self.count_job is not None:
            self.after_cancel(self.count_job)
            self.count_job = None
        if self.state == 'counting':
            self.state = 'idle'
            self.update_buttons()
            self.overlay()

    def fire(self) -> None:
        if self.mode_kind == 'photo':
            self.take_photo()
        else:
            self.start_recording()

    def take_photo(self) -> Optional[str]:
        session = self.session
        frame = session.photo_frame() if session else None
        if frame is None:
            self.app.fail('error.photo_title', t('error.no_frame'), self.panel)
            return None
        w, h, data = frame
        path = unique_path(photos_dir(), f"{t('file.photo')} {stamp()}", '.jpg')
        try:
            media.rgb_to_image(w, h, data).save(path, 'JPEG', quality=92)
        except (OSError, ValueError) as exc:
            self.app.fail('error.photo_title', t('error.photo_save', path=home_short(path),
                                                 error=str(exc)), self.panel)
            return None
        log.info("photo saved: %s (%dx%d)", path, w, h)
        self.tear()
        self.app.set_status('status.saved', name=os.path.basename(path))
        self.app.event(self.panel, strong=True)
        self.fill_gallery(force=True)
        return path

    def start_recording(self) -> None:
        fmt = self.video_format()
        session = self.session
        if fmt is None or session is None:
            return
        mic = self.mic() if (self.sound.value and self.mic()) else None
        path = unique_path(videos_dir(), f"{t('file.video')} {stamp()}", fmt.ext)
        try:
            session.start_recording(path, fmt, mic)
        except Exception as exc:                   # noqa: BLE001
            log.warning("couldn't start recording: %s", exc)
            try:
                os.remove(path)
            except OSError:
                pass
            self.app.fail('error.video_title', t('error.video_start', error=str(exc)),
                          self.panel)
            return
        self.rec_path = path
        self.state = 'recording'
        self.tear()
        self.app.set_status('status.recording', T["pink"])
        self.app.event(self.panel, strong=True)
        self.update_buttons()

    def stop_recording(self) -> None:
        if self.session is not None:
            self.session.stop_recording()
            self.stop.set_enabled(False)
            self.app.set_status('status.saving', T["gold"])

    def on_recorded(self, path: str, seconds: float) -> None:
        self.state = 'idle'
        self.timer.config(text="")
        self.update_buttons()
        self.tear()
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size < 1024:
            try:
                os.remove(path)
            except OSError:
                pass
            self.app.fail('error.video_title', t('error.video_empty'), self.panel)
            return
        log.info("video saved: %s (%.1f s, %d bytes)", path, seconds, size)
        self.app.set_status('status.saved', name=os.path.basename(path))
        self.app.event(self.panel, strong=True)
        self.fill_gallery(force=True)

    # ── the gallery ──

    def thumb(self, path: str, kind: str, mtime: float):
        from PIL import Image, ImageDraw, ImageTk
        key = (path, mtime)
        if key in self.thumbs:
            return self.thumbs[key]
        px = self.app.px
        size = (px(112), px(70))
        try:
            if kind == 'photo':
                image = Image.open(path)
                image.draft('RGB', (size[0] * 2, size[1] * 2))
                image = image.convert('RGB')
                image.thumbnail(size, Image.Resampling.BILINEAR)
            else:
                image = Image.new('RGB', size, T["tile"])
                d = ImageDraw.Draw(image)
                cx, cy, r = size[0] // 2, size[1] // 2, px(13)
                d.polygon([(cx - r // 2, cy - r), (cx - r // 2, cy + r), (cx + r, cy)],
                          outline=T["accent"], fill=None)
        except (OSError, ValueError):
            image = Image.new('RGB', size, T["tile"])
        photo = ImageTk.PhotoImage(image)
        if len(self.thumbs) > 80:
            self.thumbs.clear()
        self.thumbs[key] = photo
        return photo

    def fill_gallery(self, force: bool = False) -> None:
        px = self.app.px
        width = self.strip_frame.winfo_width()
        per = max(2, min(GALLERY_MAX, (max(width, px(500)) - px(4)) // px(122)))
        items = gallery_items(per)
        key = (per, tuple((p, m) for p, _k, m in items))
        if key == self.gallery_key and not force:
            return
        self.gallery_key = key
        for child in self.strip_frame.winfo_children():
            child.destroy()
        if not items:
            tk.Label(self.strip_frame, text=t('gallery.empty'), bg=T["bg"], fg=T["muted"],
                     font=self.app.f_small, anchor="w").pack(anchor="w", pady=px(8))
            return
        for path, kind, mtime in items:
            tile = tk.Frame(self.strip_frame, bg=T["line"], padx=1, pady=1, cursor="hand2")
            tile.pack(side="left", padx=(0, px(8)))
            label = tk.Label(tile, image=self.thumb(path, kind, mtime), bg=T["panel"],
                             bd=0)
            label.pack()
            caption = time.strftime('%H:%M:%S', time.localtime(mtime))
            if kind == 'video':
                caption = "▶ " + caption
            tk.Label(tile, text=caption, bg=T["panel"], fg=T["muted"], font=self.app.f_label,
                     anchor="w", padx=px(4)).pack(fill="x")
            for w in (tile, label) + tuple(tile.winfo_children()):
                w.bind("<ButtonRelease-1>", lambda _e, p=path: self.app.open_path(p))
                w.bind("<Enter>", lambda _e, f=tile: f.config(bg=T["accent"]))
                w.bind("<Leave>", lambda _e, f=tile: f.config(bg=T["line"]))

    # ── closing ──

    def shutdown(self) -> None:
        self.cancel_count()
        if self.session is not None and self.session.recording():
            self.session.stop_recording()
            for kind, value in finish_wait(self.session, self.session.poll):
                if kind == 'recorded':
                    log.info("recording closed on exit: %s", value[0])
        self.release()


# ─── Voice tab ────────────────────────────────────────────────────────

class VoiceScreen(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        self.monitor: Optional[media.VoiceSession] = None
        self.rec: Optional[media.VoiceSession] = None
        self.rec_path = ''
        self.play = media.Playback()
        self.rows: Dict[str, str] = {}            # path -> tree item
        self.durations: Dict[str, float] = {}
        self.pending: List[str] = []
        self.playing_path = ''
        self.message = ''
        self.rec_key = ''

        main = tk.Frame(self, bg=T["bg"])
        main.pack(fill="both", expand=True, padx=px(14), pady=(px(10), px(12)))
        self.panel = GlitchPanel(main, T["panel"])
        self.panel.pack(fill="x")
        top = tk.Frame(self.panel.inner, bg=T["panel"])
        top.pack(fill="x", padx=px(16), pady=px(12))
        left = tk.Frame(top, bg=T["panel"])
        left.pack(side="left", fill="both", expand=True)
        GlitchText(left, t('voice.heading'), app.f_head, T["panel"]).pack(anchor="w")
        row = tk.Frame(left, bg=T["panel"])
        row.pack(fill="x", pady=(px(10), 0))
        micro_label(row, app, t('side.mic')).pack(side="left")
        self.mic_pick = Choice(row, app.f_small, self.pick_mic, width=34)
        self.mic_pick.pack(side="left", padx=(px(10), 0))
        IconButton(row, "refresh", app.refresh_devices, px(26)).pack(side="left",
                                                                     padx=(px(6), 0))
        micro_label(row, app, t('side.format')).pack(side="left", padx=(px(18), px(8)))
        self.format = Segmented(row, [("OPUS", 'opus'), ("FLAC", 'flac')],
                                app.settings['voice_format'], self.pick_format, app.f_label)
        self.format.pack(side="left")
        self.meter = tk.Canvas(left, height=px(54), bg=T["panel"], highlightthickness=0, bd=0)
        self.meter.pack(fill="x", pady=(px(14), 0))
        self.note = tk.Label(left, text="", bg=T["panel"], fg=T["muted"], font=app.f_small,
                             anchor="w")
        self.note.pack(fill="x", pady=(px(4), 0))

        right = tk.Frame(top, bg=T["panel"])
        right.pack(side="right", padx=(px(24), 0))
        self.clock = tk.Label(right, text="0:00", bg=T["panel"], fg=T["text"], font=app.f_big)
        self.clock.pack(anchor="e")
        buttons = tk.Frame(right, bg=T["panel"])
        buttons.pack(anchor="e", pady=(px(8), 0))
        self.b_record = WolkButton(buttons, t('voice.record'), self.record, app.f_title,
                                   variant="primary", padx=px(16), pady=px(6))
        self.b_record.pack(side="left")
        self.b_pause = WolkButton(buttons, t('voice.pause'), self.pause, app.f_title,
                                  padx=px(16), pady=px(6))
        self.b_pause.pack(side="left", padx=(px(6), 0))
        self.b_stop = WolkButton(buttons, t('voice.stop'), self.finish, app.f_title,
                                 variant="danger", padx=px(16), pady=px(6))
        self.b_stop.pack(side="left", padx=(px(6), 0))

        # the recordings
        bar = tk.Frame(main, bg=T["bg"])
        bar.pack(fill="x", pady=(px(12), px(4)))
        micro_label(bar, app, t('voice.recordings'), T["bg"]).pack(side="left")
        tk.Label(bar, text="", bg=T["bg"]).pack(side="left")
        self.where = tk.Label(bar, text=home_short(recordings_dir()), bg=T["bg"], fg=T["dim"],
                              font=app.f_small)
        self.where.pack(side="left", padx=(px(10), 0))
        self.b_folder = IconButton(bar, "folder", lambda: app.open_folder(recordings_dir()),
                                   px(28), tip=t('voice.open_folder'))
        self.b_folder.pack(side="right")
        self.b_delete = IconButton(bar, "trash", self.delete, px(28))
        self.b_delete.pack(side="right", padx=(0, px(4)))
        self.b_rename = IconButton(bar, "rename", self.rename, px(28))
        self.b_rename.pack(side="right", padx=(0, px(4)))
        self.b_play = IconButton(bar, "play", self.toggle_play, px(28), accent=True)
        self.b_play.pack(side="right", padx=(0, px(8)))
        self.position = tk.Label(bar, text="", bg=T["bg"], fg=T["accent"], font=app.f_small)
        self.position.pack(side="right", padx=(0, px(10)))
        frame, self.tree = make_table(main, ("name", "length", "size", "date"))
        frame.pack(fill="both", expand=True)
        for col, text, width, anchor in (
                ("name", t('col.name'), 460, "w"), ("length", t('col.length'), 90, "e"),
                ("size", t('col.size'), 100, "e"), ("date", t('col.date'), 150, "w")):
            self.tree.heading(col, text=text.upper(), anchor=anchor)
            self.tree.column(col, width=px(width), anchor=anchor, stretch=(col == "name"))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.update_buttons())
        self.tree.bind("<Double-1>", lambda _e: self.toggle_play(restart=True))
        self.tree.bind("<Delete>", lambda _e: self.delete())
        self.tree.bind("<F2>", lambda _e: self.rename())
        self.empty = tk.Label(frame, text=t('voice.empty'), bg=T["panel"], fg=T["muted"],
                              font=app.f_small)
        self.meter.bind("<Configure>", lambda _e: self.draw_meter())
        self.devices_changed()
        self.fill_list()
        app.glitch.add(self.panel)

    # ── state ──

    def busy(self) -> bool:
        return self.rec is not None

    def mic(self) -> Optional[media.Source]:
        return next((m for m in self.app.mics if m.id == self.mic_pick.value), None)

    def voice_format(self) -> Optional[media.VoiceFormat]:
        return media.pick_by_key(self.app.voice_formats, self.format.value)

    def devices_changed(self) -> None:
        app = self.app
        self.mic_pick.set_items([(m.name, m.id) for m in app.mics], app.settings['voice_mic'])
        keys = [f.key for f in app.voice_formats]
        if keys and self.format.value not in keys:
            self.format.set(keys[0])
        self.update_buttons()

    def update_buttons(self) -> None:
        recording = self.rec is not None
        can = self.mic() is not None and self.voice_format() is not None
        self.b_record.set_enabled(can and not recording)
        self.b_pause.set_enabled(recording)
        self.b_stop.set_enabled(recording)
        self.b_pause.set_text(t('voice.resume') if recording and self.rec.paused
                              else t('voice.pause'))
        self.mic_pick.set_enabled(not recording and bool(self.mic_pick.items))
        selected = self.selected() is not None
        self.b_play.set_enabled(selected)
        self.b_rename.set_enabled(selected and not recording)
        self.b_delete.set_enabled(selected and not recording)
        self.b_play.set_icon("pause" if self.play.playing else "play")
        if self.mic() is None:
            self.note.config(text=t('voice.no_mic'), fg=T["gold"])
        elif self.voice_format() is None:
            self.note.config(text=t('voice.no_encoder'), fg=T["gold"])
        elif recording:
            self.note.config(text=t('voice.paused') if self.rec.paused else
                             t('voice.recording'), fg=T["pink"] if not self.rec.paused
                             else T["gold"])
        else:
            self.note.config(text=t('voice.ready'), fg=T["muted"])

    def pick_mic(self, mic_id: str) -> None:
        self.app.save(voice_mic=mic_id)
        self.start_monitor()

    def pick_format(self, key: str) -> None:
        if self.busy():
            self.format.set(self.rec_key)
            return
        self.app.save(voice_format=key)
        self.update_buttons()

    # ── the microphone ──

    def release(self) -> None:
        self.stop_play()
        if self.monitor is not None:
            self.monitor.stop_now()
            self.monitor = None
        self.draw_meter()

    def start_monitor(self) -> None:
        if self.monitor is not None:
            self.monitor.stop_now()
            self.monitor = None
        mic = self.mic()
        if mic is None or media.init():
            self.update_buttons()
            self.draw_meter()
            return
        session = media.VoiceSession(mic)
        try:
            session.start()
        except Exception as exc:                   # noqa: BLE001
            log.warning("couldn't open the microphone %s: %s", mic.name, exc)
            self.note.config(text=t('voice.mic_failed', error=str(exc)), fg=T["pink"])
            self.app.set_status('status.error', T["pink"])
            return
        self.monitor = session
        self.update_buttons()

    # ── recording ──

    def record(self) -> None:
        mic, fmt = self.mic(), self.voice_format()
        if mic is None or fmt is None or self.rec is not None:
            return
        self.stop_play()
        if self.monitor is not None:
            self.monitor.stop_now()
            self.monitor = None
        path = unique_path(recordings_dir(), f"{t('file.recording')} {stamp()}", fmt.ext)
        session = media.VoiceSession(mic, fmt, path)
        try:
            session.start()
        except Exception as exc:                   # noqa: BLE001
            log.warning("couldn't start the voice recording: %s", exc)
            self.app.fail('error.voice_title', t('error.voice_start', error=str(exc)),
                          self.panel)
            self.start_monitor()
            return
        self.rec, self.rec_path, self.rec_key = session, path, fmt.key
        self.format.set(fmt.key)
        self.app.set_status('status.recording', T["pink"])
        self.app.event(self.panel, strong=True)
        self.update_buttons()

    def pause(self) -> None:
        if self.rec is None:
            return
        if self.rec.paused:
            self.rec.resume()
            self.app.set_status('status.recording', T["pink"])
        else:
            self.rec.pause()
            self.app.set_status('status.paused', T["gold"])
        self.app.event(self.panel)
        self.update_buttons()

    def finish(self) -> None:
        if self.rec is None:
            return
        self.rec.finish()
        self.b_pause.set_enabled(False)
        self.b_stop.set_enabled(False)
        self.app.set_status('status.saving', T["gold"])

    def on_finished(self, path: str, seconds: float) -> None:
        self.rec = None
        self.clock.config(text="0:00")
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size < 64:
            try:
                os.remove(path)
            except OSError:
                pass
            self.app.fail('error.voice_title', t('error.voice_empty'), self.panel)
        else:
            log.info("voice saved: %s (%.1f s, %d bytes)", path, seconds, size)
            self.app.set_status('status.saved', name=os.path.basename(path))
            self.app.event(self.panel, strong=True)
            self.durations[path] = seconds
        self.fill_list(select=path)
        self.start_monitor()

    # ── the timer ──

    def tick(self) -> None:
        session = self.rec or self.monitor
        if session is not None:
            for kind, value in session.poll():
                if kind == 'error':
                    self.on_error(value)
                elif kind == 'finished':
                    self.on_finished(*value)
                    session = self.rec or self.monitor
        if self.rec is not None:
            self.clock.config(text=duration_text(self.rec.seconds()))
        self.draw_meter()
        ended = self.play.poll()
        if ended:
            self.playing_path = ''
            self.position.config(text="")
            self.update_buttons()
            self.mark_playing()
        elif self.play.player is not None:
            pos, dur = self.play.position()
            self.position.config(text=f"{duration_text(pos)} / {duration_text(dur)}")
        if self.pending:
            self.fill_duration(self.pending.pop(0))

    def on_error(self, text: str) -> None:
        log.warning("voice error: %s", text)
        if self.rec is not None:
            path = self.rec_path
            seconds = self.rec.seconds()
            self.rec.stop_now()
            self.app.set_status('status.error', T["pink"])
            self.app.event(self.panel, strong=True)
            self.on_finished(path, seconds)
            self.note.config(text=t('voice.stopped', error=text), fg=T["pink"])
        else:
            if self.monitor is not None:
                self.monitor.stop_now()
                self.monitor = None
            self.note.config(text=t('voice.mic_failed', error=text), fg=T["pink"])
            self.app.set_status('status.error', T["pink"])
            self.app.event(self.panel, strong=True)

    # ── the meter ──

    def draw_meter(self) -> None:
        c = self.meter
        c.delete("all")
        session = self.rec or self.monitor
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        px = self.app.px
        segs = 48
        gap = px(2)
        seg_w = max(2, (w - gap * (segs - 1)) / segs)
        rms = session.rms if session else [-90.0]
        peak = session.peak if session else [-90.0]
        rows = 2
        row_h = px(14)
        for r in range(rows):
            y = px(2) + r * (row_h + px(6))
            i = min(r, len(rms) - 1)
            level = media.level_fraction(rms[i])
            top = media.level_fraction(peak[i])
            lit = int(round(level * segs))
            tick = min(segs - 1, int(top * segs))
            for s in range(segs):
                x = s * (seg_w + gap)
                frac = s / segs
                colour = T["accent"] if frac < 0.75 else (T["gold"] if frac < 0.92
                                                           else T["pink"])
                if s < lit:
                    fill = colour
                elif s == tick and top > 0.02:
                    fill = mix(colour, T["text"], 0.4)
                else:
                    fill = T["panel2"]
                c.create_rectangle(x, y, x + seg_w, y + row_h, fill=fill, width=0)
        base = px(2) + rows * (row_h + px(6))
        for db in (-60, -40, -20, -10, 0):
            x = media.level_fraction(db) * (w - 1)
            c.create_text(min(max(x, px(8)), w - px(10)), base + px(2), anchor="n",
                          text=f"{db}", fill=T["dim"], font=self.app.f_label)

    # ── the recordings ──

    def selected(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            return None
        for path, item in self.rows.items():
            if item == sel[0]:
                return path
        return None

    def fill_list(self, select: Optional[str] = None) -> None:
        keep = select or self.selected()
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.pending = []
        files = recording_files()
        for path, mtime, size in files:
            length = self.durations.get(path)
            item = self.tree.insert("", "end", values=(
                os.path.basename(path), duration_text(length) if length else "…",
                human_size(size), file_when(mtime)))
            self.rows[path] = item
            if length is None:
                self.pending.append(path)
        if files:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.4, anchor="center")
        if keep in self.rows:
            self.tree.selection_set(self.rows[keep])
            self.tree.see(self.rows[keep])
        self.mark_playing()
        self.update_buttons()

    def fill_duration(self, path: str) -> None:
        item = self.rows.get(path)
        if item is None:
            return
        length = media.file_duration(path)
        self.durations[path] = length
        self.tree.set(item, "length", duration_text(length) if length else "?")

    def mark_playing(self) -> None:
        for path, item in self.rows.items():
            name = os.path.basename(path)
            self.tree.set(item, "name", ("▶ " + name) if path == self.playing_path else name)

    # ── playing, renaming, deleting ──

    def toggle_play(self, restart: bool = False) -> None:
        path = self.selected()
        if path is None:
            return
        if self.rec is not None:
            return
        try:
            if path == self.playing_path and not restart:
                self.play.toggle()
            else:
                self.play.play(path)
                self.playing_path = path
        except RuntimeError as exc:
            self.app.fail('error.play_title', t('error.play', error=str(exc)), self.panel)
            return
        self.mark_playing()
        self.update_buttons()

    def stop_play(self) -> None:
        if self.play.player is not None:
            self.play.stop()
        self.playing_path = ''
        self.position.config(text="")
        self.mark_playing()
        self.update_buttons()

    def rename(self) -> None:
        path = self.selected()
        if path is None or self.rec is not None:
            return
        stem, ext = os.path.splitext(os.path.basename(path))
        answer = self.app.askname(t('rename.title'), t('rename.message'), initial=stem,
                                  parent=self.app.root)
        if answer is None:
            return
        new = clean_name(answer)
        if new.lower().endswith(ext.lower()):
            new = new[:-len(ext)]
        if not new:
            self.app.fail('error.rename_title', t('error.rename_empty'), self.panel)
            return
        target = os.path.join(os.path.dirname(path), new + ext)
        if target == path:
            return
        if os.path.exists(target):
            self.app.fail('error.rename_title', t('error.rename_exists', name=new + ext),
                          self.panel)
            return
        playing = path == self.playing_path
        if playing:
            self.stop_play()
        try:
            os.rename(path, target)
        except OSError as exc:
            self.app.fail('error.rename_title', t('error.rename', error=exc.strerror or str(exc)),
                          self.panel)
            return
        if path in self.durations:
            self.durations[target] = self.durations.pop(path)
        log.info("renamed %s to %s", path, target)
        self.app.event(self.panel)
        self.fill_list(select=target)

    def delete(self) -> None:
        path = self.selected()
        if path is None or self.rec is not None:
            return
        name = os.path.basename(path)
        if not self.app.ask(t('delete.title'), t('delete.message', name=name),
                            parent=self.app.root):
            return
        if path == self.playing_path:
            self.stop_play()
        try:
            trash.trash(path)
        except (OSError, trash.NoTrash) as exc:
            # never delete for good: if the trash can't take it, the file stays
            self.app.fail('error.delete_title', t('error.delete', name=name,
                                                  error=getattr(exc, 'strerror', None) or str(exc)),
                          self.panel)
            return
        log.info("moved to the trash: %s", path)
        self.durations.pop(path, None)
        self.app.set_status('status.trashed', name=name)
        self.app.event(self.panel, strong=True)
        self.fill_list()

    # ── closing ──

    def shutdown(self) -> None:
        self.stop_play()
        if self.rec is not None:
            self.rec.finish()
            for kind, value in finish_wait(self.rec, self.rec.poll):
                if kind == 'finished':
                    log.info("voice recording closed on exit: %s", value[0])
        self.release()
        if self.rec is not None:
            self.rec.stop_now()
            self.rec = None
