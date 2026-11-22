"""One terminal: a VTE widget, its scrollbar, the shell or command running in it, and the
things Spark Terminal adds on top (links, copy on select, the bell, its title)."""

import os
import re
from typing import Any, Callable, Dict, List, Optional

from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte

from . import core
from .core import log
from .text import t

# PCRE2 flags VTE's regexes take (pcre2.h)
PCRE2_CASELESS = 0x00000008
PCRE2_MULTILINE = 0x00000400
PCRE2_UTF = 0x00080000
PCRE2_NO_UTF_CHECK = 0x40000000
MATCH_FLAGS = PCRE2_MULTILINE | PCRE2_UTF | PCRE2_NO_UTF_CHECK

CURSOR_SHAPES = {'block': Vte.CursorShape.BLOCK, 'ibeam': Vte.CursorShape.IBEAM,
                 'underline': Vte.CursorShape.UNDERLINE}


def rgba(colour: str) -> Gdk.RGBA:
    value = Gdk.RGBA()
    value.parse(colour)
    return value


def search_regex(pattern: str, regex: bool, case: bool) -> Vte.Regex:
    """A VTE search regex for what's typed in the search bar. Raises GLib.Error when a regex
    doesn't compile."""
    if not regex:
        pattern = re.escape(pattern)
    flags = MATCH_FLAGS | (0 if case else PCRE2_CASELESS)
    return Vte.Regex.new_for_search(pattern, -1, flags)


