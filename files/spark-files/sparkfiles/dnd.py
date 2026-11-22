"""Dragging files: inside Spark Files (between views, tabs, split panes, windows and onto the
sidebar), and out to other apps through XDND when the pointer leaves Spark Files' windows.

Dropping on the same drive moves, on another drive copies (like Windows); hold Shift to move
or Ctrl to copy either way. A label next to the pointer says which it will be."""

import os
from typing import List, Optional

import tkinter as tk

from .text import t
from .widgets import T


def same_drive(paths: List[str], folder: str) -> bool:
    try:
        dev = os.stat(folder).st_dev
        return all(os.lstat(p).st_dev == dev for p in paths)
    except OSError:
        return False


class DragController:
    def __init__(self, app):
        self.app = app
        self.active = False
        self.paths: List[str] = []
        self.source = None
        self.target_widget = None
        self.target: Optional[str] = None
        self.outside = False
        self.label: Optional[tk.Toplevel] = None
        self.label_text: Optional[tk.Label] = None

    def start(self, source, paths: List[str], event) -> None:
        if not paths:
            return
        self.active = True
        self.source, self.paths = source, list(paths)
        self.target = None
        self.outside = False
        self._make_label()
        try:
            source.canvas.configure(cursor='fleur')
        except (AttributeError, tk.TclError):
            pass

    def _make_label(self) -> None:
        win = tk.Toplevel(self.app.root, bg=T["line2"], padx=1, pady=1)
        win.wm_overrideredirect(True)
        try:
            win.wm_attributes('-type', 'dnd')
        except tk.TclError:
            pass
        self.label_text = tk.Label(win, text='', font=self.app.font(9, True), bg=T["panel2"],
                                   fg=T["text"], padx=8, pady=3)
        self.label_text.pack()
        self.label = win

    def action(self, state: int, folder: Optional[str]) -> str:
        if folder == 'trash:///':
            return 'trash'
        if folder and folder.startswith('pin:'):
            return 'pin'
        if state & 0x4:
            return 'copy'
        if state & 0x1:
            return 'move'
        if folder and same_drive(self.paths, folder):
            return 'move'
        return 'copy'

    def motion(self, event) -> None:
        if not self.active:
            return
        x, y = event.x_root, event.y_root
        widget = self.app.root.winfo_containing(x, y)
        if widget is None:
            self._leave_target()
            if not self.outside and self.app.xdnd is not None and self.app.xdnd.ok:
                self.outside = self.app.xdnd.drag_start(self.source.canvas, self.paths)
            if self.outside:
                self.app.xdnd.drag_motion(x, y, 'move' if event.state & 0x1 else 'copy')
                self._show_label(x, y, t('dnd.other_app', n=len(self.paths)))
            else:
                self._show_label(x, y, t('dnd.nowhere'))
            return
        if self.outside:
            self.app.xdnd.drag_cancel()
            self.outside = False
        target_widget, folder = self.app.drop_target_at(widget, x, y, self.paths)
        if target_widget is not self.target_widget:
            self._leave_target()
            self.target_widget = target_widget
        self.target = folder
        if folder is None:
            self._show_label(x, y, t('dnd.nowhere'))
            return
        act = self.action(event.state, folder)
        if folder != 'trash:///' and not folder.startswith('pin:') and \
                any(os.path.dirname(p) == folder for p in self.paths) and act == 'move':
            self.target = None
            self._show_label(x, y, t('dnd.already_here'))
            return
        name = self.app.place_name(folder)
        self._show_label(x, y, t('dnd.' + act, n=len(self.paths), where=name))

    def _show_label(self, x: int, y: int, text: str) -> None:
        if self.label is None:
            return
        self.label_text.configure(text=text)
        self.label.geometry(f'+{x + 16}+{y + 18}')

    def _leave_target(self) -> None:
        if self.target_widget is not None:
            try:
                self.target_widget.clear_drop()
            except (AttributeError, tk.TclError):
                pass
        self.target_widget = None
        self.target = None

    def drop(self, event) -> None:
        if not self.active:
            return
        paths, folder = self.paths, self.target
        outside = self.outside
        self.outside = False                 # cancel() must not cancel the outside drop
        act = self.action(event.state, folder) if folder else None
        self.cancel()
        if outside:
            self.app.xdnd.drag_drop()
            return
        if folder and act:
            self.app.drop(paths, folder, act)

    def cancel(self) -> None:
        if not self.active:
            return
        self.active = False
        self._leave_target()
        if self.outside and self.app.xdnd is not None:
            self.app.xdnd.drag_cancel()
        self.outside = False
        if self.label is not None:
            try:
                self.label.destroy()
            except tk.TclError:
                pass
            self.label = None
        try:
            self.source.canvas.configure(cursor='arrow')
        except (AttributeError, tk.TclError):
            pass
        self.paths = []
        self.source = None
