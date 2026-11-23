"""Fan and temperature discovery against a fake sysfs tree."""

import os
import shutil
import tempfile
import unittest

import support
from sparkcontroller.hwmon import Hwmon


class Discovery(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='spark-controller-hwmon-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        support.fake_tree(self.root)
        self.hw = Hwmon(self.root)

    def test_chips_in_numeric_order_and_unnamed_ones_skipped(self):
        self.assertEqual(sorted(c.name for c in self.hw.chips()),
                         ['amdgpu', 'k10temp', 'nct6799', 'nvme'])
        self.assertEqual([os.path.basename(c.path) for c in self.hw.chips()][-1], 'hwmon10')

    def test_fans_listed_with_friendly_names(self):
        fans = {f.key: f for f in self.hw.fans()}
        self.assertEqual(sorted(fans), ['amdgpu/fan1', 'nct6799/fan1', 'nct6799/fan2',
                                        'nct6799/fan3'])
        self.assertEqual(fans['amdgpu/fan1'].label, 'GPU fan')
        self.assertEqual(fans['nct6799/fan2'].label, 'Motherboard fan 2')

    def test_a_header_without_pwm_is_read_only(self):
        fans = {f.key: f for f in self.hw.fans()}
        self.assertFalse(fans['nct6799/fan3'].controllable)
        self.assertTrue(fans['nct6799/fan1'].controllable)

    def test_rpm_and_duty(self):
        fan = {f.key: f for f in self.hw.fans()}['nct6799/fan1']
        self.assertEqual(fan.rpm(), 900)
        self.assertAlmostEqual(fan.duty(), 39.2, places=1)     # 100 of 255

    def test_cpu_and_gpu_sources(self):
        self.assertEqual(self.hw.cpu_sensor().label, 'CPU Tctl')
        self.assertEqual(self.hw.gpu_sensor().label, 'GPU edge')
        temps = self.hw.source_temps()
        self.assertEqual((temps['cpu'], temps['gpu'], temps['max']), (52.0, 61.0, 61.0))

    def test_max_is_unknown_when_a_sensor_does_not_answer(self):
        support.put(os.path.join(self.root, 'hwmon3', 'temp1_input'), 'garbage')
        temps = self.hw.source_temps()
        self.assertEqual(temps['cpu'], 52.0)
        self.assertIsNone(temps['gpu'])
        self.assertIsNone(temps['max'])       # not 52: a hot GPU must not be hidden

    def test_a_dead_sensor_reads_as_none(self):
        support.put(os.path.join(self.root, 'hwmon2', 'temp1_input'), -128000)
        self.assertIsNone(self.hw.cpu_sensor().read())

    def test_two_chips_of_one_kind_get_stable_keys(self):
        support.chip(self.root, 'hwmon11', 'nvme', temp1_input=39000)
        keys = [s.key for s in self.hw.temps() if s.chip == 'nvme']
        self.assertEqual(keys, ['nvme/temp1', 'nvme#2/temp1'])

    def test_missing_tree(self):
        gone = Hwmon(os.path.join(self.root, 'nothing'))
        self.assertEqual((gone.chips(), gone.fans(), gone.temps()), ([], [], []))
        self.assertIsNone(gone.source_temps()['max'])


class Writing(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='spark-controller-hwmon-')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        support.fake_tree(self.root)
        self.fan = {f.key: f for f in Hwmon(self.root).fans()}['nct6799/fan1']
        self.pwm = os.path.join(self.root, 'hwmon10', 'pwm1')
        self.enable = os.path.join(self.root, 'hwmon10', 'pwm1_enable')

    def value(self, path):
        with open(path) as f:
            return int(f.read())

    def test_takeover_remembers_the_original_mode(self):
        self.assertEqual(self.fan.takeover(), 5)
        self.assertEqual(self.value(self.enable), 1)

    def test_set_duty_scales_to_the_chip(self):
        self.fan.set_duty(50)
        self.assertEqual(self.value(self.pwm), 128)
        self.fan.set_duty(500)
        self.assertEqual(self.value(self.pwm), 255)
        self.fan.set_duty(-4)
        self.assertEqual(self.value(self.pwm), 0)

    def test_release_restores_and_never_leaves_manual(self):
        self.fan.takeover()
        self.fan.release(5)
        self.assertEqual(self.value(self.enable), 5)
        self.fan.takeover()
        self.fan.release(None)
        self.assertEqual(self.value(self.enable), 2)
        self.fan.takeover()
        self.fan.release(1)
        self.assertEqual(self.value(self.enable), 2)


if __name__ == '__main__':
    unittest.main()
