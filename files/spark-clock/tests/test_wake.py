"""Waking the PC for an alarm: the schedule logic (sparkclock/wake.py), the engine hooking it up,
and the root helper's input checks (system/usr/libexec/spark-clock-wake). Nothing here touches
systemd, the RTC, pkexec or polkit: the helper and the scheduler are given fake runners."""

import importlib.machinery
import importlib.util
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ['SPARK_CLOCK_REDUCED_MOTION'] = '1'

from sparkclock import store, wake  # noqa: E402
from test_logic import Home, Notes, Quiet, stamp  # noqa: E402
from sparkclock import engine  # noqa: E402

HELPER_PATH = os.path.join(os.path.dirname(HERE), 'system', 'usr', 'libexec', 'spark-clock-wake')


def load_helper():
    loader = importlib.machinery.SourceFileLoader('spark_clock_wake_helper', HELPER_PATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


helper = load_helper()
NOW = 1_800_000_000.0


def config(*alarms, wake_on=True):
    return {'alarms': list(alarms), 'settings': {'wake': wake_on}}


def alarm_at(at, enabled=True):
    """An alarm that next rings at the epoch `at` (once, so no days)."""
    import datetime as dt
    when = dt.datetime.fromtimestamp(at)
    return {'id': 'a', 'time': f"{when.hour:02d}:{when.minute:02d}", 'days': [],
            'enabled': enabled}


class WakeTime(unittest.TestCase):
    def test_wakes_a_minute_early(self):
        self.assertEqual(wake.wake_time(NOW + 3600, NOW), int(NOW + 3600 - wake.LEAD))

    def test_inside_the_lead_it_wakes_at_the_ring(self):
        self.assertEqual(wake.wake_time(NOW + 40, NOW), int(NOW + 40))

    def test_about_to_ring_means_no_wake(self):
        self.assertIsNone(wake.wake_time(NOW + 5, NOW))
        self.assertIsNone(wake.wake_time(None, NOW))

    def test_too_far_away_means_no_wake(self):
        self.assertIsNone(wake.wake_time(NOW + wake.MAX_AHEAD + 60, NOW))
        self.assertIsNotNone(wake.wake_time(NOW + 7 * 86400, NOW))

    def test_always_inside_what_the_helper_accepts(self):
        for ahead in (16, 59, 61, 3600, 86400, 7 * 86400, wake.MAX_AHEAD):
            when = wake.wake_time(NOW + ahead, NOW)
            self.assertIsNotNone(when)
            helper.parse(['set', str(when)], NOW)


class NextRing(unittest.TestCase):
    def test_soonest_enabled_alarm_only(self):
        soon = alarm_at(stamp(9, 0))
        late = dict(alarm_at(stamp(10, 0)), id='b')
        off = dict(alarm_at(stamp(8, 0), enabled=False), id='c')
        now = stamp(7, 0)
        self.assertEqual(wake.next_ring(config(late, off, soon), [], now), stamp(9, 0))

    def test_a_waiting_snooze_counts(self):
        now = stamp(7, 0)
        ring = wake.next_ring(config(alarm_at(stamp(9, 0))), [{'at': now + 300}], now)
        self.assertEqual(ring, now + 300)

    def test_nothing_waiting(self):
        self.assertIsNone(wake.next_ring(config(), [], NOW))
        self.assertIsNone(wake.next_ring(config(alarm_at(NOW + 99, enabled=False)), [], NOW))


class Scheduler(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.answer = (0, '')
        self.up = True
        self.sched = wake.WakeScheduler(run=self.run_fake, is_available=lambda: self.up)
        self.now = stamp(7, 0)
        self.cfg = config(alarm_at(stamp(9, 0)))

    def run_fake(self, argv):
        self.calls.append(argv)
        return self.answer

    def test_arms_the_next_alarm_once(self):
        note = self.sched.update(self.cfg, [], self.now)
        self.assertEqual(note['state'], 'armed')
        self.assertEqual(self.calls, [[wake.PKEXEC, wake.HELPER, 'set',
                                       str(int(stamp(9, 0) - wake.LEAD))]])
        self.sched.update(self.cfg, [], self.now + 1)
        self.assertEqual(len(self.calls), 1)               # same answer, no second call

    def test_moves_when_the_next_ring_changes(self):
        self.sched.update(self.cfg, [], self.now)
        sooner = config(alarm_at(stamp(9, 0)), dict(alarm_at(stamp(8, 0)), id='b'))
        self.sched.update(sooner, [], self.now + 1)
        self.assertEqual(self.calls[-1][-1], str(int(stamp(8, 0) - wake.LEAD)))
        self.assertEqual(len(self.calls), 2)

    def test_after_the_wake_it_moves_to_the_ring_itself(self):
        self.sched.update(self.cfg, [], self.now)
        awake = stamp(9, 0) - 30
        self.sched.update(self.cfg, [], awake)
        self.assertEqual(self.calls[-1][-1], str(int(stamp(9, 0))))
        self.sched.update(self.cfg, [], awake + 1)
        self.assertEqual(len(self.calls), 2)               # not re-armed every second

    def test_option_off_clears_once_and_stays_quiet(self):
        self.sched.update(self.cfg, [], self.now)
        off = dict(self.cfg, settings={'wake': False})
        note = self.sched.update(off, [], self.now + 1)
        self.assertEqual(self.calls[-1][2:], ['clear'])
        self.assertEqual(note['state'], 'off')
        self.sched.update(off, [], self.now + 2)
        self.assertEqual(len(self.calls), 2)

    def test_last_alarm_gone_clears(self):
        self.sched.update(self.cfg, [], self.now)
        self.sched.update(config(), [], self.now + 1)
        self.assertEqual(self.calls[-1][2:], ['clear'])

    def test_no_helper_calls_nothing_and_says_unavailable(self):
        self.up = False
        note = self.sched.update(self.cfg, [], self.now)
        self.assertEqual(note['state'], 'unavailable')
        self.assertEqual(self.calls, [])

    def test_failure_is_reported_and_retried_later_not_every_second(self):
        self.answer = (1, 'not allowed')
        note = self.sched.update(self.cfg, [], self.now)
        self.assertEqual((note['state'], note['error']), ('failed', 'not allowed'))
        self.sched.update(self.cfg, [], self.now + 10)
        self.assertEqual(len(self.calls), 1)
        self.answer = (0, '')
        note = self.sched.update(self.cfg, [], self.now + wake.RETRY + 1)
        self.assertEqual(note['state'], 'armed')
        self.assertEqual(len(self.calls), 2)

    def test_a_runner_that_raises_is_a_failure_not_a_crash(self):
        def boom(argv):
            raise OSError('no pkexec')
        sched = wake.WakeScheduler(run=boom, is_available=lambda: True)
        self.assertEqual(sched.update(self.cfg, [], self.now)['state'], 'failed')


class EngineWake(Home):
    def test_the_engine_keeps_the_wake_time_and_reports_it(self):
        calls = []
        sched = wake.WakeScheduler(run=lambda argv: (calls.append(argv) or (0, '')),
                                   is_available=lambda: True)
        now = stamp(7, 0)
        eng = engine.Engine(Notes(), Quiet(), clock=lambda: now, wake=sched)
        store.update_config(lambda c: (c['settings'].update(wake=True),
                                       c['alarms'].append(store.clean_alarm(
                                           {'id': 'x', 'time': '09:00', 'enabled': True}))))
        eng.tick(now)
        self.assertEqual(calls[-1][2:], ['set', str(int(stamp(9, 0) - wake.LEAD))])
        self.assertEqual(store.load_service()['wake']['state'], 'armed')

    def test_a_broken_scheduler_never_stops_the_ringing(self):
        class Broken:
            def update(self, *args):
                raise RuntimeError('boom')
        now = stamp(7, 0)
        eng = engine.Engine(Notes(), Quiet(), clock=lambda: now, wake=Broken())
        eng.tick(now)                                       # no exception

    def test_no_scheduler_is_the_old_behaviour(self):
        now = stamp(7, 0)
        eng = engine.Engine(Notes(), Quiet(), clock=lambda: now)
        eng.tick(now)
        self.assertEqual(store.load_service()['wake'], {})

    def test_the_setting_defaults_off_and_survives_cleaning(self):
        self.assertIs(store.load_config()['settings']['wake'], False)
        store.update_config(lambda c: c['settings'].update(wake=True))
        self.assertIs(store.load_config()['settings']['wake'], True)
        store.update_config(lambda c: c['settings'].update(wake='yes'))
        self.assertIs(store.load_config()['settings']['wake'], False)


class HelperInput(unittest.TestCase):
    def go(self, argv, environ=None, now=NOW, exists=lambda p: True, answer=(0, '')):
        calls = []
        out, err = io.StringIO(), io.StringIO()
        code = helper.main(argv, {'PKEXEC_UID': '1000'} if environ is None else environ,
                           run=lambda a: (calls.append(a) or answer), clock=lambda: now,
                           out=out, err=err, exists=exists)
        return code, calls, out.getvalue(), err.getvalue()

    def test_a_good_time_runs_exactly_stop_then_one_timer(self):
        when = int(NOW + 3600)
        code, calls, out, _ = self.go(['set', str(when)])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ['/usr/bin/systemctl', 'stop', 'spark-clock-wake-1000.timer',
                                    'spark-clock-wake-1000.service'])
        run = calls[1]
        self.assertEqual(run[0], '/usr/bin/systemd-run')
        self.assertEqual(run[-1], '/usr/bin/true')
        self.assertIn('--timer-property=WakeSystem=true', run)
        self.assertIn('--unit=spark-clock-wake-1000', run)
        self.assertIn('--on-calendar=' + helper.calendar(when), run)
        self.assertTrue(helper.calendar(when).endswith(' UTC'))

    def test_clear_only_stops_the_users_timer(self):
        code, calls, out, _ = self.go(['clear'])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 'stop')

    def test_refuses_anything_that_is_not_a_plain_epoch(self):
        for bad in ('', '1', '-1', '+1800003600', '1800003600.5', '1800003600 ', ' 1800003600',
                    '0x6B49D3F0', '１８０００３６００', '--help', '1800003600\n', 'now+1h',
                    '18000036000', '180000360'):
            code, calls, _, err = self.go(['set', bad])
            self.assertEqual(code, 2, repr(bad))
            self.assertEqual(calls, [], repr(bad))
            self.assertIn('refused', err)

    def test_refuses_the_past_and_the_far_future(self):
        for when in (NOW - 5, NOW, NOW + helper.MIN_AHEAD - 1, NOW + helper.MAX_AHEAD + 1):
            code, calls, _, _ = self.go(['set', str(int(when))])
            self.assertEqual((code, calls), (2, []), when)
        for when in (NOW + helper.MIN_AHEAD, NOW + helper.MAX_AHEAD):
            self.assertEqual(self.go(['set', str(int(when))])[0], 0)

    def test_refuses_other_words_and_extra_arguments(self):
        for argv in ([], ['set'], ['reboot'], ['set', '1800003600', 'x'], ['clear', 'x'],
                     ['check', 'x'], ['--unit=foo'], ['set', '1800003600', '--on-active=1'],
                     ['stop'], ['run', '/bin/sh']):
            code, calls, _, _ = self.go(argv)
            self.assertEqual((code, calls), (2, []), argv)

    def test_the_unit_comes_from_pkexec_not_the_arguments(self):
        ok = str(int(NOW + 3600))
        for environ in ({}, {'PKEXEC_UID': ''}, {'PKEXEC_UID': '0'}, {'PKEXEC_UID': 'root'},
                        {'PKEXEC_UID': '1000; reboot'}, {'PKEXEC_UID': '-1'},
                        {'PKEXEC_UID': '01000'}, {'PKEXEC_UID': '1' * 11}):
            code, calls, _, _ = self.go(['set', ok], environ=environ)
            self.assertEqual((code, calls), (2, []), environ)
        _, calls, _, _ = self.go(['set', ok], environ={'PKEXEC_UID': '4242'})
        self.assertIn('--unit=spark-clock-wake-4242', calls[1])

    def test_check_needs_no_pkexec_and_runs_nothing(self):
        code, calls, out, _ = self.go(['check'], environ={})
        self.assertEqual((code, calls, out.strip()), (0, [], 'ok'))
        code, calls, out, _ = self.go(['check'], environ={}, exists=lambda p: False)
        self.assertEqual((code, calls), (1, []))
        self.assertTrue(out.startswith('no:'))

    def test_no_rtc_means_a_clear_failure_and_no_timer(self):
        code, calls, _, err = self.go(['set', str(int(NOW + 3600))],
                                      exists=lambda p: p != helper.RTC)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)                    # only the stop
        self.assertIn('real-time clock', err)

    def test_systemd_run_failing_is_reported(self):
        calls = []

        def run(argv):
            calls.append(argv)
            return (0, '') if argv[1] == 'stop' else (1, 'Failed to start')
        err = io.StringIO()
        code = helper.main(['set', str(int(NOW + 3600))], {'PKEXEC_UID': '1000'}, run=run,
                           clock=lambda: NOW, out=io.StringIO(), err=err,
                           exists=lambda p: True)
        self.assertEqual(code, 1)
        self.assertIn('Failed to start', err.getvalue())

    def test_the_file_is_executable_python_in_isolated_mode(self):
        self.assertTrue(os.access(HELPER_PATH, os.X_OK))
        with open(HELPER_PATH, encoding='utf-8') as f:
            self.assertEqual(f.readline().strip(), '#!/usr/bin/python3 -I')

    def test_the_polkit_action_names_the_helper_and_needs_an_active_session(self):
        policy = os.path.join(os.path.dirname(HERE), 'system', 'usr', 'share', 'polkit-1',
                              'actions', 'dev.wolklaw.SparkClock.wake.policy')
        with open(policy, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('exec.path">/usr/libexec/spark-clock-wake<', text)
        self.assertIn('<allow_any>no</allow_any>', text)
        self.assertIn('<allow_inactive>no</allow_inactive>', text)
        self.assertIn('<allow_active>yes</allow_active>', text)


if __name__ == '__main__':
    unittest.main()
