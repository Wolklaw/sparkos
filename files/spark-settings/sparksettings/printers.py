"""Printers through CUPS: lpstat to list, lpinfo to find them on the network, lpadmin to add
(driverless, 'everywhere') and lp for the test page."""

import re
from typing import List, Optional

from .core import out, run

TESTPAGES = ('/usr/share/cups/data/testprint', '/usr/share/cups/data/default-testpage.pdf')


class Printer:
    def __init__(self, name: str):
        self.name, self.state, self.uri, self.default = name, '', '', False


class Found:
    def __init__(self, uri: str, name: str):
        self.uri, self.name = uri, name


def printers() -> List[Printer]:
    by = {}
    for line in out(['lpstat', '-p']).splitlines():
        m = re.match(r'^printer\s+(\S+)\s+(.*)$', line)
        if m:
            p = by.setdefault(m.group(1), Printer(m.group(1)))
            p.state = 'idle' if 'idle' in m.group(2) else ('disabled' if 'disabled' in m.group(2)
                                                           else 'busy')
    for line in out(['lpstat', '-v']).splitlines():
        m = re.match(r'^device for (\S+):\s*(.*)$', line)
        if m and m.group(1) in by:
            by[m.group(1)].uri = m.group(2)
    m = re.search(r'destination:\s*(\S+)', out(['lpstat', '-d']))
    if m and m.group(1) in by:
        by[m.group(1)].default = True
    return list(by.values())


def discover() -> List[Found]:
    """Printers on the network that CUPS can see and aren't added yet (dnssd or ipp)."""
    have = {p.uri for p in printers()}
    found = []
    for line in out(['lpinfo', '--include-schemes', 'dnssd,ipp,ipps', '-v'], timeout=30).splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] == 'network' and parts[1] not in have \
                and parts[1].split(':')[0] in ('dnssd', 'ipp', 'ipps'):
            uri = parts[1]
            name = re.sub(r'%20', ' ', uri.split('://', 1)[-1].split('._')[0])
            found.append(Found(uri, name))
    return found


def queue_name(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_') or 'Printer'


def add(found: Found) -> str:
    cmd = ['lpadmin', '-p', queue_name(found.name), '-E', '-v', found.uri, '-m', 'everywhere']
    rc, _, err = run(cmd, timeout=60)
    return '' if rc == 0 else (err.strip() or "could not add the printer")


def remove(name: str) -> str:
    rc, _, err = run(['lpadmin', '-x', name])
    return '' if rc == 0 else (err.strip() or "could not remove the printer")


def make_default(name: str) -> bool:
    return run(['lpadmin', '-d', name])[0] == 0


def test_page(name: str) -> str:
    import os
    page = next((p for p in TESTPAGES if os.path.exists(p)), None)
    if page is None and os.environ.get('SPARK_SETTINGS_TEST_PAGE'):
        page = os.environ['SPARK_SETTINGS_TEST_PAGE']
    if page is None:
        return "No test page file found on this system"
    rc, _, err = run(['lp', '-d', name, page])
    return '' if rc == 0 else (err.strip() or "could not print")
