"""Announce _sparklink._tcp over mDNS through Avahi (in SparkOS): its D-Bus API through Gio,
which keeps the entry for as long as the service runs, or the avahi-publish command."""

import logging
import shutil
import subprocess
from typing import Dict, Optional

from . import APP_SLUG, SERVICE_TYPE

log = logging.getLogger(APP_SLUG)


def txt_records(txt: Dict[str, str]):
    return [f'{k}={v}'.encode('utf-8')[:255] for k, v in txt.items()]


class Announcer:
    def __init__(self):
        self.group_path: Optional[str] = None
        self.bus = None
        self.proc: Optional[subprocess.Popen] = None
        self.how = ''

    def start(self, name: str, port: int, txt: Dict[str, str]) -> str:
        """Announce; returns how ('avahi (D-Bus)', 'avahi-publish') or '' if it couldn't."""
        self.stop()
        # the second name is for when another PC on the network already uses the first
        for instance in (name, f"{name} ({txt.get('id', '')[:4]})"):
            if self._dbus(instance, port, txt):
                self.how = 'avahi (D-Bus)'
                return self.how
            if self.bus is None:
                break
        exe = shutil.which('avahi-publish')
        if exe:
            try:
                self.proc = subprocess.Popen(
                    [exe, '-s', name, SERVICE_TYPE, str(port)] +
                    [r.decode('utf-8', 'replace') for r in txt_records(txt)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.how = 'avahi-publish'
                return self.how
            except OSError as exc:
                log.warning("avahi-publish failed: %s", exc)
        log.warning("not announced over mDNS (no Avahi reachable); phones need the address")
        self.how = ''
        return ''

    def _dbus(self, instance: str, port: int, txt: Dict[str, str]) -> bool:
        path = None
        try:
            if self.bus is None:
                from .desktop import Bus
                self.bus = Bus(system=True)
            (path,) = self.bus.call('org.freedesktop.Avahi', '/', 'org.freedesktop.Avahi.Server',
                                    'EntryGroupNew', reply='(o)')
            # interface -1 and protocol -1: every interface, IPv4 and IPv6
            self.bus.call('org.freedesktop.Avahi', path, 'org.freedesktop.Avahi.EntryGroup',
                          'AddService', ('(iiussssqaay)', -1, -1, 0, instance, SERVICE_TYPE,
                                         '', '', port, txt_records(txt)))
            self.bus.call('org.freedesktop.Avahi', path, 'org.freedesktop.Avahi.EntryGroup',
                          'Commit')
            self.group_path = path
            return True
        except Exception as exc:
            log.info("Avahi over D-Bus: %s", exc)
            if path and self.bus is not None:
                try:
                    self.bus.call('org.freedesktop.Avahi', path,
                                  'org.freedesktop.Avahi.EntryGroup', 'Free')
                except Exception:
                    pass
            return False

    def stop(self) -> None:
        if self.group_path and self.bus:
            try:
                self.bus.call('org.freedesktop.Avahi', self.group_path,
                              'org.freedesktop.Avahi.EntryGroup', 'Free')
            except Exception:
                pass
        self.group_path = None
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.how = ''
