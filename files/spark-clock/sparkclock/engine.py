"""What rings and when. The service's brain, with no D-Bus, no GLib and no sound of its own: it is
given a notifier and a sound loop, so the tests can give it fakes and a clock.

Once a second, tick(now):
  - does what the window asked (stop, snooze) through commands.json;
  - rings every alarm whose time fell between the last tick and now (so a time that passed while
    the PC was asleep or off still rings, if it was in the last LATE_GRACE seconds; older ones
    become a "missed" notice and don't ring);
  - rings snoozed alarms and finished timers the same way;
  - stops a ring nobody answered after the "ring for" setting (5 minutes by default);
  - writes its last tick and its beat to service.json, so a restart knows where it stopped.
"""

import datetime as dt
import time
from typing import Any, Callable, Dict, List, Optional

from . import store
from .core import log
from .schedule import next_alarm_time
from .text import t

LATE_GRACE = 600          # a time missed by less than this (seconds) still rings
SAVE_EVERY = 5            # seconds between beats written to service.json
PLUS_SECONDS = 60         # "+1 min" on a finished timer


class Ring:
    def __init__(self, key: str, kind: str, ref: str, title: str, body: str, sound: str,
                 snooze: int, since: float, late: float = 0.0):
        self.key, self.kind, self.ref = key, kind, ref
        self.title, self.body, self.sound = title, body, sound
        self.label = body
        self.snooze, self.since, self.late = snooze, since, late
        self.notification = 0

    def actions(self) -> List[str]:
        """Flat [id, label, id, label] as the freedesktop notification spec wants."""
        if self.kind == 'alarm':
            return ['stop', t('action.stop'), 'snooze', t('action.snooze', minutes=self.snooze)]
        return ['stop', t('action.stop'), 'plus', t('action.plus_one')]

    def as_dict(self) -> Dict[str, Any]:
        return {'key': self.key, 'kind': self.kind, 'ref': self.ref, 'title': self.title,
                'body': self.body, 'snooze': self.snooze, 'since': self.since}


