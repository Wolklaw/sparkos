"""launcher_logic.py, the Spark shell launcher's search and sums, against tests/vectors.json.

    python3 -m unittest discover -s files/spark-shell/tests -p 'test_logic.py'
"""
import json
import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, '..'))
import launcher_logic as L  # noqa: E402

V = json.load(open(os.path.join(here, 'vectors.json'), encoding='utf-8'))


class Vectors(unittest.TestCase):
    def test_filter(self):
        for case in V['filter']:
            got = [a['name'] for a in L.filter_apps(V['apps'], case['q'], 8)]
            self.assertEqual(got, case['names'], case['q'])

    def test_limit(self):
        got = [a['name'] for a in L.filter_apps(V['apps'], 's', 2)]
        self.assertEqual(got, V['limit2'])

    def test_sums(self):
        for case in V['sums']:
            self.assertEqual(L.sum_from(case['text'], False), case['sum'], case['text'])
        for case in V['sumsFr']:
            self.assertEqual(L.sum_from(case['text'], True), case['sum'], case['text'])

    def test_commands(self):
        for case in V['commands']:
            self.assertEqual(L.sum_command(case['sum']), case['cmd'])

    def test_answers(self):
        for case in V['answers']:
            self.assertEqual(L.show_answer(case['answer'], case['fr']), case['shown'])


if __name__ == '__main__':
    unittest.main()
