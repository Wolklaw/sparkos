"""The preview pane (F11): a large thumbnail for photos and videos, the first lines of a text
file, what a folder holds, and the basics (type, size, dates)."""

import os
import threading
from typing import List, Optional

import tkinter as tk

from .core import full_date, home_short, human_size
from .listing import Entry, folder_count, type_label
from .text import t
from .widgets import T

TEXT_KINDS = ('code', 'document')
TEXT_EXTS = {'txt', 'md', 'log', 'csv', 'json', 'yaml', 'yml', 'toml', 'ini', 'conf', 'cfg',
             'py', 'sh', 'js', 'ts', 'c', 'h', 'cpp', 'rs', 'go', 'html', 'css', 'xml',
             'desktop', 'service', 'lua', 'rb', 'php', 'sql', 'diff', 'patch', 'java', 'kt'}


def read_text(path: str, limit: int = 4096) -> Optional[str]:
    try:
        with open(path, 'rb') as f:
            data = f.read(limit)
    except OSError:
        return None
    if b'\0' in data:
        return None
    for enc in ('utf-8', 'cp1252'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', 'replace')


class Preview(tk.Frame):
    def __init__(self, parent: tk.Misc, window):
        super().__init__(parent, bg=T["panel"], width=window.app.px(280))
        self.window, self.app = window, window.app
        px = self.app.px
        self.pack_propagate(False)
        self.entry: Optional[Entry] = None
        self.box = px(240)
        self.image_label = tk.Label(self, bg=T["panel"], height=self.box)
        self.image_label.pack(fill='x', padx=px(12), pady=(px(14), px(8)))
        self.name = tk.Label(self, text='', font=self.app.font(11, True), bg=T["panel"],
                             fg=T["text"], wraplength=px(250), justify='left', anchor='w')
        self.name.pack(fill='x', padx=px(14))
        self.facts = tk.Frame(self, bg=T["panel"])
        self.facts.pack(fill='x', padx=px(14), pady=(px(8), 0))
        self.text = tk.Text(self, height=12, font=self.app.font(8, False), bg=T["out_bg"],
                            fg=T["muted"], relief='flat', wrap='word', highlightthickness=0,
                            padx=px(8), pady=px(6))
        self._photo = None
        self._token = 0

    def show(self, entries: List[Entry]) -> None:
        self._token += 1
        for w in self.facts.winfo_children():
            w.destroy()
        self.text.pack_forget()
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        if not entries:
            self.entry = None
            folder = self.window.active.current_folder() if self.window.active else None
            self.image_label.configure(image=self.app.icons.get('folder', self.box // 2) or '')
            self.name.configure(text=os.path.basename(folder.rstrip('/')) or folder
                                if folder else '')
            if folder:
                n = folder_count(folder, self.app.settings['show_hidden'])
                if n is not None:
                    self._fact(t('props.contains'), t('status.items', n=n))
            return
        if len(entries) > 1:
            self.entry = None
            self.image_label.configure(image=self.app.icons.get('file', self.box // 2) or '')
            self.name.configure(text=t('status.selected', n=len(entries)))
            size = sum(e.size for e in entries if not e.is_dir)
            self._fact(t('props.size'), human_size(size))
            return
        e = entries[0]
        self.entry = e
        kind = 'broken' if e.broken else e.kind
        self.image_label.configure(image=self.app.icons.get(kind, self.box // 2, e.is_link) or '')
        self.name.configure(text=e.name)
        self._fact(t('props.type'), type_label(e, t))
        if e.is_dir:
            n = folder_count(e.path, self.app.settings['show_hidden'])
            if n is not None:
                self._fact(t('props.contains'), t('status.items', n=n))
        else:
            self._fact(t('props.size'), human_size(e.size))
        self._fact(t('props.modified'), full_date(e.mtime))
        self._fact(t('props.where'), home_short(os.path.dirname(e.path)))
        if not e.is_dir and self.app.settings['thumbnails']:
            token = self._token
            self.app.big_thumb(e, self.box, lambda photo: self._got_thumb(token, photo))
        if not e.is_dir and (e.ext in TEXT_EXTS or (e.kind == 'file' and e.size < 65536)):
            token = self._token

            def work():
                text = read_text(e.path)
                self.app.bridge.post(lambda: self._got_text(token, text))
            threading.Thread(target=work, daemon=True).start()

    def _fact(self, label: str, value: str) -> None:
        px = self.app.px
        tk.Label(self.facts, text=label.upper(), font=self.app.font(8, True), bg=T["panel"],
                 fg=T["dim"], anchor='w').pack(fill='x')
        tk.Label(self.facts, text=value, font=self.app.font(9, False), bg=T["panel"],
                 fg=T["text"], anchor='w', wraplength=px(250), justify='left').pack(
            fill='x', pady=(0, px(5)))

    def _got_thumb(self, token: int, photo) -> None:
        if token == self._token and photo is not None and self.winfo_exists():
            self._photo = photo
            self.image_label.configure(image=photo)

    def _got_text(self, token: int, text: Optional[str]) -> None:
        if token != self._token or not text or not self.winfo_exists():
            return
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text)
        self.text.configure(state='disabled')
        self.text.pack(fill='both', expand=True, padx=self.app.px(12), pady=self.app.px(10))
