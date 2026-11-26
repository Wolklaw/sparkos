"""The fan configuration file, the root helper that installs it, and the daemon's steps."""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import support
from sparkcontroller import config, helper
from sparkcontroller.daemon import Daemon
from sparkcontroller.hwmon import Hwmon


class Validation(unittest.TestCase):
    def test_defaults_fill_in(self):
        got = config.validate({"fans": {"nct6799/fan1": {"enabled": True}}})
        entry = got["fans"]["nct6799/fan1"]
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["preset"], "balanced")
        self.assertEqual(entry["source"], "max")

    def test_rejects_what_is_not_a_fan_list(self):
        bad = [[], {"fans": 5}, {"fans": {"a": 3}},
               {"fans": {"a;b": {}}}, {"fans": {"a\nb": {}}},
               {"fans": {"a": {"enabled": "yes"}}},
               {"fans": {"a": {"preset": "turbo"}}},
               {"fans": {"a": {"source": "disk"}}},
               {"fans": {"a": {"fixed": 101}}},
               {"fans": {"a": {"fixed": True}}},
               {"fans": {"a": {"fixed": float("nan")}}},
               {"fans": {"a": {"curve": []}}},
               {"fans": {"a": {"curve": [[30]]}}},
               {"fans": {"a": {"curve": [[30, 200]]}}},
               {"fans": {"a": {"min_duty": 60, "max_duty": 40}}},
               {"fans": {"a": {"ramp_up": 0}}}]
        for data in bad:
            with self.subTest(data=data):
                with self.assertRaises(config.ConfigError):
                    config.validate(data)

    def test_unknown_keys_are_dropped(self):
        got = config.validate({"fans": {"a": {"enabled": False, "run": "rm -rf /"}}})
        self.assertNotIn("run", got["fans"]["a"])

    def test_curve_is_cleaned(self):
        got = config.validate({"fans": {"a": {"preset": "custom",
                                              "curve": [[60, 50], [30, 20], [45, 10]]}}})
        self.assertEqual(got["fans"]["a"]["curve"], [[30.0, 20.0], [45.0, 20.0], [60.0, 50.0]])

    def test_invalid_json(self):
        with self.assertRaises(config.ConfigError):
            config.loads("{not json")


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-controller-config-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.path = os.path.join(self.dir, 'sub', 'fans.json')

    def test_missing_file_is_an_empty_configuration(self):
        self.assertEqual(config.load(self.path), config.empty())

    def test_save_then_load(self):
        data = {"fans": {"nct6799/fan1": {"enabled": True, "preset": "quiet", "source": "cpu"}}}
        config.save(data, self.path)
        self.assertEqual(config.load(self.path), config.validate(data))
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o644)
        self.assertFalse(os.path.exists(self.path + '.tmp'))

    def test_save_refuses_a_bad_file_and_keeps_the_old_one(self):
        config.save({"fans": {"a": {"enabled": True}}}, self.path)
        with self.assertRaises(config.ConfigError):
            config.save({"fans": {"a": {"preset": "turbo"}}}, self.path)
        self.assertTrue(config.load(self.path)["fans"]["a"]["enabled"])

    def test_broken_file_raises(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'w') as f:
            f.write('[1, 2')
        with self.assertRaises(config.ConfigError):
            config.load(self.path)

    def test_environment_overrides_the_path(self):
        with mock.patch.dict(os.environ, {"SPARK_CONTROLLER_CONFIG": self.path}):
            self.assertEqual(config.config_path(), self.path)

    def test_presets_and_fixed_make_controllers(self):
        quiet = config.controller_for({"preset": "quiet"})
        fixed = config.controller_for({"preset": "fixed", "fixed": 42, "min_duty": 0})
        self.assertEqual(fixed.update(95, 1), 42)
        self.assertLessEqual(quiet.update(30, 1), 40)


