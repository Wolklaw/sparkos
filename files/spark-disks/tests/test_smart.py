"""Turning udisks' SMART answers into a verdict."""

import unittest

import support  # noqa: F401
from sparkdisks import smart


def ata(attrs=(), **props):
    base = {'SmartSupported': True, 'SmartUpdated': 1700000000, 'SmartTemperature': 313.15,
            'SmartPowerOnSeconds': 7200 * 3600, 'SmartFailing': False}
    base.update(props)
    return {'kind': 'ata', 'props': base, 'attributes': list(attrs)}


def attr(ident, value=100, threshold=0, pretty=0):
    # (id, name, flags, value, worst, threshold, pretty, pretty unit, more)
    return (ident, 'x', 0, value, value, threshold, pretty, 0, {})


def nvme(**attrs):
    return {'kind': 'nvme', 'props': {'SmartUpdated': 1700000000, 'SmartTemperature': 310.0,
                                      'SmartPowerOnHours': 1234, 'SmartCriticalWarning': []},
            'attributes': attrs}


class Ata(unittest.TestCase):
    def test_a_healthy_drive(self):
        h = smart.summarise(ata([attr(5), attr(9, 99)]))
        self.assertEqual(h.verdict, 'good')
        self.assertEqual(h.temperature_c, 40.0)
        self.assertEqual(h.hours, 7200)
        self.assertEqual(h.problems, [])

    def test_reallocated_sectors_warn(self):
        h = smart.summarise(ata([attr(5, 90, 10, 12)]))
        self.assertEqual(h.verdict, 'warning')
        self.assertIn('smart.reallocated', h.problems)

    def test_failing_flag_or_threshold(self):
        self.assertEqual(smart.summarise(ata(SmartFailing=True)).verdict, 'failing')
        h = smart.summarise(ata([attr(1, 5, 10)]))
        self.assertEqual(h.verdict, 'failing')
        self.assertEqual(h.problems[0], 'smart.failing')

    def test_worn_ssd(self):
        h = smart.summarise(ata([attr(177, 8)]))
        self.assertEqual(h.verdict, 'warning')
        self.assertIn('smart.worn', h.problems)
        fresh = smart.summarise(ata([attr(177, 100)]))
        self.assertIn(('smart.life_left', '100'), fresh.facts)
        self.assertEqual(fresh.verdict, 'good')

    def test_not_supported_or_never_read(self):
        self.assertEqual(smart.summarise(ata(SmartSupported=False)).verdict, 'unknown')
        h = smart.summarise(ata(SmartUpdated=0))
        self.assertEqual(h.verdict, 'unknown')
        self.assertEqual(h.facts, [('smart.not_read', '')])


class Nvme(unittest.TestCase):
    def test_healthy(self):
        h = smart.summarise(nvme(percent_used=3, avail_spare=100, spare_thresh=10, media_errors=0))
        self.assertEqual(h.verdict, 'good')
        self.assertIn(('smart.life_left', '97'), h.facts)
        self.assertEqual(h.hours, 1234)

    def test_worn_low_spare_and_media_errors(self):
        self.assertEqual(smart.summarise(nvme(percent_used=95)).problems, ['smart.worn'])
        self.assertIn('smart.spare_low', smart.summarise(nvme(avail_spare=5, spare_thresh=10)).problems)
        h = smart.summarise(nvme(media_errors=2))
        self.assertEqual(h.verdict, 'warning')
        self.assertIn('smart.media_errors', h.problems)

    def test_critical_warning(self):
        data = nvme()
        data['props']['SmartCriticalWarning'] = ['reliability']
        self.assertEqual(smart.summarise(data).verdict, 'failing')
        data['props']['SmartCriticalWarning'] = ['temperature']
        self.assertEqual(smart.summarise(data).verdict, 'warning')

    def test_nothing_known(self):
        self.assertEqual(smart.summarise({'kind': 'none'}).verdict, 'unknown')
        empty = {'kind': 'nvme', 'props': {}, 'attributes': {}}
        self.assertEqual(smart.summarise(empty).verdict, 'unknown')

    def test_kelvin(self):
        self.assertIsNone(smart.kelvin_to_c(0))
        self.assertIsNone(smart.kelvin_to_c('x'))
        self.assertEqual(smart.kelvin_to_c(273.15 + 30), 30.0)


if __name__ == '__main__':
    unittest.main()
