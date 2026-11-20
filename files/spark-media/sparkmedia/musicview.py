"""The music library screen: Artists, Albums (a cover grid), Songs and Playlists, an artist's
albums, an album's or a playlist's songs, and the now-playing bar at the bottom."""

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk

from . import musiclib
from . import playlists as m3u
from .core import clock, move_to_trash, pick_files
from .listviews import RowList, TileGrid
from .musiclib import display_title, matches, search_words
from .text import plural, tr
from .widgets import T, IconButton, Segmented, WolkButton

TABS = ('artists', 'albums', 'songs', 'playlists')
REFRESH_DURING_SCAN_MS = 1500


def duration_text(seconds: float) -> str:
    seconds = int(seconds or 0)
    if seconds >= 3600:
        return tr('time.hours_minutes', h=seconds // 3600, m=(seconds % 3600) // 60)
    return tr('time.minutes', n=max(1, round(seconds / 60))) if seconds else ''


class NowPlayingBar(tk.Frame):
    """What's playing, at the bottom of the library: click it for the full player."""

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["panel"])
        self.app = app
        px = app.px
        tk.Frame(self, bg=T["line"], height=1).pack(fill="x")
        row = tk.Frame(self, bg=T["panel"])
        row.pack(fill="x", padx=px(10), pady=px(6))
        self.cover = tk.Canvas(row, width=px(36), height=px(36), bg=T["tile"],
                               highlightthickness=0, bd=0, cursor="hand2")
        self.cover.pack(side="left")
        text = tk.Frame(row, bg=T["panel"], cursor="hand2")
        text.pack(side="left", fill="x", expand=True, padx=(px(10), 0))
        self.title = tk.Label(text, text="", bg=T["panel"], fg=T["text"], font=app.font(9),
                              anchor="w", cursor="hand2")
        self.title.pack(fill="x")
        self.sub = tk.Label(text, text="", bg=T["panel"], fg=T["muted"],
                            font=app.font(8, False), anchor="w", cursor="hand2")
        self.sub.pack(fill="x")
        for widget in (self.cover, text, self.title, self.sub):
            widget.bind("<ButtonRelease-1>", lambda _e: app.show_now_playing())
        size = px(28)
        self.next_btn = IconButton(row, "next", self._next, size, tip=tr('tip.next'))
        self.next_btn.pack(side="right")
        self.play_btn = IconButton(row, "play", self._toggle, px(32), accent=True,
                                   tip=tr('tip.play'))
        self.play_btn.pack(side="right", padx=px(4))
        self.prev_btn = IconButton(row, "prev", self._prev, size, tip=tr('tip.prev'))
        self.prev_btn.pack(side="right")
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._shown_for: Optional[str] = None
        self.session = None
        self.attach()

    def attach(self):
        """Start following the music session, once there is one."""
        session = self.app.music_if_started()
        if session is not None and self.session is None:
            self.session = session
            session.listen(self._on_session)
        self.refresh()

    def _on_session(self, what: str, _data: Any):
        if what in ('track', 'state', 'tags', 'finished', 'error', 'queue'):
            self.refresh()

    def refresh(self):
        session = self.session
        if session is None or session.current is None:
            if self.winfo_ismapped():
                self.pack_forget()
            return
        if not self.winfo_ismapped():
            self.pack(side="bottom", fill="x")
        info = session.info()
        self.title.config(text=info['title'])
        self.sub.config(text=" · ".join(x for x in (info['artist'], info['album']) if x))
        self.play_btn.set_icon("pause" if session.playing else "play")
        if self._shown_for != session.current:
            self._shown_for = session.current
            self.cover.delete("all")
            image = self.app.album_cover(session.current)
            side = int(self.cover.cget("width"))
            if image is not None:
                image = image.copy()
                image.thumbnail((side, side))
                self._photo = ImageTk.PhotoImage(image)
                self.cover.create_image(side / 2, side / 2, image=self._photo)
            else:
                from .playview import draw_note
                draw_note(self.cover, side / 2, side / 2, side / 40)

    def _toggle(self):
        if self.session:
            self.session.toggle()

    def _next(self):
        if self.session:
            self.session.next()

    def _prev(self):
        if self.session:
            self.session.prev()

    def destroy(self):
        if self.session is not None:
            self.session.unlisten(self._on_session)
        super().destroy()


