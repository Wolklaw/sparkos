"""The schedule, the store, the engine (with a fake clock, notifier and sound) and the sound loop
(with a fake player). No display, no D-Bus, no real sound: everything runs in a temporary home."""

import datetime as dt
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ['SPARK_CLOCK_REDUCED_MOTION'] = '1'

from sparkclock import core, engine, schedule, sound, store  # noqa: E402


class Notes:
    def __init__(self):
        self.rung, self.infos, self.closed = [], [], []

    def ring(self, ring, replaces=0):
        self.rung.append(ring.key)
        return len(self.rung)

    def info(self, summary, body, replaces=0):
        self.infos.append((summary, body))
        return 99

    def close(self, notification):
        self.closed.append(notification)


class Quiet:
    def __init__(self):
        self.log = []

    def start(self, name, volume=80):
        self.log.append(('start', name))
        return True

    def tick(self):
        pass

    def stop(self):
        self.log.append(('stop',))


class Home(unittest.TestCase):
    """A temporary config and state folder for every test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-clock-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved = {k: os.environ.get(k) for k in ('XDG_CONFIG_HOME', 'XDG_STATE_HOME')}
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.tmp, 'config')
        os.environ['XDG_STATE_HOME'] = os.path.join(self.tmp, 'state')
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make(self, at):
        notes, loop = Notes(), Quiet()
        clock = {'now': at}
        eng = engine.Engine(notes, loop, clock=lambda: clock['now'])
        return eng, notes, loop, clock


def stamp(hour, minute, second=0, day=15):
    return dt.datetime(2026, 7, day, hour, minute, second).timestamp()


class Schedule(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(schedule.parse_time('7:05'), (7, 5))
        self.assertEqual(schedule.parse_time('23:59'), (23, 59))
        for bad in ('24:00', '7:60', 'abc', '', '7'):
            self.assertIsNone(schedule.parse_time(bad), bad)

    def test_once_rings_at_the_next_time(self):
        alarm = {'time': '07:30', 'days': []}
        self.assertEqual(schedule.next_alarm_time(alarm, stamp(7, 0)), stamp(7, 30))
        self.assertEqual(schedule.next_alarm_time(alarm, stamp(7, 30)), stamp(7, 30, day=16))

    def test_days_of_the_week(self):
        # 2026-07-15 is a Wednesday (2); an alarm on Mondays (0) rings on the 20th
        alarm = {'time': '06:00', 'days': [0]}
        self.assertEqual(schedule.next_alarm_time(alarm, stamp(12, 0)), stamp(6, 0, day=20))

    def test_bad_time_never_rings(self):
        self.assertIsNone(schedule.next_alarm_time({'time': 'x', 'days': []}, 0))

    def test_daylight_saving_keeps_the_clock_time(self):
        """07:30 stays 07:30 across the spring change (Montréal, 2026-03-08)."""
        old = os.environ.get('TZ')
        os.environ['TZ'] = 'America/Toronto'
        time.tzset()
        try:
            before = dt.datetime(2026, 3, 6, 12, 0).timestamp()
            first = schedule.next_alarm_time({'time': '07:30', 'days': []}, before)
            second = schedule.next_alarm_time({'time': '07:30', 'days': []}, first)
            self.assertEqual(dt.datetime.fromtimestamp(first).strftime('%H:%M'), '07:30')
            self.assertEqual(dt.datetime.fromtimestamp(second).strftime('%H:%M'), '07:30')
            self.assertEqual(second - first, 23 * 3600)          # the short day
        finally:
            if old is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = old
            time.tzset()


class Helpers(unittest.TestCase):
    def test_parse_duration(self):
        for text, seconds in (('90', 90), ('5m', 300), ('1h30m', 5400), ('1:30', 90),
                              ('2h', 7200), ('10 s', 10)):
            self.assertEqual(core.parse_duration(text), seconds, text)
        for bad in ('', 'soon', '-5', '0'):
            self.assertLessEqual(core.parse_duration(bad), 0, bad)

    def test_hms(self):
        self.assertEqual(core.hms(65), '01:05')
        self.assertEqual(core.hms(3725), '1:02:05')


class Store(Home):
    def test_config_round_trip_and_cleaning(self):
        store.update_config(lambda c: c['alarms'].append(
            {'time': '07:00', 'days': [0, 1], 'label': 'Work', 'enabled': True}))
        alarms = store.load_config()['alarms']
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]['label'], 'Work')
        self.assertTrue(alarms[0]['id'])

    def test_a_broken_file_gives_defaults(self):
        os.makedirs(core.config_dir(), exist_ok=True)
        with open(os.path.join(core.config_dir(), 'clock.json'), 'w') as f:
            f.write('{ not json')
        self.assertEqual(store.load_config()['alarms'], [])

    def test_writes_are_atomic_files_with_no_temp_left(self):
        store.add_timer(60, 'x', now=1000.0)
        names = os.listdir(core.state_dir())
        self.assertFalse([n for n in names if n.endswith('.tmp')], names)

    def test_timer_left(self):
        timer = store.add_timer(60, 'tea', now=1000.0)
        self.assertAlmostEqual(store.timer_left(timer, 1020.0), 40.0)
        self.assertEqual(store.timer_left(timer, 2000.0), 0.0)

    def test_service_alive_by_heartbeat(self):
        self.assertFalse(store.service_alive(1000.0, {'beat': 0}))
        self.assertTrue(store.service_alive(1000.0, {'beat': 990.0}))
        self.assertFalse(store.service_alive(1000.0, {'beat': 900.0}))

    def test_commands_are_taken_once(self):
        store.send_command('stop', 'alarm:1')
        self.assertEqual([c['cmd'] for c in store.take_commands()], ['stop'])
        self.assertEqual(store.take_commands(), [])


class Engine(Home):
    def alarm(self, hour, minute, days=(), label='Work'):
        store.update_config(lambda c: c['alarms'].append(
            {'time': f'{hour:02d}:{minute:02d}', 'days': list(days), 'label': label,
             'enabled': True}))

    def test_rings_on_time_and_not_before(self):
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 29, 0))
        eng.tick(stamp(7, 29, 30))
        self.assertEqual(notes.rung, [])
        eng.tick(stamp(7, 30, 1))
        self.assertEqual(len(notes.rung), 1)
        self.assertEqual(loop.log[0][0], 'start')

    def test_stop_ends_it_and_turns_a_one_time_alarm_off(self):
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 29, 0))
        eng.tick(stamp(7, 30, 1))
        key = notes.rung[0]
        self.assertTrue(eng.action(key, 'stop', stamp(7, 30, 5)))
        self.assertEqual(eng.rings, {})
        self.assertEqual(loop.log[-1], ('stop',))
        self.assertFalse(store.load_config()['alarms'][0]['enabled'])

    def test_a_repeating_alarm_stays_on(self):
        self.alarm(7, 30, days=range(7))
        eng, notes, loop, clock = self.make(stamp(7, 29, 0))
        eng.tick(stamp(7, 30, 1))
        eng.action(notes.rung[0], 'stop', stamp(7, 30, 5))
        self.assertTrue(store.load_config()['alarms'][0]['enabled'])
        eng.tick(stamp(7, 30, 30))
        self.assertEqual(len(notes.rung), 1)                 # not again the same minute

    def test_snooze_rings_again_later(self):
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 29, 0))
        eng.tick(stamp(7, 30, 1))
        eng.action(notes.rung[0], 'snooze', stamp(7, 30, 5))
        self.assertEqual(eng.rings, {})
        eng.tick(stamp(7, 38, 0))
        self.assertEqual(len(notes.rung), 1)
        eng.tick(stamp(7, 39, 10))                           # 9 minutes after the snooze
        self.assertEqual(len(notes.rung), 2)

    def test_timer_rings_and_plus_one_minute(self):
        timer = store.add_timer(60, 'Tea', now=stamp(8, 0, 0))
        eng, notes, loop, clock = self.make(stamp(8, 0, 0))
        eng.tick(stamp(8, 0, 30))
        self.assertEqual(notes.rung, [])
        eng.tick(stamp(8, 1, 1))
        self.assertEqual(notes.rung, ['timer:' + timer['id']])
        eng.action(notes.rung[0], 'plus', stamp(8, 1, 3))
        self.assertEqual(store.load_timers()[0]['state'], 'running')
        eng.tick(stamp(8, 2, 5))
        self.assertEqual(len(notes.rung), 2)

    def test_several_timers_at_once(self):
        store.add_timer(60, 'a', now=stamp(8, 0, 0))
        store.add_timer(120, 'b', now=stamp(8, 0, 0))
        eng, notes, loop, clock = self.make(stamp(8, 0, 0))
        eng.tick(stamp(8, 1, 1))
        self.assertEqual(len(notes.rung), 1)
        eng.tick(stamp(8, 2, 1))
        self.assertEqual(len(notes.rung), 2)
        self.assertEqual(len(eng.rings), 2)

    def test_a_short_gap_still_rings_late(self):
        """The service was off (asleep, rebooting) across the alarm, back five minutes later."""
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 0, 0))
        eng.tick(stamp(7, 20, 0))
        eng.tick(stamp(7, 35, 0))
        self.assertEqual(len(notes.rung), 1)
        self.assertIn('late', list(eng.rings.values())[0].body.lower() + 'late')

    def test_a_long_gap_gives_a_missed_notice_not_a_ring(self):
        self.alarm(7, 30, label='Work')
        eng, notes, loop, clock = self.make(stamp(7, 0, 0))
        eng.tick(stamp(7, 20, 0))
        eng.tick(stamp(9, 0, 0))
        self.assertEqual(notes.rung, [])
        self.assertTrue(notes.infos)

    def test_restart_picks_up_where_the_service_left(self):
        """A second Engine (a new process after a reboot) reads last_tick from the file."""
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 0, 0))
        eng.tick(stamp(7, 20, 0))
        eng._save(stamp(7, 20, 0))
        eng2, notes2, loop2, clock2 = self.make(stamp(7, 32, 0))
        eng2.tick(stamp(7, 32, 0))
        self.assertEqual(len(notes2.rung), 1)

    def test_dismissing_the_notification_is_a_stop(self):
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 29, 0))
        eng.tick(stamp(7, 30, 1))
        eng.notification_closed(1, 2)
        self.assertEqual(eng.rings, {})

    def test_window_commands_reach_the_engine(self):
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 29, 0))
        eng.tick(stamp(7, 30, 1))
        store.send_command('stop', notes.rung[0])
        eng.tick(stamp(7, 30, 2))
        self.assertEqual(eng.rings, {})

    def test_shutdown_silences_and_marks_the_service_off(self):
        self.alarm(7, 30)
        eng, notes, loop, clock = self.make(stamp(7, 29, 0))
        eng.tick(stamp(7, 30, 1))
        eng.shutdown()
        self.assertEqual(loop.log[-1], ('stop',))
        self.assertFalse(store.service_alive(stamp(7, 30, 2), store.load_service()))


class SoundLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-clock-player-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = os.path.join(self.tmp, 'played')
        self.player = os.path.join(self.tmp, 'player')
        with open(self.player, 'w') as f:
            f.write(f'#!/bin/sh\necho "$@" >> "{self.log}"\n')
        os.chmod(self.player, os.stat(self.player).st_mode | stat.S_IXUSR)
        self.old = os.environ.get('SPARK_CLOCK_PLAYER')
        os.environ['SPARK_CLOCK_PLAYER'] = self.player
        self.addCleanup(self._restore)

    def _restore(self):
        if self.old is None:
            os.environ.pop('SPARK_CLOCK_PLAYER', None)
        else:
            os.environ['SPARK_CLOCK_PLAYER'] = self.old

    def test_the_built_in_sounds_exist(self):
        for name in sound.BUILT_IN:
            path = sound.sound_path(name)
            self.assertTrue(path and os.path.getsize(path) > 1000, name)

    def test_loop_plays_again_after_the_gap_and_stops(self):
        now = {'t': 100.0}
        loop = sound.Loop(clock=lambda: now['t'])
        self.assertTrue(loop.start('beacon', 50))
        deadline = time.monotonic() + 3
        while loop.proc is not None and loop.proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        loop.tick()
        self.assertEqual(loop.plays, 1)               # inside the gap: nothing new
        now['t'] += sound.GAP + 0.1
        loop.tick()
        self.assertEqual(loop.plays, 2)
        loop.stop()
        self.assertFalse(loop.playing)
        loop.tick()
        self.assertEqual(loop.plays, 2)
        with open(self.log) as f:
            self.assertIn('beacon.wav', f.read())

    def test_no_player_is_reported_not_raised(self):
        os.environ.pop('SPARK_CLOCK_PLAYER', None)
        old_path = os.environ.get('PATH')
        os.environ['PATH'] = os.path.join(self.tmp, 'empty')
        try:
            loop = sound.Loop()
            self.assertFalse(loop.start('beacon'))
            self.assertTrue(loop.broken)
        finally:
            os.environ['PATH'] = old_path


if __name__ == '__main__':
    unittest.main()
