"""CUPS through lpstat and cancel. A fake runner stands in for the programs: no printer is
asked anything and no job is touched."""

import subprocess
import unittest

import harness  # noqa: F401  (puts the app on sys.path)

from sparktray import printers   # noqa: E402

LPSTAT_P = """printer Office is idle.  enabled since Tue 25 Nov 2026 09:00:00
printer Label now printing Label-4.  enabled since Tue 25 Nov 2026 09:00:00
printer Old disabled since Tue 25 Nov 2026 08:00:00 -
\treason unknown
system default destination: Office
"""
LPSTAT_O = """Label-4   me   1024   Tue 25 Nov 2026 09:10:00
Office-12 me   2048   Tue 25 Nov 2026 09:11:00
"""


def result(out='', code=0, err=''):
    return subprocess.CompletedProcess([], code, out, err)


class Fake:
    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.table.get(argv[0] + (' ' + argv[1] if len(argv) > 1 else ''),
                              self.table.get(argv[0], result()))


class PrintersTest(unittest.TestCase):
    def test_parse_printers(self):
        ps = {p.name: p for p in printers.parse_printers(LPSTAT_P)}
        self.assertEqual(ps['Office'].state, 'idle')
        self.assertTrue(ps['Office'].default)
        self.assertEqual(ps['Label'].state, 'printing')
        self.assertEqual(ps['Label'].job, 'Label-4')
        self.assertEqual(ps['Old'].state, 'stopped')
        self.assertFalse(ps['Old'].default)

    def test_parse_jobs(self):
        jobs = printers.parse_jobs(LPSTAT_O)
        self.assertEqual([j.id for j in jobs], ['Label-4', 'Office-12'])
        self.assertEqual(jobs[1].printer, 'Office')
        self.assertEqual(jobs[0].user, 'me')

    def test_state_combines_printers_and_jobs(self):
        run = Fake({'lpstat -p': result(LPSTAT_P), 'lpstat -o': result(LPSTAT_O)})
        s = printers.Printing(run).state()
        self.assertTrue(s.available)
        self.assertEqual(len(s.printers), 3)
        self.assertEqual(len(s.jobs), 2)

    def test_no_cups_tools_means_unavailable(self):
        run = Fake({'lpstat': result('', 127, 'lpstat: not found')})
        self.assertFalse(printers.Printing(run).state().available)

    def test_scheduler_not_running_means_unavailable(self):
        run = Fake({'lpstat': result('', 1, 'lpstat: Scheduler is not running.')})
        self.assertFalse(printers.Printing(run).state().available)

    def test_no_printers_is_available_but_empty(self):
        run = Fake({'lpstat -p': result('', 0), 'lpstat -o': result('', 0)})
        s = printers.Printing(run).state()
        self.assertTrue(s.available)
        self.assertEqual(s.printers, [])

    def test_cancel_and_pause_run_the_right_commands(self):
        run = Fake({})
        p = printers.Printing(run)
        self.assertTrue(p.cancel('Office-12'))
        self.assertTrue(p.set_paused('Office', True))
        self.assertTrue(p.set_paused('Office', False))
        self.assertEqual(run.calls, [['cancel', 'Office-12'], ['cupsdisable', 'Office'],
                                     ['cupsenable', 'Office']])

    def test_add_printer_prefers_spark_settings(self):
        have = {'spark-settings': '/x', 'system-config-printer': '/y'}
        self.assertEqual(printers.add_printer_command(have.get),
                         ['spark-settings', '--page', 'printers'])
        self.assertEqual(printers.add_printer_command({'system-config-printer': '/y'}.get),
                         ['system-config-printer'])
        self.assertIsNone(printers.add_printer_command({}.get))


if __name__ == '__main__':
    unittest.main()
