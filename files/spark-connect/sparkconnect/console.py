"""See (and, if you choose, type into) the text console of a server that has no desktop.

This file is not imported by Spark Connect to do anything: its text is sent to the server and run
there, as root, in the terminal Spark Connect opens:

    ssh -t <host> sudo python3 -c '<this file>' <name of this PC>

You type the sudo password in that terminal. Nothing is installed on the server and nothing is
left behind. It uses only Python's standard library, so it runs on any server that has python3.
Read it before you run it: that is why it is a plain file and not a program.

What it does, all of it:

* Reads /dev/vcsa1 (the text of the first virtual console, tty1, and its cursor) a few times a
  second and draws it in your terminal. Reading it needs root, which is why it runs with sudo.
* Writes one line on tty1, where someone standing at the server would see it, saying the console
  is being viewed from your PC; one more when typing is turned on, one when it ends.
* Ctrl+] switches "type into the console" on and off. While it is on, every key you press is
  sent to the server's console through a virtual keyboard (/dev/uinput), as if typed there.
  (TIOCSTI, the older way to push keys into a console, is off in new kernels.) It assumes the
  server's console keyboard layout is US QWERTY; other layouts give other characters.
* q or Ctrl+C (while not typing) ends it. So does closing the terminal.

No approval prompt: there is nobody to ask, and reading the console needs root anyway. Whoever
can sudo on the server can already do this.
"""

import fcntl
import os
import re
import select
import signal
import struct
import sys
import termios
import time
import tty

VCSA = '/dev/vcsa1'
TTY = '/dev/tty1'
UINPUT = '/dev/uinput'
ACTIVE = '/sys/class/tty/tty0/active'
TOGGLE = b'\x1d'                      # Ctrl+]
REFRESH_S = 0.25

# ─── the screen ───────────────────────────────────────────────

VGA_TO_ANSI = (0, 4, 2, 6, 1, 5, 3, 7)


def parse_vcsa(data):
    """(rows, cols, cursor_x, cursor_y, cells) from /dev/vcsa* bytes; cells is a list of
    (char byte, attribute byte). None when the data is too short to be one."""
    if len(data) < 4:
        return None
    rows, cols, cx, cy = data[0], data[1], data[2], data[3]
    body = data[4:4 + rows * cols * 2]
    if rows == 0 or cols == 0 or len(body) < rows * cols * 2:
        return None
    return rows, cols, cx, cy, [(body[i], body[i + 1]) for i in range(0, len(body), 2)]


def char_for(byte):
    if 32 <= byte < 127:
        return chr(byte)
    if byte >= 160:
        return bytes([byte]).decode('cp437', 'replace')
    return ' '


def sgr(attr):
    fg, bg = attr & 0x0f, (attr >> 4) & 0x07
    code = [0, 30 + VGA_TO_ANSI[fg & 7], 40 + VGA_TO_ANSI[bg]]
    if fg & 8:
        code[1] += 60
    return '\x1b[' + ';'.join(str(c) for c in code) + 'm'


def render(frame, width, height, status):
    """The text to write to the viewer's terminal: the console's rows (clipped to the terminal),
    a status line on the last row, the cursor where the console's cursor is."""
    rows, cols, cx, cy, cells = frame
    out = ['\x1b[H']
    shown_rows = min(rows, max(height - 1, 1))
    shown_cols = min(cols, width)
    for r in range(shown_rows):
        last = None
        line = []
        for c in range(shown_cols):
            ch, attr = cells[r * cols + c]
            if attr != last:
                line.append(sgr(attr))
                last = attr
            line.append(char_for(ch))
        out.append(''.join(line) + '\x1b[0m\x1b[K\r\n')
    out.append('\x1b[J')
    out.append(f'\x1b[{height};1H\x1b[7m' + status[:width].ljust(width) + '\x1b[0m')
    if cy < shown_rows and cx < shown_cols:
        out.append(f'\x1b[{cy + 1};{cx + 1}H')
    return ''.join(out)


# ─── the virtual keyboard ─────────────────────────────────────

EV_SYN, EV_KEY = 0, 1
KEY_LEFTCTRL, KEY_LEFTSHIFT = 29, 42
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_SETUP = 0x405c5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502

KEYS = {}        # character -> (key code, needs shift), US layout
for _i, _c in enumerate('1234567890'):
    KEYS[_c] = (2 + _i, False)