class MusicView(tk.Frame):
    kind = 'music'

    def __init__(self, app, page: Optional[Tuple[str, Any]] = None):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.library = app.library()
        px, font = app.px, app.font

        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        self.switch = Segmented(bar, [(tr('kind.photo'), 'photo'), (tr('kind.video'), 'video'),
                                      (tr('kind.music'), 'music')], 'music',
                                lambda k: app.show_home(k), font(8))
        self.switch.pack(side="left")
        WolkButton(bar, tr('btn.library_folders'), self._folders, font(8), padx=px(10),
                   pady=px(3)).pack(side="right")
        WolkButton(bar, tr('btn.by_folder'), self._by_folder, font(8), padx=px(10),
                   pady=px(3)).pack(side="right", padx=(0, px(6)))
        WolkButton(bar, tr('btn.open_files'), self._open_files, font(8), padx=px(10),
                   pady=px(3)).pack(side="right", padx=(0, px(6)))

        nav = tk.Frame(self, bg=T["bg"])
        nav.pack(fill="x", padx=px(16), pady=(0, px(8)))
        self.tabs = Segmented(nav, [(tr(f'tab.{t}'), t) for t in TABS], 'albums', self._tab,
                              font(8))
        self.tabs.pack(side="left")
        tk.Label(nav, text=tr('music.filter'), bg=T["bg"], fg=T["dim"],
                 font=font(7)).pack(side="left", padx=(px(14), px(6)))
        self.filter_var = tk.StringVar()
        edge = tk.Frame(nav, bg=T["line2"], padx=1, pady=1)
        edge.pack(side="left")
        self.filter = tk.Entry(edge, textvariable=self.filter_var, bg=T["panel"], fg=T["text"],
                               insertbackground=T["accent"], relief="flat", bd=0,
                               font=font(9, False), width=24, highlightthickness=0)
        self.filter.pack(ipady=px(3), padx=px(4))
        self.filter_var.trace_add('write', lambda *_a: self._filter_soon())
        self.filter.bind("<Escape>", self._clear_filter)
        self.filter.bind("<Down>", lambda _e: self._focus_list())
        self.status = tk.Label(nav, text="", bg=T["bg"], fg=T["dim"], font=font(7), anchor="e")
        self.status.pack(side="right")

        tk.Frame(self, bg=T["line"], height=1).pack(fill="x", padx=px(16))
        self.now_bar = NowPlayingBar(self, app)
        self.header = tk.Frame(self, bg=T["bg"])
        self.header.pack(fill="x", padx=px(16), pady=(px(10), 0))
        self.body = tk.Frame(self, bg=T["bg"])
        self.body.pack(fill="both", expand=True, padx=(px(16), px(4)), pady=(px(10), px(8)))
        self.list: Optional[Any] = None
        self.items: List[Any] = []            # what each row or tile stands for
        self._filter_id: Optional[str] = None
        self._refresh_id: Optional[str] = None
        self._header_cover: Optional[ImageTk.PhotoImage] = None

        first = page or (app.settings.get('music_tab') if app.settings.get('music_tab') in TABS
                         else 'albums', None)
        self.stack: List[Tuple[str, Any]] = [first]
        app.on_library(self._library_event)
        app.start_scan()
        if app.music_if_started() is not None:
            app.music.listen(self._on_session)
        self.show()
        self._update_status()

    # ── pages ──
    @property
    def page(self) -> Tuple[str, Any]:
        return self.stack[-1]

    def _tab(self, tab: str):
        self.app.settings['music_tab'] = tab
        self.stack = [(tab, None)]
        self.filter_var.set('')
        self.show()

    def open_page(self, kind: str, arg: Any):
        self.stack.append((kind, arg))
        self.filter_var.set('')
        self.show()
        self.app.glitch.now(self.app.title)

    def back(self) -> bool:
        """Esc and Backspace: up one page. False on a tab's first page."""
        if len(self.stack) > 1:
            self.stack.pop()
            self.filter_var.set('')
            self.show()
            return True
        return False

    def show(self, keep_scroll: bool = False):
        kind, arg = self.page
        root_tab = self.stack[0][0]
        self.tabs.set(root_tab)
        words = search_words(self.filter_var.get())
        builder = getattr(self, f'_page_{kind}')
        if not keep_scroll:
            for child in self.header.winfo_children():
                child.destroy()
        builder(arg, words, keep_scroll)

    def _set_list(self, kind: str, columns=None, on_activate=None, on_menu=None):
        """The body's list: reuse it when the page shows the same kind of list."""
        want = (kind, tuple(columns) if columns else None)
        if self.list is not None and getattr(self.list, '_want', None) == want:
            self.list.on_activate, self.list.on_menu = on_activate, on_menu
            return self.list
        if self.list is not None:
            self.list.destroy()
        if kind == 'grid':
            self.list = TileGrid(self.body, self.app, on_activate, on_menu,
                                 load=musiclib.load_cover)
        else:
            self.list = RowList(self.body, self.app, columns, on_activate, on_menu)
        self.list._want = want
        self.list.pack(fill="both", expand=True)
        return self.list

    def _empty(self, words: Sequence[str], nothing: str) -> str:
        if words:
            return tr('music.no_match', text=self.filter_var.get().strip())
        if not self.library.songs:
            return tr('music.scanning') if self.app.scanning() else \
                tr('music.empty', folders=', '.join(self._short(r) for r in self.app.music_roots()))
        return nothing

    def _short(self, path: str) -> str:
        home = os.path.expanduser('~')
        return '~' + path[len(home):] if path.startswith(home) else path

    def _header(self, title: str, sub: str, buttons: Sequence[Tuple[str, Callable, str]],
                cover: Optional[Image.Image] = None, back: bool = True):
        px = self.app.px
        for child in self.header.winfo_children():
            child.destroy()
        if back:
            IconButton(self.header, "back", self.back, px(26),
                       tip=tr('tip.back')).pack(side="left", anchor="n", padx=(0, px(8)))
        if cover is not None:
            side = px(72)
            image = cover.copy()
            image.thumbnail((side, side))
            self._header_cover = ImageTk.PhotoImage(image)
            tk.Label(self.header, image=self._header_cover, bg=T["bg"], bd=0).pack(
                side="left", padx=(0, px(12)))
        col = tk.Frame(self.header, bg=T["bg"])
        col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text=title, bg=T["bg"], fg=T["text"], font=self.app.font(12),
                 anchor="w").pack(fill="x")
        if sub:
            tk.Label(col, text=sub, bg=T["bg"], fg=T["muted"], font=self.app.font(8, False),
                     anchor="w").pack(fill="x", pady=(px(2), 0))
        for text, command, variant in reversed(buttons):
            WolkButton(self.header, text, command, self.app.font(8), variant=variant,
                       padx=px(10), pady=px(3)).pack(side="right", anchor="n", padx=(px(6), 0))

    # Artists
    def _page_artists(self, _arg, words, keep):
        artists = [a for a in self.library.artists()
                   if not words or matches(words, a['name'])]
        self.items = artists
        lst = self._set_list('rows', [('name', 0.7, 'w'), ('albums', 0.3, 'w')],
                             lambda i: self.open_page('artist', self.items[i]['name']),
                             self._artist_menu)
        lst.empty_text = self._empty(words, '')
        lst.set_rows([(a['name'] or tr('music.unknown_artist'),
                       plural(len(a['albums']), 'count.album', 'count.albums') + "  ·  " +
                       plural(len(a['songs']), 'count.song', 'count.songs'))
                      for a in artists], keep_scroll=keep)

    # Albums (grid)
    def _album_tiles(self, albums: Sequence[musiclib.Album]):
        return [(a.cover_id, a.title or tr('music.unknown_album'),
                 " · ".join(x for x in (a.artist or tr('music.various'),
                                        str(a.year) if a.year else '') if x))
                for a in albums]

    def _page_albums(self, _arg, words, keep):
        albums = [a for a in self.library.albums() if not words or matches(words, a.title, a.artist)]
        self.items = albums
        grid = self._set_list('grid', on_activate=lambda i: self.open_page('album', self.items[i].key),
                              on_menu=self._album_menu)
        grid.empty_text = self._empty(words, '')
        grid.set_tiles(self._album_tiles(albums), keep_scroll=keep)

    # Songs
    SONG_COLUMNS = [('title', 0.42, 'w'), ('artist', 0.25, 'w'), ('album', 0.33, 'w'),
                    ('length', 56, 'e')]

    def _song_rows(self, songs: Sequence[Dict[str, Any]], number: bool = False):
        rows = []
        for n, s in enumerate(songs):
            row = (display_title(s), s.get('artist') or '', s.get('album') or '',
                   clock(s['length']) if s.get('length') else '')
            if number:
                row = (str(s.get('track') or n + 1) if number == 'track' else str(n + 1),) + row[:2] + row[3:]
            rows.append(row)
        return rows

    def _marks(self, paths: Sequence[str], missing: bool = False) -> List[str]:
        current = self.app.music_if_started().current if self.app.music_if_started() else None
        return ['current' if p == current else ('dim' if missing and not os.path.exists(p) else '')
                for p in paths]

    def _page_songs(self, _arg, words, keep):
        songs = [s for s in self.library.all_songs()
                 if not words or matches(words, display_title(s), s.get('artist'), s.get('album'))]
        self.items = songs
        lst = self._set_list('rows', self.SONG_COLUMNS, self._play_from_list, self._song_menu)
        lst.empty_text = self._empty(words, '')
        lst.set_rows(self._song_rows(songs), self._marks([s['path'] for s in songs]),
                     keep_scroll=keep)

    # Playlists
    def _page_playlists(self, _arg, words, keep):
        lists = [p for p in self.library.playlists
                 if not words or matches(words, os.path.basename(p))]
        self.items = lists
        self._header(tr('tab.playlists'), tr('music.playlists_where',
                                            folder=self._short(m3u.folder(self.app.music_roots()[0]))),
                     [(tr('btn.new_playlist'), self._new_playlist, 'primary')], back=False)
        lst = self._set_list('rows', [('name', 0.45, 'w'), ('folder', 0.55, 'w')],
                             lambda i: self.open_page('playlist', self.items[i]),
                             self._playlist_menu)
        lst.empty_text = self._empty(words, tr('music.no_playlists'))
        lst.set_rows([(os.path.splitext(os.path.basename(p))[0], self._short(os.path.dirname(p)))
                      for p in lists], keep_scroll=keep)

    # One artist
    def _page_artist(self, name, words, keep):
        artist = self.library.artist(name)
        if artist is None:
            return self.back() or self._tab(self.stack[0][0])
        albums = [a for a in artist['albums'] if not words or matches(words, a.title)]
        self.items = albums
        paths = [s['path'] for s in artist['songs']]
        self._header(name or tr('music.unknown_artist'),
                     plural(len(artist['albums']), 'count.album', 'count.albums') + "  ·  " +
                     plural(len(paths), 'count.song', 'count.songs'),
                     [(tr('btn.play'), lambda: self._play(paths), 'primary'),
                      (tr('btn.shuffle'), lambda: self._play(paths, shuffle=True), 'ghost'),
                      (tr('btn.add_queue'), lambda: self._queue(paths), 'ghost')])
        grid = self._set_list('grid', on_activate=lambda i: self.open_page('album', self.items[i].key),
                              on_menu=self._album_menu)
        grid.empty_text = self._empty(words, '')
        grid.set_tiles(self._album_tiles(albums), keep_scroll=keep)

    # One album
    ALBUM_COLUMNS = [('n', 34, 'e'), ('title', 0.6, 'w'), ('artist', 0.4, 'w'), ('length', 56, 'e')]

    def _page_album(self, key, words, keep):
        album = self.library.album(key)
        if album is None:
            return self.back() or self._tab(self.stack[0][0])
        songs = [s for s in album.songs if not words or matches(words, display_title(s), s.get('artist'))]
        self.items = songs
        paths = [s['path'] for s in album.songs]
        facts = [album.artist or tr('music.various'), str(album.year) if album.year else '',
                 plural(len(album.songs), 'count.song', 'count.songs'),
                 duration_text(album.length)]
        if not keep:
            self._header(album.title or tr('music.unknown_album'),
                         "  ·  ".join(f for f in facts if f),
                         [(tr('btn.play'), lambda: self._play(paths), 'primary'),
                          (tr('btn.shuffle'), lambda: self._play(paths, shuffle=True), 'ghost'),
                          (tr('btn.add_queue'), lambda: self._queue(paths), 'ghost'),
                          (tr('btn.add_playlist'), lambda: self._add_to_playlist_menu(paths), 'ghost')],
                         cover=musiclib.load_cover(album.cover_id))
        lst = self._set_list('rows', self.ALBUM_COLUMNS, self._play_from_list, self._song_menu)
        lst.empty_text = self._empty(words, '')
        lst.set_rows(self._song_rows(songs, number='track'),
                     self._marks([s['path'] for s in songs]), keep_scroll=keep)

    # One playlist
    def _page_playlist(self, path, words, keep):
        try:
            playlist = m3u.read(path)
        except OSError as exc:
            messagebox.showerror(tr('tab.playlists'), tr('music.playlist_unreadable', error=exc),
                                 parent=self)
            return self.back()
        self.playlist = playlist
        songs = []
        for i, item in enumerate(playlist.items):
            song = self.library.song(item) or {
                'path': item, 'title': playlist.titles[i] or '', 'artist': '', 'album': '',
                'length': playlist.durations[i] or 0}
            songs.append(song)
        shown = [(i, s) for i, s in enumerate(songs)
                 if not words or matches(words, display_title(s), s.get('artist'))]
        self.items = [s for _i, s in shown]
        self._playlist_rows = [i for i, _s in shown]
        paths = [s['path'] for s in songs]
        missing = sum(1 for p in paths if not os.path.exists(p))
        facts = [plural(len(paths), 'count.song', 'count.songs'),
                 duration_text(sum(s.get('length') or 0 for s in songs)),
                 tr('music.missing', n=missing) if missing else '',
                 tr('music.streams_skipped', n=len(playlist.skipped)) if playlist.skipped else '']
        if not keep:
            self._header(playlist.name, "  ·  ".join(f for f in facts if f),
                         [(tr('btn.play'), lambda: self._play(paths), 'primary'),
                          (tr('btn.shuffle'), lambda: self._play(paths, shuffle=True), 'ghost'),
                          (tr('btn.add_queue'), lambda: self._queue(paths), 'ghost'),
                          (tr('btn.delete'), lambda: self._delete_playlist(path), 'danger')])
        lst = self._set_list('rows', self.ALBUM_COLUMNS, self._play_from_list, self._song_menu)
        lst.empty_text = self._empty(words, tr('music.playlist_empty'))
        lst.set_rows(self._song_rows(self.items, number='index'),
                     self._marks([s['path'] for s in self.items], missing=True), keep_scroll=keep)

    # ── playing ──
    def _play(self, paths: Sequence[str], start: int = 0, shuffle: bool = False):
        if paths:
            self.app.play_songs(list(paths), start, shuffle)
            self._after_play()

    def _queue(self, paths: Sequence[str], next_: bool = False):
        if paths:
            self.app.queue_songs(list(paths), next_)
            self._after_play()
            self.app.set_status(plural(len(paths), 'status.queued_one', 'status.queued_many'),
                                T["accent"])

    def _after_play(self):
        session = self.app.music_if_started()
        if session is not None:
            session.listen(self._on_session)
            self._on_session('track', None)
        self.now_bar.attach()

    def _play_from_list(self, index: int):
        paths = [s['path'] for s in self.items]
        self._play(paths, index)

    def _on_session(self, what: str, _data: Any):
        if what == 'track' and self.list is not None and isinstance(self.list, RowList) \
                and self.page[0] in ('songs', 'album', 'playlist'):
            self.list.marks = self._marks([s['path'] for s in self.items],
                                          missing=self.page[0] == 'playlist')
            self.list.redraw()

    # ── menus ──
    def _song_menu(self, index: int, event):
        song = self.items[index]
        path = song['path']
        menu = self.app.menu()
        menu.add_command(label=tr('menu.play'), command=lambda: self._play_from_list(index))
        menu.add_command(label=tr('menu.play_next'), command=lambda: self._queue([path], True))
        menu.add_command(label=tr('menu.add_queue'), command=lambda: self._queue([path]))
        menu.add_cascade(label=tr('menu.add_playlist'), menu=self._playlists_submenu(menu, [path]))
        if self.page[0] == 'playlist':
            row = self._playlist_rows[index]
            menu.add_separator()
            menu.add_command(label=tr('menu.move_up'), command=lambda: self._move_in_playlist(row, -1))
            menu.add_command(label=tr('menu.move_down'), command=lambda: self._move_in_playlist(row, 1))
            menu.add_command(label=tr('menu.remove_playlist'),
                             command=lambda: self._remove_from_playlist(row))
        known = self.library.song(path)
        if known:
            menu.add_separator()
            key = musiclib.album_key(known)
            if self.page != ('album', key):
                menu.add_command(label=tr('menu.go_album'),
                                 command=lambda: self.open_page('album', key))
            name = known.get('albumartist') or known.get('artist') or ''
            if self.page != ('artist', name):
                menu.add_command(label=tr('menu.go_artist'),
                                 command=lambda: self.open_page('artist', name))
        menu.add_command(label=tr('menu.show_folder'), command=lambda: self.app.show_in_folder(path))
        menu.tk_popup(event.x_root, event.y_root)

    def _album_menu(self, index: int, event):
        album = self.items[index]
        paths = [s['path'] for s in album.songs]
        self._group_menu(paths, event)

    def _artist_menu(self, index: int, event):
        paths = [s['path'] for s in self.items[index]['songs']]
        self._group_menu(paths, event)

    def _group_menu(self, paths: List[str], event):
        menu = self.app.menu()
        menu.add_command(label=tr('menu.play'), command=lambda: self._play(paths))
        menu.add_command(label=tr('menu.shuffle'), command=lambda: self._play(paths, shuffle=True))
        menu.add_command(label=tr('menu.play_next'), command=lambda: self._queue(paths, True))
        menu.add_command(label=tr('menu.add_queue'), command=lambda: self._queue(paths))
        menu.add_cascade(label=tr('menu.add_playlist'), menu=self._playlists_submenu(menu, paths))
        menu.tk_popup(event.x_root, event.y_root)

    def _playlist_menu(self, index: int, event):
        path = self.items[index]
        menu = self.app.menu()
        menu.add_command(label=tr('menu.open'), command=lambda: self.open_page('playlist', path))
        menu.add_command(label=tr('menu.play'), command=lambda: self._play_playlist(path))
        menu.add_command(label=tr('menu.show_folder'), command=lambda: self.app.show_in_folder(path))
        menu.add_separator()
        menu.add_command(label=tr('menu.delete_playlist'),
                         command=lambda: self._delete_playlist(path))
        menu.tk_popup(event.x_root, event.y_root)

    def _playlists_submenu(self, parent: tk.Menu, paths: List[str]) -> tk.Menu:
        sub = self.app.menu(parent)
        sub.add_command(label=tr('menu.new_playlist'), command=lambda: self._new_playlist(paths))
        if self.library.playlists:
            sub.add_separator()
        for pl in self.library.playlists[:40]:
            sub.add_command(label=os.path.splitext(os.path.basename(pl))[0],
                            command=lambda pl=pl: self._append_to_playlist(pl, paths))
        return sub

    def _add_to_playlist_menu(self, paths: List[str]):
        menu = self._playlists_submenu(self.app.menu(), paths)
        x, y = self.winfo_pointerxy()
        menu.tk_popup(x, y)

    # ── playlist changes ──
    def _play_playlist(self, path: str):
        try:
            self._play(m3u.read(path).items)
        except OSError as exc:
            messagebox.showerror(tr('tab.playlists'), tr('music.playlist_unreadable', error=exc),
                                 parent=self)

    def _new_playlist(self, paths: Optional[List[str]] = None):
        made = self.app.save_as_playlist(paths or [])
        if made and self.page[0] == 'playlists':
            self.show(keep_scroll=True)

    def _append_to_playlist(self, playlist_path: str, paths: List[str]):
        try:
            current = m3u.read(playlist_path)
            self.app.write_playlist(playlist_path, current.items + list(paths))
        except OSError as exc:
            messagebox.showerror(tr('tab.playlists'), str(exc), parent=self)
            return
        self.app.set_status(tr('status.added_to', name=os.path.splitext(
            os.path.basename(playlist_path))[0]), T["accent"])

    def _rewrite_playlist(self, change: Callable[[List[str]], List[str]]):
        path = self.page[1]
        try:
            items = change(m3u.read(path).items)
            self.app.write_playlist(path, items)
        except OSError as exc:
            messagebox.showerror(tr('tab.playlists'), str(exc), parent=self)
            return
        self.show(keep_scroll=True)

    def _remove_from_playlist(self, row: int):
        self._rewrite_playlist(lambda items: items[:row] + items[row + 1:])

    def _move_in_playlist(self, row: int, delta: int):
        def change(items):
            to = max(0, min(len(items) - 1, row + delta))
            items.insert(to, items.pop(row))
            return items
        self._rewrite_playlist(change)
        if self.list is not None:
            self.list.select(self.list.selected + delta)

    def _delete_playlist(self, path: str):
        name = os.path.splitext(os.path.basename(path))[0]
        if not messagebox.askyesno(tr('menu.delete_playlist'),
                                   tr('music.delete_playlist_q', name=name), parent=self):
            return
        problem = move_to_trash(path)
        if problem:
            messagebox.showerror(tr('menu.delete_playlist'), problem, parent=self)
            return
        if path in self.library.playlists:
            self.library.playlists.remove(path)
        self.app.set_status(tr('status.trashed'), T["accent"])
        if self.page[0] == 'playlist':
            self.back()
        else:
            self.show(keep_scroll=True)

    # ── buttons ──
    def _open_files(self):
        paths = pick_files('music', self.app.music_roots()[0])
        if paths:
            self.app.open_path(paths[0], playlist=paths if len(paths) > 1 else None)

    def _by_folder(self):
        self.app.settings['music_mode'] = 'folders'
        self.app.show_home('music')

    def _folders(self):
        self.app.edit_music_folders()

    # ── filter ──
    def _filter_soon(self):
        if self._filter_id:
            self.after_cancel(self._filter_id)
        self._filter_id = self.after(150, self._apply_filter)

    def _apply_filter(self):
        self._filter_id = None
        self.show(keep_scroll=False)

    def _clear_filter(self, _event=None):
        if self.filter_var.get():
            self.filter_var.set('')
            return "break"
        self._focus_list()
        return "break"

    def _focus_list(self):
        if self.list is not None:
            self.list.canvas.focus_set()
            self.list.select(self.list.selected)
        return "break"

    # ── scanning ──
    def _library_event(self, what: str, data: Any):
        if what in ('songs', 'start'):
            if self._refresh_id is None:
                self._refresh_id = self.after(REFRESH_DURING_SCAN_MS, self._refresh)
        elif what in ('done', 'error'):
            if self._refresh_id:
                self.after_cancel(self._refresh_id)
                self._refresh_id = None
            self._refresh()
        self._update_status()

    def _refresh(self):
        self._refresh_id = None
        self.library = self.app.library()
        self.show(keep_scroll=True)

    def _update_status(self):
        scan = self.app.scanner
        n = len(self.library.songs)
        if scan is not None and scan.running:
            done = self.app.scan_progress
            text = tr('music.scan_progress', done=done[0], total=done[1]) if done[1] else \
                tr('music.scan_looking')
            self.status.config(text=text, fg=T["accent"])
        else:
            self.status.config(text=plural(n, 'count.song', 'count.songs').upper(), fg=T["dim"])

    # ── keys ──
    def key(self, event) -> bool:
        if event.widget is self.filter:
            return False
        k = event.keysym
        if k == 'BackSpace':
            return self.back()
        if k == 'slash' or (k in ('f', 'F') and event.state & 0x4):
            self.filter.focus_set()
            return True
        if k == 'space' and self.app.music_if_started() is not None:
            self.app.music.toggle()
            return True
        if self.list is not None:
            return self.list.key(event)
        return False

    def destroy(self):
        self.app.off_library(self._library_event)
        session = self.app.music_if_started()
        if session is not None:
            session.unlisten(self._on_session)
        for job in (self._filter_id, self._refresh_id):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        super().destroy()
