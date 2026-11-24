"""The base of the four tabs: knows the app, builds small labelled pieces."""

from typing import Callable

import tkinter as tk

from .widgets import T, WolkButton


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
                          padx=self.app.px(12), pady=self.app.px(5))

    def refresh(self) -> None:
        """Called every sample while this tab is open."""


def temp_text(value) -> str:
    return "--" if value is None else f"{value:.0f} °C"


def rpm_text(value) -> str:
    return "--" if value is None else f"{value:,} RPM".replace(",", " ")


def duty_text(value) -> str:
    return "--" if value is None else f"{value:.0f} %"
