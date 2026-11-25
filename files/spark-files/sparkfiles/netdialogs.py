"""The "Connect to server" dialog."""

import tkinter as tk

from . import network
from .text import t
from .ui import Check, Dialog, entry, set_entry_error
from .widgets import T


class ConnectDialog(Dialog):
    """Address, user, password, and whether to keep the password and show the server in the
    sidebar. Connecting happens in the background (app.network_go): Cancel gives up waiting,
    and the window stays usable until then."""

    def __init__(self, app, window):
        super().__init__(app, window, t('net.title'))
        self.window = window
        self.cancel_connect = None
        px = app.px
        f = app.font(10, False)
        c = self.content

        def caption(text: str) -> None:
            tk.Label(c, text=text.upper(), font=app.font(8, True), bg=T["panel"],
                     fg=T["muted"], anchor='w').pack(fill='x', pady=(px(8), px(2)))

        caption(t('net.address'))
        self.address = entry(c, f, width=46)
        self.address.pack(fill='x', ipady=px(4))
        self.address.insert(0, 'sftp://')
        tk.Label(c, text=t('net.address_hint'), font=app.font(8, False), bg=T["panel"],
                 fg=T["dim"], anchor='w').pack(fill='x', pady=(px(2), 0))
        caption(t('net.user'))
        self.user = entry(c, f, width=46)
        self.user.pack(fill='x', ipady=px(4))
        caption(t('net.password'))
        self.password = entry(c, f, width=46)
        self.password.configure(show='•')
        self.password.pack(fill='x', ipady=px(4))
        self.remember = Check(c, t('net.remember'), False, app.font(9, False))
        self.remember.pack(anchor='w', pady=(px(8), 0))
        self.keep = Check(c, t('net.save'), True, app.font(9, False),
                          command=lambda on: self.name.configure(
                              state='normal' if on else 'disabled'))
        self.keep.pack(anchor='w', pady=(px(6), px(2)))
        self.name = entry(c, f, width=46)
        self.name.pack(fill='x', ipady=px(4))
        self.status = tk.Label(c, text='', font=app.font(9, False), bg=T["panel"],
                               fg=T["pink"], anchor='w', justify='left',
                               wraplength=px(440))
        self.status.pack(fill='x', pady=(px(8), 0))
        self.button(t('button.cancel'), self.cancel)
        self.go_button = self.button(t('net.connect_btn'), self.connect, 'primary')
        for e in (self.address, self.user, self.password, self.name):
            e.bind('<Return>', lambda _e: self.connect())
            e.bind('<KeyRelease>', lambda _e: self._clear_error())

    def focus_first(self) -> None:
        self.address.focus_set()
        self.address.icursor('end')

    def _clear_error(self) -> None:
        set_entry_error(self.address, False)
        if not self.cancel_connect:
            self.status.configure(text='')

    def fail(self, text: str) -> None:
        """Back to the form with what went wrong (text is '' when the user said no)."""
        self.cancel_connect = None
        self.status.configure(text=text, fg=T["pink"])
        if text:
            self.app.glitch.now(self.head)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def connect(self) -> None:
        if self.cancel_connect:
            return
        try:
            server, typed_password = network.parse_address(self.address.get(),
                                                           self.user.get())
        except network.NetworkError as err:
            set_entry_error(self.address, True)
            self.status.configure(text=self.app.network_error_text(err, ''), fg=T["pink"])
            self.app.glitch.now(self.head)
            return
        password = typed_password if typed_password is not None else \
            (self.password.get() or None)
        name = self.name.get().strip() or server.host
        self.status.configure(text=t('net.connecting', name=name), fg=T["accent"])
        # the dialog closes only when the connection works; until then Cancel gives up
        self.cancel_connect = self.app.network_go(
            self.window, server, password, name=name,
            saved=password is None, remember=bool(password) and self.remember.value,
            save_as=name if self.keep.value else '',
            on_fail=self.fail, on_ok=self._ok)

    def _ok(self) -> None:
        self.cancel_connect = None
        self.done(True)

    def cancel(self) -> None:
        if self.cancel_connect:
            self.cancel_connect()
            self.cancel_connect = None
        self.done(None)