for _i, _c in enumerate('!@#$%^&*()'):
    KEYS[_c] = (2 + _i, True)
for _row, _start in (('qwertyuiop', 16), ('asdfghjkl', 30), ('zxcvbnm', 44)):
    for _i, _c in enumerate(_row):
        KEYS[_c] = (_start + _i, False)
        KEYS[_c.upper()] = (_start + _i, True)
for _plain, _shifted, _code in (('-', '_', 12), ('=', '+', 13), ('[', '{', 26), (']', '}', 27),
                                (';', ':', 39), ("'", '"', 40), ('`', '~', 41),
                                ('\\', '|', 43), (',', '<', 51), ('.', '>', 52), ('/', '?', 53)):
    KEYS[_plain] = (_code, False)
    KEYS[_shifted] = (_code, True)
KEYS[' '] = (57, False)

NAMED = {'esc': 1, 'backspace': 14, 'tab': 15, 'enter': 28, 'home': 102, 'up': 103, 'pgup': 104,
         'left': 105, 'right': 106, 'end': 107, 'down': 108, 'pgdn': 109, 'insert': 110,
         'delete': 111}
SEQUENCES = {b'[A': 'up', b'[B': 'down', b'[C': 'right', b'[D': 'left', b'[H': 'home',
             b'[F': 'end', b'OA': 'up', b'OB': 'down', b'OC': 'right', b'OD': 'left',
             b'OH': 'home', b'OF': 'end', b'[2~': 'insert', b'[3~': 'delete', b'[5~': 'pgup',
             b'[6~': 'pgdn', b'[1~': 'home', b'[4~': 'end', b'[7~': 'home', b'[8~': 'end'}


def all_key_codes():
    codes = {code for code, _ in KEYS.values()} | set(NAMED.values())
    return sorted(codes | {KEY_LEFTCTRL, KEY_LEFTSHIFT})


def decode_keys(data):
    """Terminal bytes -> [(key code, shift, ctrl)] for the virtual keyboard. Bytes it has no key
    for (anything outside ASCII, unknown escape sequences) are dropped."""
    out = []
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x1b:
            for seq in sorted(SEQUENCES, key=len, reverse=True):
                if data[i + 1:i + 1 + len(seq)] == seq:
                    out.append((NAMED[SEQUENCES[seq]], False, False))
                    i += 1 + len(seq)
                    break
            else:
                if i + 1 == len(data):
                    out.append((NAMED['esc'], False, False))
                    i += 1
                elif data[i + 1:i + 2] == b'[':          # a CSI sequence we don't know: skip it
                    j = i + 2
                    while j < len(data) and 0x20 <= data[j] <= 0x3f:
                        j += 1
                    i = j + 1
                else:
                    i += 2                 # Alt+key or SS3 we don't know: skip its start
            continue
        i += 1
        if b in (0x0d, 0x0a):
            out.append((NAMED['enter'], False, False))
        elif b == 0x09:
            out.append((NAMED['tab'], False, False))
        elif b in (0x7f, 0x08):
            out.append((NAMED['backspace'], False, False))
        elif 1 <= b <= 26:
            code, _ = KEYS[chr(b + 96)]
            out.append((code, False, True))
        elif b < 127 and chr(b) in KEYS:
            code, shift = KEYS[chr(b)]
            out.append((code, shift, False))
    return out


def event(kind, code, value):
    return struct.pack('llHHi', 0, 0, kind, code, value)


class Keyboard:
    """A virtual keyboard made through /dev/uinput. Needs root."""

    def __init__(self, path=UINPUT):
        self.fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            for code in all_key_codes():
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            setup = struct.pack('HHHH80sI', 0x06, 0x1209, 0x5350, 1,
                                b'Spark Connect console keyboard', 0)
            fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        time.sleep(0.3)                 # the console needs a moment to see the new keyboard

    def _send(self, kind, code, value):
        os.write(self.fd, event(kind, code, value) + event(EV_SYN, 0, 0))

    def type(self, data):
        for code, shift, ctrl in decode_keys(data):
            for held, down in ((KEY_LEFTSHIFT, shift), (KEY_LEFTCTRL, ctrl)):
                if down:
                    self._send(EV_KEY, held, 1)
            self._send(EV_KEY, code, 1)
            self._send(EV_KEY, code, 0)
            for held, down in ((KEY_LEFTCTRL, ctrl), (KEY_LEFTSHIFT, shift)):
                if down:
                    self._send(EV_KEY, held, 0)
            time.sleep(0.005)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(self.fd)