class Pane(Gtk.Box):
    """A terminal with its scrollbar. on_exit(pane) runs when what it started ends and the
    pane should close; on_title(pane) when its title changes; on_focus(pane) when it gets the
    keyboard; on_bell(pane) on the bell; on_context(pane, x, y, link) for a right click."""

    def __init__(self, settings: Dict[str, Any], callbacks: Dict[str, Callable]):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True, vexpand=True)
        self.add_css_class('pane')
        self.settings = settings
        self.cb = callbacks
        self.argv: List[str] = []
        self.pid = -1
        self.hold = False
        self.command = False
        self.exited = False
        self.title = ''
        self.font_scale = 1.0

        term = self.terminal = Vte.Terminal()
        term.set_hexpand(True)
        term.set_vexpand(True)
        term.set_size(100, 30)
        term.set_allow_hyperlink(True)
        term.set_scroll_on_keystroke(True)
        term.set_scroll_on_output(False)
        term.set_mouse_autohide(True)
        term.set_bold_is_bright(False)
        term.set_enable_bidi(True)
        term.set_enable_shaping(True)
        term.set_word_char_exceptions('-_.:/~+@%=')
        self.apply_settings(settings)
        self._add_link_patterns()

        scrollbar = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL,
                                  adjustment=term.get_vadjustment())
        self.append(term)
        self.append(scrollbar)

        term.connect('child-exited', self._on_child_exited)
        term.connect('selection-changed', self._on_selection)
        term.connect('bell', lambda _t: self.cb['bell'](self))
        term.connect('termprop-changed', self._on_termprop)

        focus = Gtk.EventControllerFocus()
        focus.connect('enter', lambda _c: self.cb['focus'](self))
        term.add_controller(focus)

        # Ctrl+click opens links; right click is our own menu. Capture phase, so VTE doesn't
        # start a selection or show its own menu first.
        click = Gtk.GestureClick(button=0)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed', self._on_press)
        term.add_controller(click)

    # ─── settings ───────────────────────────────────────────

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        self.settings = settings
        term = self.terminal
        scheme = core.SCHEME
        term.set_colors(rgba(scheme['foreground']), rgba(scheme['background']),
                        [rgba(c) for c in scheme['palette']])
        term.set_color_cursor(rgba(scheme['cursor']))
        term.set_color_cursor_foreground(rgba(scheme['cursor_text']))
        term.set_color_highlight(rgba(scheme['highlight']))
        term.set_color_highlight_foreground(rgba(scheme['highlight_text']))
        font = Pango.FontDescription.from_string(settings['font'])
        font.set_size(settings['font_size'] * Pango.SCALE)
        term.set_font(font)
        term.set_font_scale(self.font_scale)
        term.set_scrollback_lines(settings['scrollback'])
        term.set_cursor_shape(CURSOR_SHAPES.get(settings['cursor'], Vte.CursorShape.BLOCK))
        term.set_cursor_blink_mode(Vte.CursorBlinkMode.ON if settings['cursor_blink']
                                   else Vte.CursorBlinkMode.OFF)
        term.set_audible_bell(settings['bell'] == 'sound')

    def zoom(self, step: int) -> None:
        """step +1/-1 changes the size by about 10%, 0 goes back to the setting's size."""
        if step == 0:
            self.font_scale = 1.0
        else:
            self.font_scale = max(0.3, min(4.0, self.font_scale * (1.1 if step > 0 else 1 / 1.1)))
        self.terminal.set_font_scale(self.font_scale)

    def _add_link_patterns(self) -> None:
        self.link_tags = {}
        for kind, pattern in (('url', core.URL_PATTERN), ('path', core.PATH_PATTERN)):
            try:
                regex = Vte.Regex.new_for_match(pattern, -1, MATCH_FLAGS)
            except GLib.Error as exc:            # never happens with our own patterns
                log.warning("link pattern %s: %s", kind, exc)
                continue
            tag = self.terminal.match_add_regex(regex, 0)
            self.terminal.match_set_cursor_name(tag, 'pointer')
            self.link_tags[tag] = kind

    # ─── starting and stopping ──────────────────────────────

    def spawn(self, argv: List[str], cwd: str, hold: bool = False, command: bool = False) -> None:
        """Start argv in cwd. command=True for a program given with -e (not a shell)."""
        self.argv, self.hold, self.command = list(argv), hold, command
        self.title = core.command_label(argv)
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT, cwd, self.argv, core.child_env(), GLib.SpawnFlags.SEARCH_PATH,
            None, None, -1, None, self._on_spawned, None)

    def _on_spawned(self, _term, pid, error, _data=None) -> None:
        if error is not None or pid < 0:
            why = error.message if error is not None else '?'
            log.warning("could not start %s: %s", self.argv, why)
            self.exited, self.hold = True, True
            self.feed_note(t('spawn_failed', cmd=core.command_label(self.argv), why=why), error=True)
            self.feed_note(t('exited_hold'))
            self.cb['exit'](self)
            return
        self.pid = pid
        log.info("started %s (pid %d)", ' '.join(self.argv), pid)
        self.cb['title'](self)

    def _on_child_exited(self, _term, status: int) -> None:
        self.exited = True
        label = core.command_label(self.argv)
        if self.hold:
            if os.WIFSIGNALED(status):
                self.feed_note(t('exited_signal', cmd=label, sig=os.WTERMSIG(status)), error=True)
            else:
                code = os.waitstatus_to_exitcode(status) if status >= 0 else status
                self.feed_note(t('exited', cmd=label, code=code), error=code != 0)
            self.feed_note(t('exited_hold'))
        self.cb['exit'](self)

    def feed_note(self, line: str, error: bool = False) -> None:
        """A line from Spark Terminal itself, in pink for errors, muted otherwise."""
        colour = '38;2;255;158;187' if error else '38;2;179;176;210'
        self.terminal.feed(f'\r\n\x1b[{colour}m{line}\x1b[0m\r\n'.encode())

    def stop(self) -> None:
        """Hang up on what's running, as closing a terminal does."""
        if self.pid > 0 and not self.exited:
            try:
                os.kill(self.pid, 1)                         # SIGHUP
            except OSError:
                pass

    # ─── what's going on inside ─────────────────────────────

    def running(self) -> Optional[str]:
        """Name of a program running in the foreground other than the shell, or None. A
        command started with -e counts as running for as long as it runs."""
        if self.exited or self.pid <= 0:
            return None
        pty = self.terminal.get_pty()
        if pty is None:
            return None
        try:
            pgid = os.tcgetpgrp(pty.get_fd())
        except OSError:
            return None
        name = core.running_program(self.pid, pgid)
        if name is None and self.command:
            return core.command_label(self.argv)
        return name

    def cwd(self) -> Optional[str]:
        """The shell's current folder: what it reported (OSC 7), or what /proc says."""
        uri = None
        try:
            uri = self.terminal.ref_termprop_uri(Vte.TERMPROP_CURRENT_DIRECTORY_URI)
            uri = uri.to_string() if uri is not None else None
        except (AttributeError, TypeError, GLib.Error):
            pass
        path = core.uri_to_path(uri)
        if path and os.path.isdir(path):
            return path
        if self.pid > 0 and not self.exited:
            return core.process_cwd(self.pid)
        return None

    def _on_termprop(self, _term, name: str) -> None:
        if name == Vte.TERMPROP_XTERM_TITLE:
            self._update_title()

    def _update_title(self) -> None:
        title = ''
        try:
            title = self.terminal.get_termprop_string(Vte.TERMPROP_XTERM_TITLE)[0] or ''
        except (AttributeError, TypeError, IndexError):
            pass
        self.title = title.strip() or core.command_label(self.argv)
        self.cb['title'](self)

    # ─── selection, links, mouse ────────────────────────────

    def _on_selection(self, term) -> None:
        if self.settings.get('copy_on_select') and term.get_has_selection():
            term.copy_clipboard_format(Vte.Format.TEXT)

    def link_at(self, x: float, y: float) -> Optional[Dict[str, str]]:
        """{'kind': 'url'|'path', 'text': ..., 'target': uri} for a link under (x, y)."""
        term = self.terminal
        try:
            uri = term.check_hyperlink_at(x, y)            # OSC 8 links (ls --hyperlink, gcc)
        except (TypeError, GLib.Error):
            uri = None
        if uri:
            return {'kind': 'url', 'text': uri, 'target': uri}
        try:
            text, tag = term.check_match_at(x, y)
        except (TypeError, GLib.Error):
            return None
        if not text:
            return None
        kind = self.link_tags.get(tag)
        if kind == 'url':
            return {'kind': 'url', 'text': text, 'target': text}
        if kind == 'path':
            path = core.path_target(text, self.cwd())
            if path:
                return {'kind': 'path', 'text': text, 'target': Gio.File.new_for_path(path).get_uri(),
                        'path': path}
        return None

    def _on_press(self, gesture, n_press, x, y) -> None:
        button = gesture.get_current_button()
        state = gesture.get_current_event_state()
        if button == 1 and state & Gdk.ModifierType.CONTROL_MASK:
            link = self.link_at(x, y)
            if link:
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                open_uri(link['target'], self.get_root())
        elif button == 3 and not state & Gdk.ModifierType.SHIFT_MASK:
            # Shift+right click goes through to programs that use the mouse (mc, vim)
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.terminal.grab_focus()
            self.cb['context'](self, x, y, self.link_at(x, y))


def open_uri(uri: str, window: Optional[Gtk.Widget] = None) -> None:
    log.info("opening %s", uri)
    launcher = Gtk.UriLauncher.new(uri) if hasattr(Gtk, 'UriLauncher') else None
    if launcher is not None:
        launcher.launch(window if isinstance(window, Gtk.Window) else None, None, None, None)
        return
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error as exc:
        log.warning("could not open %s: %s", uri, exc)
