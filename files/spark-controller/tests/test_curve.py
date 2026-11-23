"""Curve interpolation, and the controller's smoothing, hysteresis and limits."""

import unittest

import support  # noqa: F401
from sparkcontroller import curve
from sparkcontroller.curve import FanController, fixed_curve, interpolate, normalise


class Points(unittest.TestCase):
    def test_sorted_and_never_falling(self):
        got = normalise([(60, 50), (30, 20), (45, 10), (45, 30)])
        self.assertEqual(got, [(30.0, 20.0), (45.0, 30.0), (60.0, 50.0)])
        duties = [d for _, d in normalise([(30, 60), (40, 20), (50, 70)])]
        self.assertEqual(duties, sorted(duties))

    def test_values_are_kept_in_range(self):
        self.assertEqual(normalise([(-5, -5), (200, 300)]), [(0.0, 0.0), (120.0, 100.0)])

    def test_at_most_twelve_points(self):
        self.assertEqual(len(normalise([(t, t) for t in range(30)])), curve.MAX_POINTS)


class Interpolation(unittest.TestCase):
    pts = [(30.0, 20.0), (50.0, 40.0), (70.0, 100.0)]

    def test_between_points(self):
        self.assertAlmostEqual(interpolate(self.pts, 40), 30.0)
        self.assertAlmostEqual(interpolate(self.pts, 60), 70.0)

    def test_flat_outside(self):
        self.assertEqual(interpolate(self.pts, 10), 20.0)
        self.assertEqual(interpolate(self.pts, 99), 100.0)

    def test_on_a_point(self):
        self.assertEqual(interpolate(self.pts, 50), 40.0)

    def test_empty_curve_is_full_speed(self):
        self.assertEqual(interpolate([], 40), 100.0)

    def test_fixed_curve_is_flat(self):
        flat = fixed_curve(35)
        self.assertEqual({interpolate(flat, t) for t in (0, 40, 100)}, {35.0})

    def test_every_preset_is_valid(self):
        for name, points in curve.PRESETS.items():
            with self.subTest(preset=name):
                self.assertEqual(normalise(points), [tuple(map(float, p)) for p in points])


def controller(**kw):
    return FanController(kw.pop('points', [(30, 20), (50, 40), (70, 100)]), **kw)


class Controller(unittest.TestCase):
    def test_first_call_goes_straight_to_target(self):
        self.assertEqual(controller(min_duty=0).update(50, 1), 40)

    def test_speeds_up_by_the_ramp_not_in_one_jump(self):
        c = controller(min_duty=0, ramp_up=8, average_s=0)
        c.update(30, 1)
        self.assertEqual(c.update(70, 1), 28)      # 20 + 8
        self.assertEqual(c.update(70, 1), 36)

    def test_slows_down_slower_than_it_speeds_up(self):
        c = controller(min_duty=0, ramp_down=2, average_s=0, hysteresis=0)
        c.update(70, 1)
        self.assertEqual(c.update(30, 1), 98)

    def test_a_short_spike_is_averaged_away(self):
        c = controller(min_duty=0, average_s=6)
        c.update(40, 1)
        c.update(75, 1)                            # a 1 second spike
        self.assertLess(c.duty, 60)

    def test_hysteresis_holds_the_speed_on_small_drops(self):
        c = controller(min_duty=0, average_s=0, hysteresis=3, ramp_down=100)
        c.update(50, 1)
        self.assertEqual(c.update(48.5, 1), 40)    # 1.5 degrees cooler: no change
        self.assertLess(c.update(45, 1), 40)       # 5 degrees cooler: it slows down

    def test_hotter_is_followed_at_once(self):
        c = controller(min_duty=0, average_s=0, hysteresis=3, ramp_up=100)
        c.update(50, 1)
        self.assertGreater(c.update(50.5, 1), 40)

    def test_minimum_and_maximum(self):
        self.assertEqual(controller(min_duty=25, average_s=0).update(10, 1), 25)
        self.assertEqual(controller(max_duty=60, average_s=0).update(90, 1), 60)

    def test_no_reading_means_the_safe_speed(self):
        c = controller(failsafe=80, ramp_up=100)
        c.update(35, 1)
        self.assertEqual(c.update(None, 1), 80)

    def test_a_long_or_negative_time_step_does_not_break_it(self):
        c = controller(min_duty=0)
        c.update(50, 1)
        self.assertEqual(c.update(50, 10_000), 40)
        self.assertEqual(c.update(50, -3), 40)


if __name__ == '__main__':
    unittest.main()
