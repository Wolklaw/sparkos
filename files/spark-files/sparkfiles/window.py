"""A Spark Files window: the header and its tools, the sidebar, tabs (each with one pane, or
two side by side in the split view), the preview pane and the jobs panel."""

import os
from typing import List, Optional

import tkinter as tk

from . import APP_CLASS, APP_NAME
from .core import home
from .jobs import JobsPanel
from .pane import Pane
from .places import TRASH
from .preview import Preview
from .sidebar import Sidebar
from .text import t
from .ui import TabStrip, Timers, menu, separator
from .widgets import T, GlitchText, IconButton, Mark, Strip


class Tab:
    _n = 0

    def __init__(self):
        Tab._n += 1
        self.key = Tab._n
        self.panes: List[Pane] = []
        self.active = 0


class MainArea(tk.Frame):
    def show_jobs(self, panel) -> None:
        panel.grid(row=2, column=0, sticky='ew')

    def hide_jobs(self, panel) -> None:
        panel.grid_remove()


class Window(Timers, tk.Toplevel):
    def __init__(self, app, paths: List[str], select: Optional[List[str]] = None):
        super().__init__(app.root, bg=T["bg"], class_=APP_CLASS)
        self.withdraw()
        self.app = app
        px = app.px
        self.tabs: List[Tab] = []
        self.tab: Optional[Tab] = None
        self.search_prompt: Optional[Pane] = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.title(APP_NAME)

        # header
        head = tk.Frame(self, bg=T["bg"])
        head.pack(fill='x', padx=px(10), pady=(px(8), px(6)))
        self.mark = Mark(head, px(26), T["bg"])
        self.mark.pack(side='left')
        self.title_text = GlitchText(head, 'SPARK FILES', app.font(12, True), bg=T["bg"])
        self.title_text.pack(side='left', padx=(px(8), 0))
        tools = tk.Frame(head, bg=T["bg"])
        tools.pack(side='right')
        size = px(28)
        self.b_menu = IconButton(tools, 'menu', self.main_menu, size)
        self.b_term = IconButton(tools, 'terminal', lambda: app.open_terminal(self.active), size)
        self.b_split = IconButton(tools, 'split', self.toggle_split, size)
        self.b_preview = IconButton(tools, 'preview', self.toggle_preview, size)
        self.b_hidden = IconButton(tools, 'eye', app.toggle_hidden, size)
        self.b_view = IconButton(tools, 'grid', app.toggle_view, size)
        self.b_new = IconButton(tools, 'newfolder', lambda: app.new_folder(self.active), size)
        for b, tip in ((self.b_menu, 'tip.menu'), (self.b_term, 'tip.terminal'),
                       (self.b_split, 'tip.split'), (self.b_preview, 'tip.preview'),
                       (self.b_hidden, 'tip.hidden'), (self.b_view, 'tip.view'),
                       (self.b_new, 'tip.new_folder')):
            b.pack(side='right', padx=(px(2), 0))
            app.tooltip.attach(b, t(tip))
        self.strip = Strip(self)
        self.strip.pack(fill='x')

        body = tk.Frame(self, bg=T["bg"])
        body.pack(fill='both', expand=True)
        self.sidebar = Sidebar(body, self)
        self.sidebar.configure(width=px(210))
        self.sidebar.pack_propagate(False)
        self.side_line = separator(body, vertical=True)
        self.main = MainArea(body, bg=T["bg"])
        self.preview = Preview(body, self)
        self.preview_line = separator(body, vertical=True)
        self.sidebar.pack(side='left', fill='y')
        self.side_line.pack(side='left', fill='y')
        self.main.pack(side='left', fill='both', expand=True)
        self.tabstrip = TabStrip(self.main, app.font(9, False), px, self.select_tab,
                                 self.close_tab, self.tab_menu)
        self.tabstrip.grid(row=0, column=0, sticky='ew')
        self.panes_frame = tk.Frame(self.main, bg=T["bg"])
        self.panes_frame.grid(row=1, column=0, sticky='nsew')
        self.main.rowconfigure(1, weight=1)
        self.main.columnconfigure(0, weight=1)
        self.jobs = JobsPanel(self.main, app)
        self.apply_settings()

        for path in paths or [home()]:
            self.new_tab(path, select=True, select_items=select)
        self._bind_keys()
        geometry = app.settings.get('geometry')
        self.geometry(geometry if isinstance(geometry, str) and not app.windows
                      else f'{px(1100)}x{px(700)}')
        self.minsize(px(560), px(360))
        self.bind('<FocusIn>', lambda e: app.window_focused(self) if e.widget is self else None)
        self.bind('<Configure>', self._remember_size)

    # ─── tabs and panes ──────────────────────────────────────

    @property
    def active(self) -> Pane:
        return self.tab.panes[self.tab.active]

    def new_tab(self, path: str, select: bool = True,
                select_items: Optional[List[str]] = None) -> Tab:
        tab = Tab()
        pane = Pane(self.panes_frame, self, path)
        tab.panes.append(pane)
        self.tabs.append(tab)
        self.tabstrip.add(tab.key, pane.title())
        if select or self.tab is None:
            self.select_tab(tab.key)
        if select_items:
            pane.load(select=select_items)
        self._tabs_visible()
        return tab

    def _tabs_visible(self) -> None:
        if len(self.tabs) > 1:
            self.tabstrip.grid()
        else:
            self.tabstrip.grid_remove()

    def tab_by_key(self, key) -> Optional[Tab]:
        return next((tb for tb in self.tabs if tb.key == key), None)

    def select_tab(self, key) -> None:
        tab = self.tab_by_key(key)
        if tab is None:
            return
        if self.tab is not None and self.tab is not tab:
            for p in self.tab.panes:
                p.pack_forget()
        self.tab = tab
        self._layout_panes()
        self.tabstrip.select(key)
        self.pane_moved(self.active)
        self.active.view.canvas.focus_set()
        self.b_split.set_icon('split')

    def _layout_panes(self) -> None:
        for child in self.panes_frame.winfo_children():
            if isinstance(child, tk.Frame) and getattr(child, 'is_split_line', False):
                child.destroy()
        for p in self.tab.panes:
            p.pack_forget()
        for i, p in enumerate(self.tab.panes):
            if i:
                line = tk.Frame(self.panes_frame, bg=T["line"], width=1)
                line.is_split_line = True
                line.pack(side='left', fill='y')
            p.pack(side='left', fill='both', expand=True)
            p.set_active(i == self.tab.active and len(self.tab.panes) > 1)

    def close_tab(self, key=None) -> None:
        tab = self.tab_by_key(key) if key is not None else self.tab
        if tab is None:
            return
        if len(self.tabs) == 1:
            self.close()
            return
        i = self.tabs.index(tab)
        for p in tab.panes:
            p.close()
            p.destroy()
        self.tabs.remove(tab)
        self.tabstrip.remove(tab.key)
        self.app.closed_tabs.append(tab.panes[tab.active].path if tab.panes else home())
        if tab is self.tab:
            self.tab = None
            self.select_tab(self.tabs[min(i, len(self.tabs) - 1)].key)
        self._tabs_visible()

    def next_tab(self, step: int) -> None:
        if len(self.tabs) < 2:
            return
        i = self.tabs.index(self.tab)
        self.select_tab(self.tabs[(i + step) % len(self.tabs)].key)

    def tab_menu(self, key, event) -> None:
        m = menu(self, self.app.font(10, False))
        m.add_command(label=t('menu.new_tab'), command=lambda: self.new_tab(self.active.path
                      if self.active.path != TRASH else home()))
        m.add_command(label=t('menu.close_tab'), command=lambda: self.close_tab(key))
        m.add_command(label=t('menu.close_others'), command=lambda: self.close_others(key))
        m.tk_popup(event.x_root, event.y_root)

    def close_others(self, key) -> None:
        for tab in list(self.tabs):
            if tab.key != key:
                self.close_tab(tab.key)

    def toggle_split(self) -> None:
        """F3: a second pane next to the first (in this tab), or back to one."""
        tab = self.tab
        if len(tab.panes) == 1:
            start = self.active.path if self.active.mode != 'search' else self.active.path
            pane = Pane(self.panes_frame, self, start)
            tab.panes.append(pane)
            tab.active = 1
        else:
            keep = tab.panes[tab.active]
            for p in tab.panes:
                if p is not keep:
                    p.close()
                    p.destroy()
            tab.panes = [keep]
            tab.active = 0
        self.app.settings['split'] = len(tab.panes) > 1
        self._layout_panes()
        self.active.view.canvas.focus_set()
        self.pane_moved(self.active)
        self.app.glitch.now(self.strip)

    def other_pane(self, pane: Pane) -> Optional[Pane]:
        if pane in self.tab.panes and len(self.tab.panes) == 2:
            return self.tab.panes[1 - self.tab.panes.index(pane)]
        return None

    def set_active(self, pane: Pane) -> None:
        if self.tab is None or pane not in self.tab.panes:
            return
        i = self.tab.panes.index(pane)
        if i != self.tab.active:
            self.tab.active = i
            for k, p in enumerate(self.tab.panes):
                p.set_active(k == i and len(self.tab.panes) > 1)
            self.pane_moved(pane)

    def pane_moved(self, pane: Pane) -> None:
        """A pane went somewhere: tab name, window title, sidebar, preview."""
        for tab in self.tabs:
            if pane in tab.panes:
                self.tabstrip.rename(tab.key, tab.panes[tab.active].title())
        if self.tab is None or pane is not self.active:
            return
        self.title(f"{pane.title()} — {APP_NAME}")
        self.sidebar.highlight(pane.path)
        self.selection_changed(pane)

    def selection_changed(self, pane: Pane) -> None:
        if self.tab is not None and pane is self.active and self.preview.winfo_ismapped():
            self.preview.show(pane.view.selected_entries())

    # ─── search prompt (Ctrl+F) ──────────────────────────────

    def start_search_prompt(self) -> None:
        pane = self.active
        if pane.mode == 'trash':
            return
        self.search_prompt = pane
        pane.focus_filter(search=True)
        pane.flash(t('search.prompt', where=pane.title()), ms=3000)

    def searching(self, pane: Pane) -> bool:
        return self.search_prompt is pane

    def search_mode_requested(self, pane: Pane) -> bool:
        return self.search_prompt is pane

    def end_search_prompt(self, pane: Pane) -> None:
        if self.search_prompt is pane:
            self.search_prompt = None
            pane._paint_hint()

    # ─── look ────────────────────────────────────────────────

    def apply_settings(self) -> None:
        s = self.app.settings
        self.b_view.set_icon('list' if s['view'] == 'grid' else 'grid')
        if s['sidebar']:
            if not self.sidebar.winfo_ismapped():
                self.sidebar.pack(side='left', fill='y', before=self.main)
                self.side_line.pack(side='left', fill='y', before=self.main)
        else:
            self.sidebar.pack_forget()
            self.side_line.pack_forget()
        if s['preview']:
            if not self.preview.winfo_ismapped():
                self.preview_line.pack(side='left', fill='y')
                self.preview.pack(side='left', fill='y')
        else:
            self.preview.pack_forget()
            self.preview_line.pack_forget()

    def toggle_preview(self) -> None:
        self.app.settings['preview'] = not self.app.settings['preview']
        self.app.settings_changed()
        if self.app.settings['preview']:
            self.preview.show(self.active.view.selected_entries())

    def toggle_sidebar(self) -> None:
        self.app.settings['sidebar'] = not self.app.settings['sidebar']
        self.app.settings_changed()

    def main_menu(self) -> None:
        a = self.app
        m = menu(self, a.font(10, False))
        m.add_command(label=t('menu.new_window'), accelerator='Ctrl+N',
                      command=lambda: a.new_window(self.active.path))
        m.add_command(label=t('menu.new_tab'), accelerator='Ctrl+T', command=self.dup_tab)
        m.add_command(label=t('menu.reopen_tab'), accelerator='Ctrl+Shift+T',
                      command=self.reopen_tab,
                      state='normal' if a.closed_tabs else 'disabled')
        m.add_separator()
        m.add_command(label=t('menu.search'), accelerator='Ctrl+F',
                      command=self.start_search_prompt)
        m.add_separator()
        view = menu(m, a.font(10, False))
        view.add_radiobutton(label=t('menu.view_list'), accelerator='Ctrl+1',
                             command=lambda: a.set_view('list'),
                             value='list', variable=a.view_var)
        view.add_radiobutton(label=t('menu.view_grid'), accelerator='Ctrl+2',
                             command=lambda: a.set_view('grid'),
                             value='grid', variable=a.view_var)
        view.add_separator()
        for key in ('name', 'modified', 'size', 'type'):
            view.add_radiobutton(label=t('sort.' + key), value=key, variable=a.sort_var,
                                 command=lambda k=key: a.set_sort_key(k))
        view.add_checkbutton(label=t('sort.reverse'), variable=a.reverse_var,
                             command=lambda: a.set_setting('sort_reverse', a.reverse_var.get()))
        view.add_checkbutton(label=t('sort.folders_first'), variable=a.folders_first_var,
                             command=lambda: a.set_setting('folders_first',
                                                           a.folders_first_var.get()))
        view.add_separator()
        view.add_checkbutton(label=t('menu.hidden'), accelerator='Ctrl+H',
                             variable=a.hidden_var, command=a.toggle_hidden)
        view.add_checkbutton(label=t('menu.thumbnails'), variable=a.thumbs_var,
                             command=lambda: a.set_setting('thumbnails', a.thumbs_var.get()))
        view.add_checkbutton(label=t('menu.sidebar'), accelerator='F9',
                             variable=a.sidebar_var, command=self.toggle_sidebar)
        view.add_checkbutton(label=t('menu.preview'), accelerator='F11',
                             variable=a.preview_var, command=self.toggle_preview)
        view.add_command(label=t('menu.split'), accelerator='F3', command=self.toggle_split)
        view.add_separator()
        view.add_command(label=t('menu.zoom_in'), accelerator='Ctrl++', command=lambda: a.zoom(1))
        view.add_command(label=t('menu.zoom_out'), accelerator='Ctrl+-',
                         command=lambda: a.zoom(-1))
        m.add_cascade(label=t('menu.view'), menu=view)
        m.add_checkbutton(label=t('menu.glitch'), variable=a.glitch_var,
                          command=lambda: a.set_setting('glitch', a.glitch_var.get()))
        m.add_separator()
        m.add_command(label=t('menu.trash'), command=lambda: self.active.go(TRASH))
        m.add_command(label=t('menu.empty_trash'), command=a.empty_trash)
        m.add_separator()
        m.add_command(label=t('menu.shortcuts'), command=lambda: a.show_shortcuts(self))
        m.add_command(label=t('menu.about'), command=lambda: a.about(self))
        m.add_separator()
        m.add_command(label=t('menu.close_window'), accelerator='Ctrl+Q', command=self.close)
        a.sync_vars()
        x = self.b_menu.winfo_rootx()
        y = self.b_menu.winfo_rooty() + self.b_menu.winfo_height()
        m.tk_popup(x, y)

    def dup_tab(self) -> None:
        p = self.active
        self.new_tab(p.path if p.mode == 'folder' else home())

    def reopen_tab(self) -> None:
        if self.app.closed_tabs:
            path = self.app.closed_tabs.pop()
            self.new_tab(path if (path == TRASH or os.path.isdir(path)) else home())

    # ─── keys ────────────────────────────────────────────────

    def _bind_keys(self) -> None:
        a = self.app

        def in_text(event) -> bool:
            return event.widget.winfo_class() in ('Entry', 'Text', 'Listbox')

        def key(seq, fn, text_too=False):
            def handler(event):
                if not text_too and in_text(event):
                    return None
                fn()
                return 'break'
            self.bind(seq, handler)

        p = lambda: self.active                                     # noqa: E731
        key('<Control-t>', self.dup_tab, True)
        key('<Control-T>', self.reopen_tab, True)
        key('<Control-w>', self.close_tab, True)
        key('<Control-q>', self.close, True)
        key('<Control-n>', lambda: a.new_window(p().path), True)
        key('<Control-Tab>', lambda: self.next_tab(1), True)
        key('<Control-ISO_Left_Tab>', lambda: self.next_tab(-1), True)
        key('<Control-Shift-Tab>', lambda: self.next_tab(-1), True)
        key('<Control-Prior>', lambda: self.next_tab(-1), True)
        key('<Control-Next>', lambda: self.next_tab(1), True)
        key('<Control-l>', lambda: p().pathbar.edit(), True)
        key('<Alt-d>', lambda: p().pathbar.edit(), True)
        key('<Control-f>', self.start_search_prompt, True)
        key('<Control-h>', a.toggle_hidden, True)
        key('<Control-period>', a.toggle_hidden, True)
        key('<F3>', self.toggle_split, True)
        key('<F5>', lambda: p().reload(user=True), True)
        key('<Control-r>', lambda: p().reload(user=True), True)
        key('<F9>', self.toggle_sidebar, True)
        key('<F11>', self.toggle_preview, True)
        key('<F2>', lambda: a.rename_selected(p()))
        key('<Shift-F4>', lambda: a.open_terminal(p()), True)
        key('<Alt-Left>', lambda: p().back(), True)
        key('<Alt-Right>', lambda: p().forward(), True)
        key('<Alt-Up>', lambda: p().go_up(), True)
        key('<Alt-Home>', lambda: p().go(home()), True)
        key('<Button-8>', lambda: p().back(), True)
        key('<Button-9>', lambda: p().forward(), True)
        key('<Control-Key-1>', lambda: a.set_view('list'), True)
        key('<Control-Key-2>', lambda: a.set_view('grid'), True)
        key('<Control-plus>', lambda: a.zoom(1), True)
        key('<Control-equal>', lambda: a.zoom(1), True)
        key('<Control-minus>', lambda: a.zoom(-1), True)
        key('<Control-Key-0>', lambda: a.zoom(0), True)
        key('<Control-N>', lambda: a.new_folder(p()), True)
        key('<Control-Shift-n>', lambda: a.new_folder(p()), True)
        key('<Control-a>', lambda: p().view.select_all())
        key('<Control-i>', lambda: p().view.invert_selection())
        key('<Control-c>', lambda: a.copy_selection(p(), cut=False))
        key('<Control-x>', lambda: a.copy_selection(p(), cut=True))
        key('<Control-v>', lambda: a.paste(p()))
        key('<Control-C>', lambda: a.copy_paths(p()))
        key('<Delete>', lambda: a.trash_selected(p()))
        key('<KP_Delete>', lambda: a.trash_selected(p()))
        key('<Shift-Delete>', lambda: a.delete_selected(p()))
        key('<Alt-Return>', lambda: a.properties(self, [e.path for e in
                                                         p().view.selected_entries()]
                                                 or [p().path]))
        key('<Control-z>', lambda: a.undo(p()))
        key('<Escape>', lambda: p().escape())

    # ─── closing ─────────────────────────────────────────────

    def _remember_size(self, event) -> None:
        if event.widget is self and self.state() == 'normal':
            self.app.settings['geometry'] = f'{self.winfo_width()}x{self.winfo_height()}'

    def close(self) -> None:
        for tab in self.tabs:
            for p in tab.panes:
                p.close()
        self.app.window_closed(self)
        self.destroy()
