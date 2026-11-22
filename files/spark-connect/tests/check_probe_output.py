"""Check one probe output file: valid JSON with the expected keys. CI runs the probe inside
plain fedora:latest and ubuntu:24.04 containers (no systemd there) and checks the result here.

    python3 tests/check_probe_output.py OUTPUT.json [--expect-no-systemd]
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sparkconnect.probe import parse_probe  # noqa: E402

KEYS = ('probe', 'time', 'hostname', 'os', 'kernel', 'systemd', 'uptime_s', 'cpus', 'load',
        'cpu_pct', 'memory', 'disks', 'temps', 'net', 'units', 'failed', 'tunnel', 'failover',
        'local_checks')


def main(path: str, no_systemd: bool) -> int:
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    raw = json.loads(text)
    missing = [k for k in KEYS if k not in raw]
    assert not missing, f"missing keys: {missing}"
    d = parse_probe(text)
    assert d['memory']['total'] and d['memory']['total'] > 0, d['memory']
    assert d['uptime_s'] is not None and d['cpus'], (d['uptime_s'], d['cpus'])
    if no_systemd:
        assert d['systemd'] is False and d['units'] == [] and d['failed'] == [], d
    print(f"ok: {d['os'] or '?'}, systemd {d['systemd']}, {len(d['disks'])} disks, "
          f"{len(d['net'])} interfaces, failover {d['failover'] is not None}, "
          f"local checks {[c['error'] or c['status'] for c in d['local_checks']]}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], '--expect-no-systemd' in sys.argv[2:]))
