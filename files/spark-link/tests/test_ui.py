"""The window with a stand-in service: every tab draws, the prompts appear, buttons send the
right requests. Needs a display (CI runs it under Xvfb); skipped without one."""

import copy
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.destroy()
    DISPLAY = True
except Exception:                                  # no tkinter or no display
    DISPLAY = False

STATUS = {
    'ok': True,
    'pc': {'id': 'a' * 32, 'name': 'Spark PC', 'key': '3F2A 91C0 7D11 4E8B', 'fp': '3f' * 32,
           'addresses': ['192.168.1.23']},
    'listening': True, 'port': 47100, 'error': '', 'mdns': 'avahi (D-Bus)',
    'features': {'url': True, 'clipboard': False, 'files': True, 'notify': True,
                 'battery': True, 'ring': True},
    'pairing': {'active': False, 'note': ''},
    'devices': [
        {'id': 'b' * 32, 'name': 'Pixel 8', 'connected': True, 'address': '192.168.1.40',
         'last_seen': time.time(), 'paired_at': time.time() - 86400, 'battery': 82,
         'charging': True, 'always_accept': False, 'key': '11AA 22BB 33CC 44DD',
         'features': ['url', 'files', 'notify', 'battery', 'ring']},
        {'id': 'c' * 32, 'name': 'Old tablet', 'connected': False, 'address': '',
         'last_seen': time.time() - 7200, 'paired_at': time.time() - 864000, 'battery': 9,
         'charging': False, 'always_accept': True, 'key': '55EE 66FF 7700 8811',
         'features': []},
    ],
    'transfers': [
        {'key': 'b:in:4', 'device': 'b' * 32, 'direction': 'in', 'name': 'photo.jpg',
         'size': 2_000_000, 'done': 2_000_000, 'state': 'done', 'reason': '', 'path': ''},
        {'key': 'b:out:9', 'device': 'b' * 32, 'direction': 'out', 'name': 'report.pdf',
         'size': 4_000_000, 'done': 1_000_000, 'state': 'sending', 'reason': '', 'path': ''},
    ],
    'events': [{'t': time.time(), 'text': 'Pixel 8 connected.', 'kind': 'info'}],
    'clipboard': False,
}


class FakeControl:
    def __init__(self, status):
        self.status = status
        self.sent = []

    def request(self, req):
        self.sent.append(req)
        if req['cmd'] == 'status':
            return copy.deepcopy(self.status)
        if req['cmd'] == 'pair.start':
            self.status['pairing'] = {
                'active': True, 'note': '', 'code': '123456', 'left': 299, 'wrong': 0,
                'link': 'sparklink://pair?v=1&host=192.168.1.23&port=47100&id=' + 'a' * 32 +
                        '&fp=' + '3f' * 32 + '&code=123456&name=Spark%20PC'}
        return {'ok': True}


