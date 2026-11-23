"""The curve editor: temperature across, fan duty up. Drag a point to move it, click empty space
to add one, double-click a point to remove it. Presets show their curve read-only; touching a
preset's curve turns it into a custom one (the window does that through on_edit)."""

from typing import Callable, List, Optional, Sequence, Tuple

import tkinter as tk

from .curve import MAX_POINTS, normalise
from .widgets import T

T_MIN, T_MAX = 20.0, 100.0
GRAB = 10        # pixels


class CurveEditor(tk.Canvas):
    def __init__(self, parent: tk.Misc, height: int, font, on_change: Callable[[List[List[float]]], None],
                 on_edit: Optional[Callable[[], bool]] = None):
        super().__init__(parent, height=height, bg=T["panel"], highlightthickness=1,
                         highlightbackground=T["line"], bd=0)
        self.font = font
        self.on_change = on_change
        self.on_edit = on_edit          # called before the first edit of a preset; False cancels
        self.points: List[List[float]] = []
        self.editable = False
        self.live: Tuple[Optional[float], Optional[float]] = (None, None)
        self.drag: Optional[int] = None
        self.margin = (34, 10, 10, 20)      # left, top, right, bottom
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Double-Button-1>", self._double)

    # — data —
    def set_points(self, points: Sequence[Sequence[float]], editable: bool) -> None:
        self.points = [list(p) for p in points]
        self.editable = editable
        self.draw()

    def set_live(self, temp: Optional[float], duty: Optional[float]) -> None:
        self.live = (temp, duty)
        self.draw()

    # — geometry —
    def _box(self) -> Tuple[float, float, float, float]:
        left, top, right, bottom = self.margin
        return left, top, max(left + 10, self.winfo_width() - right), \
            max(top + 10, self.winfo_height() - bottom)

    def to_px(self, temp: float, duty: float) -> Tuple[float, float]:
        x0, y0, x1, y1 = self._box()
        return (x0 + (temp - T_MIN) / (T_MAX - T_MIN) * (x1 - x0),
                y1 - duty / 100.0 * (y1 - y0))

    def from_px(self, x: float, y: float) -> Tuple[float, float]:
        x0, y0, x1, y1 = self._box()
        temp = T_MIN + (x - x0) / (x1 - x0) * (T_MAX - T_MIN)
        duty = (y1 - y) / (y1 - y0) * 100.0
        return max(T_MIN, min(T_MAX, temp)), max(0.0, min(100.0, duty))

    # — drawing —
    def draw(self) -> None:
        self.delete("all")
        x0, y0, x1, y1 = self._box()
        for duty in (0, 25, 50, 75, 100):
            _x, y = self.to_px(T_MIN, duty)
            self.create_line(x0, y, x1, y, fill=T["line"])
            self.create_text(x0 - 5, y, text=str(duty), anchor="e", fill=T["dim"], font=self.font)
        for temp in range(int(T_MIN), int(T_MAX) + 1, 10):
            x, _y = self.to_px(temp, 0)
            self.create_line(x, y0, x, y1, fill=T["line"])
            self.create_text(x, y1 + 4, text=str(temp), anchor="n", fill=T["dim"], font=self.font)
        if self.points:
            line = [(T_MIN, self.points[0][1])] + [tuple(p) for p in self.points] + \
                   [(T_MAX, self.points[-1][1])]
            pixels = [c for temp, duty in line for c in self.to_px(temp, duty)]
            for dx, colour in ((-2, T["ch_a"]), (2, T["ch_b"])):      # the channel slip
                shifted = [v + (dx if i % 2 == 0 else 0) for i, v in enumerate(pixels)]
                self.create_line(*shifted, fill=colour, width=1)
            self.create_line(*pixels, fill=T["accent"], width=2)
            for temp, duty in self.points:
                x, y = self.to_px(temp, duty)
                self.create_rectangle(x - 4, y - 4, x + 4, y + 4, outline=T["accent"],
                                      fill=T["accent"] if self.editable else T["panel"])
        temp, duty = self.live
        if temp is not None:
            x, _y = self.to_px(max(T_MIN, min(T_MAX, temp)), 0)
            self.create_line(x, y0, x, y1, fill=T["gold"], dash=(3, 3))
            if duty is not None:
                _x, y = self.to_px(temp, duty)
                self.create_oval(x - 4, y - 4, x + 4, y + 4, fill=T["gold"], outline="")

    # — mouse —
    def _nearest(self, x: float, y: float) -> Optional[int]:
        best, where = GRAB * GRAB, None
        for i, (temp, duty) in enumerate(self.points):
            px, py = self.to_px(temp, duty)
            d = (px - x) ** 2 + (py - y) ** 2
            if d <= best:
                best, where = d, i
        return where

    def _allowed(self) -> bool:
        if self.editable:
            return True
        return bool(self.on_edit and self.on_edit())

    def _press(self, event) -> None:
        if not self._allowed():
            return
        index = self._nearest(event.x, event.y)
        if index is None and len(self.points) < MAX_POINTS:
            temp, duty = self.from_px(event.x, event.y)
            self.points = [list(p) for p in normalise(self.points + [[round(temp), round(duty)]])]
            index = self._nearest(event.x, event.y)
        self.drag = index
        self.draw()

    def _move(self, event) -> None:
        if self.drag is None or not self.editable:
            return
        temp, duty = self.from_px(event.x, event.y)
        i = self.drag
        low_t = self.points[i - 1][0] + 1 if i > 0 else T_MIN
        high_t = self.points[i + 1][0] - 1 if i < len(self.points) - 1 else T_MAX
        low_d = self.points[i - 1][1] if i > 0 else 0.0
        high_d = self.points[i + 1][1] if i < len(self.points) - 1 else 100.0
        self.points[i] = [round(max(low_t, min(high_t, temp))),
                          round(max(low_d, min(high_d, duty)))]
        self.draw()

    def _release(self, _event) -> None:
        if self.drag is not None:
            self.drag = None
            self.on_change([list(p) for p in self.points])

    def _double(self, event) -> None:
        if not self.editable or len(self.points) <= 2:
            return
        index = self._nearest(event.x, event.y)
        if index is not None:
            del self.points[index]
            self.draw()
            self.on_change([list(p) for p in self.points])
