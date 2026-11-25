"""A real spark-polkit agent with a scripted window, for the tests. It registers on the system
bus (real polkit or the fake authority), then answers each prompt from SPARK_TEST_PASSWORDS
(comma separated, tried in order; "CANCEL" cancels). Everything it sees is appended to the
file named by SPARK_TEST_EVENTS, one JSON object per line. Passwords are never written there."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib  # noqa: E402

from sparksession import polkit_agent  # noqa: E402

EVENTS = os.environ['SPARK_TEST_EVENTS']
PASSWORDS = os.environ.get('SPARK_TEST_PASSWORDS', '').split(',')


def event(kind, **data):
    with open(EVENTS, 'a') as handle:
        handle.write(json.dumps({'event': kind, **data}) + '\n')


class Ui:
    def __init__(self, request, flow):
        self.request, self.flow = request, flow
        self.tries = 0
        event('window', action_id=request.action_id, message=request.message,
              choices=[c.label for c in request.choices], details=request.details)

    def ask(self, prompt, echo):
        event('ask', prompt=prompt, echo=echo)
        GLib.idle_add(self._answer)

    def _answer(self):
        word = PASSWORDS[min(self.tries, len(PASSWORDS) - 1)]
        self.tries += 1
        if word == 'WAIT':
            pass
        elif word == 'CANCEL':
            self.flow.cancel()
        else:
            self.flow.answer(word)
        return False

    def info(self, text):
        event('info', text=text)

    def error(self, text):
        event('error', text=text)

    def wrong(self):
        event('wrong')

    def checking(self):
        pass

    def choices_changed(self):
        pass

    def close(self):
        event('closed')


def main():
    agent, handle = polkit_agent.register(Ui)
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    event('registered', name=bus.get_unique_name())
    GLib.MainLoop().run()


main()
