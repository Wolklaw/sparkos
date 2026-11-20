"""The app: window, header, switching between the library, the photo viewer and the player,
and the command line."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from PIL import Image

from . import APP_CLASS, APP_ID, APP_NAME, APP_SLUG, KINDS, VERSION
from . import musiclib
from . import player as gst
from . import playlists as m3u
from .core import (folder_items, image_formats, kind_of, load_json, log, natural_key,
                   open_externally, path_from_arg, pick_files, pick_folder, reduced_motion,
                   save_json, setup_logging, siblings, user_dir)
from .library import HomeView
from .musicview import MusicView
from .playview import MusicPlayerView, PlayerView
from .session import MusicSession
from .text import tr
from .viewer import PhotoView
from .widgets import T, Glitch, GlitchText, IconButton, Mark, Strip, WolkButton, pick_mono


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
        # music: the library index, its scanner, and the session that plays
        self._library: Optional[musiclib.Library] = None
        self.scanner: Optional[musiclib.Scanner] = None
        self.scan_progress: Tuple[int, int] = (0, 0)
        self._scan_id: Optional[str] = None
        self._scan_ended = 0.0
        self._library_listeners: List[Callable[[str, Any], None]] = []
        self._music: Optional[MusicSession] = None
        self._covers: Dict[str, Optional[Image.Image]] = {}
        self._build()

        opened = False
        if paths:
            lists = [p for p in paths if os.path.isfile(p) and m3u.is_playlist(p)]
            files = [p for p in paths if os.path.isfile(p) and kind_of(p)]
            if lists:
                opened = self.open_path(lists[0])
            elif files:
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
                    APP_NAME, tr('app.cant_open', path=missing), parent=self.root))
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

    def menu(self, parent: Optional[tk.Misc] = None) -> tk.Menu:
        """A right-click menu in the app's colours."""
        return tk.Menu(parent or self.root, tearoff=0, bg=T["panel2"], fg=T["text"],
                       activebackground=T["hover"], activeforeground=T["accent"],
                       disabledforeground=T["dim"], relief="flat", bd=1,
                       font=self.font(9, False))

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status(tr('status.went_wrong'), T["pink"])
        self.glitch.now(self.title, strong=True)
        messagebox.showerror(APP_NAME, tr('app.unexpected', error=exc_value), parent=self.root)

    # window
    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.minsize(px(560), px(420))

        self.head = tk.Frame(root, bg=bg)
        self.head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.back = IconButton(self.head, "back", self.go_back, px(30), tip=tr('tip.back'))
        self.mark = Mark(self.head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(self.head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK MEDIA", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="● " + tr('status.ready'), bg=bg, fg=T["accent"],
                               font=self.font(7))
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
        self.status.config(text="● " + tr('status.ready'), fg=T["accent"])

    def _swap(self, view: tk.Frame):
        if self.view is not None:
            self.view.destroy()
        self.view = view
        view.pack(fill="both", expand=True)
        is_home = isinstance(view, (HomeView, MusicView))
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
        if kind == 'music' and folder is None and self.settings.get('music_mode') != 'folders':
            self._swap(MusicView(self))
        else:
            self._swap(HomeView(self, kind, folder))
        self.set_window_title(None)
        self.glitch.now(self.title)

    def open_path(self, path: str, playlist: Optional[List[str]] = None,
                  slideshow: bool = False) -> bool:
        if m3u.is_playlist(path):
            return self.open_playlist(path)
        kind = kind_of(path)
        if kind is None:
            messagebox.showerror(APP_NAME, tr('app.wrong_kind', path=path), parent=self.root)
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
        elif kind == 'video':
            self._swap(PlayerView(self, path, files))
        else:
            self.play_songs(files, files.index(path))
            self.show_now_playing()
        self.view.focus_set()
        self.glitch.now(self.title)
        log.info("opened %s (%d in list)", path, len(files))
        return True

    def open_playlist(self, path: str) -> bool:
        try:
            playlist = m3u.read(path)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr('music.playlist_unreadable', error=exc),
                                 parent=self.root)
            return False
        items = [p for p in playlist.items if kind_of(p) in ('music', None)]
        if not items:
            messagebox.showerror(APP_NAME, tr('music.playlist_nothing', name=playlist.name),
                                 parent=self.root)
            return False
        self.settings["kind"] = 'music'
        self.play_songs(items, 0)
        self.show_now_playing()
        self.view.focus_set()
        log.info("opened playlist %s (%d songs, %d skipped)", path, len(items),
                 len(playlist.skipped))
        return True

    def go_back(self):
        handler = getattr(self.view, 'back', None)
        if handler is not None and handler():
            return
        if isinstance(self.view, (HomeView, MusicView)):
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
        if isinstance(event.widget, tk.Entry) and k != 'Escape':
            return None                          # typing in a search box
        if isinstance(event.widget, tk.Listbox) and k in ('Up', 'Down', 'Return', 'Prior', 'Next'):
            return None
        home = isinstance(self.view, (HomeView, MusicView))
        if k in ('F11',) or (k in ('f', 'F') and not home and not event.state & 0x4):
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

    # ── music: the session ──
    @property
    def music(self) -> MusicSession:
        if self._music is None:
            self._music = MusicSession(self)
        return self._music

    def music_if_started(self) -> Optional[MusicSession]:
        return self._music

    def play_songs(self, paths: List[str], start: int = 0, shuffle: bool = False):
        self.music.play(paths, start, shuffle)
        if self.music.problem:
            self.set_status(tr('status.play_error'), T["pink"])

    def queue_songs(self, paths: List[str], next_: bool = False):
        if next_:
            self.music.play_next(paths)
        else:
            self.music.add(paths)

    def pause_music(self):
        if self._music is not None:
            self._music.pause()

    def show_now_playing(self):
        if self.fullscreen:
            self.toggle_fullscreen()
        self.settings["kind"] = 'music'
        self._swap(MusicPlayerView(self))
        self.glitch.now(self.title)

    # ── music: the library ──
    def library(self) -> musiclib.Library:
        if self._library is None:
            self._library = musiclib.Library.load()
        return self._library

    def music_roots(self) -> List[str]:
        roots = [user_dir('music')]
        extra = self.settings.get('music_folders')
        if isinstance(extra, list):
            for folder in extra:
                if isinstance(folder, str) and folder not in roots:
                    roots.append(folder)
        return roots

    def scanning(self) -> bool:
        return self.scanner is not None and self.scanner.running

    def start_scan(self, force: bool = False):
        """Bring the library up to date with the disk, in the background. Opening the music
        library does this; it's skipped if a scan finished in the last 30 seconds."""
        if self.scanning():
            return
        if not force and self._scan_ended and time.monotonic() - self._scan_ended < 30:
            return
        self.scanner = musiclib.Scanner(self.library(), self.music_roots())
        self.scan_progress = (0, 0)
        self.scanner.start()
        if self._scan_id is None:
            self._scan_id = self.root.after(200, self._scan_tick)

    def _scan_tick(self):
        self._scan_id = None
        if self.scanner is None:
            return
        for what, data in self.scanner.poll():
            if what == 'start':
                self.scan_progress = (0, data['total'])
            elif what == 'progress':
                self.scan_progress = (data, self.scan_progress[1])
            elif what == 'done':
                self.scan_progress = (self.scan_progress[1], self.scan_progress[1])
                self._scan_ended = time.monotonic()
                self._covers.clear()
            elif what == 'error':
                self.set_status(tr('status.scan_failed'), T["pink"])
            for fn in list(self._library_listeners):
                fn(what, data)
        if self.scanner.running:
            self._scan_id = self.root.after(200, self._scan_tick)     # only while scanning

    def on_library(self, fn: Callable[[str, Any], None]):
        if fn not in self._library_listeners:
            self._library_listeners.append(fn)

    def off_library(self, fn: Callable[[str, Any], None]):
        if fn in self._library_listeners:
            self._library_listeners.remove(fn)

    def song_info(self, path: str) -> Optional[Dict[str, Any]]:
        return self._library.song(path) if self._library is not None else None

    def album_cover(self, path: str) -> Optional[Image.Image]:
        """The cached cover of the album a song is on, if the library has one."""
        song = self.song_info(path)
        if song is None:
            return None
        key = musiclib.Album(musiclib.album_key(song), '').cover_id
        if key not in self._covers:
            if len(self._covers) > 64:
                self._covers.clear()
            self._covers[key] = musiclib.load_cover(key)
        return self._covers[key]

    def edit_music_folders(self):
        FoldersDialog(self)

    def show_in_folder(self, path: str):
        problem = open_externally(path)
        if problem:
            self.set_status(problem.upper(), T["pink"])

    # ── playlists ──
    def write_playlist(self, path: str, items: List[str]):
        info = []
        for item in items:
            song = self.song_info(item)
            if song:
                title = song.get('title') or ''
                artist = song.get('artist') or ''
                label = f"{artist} - {title}" if artist and title else (title or None)
                info.append((song.get('length') or None, label))
            else:
                info.append((None, None))
        m3u.write(path, items, info)
        lib = self.library()
        if path not in lib.playlists:
            lib.playlists.append(path)
            lib.playlists.sort(key=lambda p: natural_key(os.path.basename(p)))

    def save_as_playlist(self, items: List[str], name: Optional[str] = None) -> Optional[str]:
        """Make a playlist in Music/Playlists, asking for its name unless given."""
        while True:
            if name is None:
                name = ask_text(self, tr('playlist.new_title'), tr('playlist.name_prompt'))
                if name is None:
                    return None
            path = m3u.new_path(self.music_roots()[0], name)
            if path is not None:
                break
            messagebox.showerror(tr('playlist.new_title'),
                                 tr('playlist.name_taken', name=name) if m3u.safe_name(name)
                                 else tr('playlist.name_empty'), parent=self.root)
            name = None
        try:
            self.write_playlist(path, items)
        except OSError as exc:
            messagebox.showerror(tr('playlist.new_title'), str(exc), parent=self.root)
            return None
        self.set_status(tr('status.playlist_saved', name=os.path.splitext(
            os.path.basename(path))[0]), T["accent"])
        return path

    def _on_close(self):
        if not self.fullscreen and self.root.state() == 'normal':
            self.settings["geometry"] = self.root.geometry()
        self.settings["folders"] = self.last_folder
        self.settings["version"] = VERSION
        if self.view is not None:
            self.view.destroy()
            self.view = None
        if self._music is not None:
            self._music.close()
            self._music = None
        if self.scanner is not None and self.scanner.running:
            self.scanner.stop()
            if self.scanner.thread is not None:
                self.scanner.thread.join(timeout=2)
            self.scanner.poll(limit=100000)            # keep what it found so far
            if self._library is not None:
                self._library.save()
        save_json('config.json', self.settings)
        log.info("--- shutting down ---")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def ask_text(app: App, title: str, prompt: str, initial: str = '') -> Optional[str]:
    """A small dialog with one line of text. None if cancelled."""
    px = app.px
    top = tk.Toplevel(app.root, bg=T["panel"])
    top.title(title)
    top.transient(app.root)
    top.resizable(False, False)
    tk.Label(top, text=prompt, bg=T["panel"], fg=T["text"], font=app.font(9),
             anchor="w").pack(fill="x", padx=px(16), pady=(px(14), px(6)))
    edge = tk.Frame(top, bg=T["line2"], padx=1, pady=1)
    edge.pack(fill="x", padx=px(16))
    value = tk.StringVar(value=initial)
    entry = tk.Entry(edge, textvariable=value, bg=T["bg"], fg=T["text"], relief="flat", bd=0,
                     insertbackground=T["accent"], font=app.font(10, False), width=36)
    entry.pack(fill="x", ipady=px(4), padx=px(4))
    result: List[Optional[str]] = [None]

    def ok(_e=None):
        result[0] = value.get().strip()
        top.destroy()

    row = tk.Frame(top, bg=T["panel"])
    row.pack(fill="x", padx=px(16), pady=px(14))
    WolkButton(row, tr('btn.ok'), ok, app.font(8), variant="primary", padx=px(10),
               pady=px(3)).pack(side="right")
    WolkButton(row, tr('btn.cancel'), top.destroy, app.font(8), padx=px(10),
               pady=px(3)).pack(side="right", padx=(0, px(6)))
    entry.bind("<Return>", ok)
    entry.bind("<Escape>", lambda _e: top.destroy())
    entry.focus_set()
    top.update_idletasks()
    x = app.root.winfo_rootx() + (app.root.winfo_width() - top.winfo_width()) // 2
    y = app.root.winfo_rooty() + (app.root.winfo_height() - top.winfo_height()) // 3
    top.geometry(f"+{max(0, x)}+{max(0, y)}")
    try:
        top.grab_set()
    except tk.TclError:
        pass
    app.root.wait_window(top)
    return result[0] or None


