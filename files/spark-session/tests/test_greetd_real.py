"""The greeter's client library against the real greetd and real PAM in a throwaway container
(CI). greetd runs tests/greeter_probe.py as the greeter; it fails once, signs in, and starts a
session that writes a marker. Needs root and greetd, skips otherwise. Never run it on a desktop:
it starts a daemon that makes sessions (vt = none, so it does not touch a VT)."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
USER, PASSWORD = 'sparkgd', 'tiny-umbrella-5'


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('greetd') and os.path.exists('/.dockerenv')
                     or os.environ.get('SPARK_ALLOW_REAL_GREETD'),
                     'needs root, greetd and a container (runs in CI)')
class RealGreetd(unittest.TestCase):
    def setUp(self):
        subprocess.run(['useradd', '-m', USER], check=True)
        subprocess.run(['chpasswd'], input=f'{USER}:{PASSWORD}\n', text=True, check=True)
        self.dir = tempfile.mkdtemp()
        os.chmod(self.dir, 0o777)
        self.out = os.path.join(self.dir, 'result.json')
        self.marker = os.path.join(self.dir, 'marker')
        self.config = os.path.join(self.dir, 'config.toml')
        # greetd runs the session command through the user's shell, joined without quoting, so
        # keep the command a single path
        self.session = os.path.join(self.dir, 'session.sh')
        with open(self.session, 'w') as handle:
            handle.write(f'#!/bin/sh\n{{ id -un; echo "$XDG_SESSION_DESKTOP"; }} > {self.marker}\n')
        os.chmod(self.session, 0o755)
        with open(self.config, 'w') as handle:
            handle.write(f'[terminal]\nvt = "none"\n[default_session]\n'
                         f'command = "{sys.executable} -I {HERE}/greeter_probe.py {self.out} {USER} {PASSWORD} '
                         f'{self.session}"\nuser = "greetd"\n')
        # the greetd user must be able to read the sources
        subprocess.run(['chmod', '-R', 'a+rX', os.path.dirname(HERE)], check=True)
        self.greetd = subprocess.Popen(['greetd', '--config', self.config],
                                       stderr=subprocess.PIPE, text=True)

    def tearDown(self):
        if self.greetd.poll() is None:
            self.greetd.terminate()
            try:
                self.greetd.wait(10)
            except subprocess.TimeoutExpired:
                self.greetd.kill()
                self.greetd.wait()
        subprocess.run(['userdel', '-r', USER], check=False, capture_output=True)
        shutil.rmtree(self.dir, ignore_errors=True)

    def wait_for(self, path, timeout=40):
        end = time.time() + timeout
        while time.time() < end:
            if os.path.exists(path) and os.path.getsize(path):
                time.sleep(0.3)
                return
            if self.greetd.poll() is not None:
                self.fail(f'greetd exited: {self.greetd.stderr.read()}')
            time.sleep(0.1)
        self.fail(f'{path} never appeared; greetd said: {self._stderr()}')

    def _stderr(self):
        self.greetd.terminate()
        try:
            return self.greetd.communicate(timeout=10)[1]
        except subprocess.TimeoutExpired:
            return '(greetd did not stop)'

    def test_wrong_password_then_right_one_starts_the_session_as_the_user(self):
        self.wait_for(self.out)
        with open(self.out) as handle:
            result = json.load(handle)
        self.assertNotIn('error', result)
        self.assertEqual(result['wrong'], 'auth_error')
        self.assertEqual(result['right'], 'started')
        self.assertEqual(result['prompts'], ['secret'])
        self.wait_for(self.marker)
        with open(self.marker) as handle:
            self.assertEqual(handle.read().split(), [USER, 'spark-test'])


if __name__ == '__main__':
    unittest.main()
