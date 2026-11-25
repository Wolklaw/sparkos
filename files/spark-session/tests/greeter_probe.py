"""Stands in for the greeter inside a real greetd (test_greetd_real.py). greetd runs it as the
greetd user with GREETD_SOCK set. It uses the same client library the real greeter uses: one wrong
password (mode wrong) or the right one and a session that writes a marker file (mode right).\nTwo greetd runs, because on the CI host greetd would not take a second login after a failed one."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sparksession import greetd  # noqa: E402

OUT, USER, PASSWORD, SESSION, MODE = sys.argv[1:6]       # greetd gives the greeter no environment
result = {}

try:
    client = greetd.Client()
    if MODE == 'wrong':
        try:
            greetd.login(client, USER, lambda kind, text: 'definitely-wrong', ['/bin/true'])
            result['wrong'] = 'accepted'
        except greetd.GreetdError as exc:
            result['wrong'] = exc.kind
    else:
        seen = []

        def answer(kind, text):
            seen.append(kind)
            return PASSWORD
        greetd.login(client, USER, answer, [SESSION], ['XDG_SESSION_DESKTOP=spark-test'])
        result['right'] = 'started'
        result['prompts'] = seen
except Exception as exc:                        # noqa: BLE001
    result['error'] = f'{type(exc).__name__}: {exc}'
with open(OUT, 'w') as handle:
    json.dump(result, handle)
os.chmod(OUT, 0o644)
