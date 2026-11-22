"""SSH end to end, for CI only: against a throwaway container with sshd, a throwaway key and a
dummy user unit (see .github/workflows/spark-connect.yml). Never point this at a real machine.

    python3 tests/e2e_ssh.py SSH_CONFIG HOST_ALIAS UNKNOWN_KEY_ALIAS

SSH_CONFIG is an ssh_config file that defines both aliases. HOST_ALIAS has the container's host
key in its known_hosts; UNKNOWN_KEY_ALIAS points at the same container with an empty one.
Checks: one refresh through the real ssh client gives the probe's JSON with the dummy unit
running; a restart of the dummy user unit goes through and shows on the next refresh; a system
unit restart stops at sudo's password question; an unknown host key is refused, not accepted.
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparkconnect import config  # noqa: E402
from sparkconnect.probe import HOSTKEY_UNKNOWN, problems  # noqa: E402
from sparkconnect.transport import DONE, NEEDS_PASSWORD, SshTransport  # noqa: E402

DUMMY = 'spark-dummy'


def main(ssh_config: str, host: str, unknown_host: str) -> int:
    tr = SshTransport(extra_options=['-F', ssh_config])
    m = config.Machine('test box', host, units=['sshd'], user_units=[DUMMY],
                       restartable=[('user', DUMMY), ('system', 'sshd')],
                       tunnel=None)
    first = tr.fetch(m)
    assert first.ok, f"refresh failed: {first.problem}: {first.message}"
    d = first.data
    print(f"refresh 1: {d['hostname']} {d['os']}, systemd {d['systemd']}, "
          f"units {[(u['name'], u['state']) for u in d['units']]}")
    assert d['systemd'], "no systemd in the test container"
    units = {(u['scope'], u['name']): u for u in d['units']}
    dummy = units[('user', DUMMY)]
    assert dummy['state'] == 'running', dummy
    print("verdict 1:", [p.key for p in problems(m, first)] or 'all good')

    time.sleep(2)
    outcome = tr.restart(m, 'user', DUMMY)
    print("restart user unit:", outcome)
    assert outcome.outcome == DONE, outcome
    time.sleep(1)
    second = tr.fetch(m)
    assert second.ok, second.message
    again = {(u['scope'], u['name']): u for u in second.data['units']}[('user', DUMMY)]
    print(f"refresh 2: {DUMMY} {again['state']} for {again['since_s']} s "
          f"(was {dummy['since_s']} s)")
    assert again['state'] == 'running'
    assert again['since_s'] is not None and again['since_s'] < 5, again
    assert any('Started' in line or 'Starting' in line for line in again['log']), again['log']

    outcome = tr.restart(m, 'system', 'sshd')
    print("restart system unit without passwordless sudo:", outcome)
    assert outcome.outcome == NEEDS_PASSWORD, outcome

    unknown = tr.fetch(config.Machine('unknown key', unknown_host))
    print("unknown host key:", unknown.problem, unknown.message)
    assert not unknown.ok and unknown.problem == HOSTKEY_UNKNOWN, unknown

    lines = []
    tail = tr.tail(m, 'user', DUMMY, lines.append, lines=5)
    time.sleep(3)
    tail.stop()
    print(f"log tail: {len(lines)} lines")
    assert lines, "journal tail gave nothing"
    print("ssh end to end passed")
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
