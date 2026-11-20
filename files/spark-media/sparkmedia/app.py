"""The app: window, header, switching between the library, the photo viewer and the player,
and the command line."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from . import APP_CLASS, APP_ID, APP_NAME, APP_SLUG, KINDS, VERSION
from . import player as gst
from .core import (folder_items, image_formats, kind_of, load_json, log, path_from_arg,
                   pick_files, reduced_motion, save_json, setup_logging, siblings)
from .library import HomeView
from .playview import PlayerView
from .viewer import PhotoView
from .widgets import T, Glitch, GlitchText, IconButton, Mark, Strip, pick_mono


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_MEDIA_SCALE')
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


class App:
    def __init__(self, paths: List[str], start_kind: Optional[str] = None):
        if os.name == 'nt':                      # Windows dev runs only: no bitmap stretching
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
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
        self.settings = load_json('config.json')
        saved = self.settings.get("folders")
        self.last_folder: Dict[str, str] = saved if isinstance(saved, dict) else {}
        self.glitch = Glitch(self.root, enabled=not reduced_motion()
                             and self.settings.get("glitch", True) is not False)
        self.fullscreen = False
        self.view: Optional[tk.Frame] = None
        self._status_id: Optional[str] = None
        self._build()

        opened = False
        if paths:
            files = [p for p in paths if os.path.isfile(p) and kind_of(p)]
            if files:
                playlist = files if len(files) > 1 and \
                    len({kind_of(f) for f in files}) == 1 else None
                opened = self.open_path(files[0], playlist=playlist)
            elif len(paths) == 1 and os.path.isdir(paths[0]):
                folder = paths[0]
                _dirs, found = folder_items(folder)
                kind = start_kind or (kind_of(found[0]) if found else 'photo')
                self.show_home(kind, folder)
                opened = True
            else:
                missing = paths[0]
                self.root.after(300, lambda: messagebox.showerror(
                    APP_NAME, f"Spark Media can't open this:\n{missing}", parent=self.root))
        if not opened:
            self.show_home(start_kind or self.settings.get("kind") or 'photo')
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)

    # look helpers
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

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status("SOMETHING WENT WRONG", T["pink"])
        self.glitch.now(self.title, strong=True)
        messagebox.showerror(APP_NAME, f"Unexpected error:\n{exc_value}", parent=self.root)

    # window
    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.minsize(px(560), px(420))

        self.head = tk.Frame(root, bg=bg)
        self.head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.back = IconButton(self.head, "back", self.go_back, px(30))
        self.mark = Mark(self.head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(self.head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK MEDIA", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="● READY", bg=bg, fg=T["accent"], font=self.font(7))
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(self.head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)

        root.bind("<KeyPress>", self._key)
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w, h = min(px(1180), int(sw * 0.8)), min(px(780), int(sh * 0.8))
            root.geometry(f"{w}x{h}")

    def set_window_title(self, name: Optional[str]):
        self.root.title(f"{name} — {APP_NAME}" if name else APP_NAME)

    def set_status(self, text: str, colour: str = T["accent"], hold_ms: int = 2500):
        self.status.config(text=f"● {text}", fg=colour)
        if self._status_id:
            self.root.after_cancel(self._status_id)
        self._status_id = self.root.after(hold_ms, self._status_idle)

    def _status_idle(self):
        self._status_id = None
        self.status.config(text="● READY", fg=T["accent"])

    def _swap(self, view: tk.Frame):
        if self.view is not None:
            self.view.destroy()
        self.view = view
        view.pack(fill="both", expand=True)
        is_home = isinstance(view, HomeView)
        if is_home and self.back.winfo_ismapped():
            self.back.pack_forget()
        elif not is_home and not self.back.winfo_ismapped():
            self.back.pack(side="left", padx=(0, self.px(8)), before=self.mark)

    def show_home(self, kind: str, folder: Optional[str] = None):
        if kind not in KINDS:
            kind = 'photo'
        if self.fullscreen:
            self.toggle_fullscreen()
        self.settings["kind"] = kind
        self._swap(HomeView(self, kind, folder))
        self.set_window_title(None)
        self.glitch.now(self.title)

    def open_path(self, path: str, playlist: Optional[List[str]] = None,
                  slideshow: bool = False) -> bool:
        kind = kind_of(path)
        if kind is None:
            messagebox.showerror(APP_NAME, f"Spark Media doesn't open this kind of file:\n{path}",
                                 parent=self.root)
            return False
        path = os.path.abspath(path)
        files = [os.path.abspath(p) for p in playlist] if playlist else siblings(path)
        files = [f for f in files if kind_of(f) == kind] or [path]
        if path not in files:
            files.insert(0, path)
        self.last_folder[kind] = os.path.dirname(path)
        self.settings["kind"] = kind
        if kind == 'photo':
            self._swap(PhotoView(self, path, files, slideshow=slideshow))
        else:
            self._swap(PlayerView(self, path, files))
        self.view.focus_set()
        self.glitch.now(self.title)
        log.info("opened %s (%d in list)", path, len(files))
        return True

    def go_back(self):
        if isinstance(self.view, HomeView):
            return
        kind = getattr(self.view, 'kind', 'photo')
        self.show_home(kind)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes('-fullscreen', self.fullscreen)
        if self.fullscreen:
            self.head.pack_forget()
            self.strip.pack_forget()
        else:
            self.head.pack(fill="x", padx=self.px(14), pady=(self.px(10), self.px(8)),
                           before=self.body)
            self.strip.pack(fill="x", before=self.body)
        handler = getattr(self.view, 'fullscreen_changed', None)
        if handler:
            handler(self.fullscreen)

    def _key(self, event):
        k = event.keysym
        if isinstance(event.widget, tk.Listbox) and k in ('Up', 'Down', 'Return', 'Prior', 'Next'):
            return None
        if k in ('F11',) or (k in ('f', 'F') and not isinstance(self.view, HomeView)):
            self.toggle_fullscreen()
            return "break"
        if k == 'Escape':
            if self.fullscreen:
                self.toggle_fullscreen()
            else:
                self.go_back()
            return "break"
        if k in ('q', 'Q') and event.state & 0x4:
            self._on_close()
            return "break"
        if k in ('o', 'O') and event.state & 0x4:
            kind = getattr(self.view, 'kind', None)
            files = pick_files(kind, self.last_folder.get(kind or 'photo', os.path.expanduser('~')))
            if files:
                self.open_path(files[0], playlist=files if len(files) > 1 else None)
            return "break"
        handler = getattr(self.view, 'key', None)
        if handler and handler(event):
            return "break"
        return None

    def _on_close(self):
        if not self.fullscreen and self.root.state() == 'normal':
            self.settings["geometry"] = self.root.geometry()
        self.settings["folders"] = self.last_folder
        self.settings["version"] = VERSION
        if self.view is not None:
            self.view.destroy()
            self.view = None
        save_json('config.json', self.settings)
        log.info("--- shutting down ---")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Self-test: no display needed ─────────────────────────────

def self_test(require: List[str]) -> int:
    """Open sample photos of each format, make short test media with GStreamer and play each
    one to the end, and list the decoders. Exit 1 when something required is missing."""
    from PIL import Image
    from .core import Photo, PhotoError, photo_thumbnail
    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test")

    formats = image_formats()
    print("photos:   " + "  ".join(f"{k}:{'yes' if v else 'no'}" for k, v in formats.items()))
    scratch = tempfile.mkdtemp(prefix='spark-media-test-')
    os.environ.setdefault('XDG_CACHE_HOME', scratch)
    sample = Image.new('RGB', (640, 400), '#3de8c8')
    for ext, fmt in (('jpg', 'JPEG'), ('png', 'PNG'), ('webp', 'WEBP'), ('gif', 'GIF'),
                     ('bmp', 'BMP'), ('tiff', 'TIFF')):
        path = os.path.join(scratch, f'sample.{ext}')
        try:
            sample.save(path, fmt)
            photo = Photo(path)
            assert photo.size == (640, 400), photo.size
            assert photo_thumbnail(path) is not None, "no thumbnail"
            print(f"  open {ext}: ok")
        except (OSError, PhotoError, AssertionError, KeyError) as exc:
            print(f"  open {ext}: FAILED ({exc})")
            failures.append(f"photo {ext}")

    problem = gst.init()
    if problem:
        print(f"gstreamer: FAILED ({problem})")
        failures.append("gstreamer")
    else:
        print(f"gstreamer: {gst.gst_version()}   video output: "
              f"{', '.join(gst.video_sink_names()) or 'NONE'}")
        found = gst.decoders()
        print("decoders: " + "  ".join(f"{k}:{'yes' if v else 'no'}" for k, v in found.items()))
        for name in ['vp8', 'vorbis', 'opus', 'flac'] + require:
            if not found.get(name):
                failures.append(f"decoder {name}")
        if not gst.video_sink_names():
            failures.append("video output")
        failures += _play_samples(scratch)

    shutil.rmtree(scratch, ignore_errors=True)
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def _play_samples(folder: str) -> List[str]:
    """Encode two seconds of test video and audio, then play each to the end."""
    import time
    Gst = gst.Gst
    failures = []
    samples = (
        ('video.webm', 'videotestsrc num-buffers=50 ! video/x-raw,width=320,height=180,'
                       'framerate=25/1 ! vp8enc deadline=1 ! webmmux name=m ! filesink '
                       'location={out}  audiotestsrc num-buffers=86 ! audioconvert ! '
                       'vorbisenc ! m.', True),
        ('music.ogg', 'audiotestsrc num-buffers=86 ! audioconvert ! vorbisenc ! oggmux ! '
                      'filesink location={out}', False),
        ('music.opus', 'audiotestsrc num-buffers=86 ! audioconvert ! audioresample ! '
                       'opusenc ! oggmux ! filesink location={out}', False),
        ('music.flac', 'audiotestsrc num-buffers=86 ! audioconvert ! flacenc ! '
                       'filesink location={out}', False),
    )
    for name, launch, video in samples:
        out = os.path.join(folder, name)
        try:
            pipeline = Gst.parse_launch(launch.format(out=out))
        except Exception as exc:      # noqa: BLE001
            print(f"  make {name}: skipped ({exc})")
            continue
        pipeline.set_state(Gst.State.PLAYING)
        msg = pipeline.get_bus().timed_pop_filtered(
            30 * gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        pipeline.set_state(Gst.State.NULL)
        if msg is None or msg.type != Gst.MessageType.EOS:
            print(f"  make {name}: FAILED")
            failures.append(f"make {name}")
            continue
        events: List[str] = []
        p = gst.Player(lambda what, _d: events.append(what), audio_sink='fakesink',
                       video_sink='fakesink')
        p.load(out, video=video)
        deadline = time.time() + 20
        while time.time() < deadline and 'eos' not in events and 'error' not in events:
            p.poll()
            time.sleep(0.05)
        duration = p.duration
        p.close()
        if 'eos' in events and duration and 1.5 < duration < 2.5:
            print(f"  play {name}: ok ({duration:.2f} s)")
        else:
            print(f"  play {name}: FAILED (events {events}, duration {duration}, {p.error})")
            failures.append(f"play {name}")
        if video:
            thumb = gst.video_thumbnail(out)
            if thumb is None:
                print("  video thumbnail: FAILED")
                failures.append("video thumbnail")
            else:
                print(f"  video thumbnail: ok ({thumb.width}×{thumb.height})")
    return failures


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: photos, videos "
                                     "and music for SparkOS.")
    parser.add_argument('files', nargs='*', help="files or one folder to open")
    group = parser.add_mutually_exclusive_group()
    for kind, flag in (('photo', '--photos'), ('video', '--videos'), ('music', '--music')):
        group.add_argument(flag, dest='kind', action='store_const', const=kind,
                           help=f"start in {flag[2:].capitalize()}")
    parser.add_argument('--self-test', action='store_true',
                        help="check photo formats, decoders and playback; no display needed")
    parser.add_argument('--require', default='',
                        help="with --self-test: decoders that must exist, e.g. h264,h265,aac")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test([r.strip() for r in args.require.split(',') if r.strip()])
    setup_logging()
    try:
        app = App([path_from_arg(a) for a in args.files], args.kind)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