class FoldersDialog:
    """The folders the music library reads: Music always, plus any you add."""

    def __init__(self, app: App):
        self.app = app
        px = app.px
        self.top = top = tk.Toplevel(app.root, bg=T["panel"])
        top.title(tr('folders.title'))
        top.transient(app.root)
        tk.Label(top, text=tr('folders.intro'), bg=T["panel"], fg=T["muted"],
                 font=app.font(8, False), anchor="w", justify="left",
                 wraplength=px(440)).pack(fill="x", padx=px(16), pady=(px(14), px(8)))
        edge = tk.Frame(top, bg=T["line"], padx=1, pady=1)
        edge.pack(fill="both", expand=True, padx=px(16))
        self.listbox = tk.Listbox(edge, bg=T["bg"], fg=T["text"], font=app.font(9, False),
                                  bd=0, highlightthickness=0, activestyle="none", width=56,
                                  height=7, selectbackground=T["hover"],
                                  selectforeground=T["accent"], exportselection=False)
        self.listbox.pack(fill="both", expand=True)
        row = tk.Frame(top, bg=T["panel"])
        row.pack(fill="x", padx=px(16), pady=px(14))
        WolkButton(row, tr('btn.done'), self.close, app.font(8), variant="primary", padx=px(10),
                   pady=px(3)).pack(side="right")
        self.remove_btn = WolkButton(row, tr('folders.remove'), self.remove, app.font(8),
                                     variant="danger", padx=px(10), pady=px(3))
        self.remove_btn.pack(side="left", padx=(px(6), 0))
        WolkButton(row, tr('folders.add'), self.add, app.font(8), padx=px(10),
                   pady=px(3)).pack(side="left")
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._paint())
        top.protocol("WM_DELETE_WINDOW", self.close)
        self.changed = False
        self.fill()

    def fill(self):
        self.listbox.delete(0, "end")
        roots = self.app.music_roots()
        for i, root in enumerate(roots):
            self.listbox.insert("end", ("  " + root) + (f"   ({tr('folders.music')})" if i == 0 else ""))
        self._paint()

    def _paint(self):
        sel = self.listbox.curselection()
        self.remove_btn.set_enabled(bool(sel) and sel[0] > 0)

    def add(self):
        folder = pick_folder(os.path.expanduser('~'))
        if folder and folder not in self.app.music_roots():
            extra = [f for f in self.app.settings.get('music_folders') or [] if isinstance(f, str)]
            self.app.settings['music_folders'] = extra + [folder]
            self.changed = True
            self.fill()

    def remove(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] == 0:
            return
        folder = self.app.music_roots()[sel[0]]
        extra = [f for f in self.app.settings.get('music_folders') or [] if f != folder]
        self.app.settings['music_folders'] = extra
        self.changed = True
        self.fill()

    def close(self):
        self.top.destroy()
        if self.changed:
            self.app.start_scan(force=True)


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
    # what reads music tags and develops camera RAW here (reported, not required)
    from . import raw, tags
    print(f"music tags: {tags.backend()}")
    print(f"camera raw: built-in preview: yes   full decode: {raw.decoder() or 'no (no LibRaw)'}")

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
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=tr('cli.description'))
    parser.add_argument('files', nargs='*', help=tr('cli.files'))
    group = parser.add_mutually_exclusive_group()
    for kind, flag in (('photo', '--photos'), ('video', '--videos'), ('music', '--music')):
        group.add_argument(flag, dest='kind', action='store_const', const=kind,
                           help=tr(f'cli.start_{kind}'))
    parser.add_argument('--self-test', action='store_true', help=tr('cli.self_test'))
    parser.add_argument('--require', default='', help=tr('cli.require'))
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test([r.strip() for r in args.require.split(',') if r.strip()])
    setup_logging()
    try:
        app = App([path_from_arg(a) for a in args.files], args.kind)
    except tk.TclError as exc:
        print(tr("cli.need_display", error=exc), file=sys.stderr)
        return 1
    app.run()
    return 0