class Engine:
    def __init__(self, notifier, loop, clock: Callable[[], float] = time.time):
        self.notifier, self.loop, self.clock = notifier, loop, clock
        self.rings: Dict[str, Ring] = {}
        service = store.load_service()
        self.snoozes: List[Dict[str, Any]] = service['snoozes']
        last = service.get('last_tick')
        now = clock()
        # no note, or a note from the future (the clock was set back): start from now
        self.last_tick = last if isinstance(last, (int, float)) and last <= now else now
        self.saved_at = 0.0
        self.changed = True

    # ─── the tick ───

    def tick(self, now: Optional[float] = None) -> None:
        now = self.clock() if now is None else now
        if now < self.last_tick:
            self.last_tick = now
        for command in store.take_commands():
            self.action(str(command.get('key', '')), str(command.get('cmd', '')), now)
        config = store.load_config()
        self._alarms(config, now)
        self._snoozes(now)
        self._timers(now)
        self._expire(config, now)
        self.loop.tick()
        self.last_tick = now
        if self.changed or now - self.saved_at >= SAVE_EVERY:
            self._save(now)

    def _alarms(self, config: Dict[str, Any], now: float) -> None:
        once_done: List[str] = []
        for alarm in config['alarms']:
            if not alarm['enabled']:
                continue
            at = next_alarm_time(alarm, self.last_tick)
            if at is None or at > now:
                continue
            late = now - at
            if not alarm['days']:
                once_done.append(alarm['id'])
            if late > LATE_GRACE:
                self._missed(alarm['time'], alarm['label'], at)
                continue
            self._start(Ring(f"alarm:{alarm['id']}", 'alarm', alarm['id'],
                             t('ring.alarm_title', time=alarm['time']), alarm['label'],
                             alarm['sound'] or config['settings']['sound'], alarm['snooze'],
                             now, late), config)
        if once_done:
            def off(cfg):
                for a in cfg['alarms']:
                    if a['id'] in once_done:
                        a['enabled'] = False
            store.update_config(off)

    def _snoozes(self, now: float) -> None:
        due = [s for s in self.snoozes if s.get('at', 0) <= now]
        if not due:
            return
        self.snoozes = [s for s in self.snoozes if s not in due]
        self.changed = True
        config = store.load_config()
        for s in due:
            self._start(Ring(s['key'], 'alarm', s['ref'], s['title'], s['body'], s['sound'],
                             s['snooze'], now), config)

    def _timers(self, now: float) -> None:
        fired: List[Dict[str, Any]] = []

        def mark(timers):
            for timer in timers:
                if timer['state'] == 'running' and timer['end'] is not None \
                        and timer['end'] <= now:
                    late = now - timer['end']
                    timer['state'] = 'ringing' if late <= LATE_GRACE else 'done'
                    timer['remaining'] = 0.0
                    fired.append(dict(timer, late=late))

        if any(x['state'] == 'running' and x['end'] is not None and x['end'] <= now
               for x in store.load_timers()):
            store.update_timers(mark)
        if not fired:
            return
        config = store.load_config()
        for timer in fired:
            from .core import duration_words
            body = timer['label'] or duration_words(timer['duration'])
            if timer['late'] > LATE_GRACE:
                self.notifier.info(t('ring.timer_missed'), body, 0)
                continue
            self._start(Ring(f"timer:{timer['id']}", 'timer', timer['id'],
                             t('ring.timer_title'), body,
                             timer['sound'] or config['settings']['sound'], 0, now,
                             timer['late']), config)

    def _expire(self, config: Dict[str, Any], now: float) -> None:
        limit = config['settings']['ring_minutes'] * 60
        for ring in list(self.rings.values()):
            if now - ring.since >= limit:
                log.info("%s rang %d s with no answer", ring.key, limit)
                self._end(ring, now, answered=False,
                          minutes=config['settings']['ring_minutes'])

    # ─── rings ───

    def _start(self, ring: Ring, config: Dict[str, Any]) -> None:
        old = self.rings.get(ring.key)
        if old is not None:
            ring.notification = old.notification
        self.rings[ring.key] = ring
        if ring.late > 5:
            ring.body = (ring.body + "  " if ring.body else "") + t(
                'ring.late', minutes=max(1, int(ring.late // 60)))
        log.info("ringing %s (%s)", ring.key, ring.title)
        ring.notification = self.notifier.ring(ring, ring.notification)
        self.loop.start(ring.sound, config['settings']['volume'])
        self.changed = True

    def _missed(self, when: str, label: str, at: float) -> None:
        day = dt.datetime.fromtimestamp(at).strftime('%H:%M')
        log.info("missed alarm %s (due %s)", when, day)
        self.notifier.info(t('ring.alarm_missed', time=when), label or t('ring.missed_why'), 0)

    def _end(self, ring: Ring, now: float, answered: bool, minutes: int = 0) -> None:
        self.rings.pop(ring.key, None)
        if not self.rings:
            self.loop.stop()
        else:
            last = list(self.rings.values())[-1]
            config = store.load_config()
            self.loop.start(last.sound, config['settings']['volume'])
        if answered:
            self.notifier.close(ring.notification)
        else:
            self.notifier.info(t('ring.unanswered', title=ring.title, minutes=minutes), ring.body,
                               ring.notification)
        if ring.kind == 'timer':
            def done(timers):
                for timer in timers:
                    if timer['id'] == ring.ref and timer['state'] == 'ringing':
                        timer['state'] = 'done'
            store.update_timers(done)
        self.changed = True

    def action(self, key: str, act: str, now: Optional[float] = None) -> bool:
        """The person answered: 'stop', 'snooze' (alarms) or 'plus' (timers)."""
        now = self.clock() if now is None else now
        ring = self.rings.get(key)
        if ring is None:
            return False
        if act == 'snooze' and ring.kind == 'alarm':
            self.snoozes.append({'at': now + ring.snooze * 60, 'key': ring.key, 'ref': ring.ref,
                                 'title': ring.title, 'body': ring.label,
                                 'sound': ring.sound, 'snooze': ring.snooze})
            self._end(ring, now, answered=True)
            self.notifier.info(t('ring.snoozed', minutes=ring.snooze), ring.title, 0)
        elif act == 'plus' and ring.kind == 'timer':
            self._end(ring, now, answered=True)

            def more(timers):
                for timer in timers:
                    if timer['id'] == ring.ref:
                        timer.update(state='running', end=now + PLUS_SECONDS,
                                     remaining=PLUS_SECONDS)
            store.update_timers(more)
        elif act in ('stop', 'dismiss'):
            self._end(ring, now, answered=True)
        else:
            return False
        self._save(now)
        return True

    def notification_closed(self, notification: int, reason: int) -> None:
        """The person dismissed the notification itself (reason 2): that is a stop."""
        if reason != 2:
            return
        for ring in list(self.rings.values()):
            if ring.notification == notification:
                self.action(ring.key, 'stop')

    def shutdown(self) -> None:
        """The service is stopping: silence, close what is on screen. Snoozes stay in the
        file, so a restart picks them up."""
        for ring in list(self.rings.values()):
            self.notifier.close(ring.notification)
        self.rings.clear()
        self.loop.stop()
        self._save(0.0, pid=None)

    def _save(self, now: float, pid: Any = 0) -> None:
        import os
        store.save_service({
            'pid': os.getpid() if pid == 0 else pid, 'beat': now, 'last_tick': self.last_tick,
            'snoozes': self.snoozes, 'ringing': [r.as_dict() for r in self.rings.values()]})
        self.saved_at = now
        self.changed = False
