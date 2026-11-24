"""The base of the three tabs, plus the sentences shared by all of them."""

from typing import Callable

import tkinter as tk

from .imagewrite import Cancelled, VerifyFailed
from .lang import local_units
from .model import human_size
from .ops import BadInput, Refused
from .text import t
from .udisks import DiskError
from .widgets import T, WolkButton


def size_text(n: int) -> str:
    return local_units(human_size(n))


def error_text(exc: BaseException) -> str:
    """A sentence for whatever went wrong. The refusals and bad inputs are ours; DiskError is
    udisks' (with its own words appended, they're the only detail that helps)."""
    if isinstance(exc, Refused):
        return t(exc.verdict.key, **exc.verdict.args)
    if isinstance(exc, BadInput):
        return t(exc.key, **{k: (size_text(int(v)) if k in ('max', 'image', 'drive') and str(v).isdigit()
                                 else v) for k, v in exc.args.items()})
    if isinstance(exc, DiskError):
        base = t(exc.key)
        return f'{base} ({exc.detail})' if exc.detail and exc.key == 'err.failed' else base
    if isinstance(exc, Cancelled):
        return t('image.stopped')
    if isinstance(exc, VerifyFailed):
        return t('image.verify_failed', offset=exc.offset)
    return t('err.failed') + f' ({exc})'


class View(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app

    def text(self, parent: tk.Misc, value: str = "", size: int = 9, bold: bool = False,
             fg: str = "", bg: str = "", **kw) -> tk.Label:
        return tk.Label(parent, text=value, font=self.app.font(size, bold),
                        fg=fg or T["text"], bg=bg or parent.cget("bg"), anchor="w", **kw)

    def heading(self, parent: tk.Misc, value: str) -> tk.Label:
        return self.text(parent, value.upper(), 8, True, T["muted"])

    def note(self, parent: tk.Misc, value: str, wrap: int = 0, fg: str = "") -> tk.Label:
        return self.text(parent, value, 8, False, fg or T["muted"], justify="left",
                         wraplength=wrap or self.app.px(640))

    def button(self, parent: tk.Misc, value: str, command: Callable[[], None],
               variant: str = "ghost") -> WolkButton:
        return WolkButton(parent, value, command, self.app.font(8), variant,
                          padx=self.app.px(10), pady=self.app.px(5))

    def refresh(self) -> None:
        """Called when this tab opens."""

    def disks_changed(self) -> None:
        """Called when the list of drives was read again."""
