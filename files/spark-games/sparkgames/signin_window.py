"""An optional small sign-in window that catches the code for you.

It needs WebKitGTK and PyGObject (python3-gobject and webkit2gtk), which SparkOS doesn't ship
today. Without them Spark Games uses the paste-the-code way, which always works. This file is
run as its own process so a missing library can never stop the app:

    python3 -m sparkgames.signin_window <epic|gog|amazon> <url>

It prints the code on its last line and exits 0, or exits 1 when the window is closed first.
It has not been run on a real sign-in page yet (README, Known gaps).
"""

import subprocess
import sys

CHECK = ("import gi; gi.require_version('Gtk','3.0'); "
         "gi.require_version('WebKit2','{v}'); from gi.repository import Gtk, WebKit2")
_available = None


def webkit_version() -> str:
    """'4.1' or '4.0' when WebKitGTK can be imported, else ''. Checked in a subprocess."""
    for version in ('4.1', '4.0'):
        try:
            done = subprocess.run([sys.executable, '-c', CHECK.format(v=version)],
                                  capture_output=True, timeout=20, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return ''
        if done.returncode == 0:
            return version
    return ''


def available() -> bool:
    global _available
    if _available is None:
        _available = bool(webkit_version())
    return _available


def run(store: str, url: str, timeout: float = 600.0, cwd: str = '') -> str:
    """Open the window and return the code, or '' if it was closed without one."""
    import os
    cwd = cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        done = subprocess.run([sys.executable, '-m', 'sparkgames.signin_window', store, url],
                              capture_output=True, text=True, timeout=timeout, cwd=cwd,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    lines = (done.stdout or '').strip().splitlines()
    return lines[-1].strip() if done.returncode == 0 and lines else ''


def main(argv) -> int:
    store, url = argv[1], argv[2]
    version = webkit_version()
    if not version:
        return 1
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', version)
    from gi.repository import Gtk, WebKit2
    from sparkgames import stores

    result = {'code': ''}
    window = Gtk.Window(title='Sign in')
    window.set_default_size(520, 720)
    view = WebKit2.WebView()
    window.add(view)

    def found(text: str) -> None:
        code = stores.extract_code(store, text)
        if code and not result['code']:
            result['code'] = code
            Gtk.main_quit()

    def on_load(_view, event):
        if event == WebKit2.LoadEvent.FINISHED:
            found(view.get_uri() or '')
            if store == 'epic':      # Epic shows the code as JSON text on the page
                view.run_javascript('document.body.innerText', None, on_text, None)

    def on_text(_view, task, _data):
        try:
            value = view.run_javascript_finish(task).get_js_value().to_string()
            found(value)
        except Exception:            # noqa: BLE001 - the paste way is still there
            pass

    view.connect('load-changed', on_load)
    window.connect('destroy', Gtk.main_quit)
    view.load_uri(url)
    window.show_all()
    Gtk.main()
    if result['code']:
        print(result['code'])
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