class Helper(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-controller-helper-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.path = os.path.join(self.dir, 'fans.json')
        patcher = mock.patch.object(helper, '_systemctl', return_value=0)
        self.systemctl = patcher.start()
        self.addCleanup(patcher.stop)

    def test_installs_and_starts_the_service(self):
        self.systemctl.side_effect = lambda *args: 3 if args[0] == "is-active" else 0
        text = json.dumps({"fans": {"a": {"enabled": True}}})
        self.assertEqual(helper.install_config(text, self.path), 0)
        self.assertTrue(config.load(self.path)["fans"]["a"]["enabled"])
        self.systemctl.assert_any_call("start", helper.SERVICE)
        # no SIGHUP to a daemon that is just starting: it would end it
        self.assertNotIn(mock.call("kill", "--signal=SIGHUP", helper.SERVICE),
                         self.systemctl.call_args_list)

    def test_running_service_reloads_without_restart(self):
        text = json.dumps({"fans": {"a": {"enabled": True}}})
        self.assertEqual(helper.install_config(text, self.path), 0)
        self.systemctl.assert_any_call("kill", "--signal=SIGHUP", helper.SERVICE)
        self.assertNotIn(mock.call("start", helper.SERVICE), self.systemctl.call_args_list)

    def test_stops_the_service_when_no_fan_is_on(self):
        self.assertEqual(helper.install_config('{"fans": {"a": {"enabled": false}}}', self.path), 0)
        self.systemctl.assert_called_once_with("stop", helper.SERVICE)

    def test_refuses_a_broken_configuration(self):
        for text in ('{"fans": 5}', 'garbage', '{"fans": {"a": {"preset": "x"}}}'):
            with self.subTest(text=text):
                self.assertEqual(helper.install_config(text, self.path), 2)
        self.assertFalse(os.path.exists(self.path))
        self.systemctl.assert_not_called()

    def test_main_usage(self):
        self.assertEqual(helper.main(['nonsense']), 64)
        self.assertEqual(helper.main(['release']), 0)


class Steps(unittest.TestCase):
    """The daemon against the fake tree: it takes a fan over, writes duty, hands it back."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-controller-daemon-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.tree = os.path.join(self.dir, 'hwmon')
        support.fake_tree(self.tree)
        self.cfg = os.path.join(self.dir, 'fans.json')
        self.run_dir = os.path.join(self.dir, 'run')
        self.now = 100.0
        self.pwm = os.path.join(self.tree, 'hwmon10', 'pwm1')
        self.enable = os.path.join(self.tree, 'hwmon10', 'pwm1_enable')

    def daemon(self):
        return Daemon(Hwmon(self.tree), None, self.cfg, self.run_dir, clock=lambda: self.now)

    def number(self, path):
        with open(path) as f:
            return int(f.read())

    def write_config(self, **entry):
        base = {"enabled": True, "preset": "fixed", "fixed": 50, "source": "cpu", "min_duty": 0}
        base.update(entry)
        config.save({"fans": {"nct6799/fan1": base}}, self.cfg)

    def test_takes_over_sets_duty_and_reports(self):
        self.write_config()
        d = self.daemon()
        report = d.step()
        self.assertEqual(report["nct6799/fan1"]["duty"], 50)
        self.assertEqual(self.number(self.enable), 1)
        self.assertEqual(self.number(self.pwm), 128)
        with open(os.path.join(self.run_dir, 'state.json')) as f:
            state = json.load(f)
        self.assertEqual(state["temps"]["cpu"], 52.0)
        # a fan nobody asked for stays alone
        self.assertEqual(self.number(os.path.join(self.tree, 'hwmon10', 'pwm2_enable')), 5)

    def test_release_all_gives_the_original_mode_back(self):
        self.write_config()
        d = self.daemon()
        d.step()
        d.release_all()
        self.assertEqual(self.number(self.enable), 5)
        with open(os.path.join(self.run_dir, 'originals.json')) as f:
            self.assertEqual(json.load(f), {})

    def test_turning_a_fan_off_in_the_file_hands_it_back(self):
        self.write_config()
        d = self.daemon()
        d.step()
        self.now += 2
        self.write_config(enabled=False)
        os.utime(self.cfg, (1, 1))              # make sure the change is noticed
        d.step()
        self.assertEqual(self.number(self.enable), 5)

    def test_a_crash_leftover_is_released_at_the_next_start(self):
        self.write_config()
        first = self.daemon()
        first.step()                            # then "crashes": no release_all
        self.assertEqual(self.number(self.enable), 1)
        second = self.daemon()
        second.release_leftovers()
        self.assertEqual(self.number(self.enable), 5)

    def test_missing_temperature_runs_the_fan_at_the_safe_speed(self):
        self.write_config(preset="balanced", min_duty=20)
        support.put(os.path.join(self.tree, 'hwmon2', 'temp1_input'), 'garbage')
        report = self.daemon().step()
        self.assertEqual(report["nct6799/fan1"]["duty"], 80)

    def test_a_broken_file_keeps_the_last_good_configuration(self):
        self.write_config()
        d = self.daemon()
        d.step()
        with open(self.cfg, 'w') as f:
            f.write('{"fans": 5}')
        self.now += 2
        report = d.step()
        self.assertIn("nct6799/fan1", report)

    def test_a_fan_that_is_not_there_is_ignored(self):
        config.save({"fans": {"gone/fan9": {"enabled": True}}}, self.cfg)
        self.assertEqual(self.daemon().step(), {})

    def test_request_stop_ends_run_at_once_and_hands_the_fan_back(self):
        import threading
        import time
        from sparkcontroller import daemon as daemon_mod
        self.write_config()
        d = self.daemon()
        with mock.patch.object(daemon_mod, 'INTERVAL_S', 30):
            t = threading.Thread(target=d.run)
            t.start()
            deadline = time.monotonic() + 5
            while not os.path.exists(os.path.join(self.run_dir, 'state.json')) \
                    and time.monotonic() < deadline:
                time.sleep(0.02)
            began = time.monotonic()
            d.request_stop()
            t.join(5)
        self.assertFalse(t.is_alive())
        self.assertLess(time.monotonic() - began, 2)
        self.assertEqual(self.number(self.enable), 5)


if __name__ == '__main__':
    unittest.main()
