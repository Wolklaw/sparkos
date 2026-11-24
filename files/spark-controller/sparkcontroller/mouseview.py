"""Spark Mouse: the DPI slots, the report rate and the onboard profile of a gaming mouse, through
ratbagd. Everything is edited on a copy; nothing is sent to the mouse until Apply, which writes
the difference and saves it in the mouse's own memory."""

from typing import Dict, List, Optional

import tkinter as tk

from . import mouse
from .mouse import Mouse, MouseError, Profile
from .text import t
from .ui import scrollable
from .viewkit import View
from .widgets import T, Segmented, Toggle


class MouseView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        self.backend = app.mouse_backend
        self.mice: List[Mouse] = []              # as read from the mouse
        self.edits: Dict[str, Mouse] = {}        # what the tab shows, by device path
        self.current: Optional[Mouse] = None     # the original of the mouse on screen
        self.profile: Optional[Profile] = None   # the edited profile on screen
        self.scanning = self.scanned = self.applying = False

        outer, body = scrollable(self, T["bg"])
        outer.pack(fill="both", expand=True)
        pad = tk.Frame(body, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))

        top = tk.Frame(pad, bg=T["bg"])
        top.pack(fill="x")
        self.title = self.text(top, t("mouse.scanning"), 11, True)
        self.title.pack(side="left")
        self.rescan_button = self.button(top, t("mouse.rescan"), self.scan)
        self.rescan_button.pack(side="right")
        self.mice_row = tk.Frame(pad, bg=T["bg"])      # a picker, only with two mice or more
        self.mice_row.pack(fill="x")
        self.message = self.note(pad, "", px(720))
        self.message.pack(anchor="w", pady=(px(4), 0))

        self.controls = tk.Frame(pad, bg=T["bg"])
        self.heading(self.controls, t("mouse.profiles")).pack(anchor="w", pady=(px(8), 0))
        self.profile_row = tk.Frame(self.controls, bg=T["bg"])
        self.profile_row.pack(anchor="w", pady=(px(4), 0))
        line = tk.Frame(self.controls, bg=T["bg"])
        line.pack(fill="x", pady=(px(6), 0))
        self.profile_state = self.note(line, "", px(520))
        self.profile_state.pack(side="left")
        self.use_button = self.button(line, t("mouse.use_profile"), self.use_profile)
        self.use_button.pack(side="left", padx=(px(10), 0))

        self.warn_box = tk.Frame(self.controls, bg=T["bg"])      # empty (no height) unless warned
        self.warn_box.pack(fill="x")
        self.warning = self.text(self.warn_box, "", 9, True, T["gold"], justify="left",
                                 wraplength=px(720))
        self.warning_row = tk.Frame(self.warn_box, bg=T["bg"])
        self.fix_button = self.button(self.warning_row, "", self.fix_dpi, "primary")

        self.heading(self.controls, t("mouse.slots")).pack(anchor="w", pady=(px(14), px(4)))
        self.slots = tk.Frame(self.controls, bg=T["panel"], highlightthickness=1,
                              highlightbackground=T["line"])
        self.slots.pack(fill="x")
        self.heading(self.controls, t("mouse.rate")).pack(anchor="w", pady=(px(14), px(4)))
        self.rate_row = tk.Frame(self.controls, bg=T["bg"])
        self.rate_row.pack(anchor="w")

        bar = tk.Frame(self.controls, bg=T["bg"])
        bar.pack(fill="x", pady=(px(16), 0))
        self.apply_button = self.button(bar, t("mouse.apply"), self.apply, "primary")
        self.apply_button.pack(side="left")
        self.revert_button = self.button(bar, t("mouse.revert"), self.revert)
        self.revert_button.pack(side="left", padx=(px(8), 0))
        self.result = self.note(self.controls, "", px(720))
        self.result.pack(anchor="w", pady=(px(8), 0))
        self.note(self.controls, t("mouse.note"), px(720)).pack(anchor="w", pady=(px(10), 0))
        self.apply_button.set_enabled(False)
        self.revert_button.set_enabled(False)

    # — finding mice —
    def refresh(self) -> None:
        if not self.scanned and not self.scanning:
            self.scan()

    def scan(self) -> None:
        if self.scanning or self.applying:
            return
        self.scanning = True
        self.title.config(text=t("mouse.scanning"))
        self.app.set_status(t("status.mouse_scanning"), T["gold"])

        def found(mice, error) -> None:
            self.scanning = self.scanned = True
            self.app.set_status(t("status.watching"), T["accent"])
            if error is not None:
                self._problem(error)
                return
            self.mice = mice or []
            self.edits = {m.key: m.clone() for m in self.mice}
            if not self.mice:
                self._problem(None, t("mouse.none"))
                return
            keep = self.current.key if self.current else ""
            self._pick(next((m for m in self.mice if m.key == keep), self.mice[0]))
        self.app.worker.run(self.backend.list_mice, found)

    def _problem(self, error, text: str = "") -> None:
        self.current = self.profile = None
        self.controls.pack_forget()
        self._clear(self.mice_row)
        if error is not None:
            kind = error.kind if isinstance(error, MouseError) else mouse.FAILED
            known = {mouse.NO_GIO: "mouse.no_gio", mouse.NO_DAEMON: "mouse.no_daemon",
                     mouse.DENIED: "mouse.denied", mouse.BUSY: "mouse.busy"}
            text = t(known[kind]) if kind in known else t("mouse.failed", error=str(error))
        self.title.config(text=t("tab.mouse"))
        self.message.config(text=text, fg=T["gold"])

    @staticmethod
    def _clear(frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _pick(self, original: Mouse) -> None:
        self.current = original
        self.title.config(text=original.name)
        self.message.config(text="")
        self._clear(self.mice_row)
        if len(self.mice) > 1:
            Segmented(self.mice_row, [(m.name.upper(), m.key) for m in self.mice], original.key,
                      lambda key: self._pick(next(m for m in self.mice if m.key == key)),
                      self.app.font(8)).pack(anchor="w", pady=(self.app.px(6), 0))
        self.controls.pack(fill="x")
        edited = self.edits[original.key]
        shown = edited.active_profile or (edited.profiles[0] if edited.profiles else None)
        self.profile = shown
        self._show()

    # — drawing the editable parts —
    @property
    def edited(self) -> Optional[Mouse]:
        return self.edits.get(self.current.key) if self.current else None

    def _show(self) -> None:
        edited, profile = self.edited, self.profile
        if edited is None or profile is None:
            return
        px = self.app.px
        self._clear(self.profile_row)
        options = [(t("mouse.profile_off" if not p.enabled else "mouse.profile_n",
                      n=mouse.profile_label(p)).upper(), str(p.index)) for p in edited.profiles]
        Segmented(self.profile_row, options, str(profile.index), self._profile_picked,
                  self.app.font(8)).pack(anchor="w")
        active = edited.active_profile
        was = self.current.active_profile
        if active is not None:
            key = "mouse.active_now" if was is not None and was.index == active.index \
                else "mouse.active_next"
            self.profile_state.config(text=t(key, n=mouse.profile_label(active)))
        in_use = profile.active
        self.use_button.set_text(t("mouse.in_use" if in_use else "mouse.use_profile"))
        self.use_button.set_enabled(profile.enabled and not in_use)

        self._clear(self.slots)
        if not profile.enabled:
            self.note(self.slots, t("mouse.profile_is_off"), px(600)).pack(
                anchor="w", padx=px(10), pady=px(8))
        for slot in profile.slots:
            self._slot_row(profile, slot)
        self._clear(self.rate_row)
        if profile.rates:
            Segmented(self.rate_row, [(t("mouse.hz", hz=r).upper(), str(r))
                                      for r in profile.rates], str(profile.rate),
                      lambda value: self.set_rate(int(value)),
                      self.app.font(8)).pack(anchor="w")
        self._sync()

    def _slot_row(self, profile: Profile, slot) -> None:
        px = self.app.px
        row = tk.Frame(self.slots, bg=T["panel"])
        row.pack(fill="x", padx=px(8), pady=px(3))
        i = slot.index
        on = Toggle(row, t("mouse.on"), slot.enabled, lambda v, i=i: self.set_enabled(i, v),
                    self.app.font(8))
        on.pack(side="left")
        if not slot.can_disable:
            on.config(state="disabled")
        self.text(row, t("mouse.slot_n", n=i + 1), 9, False, T["muted"], width=8).pack(
            side="left", padx=(px(10), 0))
        self.button(row, "-", lambda i=i: self.step_slot(i, -1)).pack(side="left")
        self.text(row, t("mouse.dpi", dpi=slot.value), 10, True,
                  T["text"] if slot.enabled else T["dim"], width=11, justify="center").pack(
            side="left", padx=px(4))
        self.button(row, "+", lambda i=i: self.step_slot(i, 1)).pack(side="left")
        tk.Frame(row, bg=T["panel"]).pack(side="left", expand=True, fill="x")
        Toggle(row, t("mouse.active"), slot.active, lambda _v, i=i: self.make_active(i),
               self.app.font(8)).pack(side="left", padx=(0, px(6)))
        Toggle(row, t("mouse.default"), slot.default, lambda _v, i=i: self.make_default(i),
               self.app.font(8)).pack(side="left")

    def _sync(self, note: bool = True) -> None:
        """The warning, and whether Apply has anything to do."""
        edited, profile = self.edited, self.profile
        if edited is None or profile is None or self.current is None:
            return
        problem = mouse.low_dpi_problem(profile) if profile.enabled else None
        if problem is None:
            self.warning.pack_forget()
            self.warning_row.pack_forget()
            self.warning.config(text="")
        else:
            kind, dpi = problem
            suggest = mouse.suggestion(profile)
            slot = profile.active_slot
            self.warning.config(text=t("mouse.warn_off" if kind == "off" else "mouse.warn_low",
                                       dpi=dpi, slot=(slot.index + 1) if slot else 0,
                                       suggest=suggest))
            self.fix_button.set_text(t("mouse.fix", dpi=suggest))
            self.warning.pack(anchor="w", pady=(self.app.px(10), 0))
            self.fix_button.pack(side="left")
            self.warning_row.pack(anchor="w", pady=(self.app.px(6), 0))
        changes = mouse.diff_ops(self.current, edited)
        self.apply_button.set_enabled(bool(changes) and not self.applying)
        self.revert_button.set_enabled(bool(changes) and not self.applying)
        if changes and note:
            self.result.config(text=t("mouse.unsaved"), fg=T["gold"])
        elif self.result.cget("text") == t("mouse.unsaved"):
            self.result.config(text="")

    # — editing (all on the copy) —
    def _profile_picked(self, value: str) -> None:
        edited = self.edited
        if edited is not None:
            self.profile = next((p for p in edited.profiles if str(p.index) == value),
                                self.profile)
            self._show()

    def use_profile(self) -> None:
        if self.edited is not None and self.profile is not None and self.profile.enabled:
            mouse.set_active_profile(self.edited, self.profile.index)
            self._show()

    def _slot(self, index: int):
        return next((s for s in (self.profile.slots if self.profile else [])
                     if s.index == index), None)

    def step_slot(self, index: int, direction: int) -> None:
        slot = self._slot(index)
        if slot is not None:
            slot.value = mouse.step(slot.allowed, slot.value, direction)
            self._show()

    def set_enabled(self, index: int, on: bool) -> None:
        slot = self._slot(index)
        if slot is None or self.profile is None:
            return
        if not on:
            others = [s for s in self.profile.slots if s.enabled and s.index != index]
            if slot.active or slot.default or not others:
                self.result.config(text=t("mouse.keep_on"), fg=T["gold"])
                self._show()
                return
        slot.enabled = on
        self.result.config(text="")
        self._show()

    def make_active(self, index: int) -> None:
        slot = self._slot(index)
        if slot is not None and self.profile is not None:
            slot.enabled = True
            mouse.set_active_slot(self.profile, index)
            self._show()

    def make_default(self, index: int) -> None:
        slot = self._slot(index)
        if slot is not None and self.profile is not None:
            slot.enabled = True
            mouse.set_default_slot(self.profile, index)
            self._show()

    def set_rate(self, hz: int) -> None:
        if self.profile is not None:
            self.profile.rate = hz
            self._show()

    def fix_dpi(self) -> None:
        if self.profile is not None:
            mouse.apply_low_dpi_fix(self.profile)
            self._show()

    def revert(self) -> None:
        if self.current is not None and not self.applying:
            keep = self.profile.index if self.profile else 0
            self.edits[self.current.key] = self.current.clone()
            self.profile = next((p for p in self.edits[self.current.key].profiles
                                 if p.index == keep), None)
            self.result.config(text="")
            self._show()

    # — applying —
    def apply(self) -> None:
        original, edited = self.current, self.edited
        if original is None or edited is None or self.applying:
            return
        problems = mouse.validate(edited, original)
        if problems:
            key, blanks = problems[0]
            self.result.config(text=t(key, **blanks), fg=T["pink"])
            return
        if not mouse.diff_ops(original, edited):
            return
        self.applying = True
        self.apply_button.set_enabled(False)
        self.revert_button.set_enabled(False)
        self.app.set_status(t("status.applying"), T["gold"])
        backend = self.backend

        def job():
            backend.apply(original, edited)
            return backend.reread(original)

        def done(fresh, error) -> None:
            self.applying = False
            if error is not None:
                self._failed(error)
                return
            wanted = edited
            if fresh is None:
                self.result.config(text=t("mouse.applied_unread"), fg=T["gold"])
                self.app.set_status(t("status.saved"), T["accent"], 4000)
                self._adopt(wanted.clone(), wanted)
                return
            missing = mouse.differences(wanted, fresh)
            if missing:
                self.result.config(text=t("mouse.not_kept", n=len(missing)), fg=T["pink"])
                self.app.set_status(t("status.failed"), T["pink"], 6000)
                self.app.glitch.now(self.app.title, strong=True)
            else:
                self.result.config(text=t("mouse.applied"), fg=T["accent"])
                self.app.set_status(t("status.saved"), T["accent"], 4000)
                self.app.glitch.now(self.app.title)
            self._adopt(fresh, fresh.clone())
        self.app.worker.run(job, done)

    def _adopt(self, original: Mouse, edited: Mouse) -> None:
        """What the mouse holds now becomes the starting point again."""
        keep = self.profile.index if self.profile else 0
        self.mice = [original if m.key == original.key else m for m in self.mice]
        self.current = original
        self.edits[original.key] = edited
        self.profile = next((p for p in edited.profiles if p.index == keep), None)
        self._show()

    def _failed(self, error: BaseException) -> None:
        kind = error.kind if isinstance(error, MouseError) else mouse.FAILED
        known = {mouse.BUSY: "mouse.busy", mouse.DENIED: "mouse.denied",
                 mouse.NO_DAEMON: "mouse.no_daemon", mouse.NO_GIO: "mouse.no_gio"}
        text = t(known[kind]) if kind in known else t("mouse.apply_failed", error=str(error))
        self.result.config(text=text, fg=T["pink"])
        self.app.set_status(t("status.failed"), T["pink"], 6000)
        self.app.glitch.now(self.app.title, strong=True)
        self._sync(note=False)
