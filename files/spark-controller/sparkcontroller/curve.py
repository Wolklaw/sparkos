"""Fan curves: temperature to duty, with the smoothing that keeps fans from running in bursts.

A fan on its own firmware curve follows the temperature sample by sample, so a short load spike
(a game loading, a browser tab) turns into a loud ramp and a drop a second later. FanController
does three things the firmware doesn't:
  - averages the temperature over a few seconds (exponential moving average),
  - holds the speed until the temperature has moved by the hysteresis amount on the way down,
  - moves the duty at a limited rate: up fast enough to stay safe, down slowly.
"""

import math
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

PRESETS = {
    # (temperature in C, duty in %)
    "quiet": [(40, 20), (55, 30), (65, 45), (75, 65), (85, 100)],
    "balanced": [(35, 30), (50, 40), (60, 55), (70, 75), (80, 100)],
    "performance": [(30, 40), (45, 55), (60, 75), (70, 90), (75, 100)],
}
PRESET_ORDER = ("quiet", "balanced", "performance", "fixed")

MAX_POINTS = 12


def normalise(points: Sequence[Sequence[float]]) -> List[Point]:
    """Sorted by temperature, one point per temperature, duty never falling as it gets hotter
    (a curve that slows a fan when the PC heats up is a mistake), values kept in range."""
    cleaned = {}
    for point in points:
        temp = max(0.0, min(120.0, float(point[0])))
        duty = max(0.0, min(100.0, float(point[1])))
        cleaned[round(temp, 1)] = duty
    out: List[Point] = []
    for temp in sorted(cleaned):
        duty = cleaned[temp]
        if out and duty < out[-1][1]:
            duty = out[-1][1]
        out.append((temp, duty))
    return out[:MAX_POINTS]


def interpolate(points: Sequence[Point], temp: float) -> float:
    """Duty for a temperature: a straight line between neighbouring points, flat outside."""
    if not points:
        return 100.0
    if temp <= points[0][0]:
        return points[0][1]
    if temp >= points[-1][0]:
        return points[-1][1]
    for (t0, d0), (t1, d1) in zip(points, points[1:]):
        if t0 <= temp <= t1:
            if t1 == t0:
                return d1
            return d0 + (d1 - d0) * (temp - t0) / (t1 - t0)
    return points[-1][1]


def fixed_curve(duty: float) -> List[Point]:
    duty = max(0.0, min(100.0, float(duty)))
    return [(0.0, duty), (100.0, duty)]


class FanController:
    """One fan's brain. Call update() with the source temperature and the seconds since the
    last call; it returns the duty (a whole percent) to write."""

    def __init__(self, points: Sequence[Point], hysteresis: float = 3.0, min_duty: float = 20.0,
                 max_duty: float = 100.0, ramp_up: float = 8.0, ramp_down: float = 2.0,
                 average_s: float = 6.0, failsafe: float = 80.0):
        self.points = normalise(points)
        self.hysteresis = max(0.0, hysteresis)
        self.min_duty = max(0.0, min_duty)
        self.max_duty = max(self.min_duty, min(100.0, max_duty))
        self.ramp_up = max(0.5, ramp_up)         # percent per second
        self.ramp_down = max(0.1, ramp_down)
        self.average_s = max(0.0, average_s)
        self.failsafe = max(self.min_duty, min(self.max_duty, failsafe))
        self.smoothed: Optional[float] = None    # averaged temperature
        self.reference: Optional[float] = None   # the temperature the speed is based on
        self.duty: Optional[float] = None        # where the fan is now

    def _clamp(self, duty: float) -> float:
        return max(self.min_duty, min(self.max_duty, duty))

    def target(self) -> float:
        if self.reference is None:
            return self.failsafe
        return self._clamp(interpolate(self.points, self.reference))

    def update(self, temp: Optional[float], dt: float) -> int:
        dt = max(0.0, dt)
        if temp is None:
            # no reading: go to the safe speed rather than hold a guess
            goal = self.failsafe
            self.smoothed = self.reference = None
        else:
            if self.smoothed is None:
                self.smoothed = temp
                self.reference = temp
            else:
                alpha = 1.0 if self.average_s <= 0 else 1.0 - math.exp(-dt / self.average_s)
                self.smoothed += (temp - self.smoothed) * alpha
            if self.reference is None or self.smoothed >= self.reference:
                self.reference = self.smoothed                # hotter: follow at once
            elif self.smoothed <= self.reference - self.hysteresis:
                self.reference = self.smoothed + self.hysteresis / 2   # cooler: step down
            goal = self.target()
        if self.duty is None:
            self.duty = goal                                  # first call: no slow start
        elif goal > self.duty:
            self.duty = min(goal, self.duty + self.ramp_up * dt)
        else:
            self.duty = max(goal, self.duty - self.ramp_down * dt)
        return int(round(self._clamp(self.duty)))