@unittest.skipUnless(DISPLAY, 'needs a display')
class Window(unittest.TestCase):
    def setUp(self):
        os.environ['SPARK_LINK_REDUCED_MOTION'] = '1'
        from sparklink.app import App
        self.ctl = FakeControl(copy.deepcopy(STATUS))
        self.app = App(tab='devices', control=self.ctl, poll=False)
        self.app.apply_status(self.ctl.request({'cmd': 'status'}))
        self.pump()

    def tearDown(self):
        self.app.destroy()

    def pump(self, secs=0.3):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            self.app.worker.pump()
            self.app.root.update()
            time.sleep(0.01)

    def press(self, widget):
        """Keyboard events go to the focused widget, so focus it first, as Tab would."""
        widget.focus_force()
        self.pump(0.05)
        widget.event_generate('<Return>')

    def texts(self, widget=None):
        widget = widget or self.app.root
        out = []
        try:
            out.append(str(widget.cget('text')))
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            out.extend(self.texts(child))
        return out

    def test_devices(self):
        text = '\n'.join(self.texts())
        self.assertIn('Pixel 8', text)
        self.assertIn('battery 82 %, charging', text)
        self.assertIn('Old tablet', text)
        self.assertIn('last seen 2 h ago', text)
        self.assertIn('report.pdf', text)
        self.assertIn('25 %', text)
        self.assertIn('● LISTENING ON PORT 47100', text)

    def test_buttons_send_requests(self):
        ring = [w for w in self._all() if isinstance(w, tk.Label) and w.cget('text') == 'RING']
        self.assertEqual(len(ring), 2)
        self.press(ring[0])
        self.pump()
        self.assertIn({'cmd': 'ring', 'device': 'b' * 32}, self.ctl.sent)
        before = len(self.ctl.sent)
        self.press(ring[1])            # the tablet isn't connected
        self.pump()
        self.assertEqual(len([r for r in self.ctl.sent[before:] if r['cmd'] == 'ring']), 0)

    def test_pairing_tab_and_prompt(self):
        self.app.show('pair')
        self.pump()
        start = [w for w in self._all() if isinstance(w, tk.Label) and
                 w.cget('text') == 'SHOW A PAIRING CODE']
        self.press(start[0])
        self.pump(0.6)
        self.app.apply_status(self.ctl.request({'cmd': 'status'}))
        self.pump()
        text = '\n'.join(self.texts())
        self.assertIn('123 456', text)
        self.assertIn('address 192.168.1.23:47100, code 123456', text)
        self.assertIn('3F2A 91C0 7D11 4E8B', text)
        from sparklink.app import QRView
        qr = [w for w in self._all() if isinstance(w, QRView)][0]
        self.assertGreater(len(qr.find_all()), 100)
        # a phone asks to pair
        st = self.ctl.request({'cmd': 'status'})
        st['pairing']['request'] = {'name': 'Pixel 8', 'key': '11AA 22BB 33CC 44DD'}
        self.app.apply_status(st)
        self.pump()
        self.assertIn('Pair with Pixel 8?', self.texts())
        yes = [w for w in self._all() if isinstance(w, tk.Label) and w.cget('text') == 'PAIR']
        self.press(yes[0])
        self.pump()
        self.assertIn({'cmd': 'pair.answer', 'yes': True}, self.ctl.sent)

    def test_incoming_offer(self):
        st = self.ctl.request({'cmd': 'status'})
        st['transfers'].append({'key': 'b:in:12', 'device': 'b' * 32, 'direction': 'in',
                                'name': 'notes.txt', 'size': 1500, 'done': 0,
                                'state': 'waiting', 'reason': '', 'path': ''})
        self.app.apply_status(st)
        self.pump()
        self.assertIn('Pixel 8 wants to send notes.txt (1.5 KB).', self.texts())
        accept = [w for w in self._all() if isinstance(w, tk.Label) and
                  w.cget('text') == 'ACCEPT']
        self.press(accept[0])
        self.pump()
        self.assertIn({'cmd': 'file.answer', 'key': 'b:in:12', 'accept': True}, self.ctl.sent)

    def test_features(self):
        self.app.show('features')
        self.pump()
        from sparklink.widgets import Toggle
        toggles = [w for w in self._all() if isinstance(w, Toggle)]
        clip = [w for w in toggles if 'CLIPBOARD' in w.cget('text')][0]
        self.assertFalse(clip.value)
        self.press(clip)
        self.pump()
        self.assertIn({'cmd': 'feature', 'name': 'clipboard', 'on': True}, self.ctl.sent)

    def test_not_running(self):
        self.app.apply_status(None, running=False)
        self.pump()
        text = '\n'.join(self.texts())
        self.assertIn('● NOT RUNNING', text)
        self.assertIn('START SPARK LINK', text)

    def _all(self, widget=None):
        widget = widget or self.app.root
        out = [widget]
        for child in widget.winfo_children():
            out.extend(self._all(child))
        return out


if __name__ == '__main__':
    unittest.main()