# ─── the notice on the console ────────────────────────────────

def clean(name):
    return re.sub(r'[^\w.\-]', '', name or '')[:40] or 'another PC'


def notice(path, text):
    """One line on the console itself, for whoever is standing at the server."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        os.write(fd, ('\r\n[Spark Connect] ' + text + '\r\n').encode('utf-8', 'replace'))
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def foreground_is(active_path, tty_path):
    """True when the console shown on the server's screen is the one we mirror: keys typed
    through the virtual keyboard go to whichever console is in front."""
    try:
        with open(active_path) as f:
            return f.read().strip() == os.path.basename(tty_path)
    except OSError:
        return False


# ─── the loop ─────────────────────────────────────────────────

class Stop(Exception):
    pass


def run(pc, stdin_fd, out, vcsa=VCSA, tty_path=TTY, uinput=UINPUT, active=ACTIVE,
        size=None, max_frames=None):
    """Mirror vcsa to out until q, Ctrl+C or a signal. size() gives (columns, rows) of the
    viewer's terminal. Returns why it ended."""
    pc = clean(pc)
    typing = False
    keyboard = None
    message = ''
    last = None
    frames = 0
    fd = os.open(vcsa, os.O_RDONLY)
    notice(tty_path, f"this console is being viewed from {pc} (Spark Connect).")
    try:
        while True:
            data = os.pread(fd, 4 + 255 * 255 * 2, 0)
            frame = parse_vcsa(data)
            if frame is None:
                raise Stop("could not read the console")
            width, height = size() if size else (80, 25)
            if typing:
                status = " TYPING into the server's console. Ctrl+] to stop typing. "
            else:
                status = f" VIEWING tty1 from {pc}. Ctrl+] to type into it, q to quit. "
            if message:
                status = ' ' + message + ' ' + status.strip()
            key = (data, width, height, status)
            if key != last:
                out.write(render(frame, width, height, status))
                out.flush()
                last = key
            frames += 1
            if max_frames and frames >= max_frames:
                return 'frames'
            ready, _, _ = select.select([stdin_fd], [], [], REFRESH_S)
            if not ready:
                continue
            chunk = os.read(stdin_fd, 1024)
            if not chunk:
                return 'terminal closed'
            while TOGGLE in chunk:
                before, _, chunk = chunk.partition(TOGGLE)
                if typing and keyboard and before:
                    keyboard.type(before)
                typing = not typing
                message = ''
                if typing:
                    if not foreground_is(active, tty_path):
                        typing, message = False, "tty1 is not the console on screen."
                    else:
                        try:
                            keyboard = keyboard or Keyboard(uinput)
                            notice(tty_path, f"{pc} is now typing into this console.")
                        except OSError as exc:
                            typing, message = False, f"No virtual keyboard: {exc.strerror}."
                else:
                    notice(tty_path, f"{pc} stopped typing into this console.")
            if typing and keyboard:
                keyboard.type(chunk)
            elif chunk and not typing and chunk[:1] in (b'q', b'Q', b'\x03'):
                return 'quit'
    finally:
        os.close(fd)
        if keyboard:
            keyboard.close()
        notice(tty_path, f"the console is no longer being viewed from {pc}.")


def main(argv):
    pc = argv[0] if argv else ''
    if os.geteuid() != 0:
        sys.stderr.write("This needs root to read the console: run it with sudo.\n")
        return 3
    if not sys.stdin.isatty():
        sys.stderr.write("This needs a terminal (ssh -t).\n")
        return 2

    def bye(_sig, _frame):
        raise Stop("terminal closed")
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, bye)

    def size():
        s = os.get_terminal_size(sys.stdout.fileno())
        return s.columns, s.lines
    saved = termios.tcgetattr(sys.stdin.fileno())
    why = 'quit'
    try:
        tty.setraw(sys.stdin.fileno())
        sys.stdout.write('\x1b[2J')
        why = run(pc, sys.stdin.fileno(), sys.stdout, size=size)
    except Stop as exc:
        why = str(exc)
    except OSError as exc:
        why = f"error: {exc.strerror or exc}"
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved)
        sys.stdout.write('\x1b[0m\x1b[2J\x1b[H')
        sys.stdout.flush()
    print(f"Console view ended ({why}).")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
