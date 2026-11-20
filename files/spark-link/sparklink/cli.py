"""The command line.

    spark-link                       the window
    spark-link --service             the background service (the systemd user unit runs this)
    spark-link --send FILE...        send files to the connected phone (Dolphin's "Send to phone")
    spark-link --send-url URL        send a link (Soot's "send this tab to phone" can call this)
    spark-link --ring                make the phone ring
    spark-link --status              what the service is doing, as text
    spark-link --self-test           check what Spark Link needs; no display or phone needed
"""

import argparse
import os
import ssl
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test() -> int:
    import shutil
    import tempfile
    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    print(f"ssl:       {ssl.OPENSSL_VERSION}, TLS 1.3 "
          f"{'yes' if getattr(ssl, 'HAS_TLSv1_3', False) else 'NO'}")
    if not getattr(ssl, 'HAS_TLSv1_3', False):
        failures.append('TLS 1.3')
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc}); the window can't open, the service still runs")
        failures.append('tkinter')

    from . import identity, qr
    how = identity.backend()
    work = tempfile.mkdtemp(prefix='spark-link-selftest-')
    try:
        ident = identity.load_or_create(work)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(ident.cert_path, ident.key_path)
        print(f"keys:      ECDSA P-256 made with {how}, key check {identity.short_fp(ident.fp)}")
    except Exception as exc:
        print(f"keys:      FAILED ({exc})")
        failures.append('keys')
    finally:
        shutil.rmtree(work, ignore_errors=True)
    try:
        size = len(qr.encode('sparklink://pair?v=1&host=192.168.100.200&port=47100&id=' +
                             '0' * 32 + '&fp=' + '0' * 64 + '&code=123456&name=PC', 'M'))
        print(f"qr:        pairing link fits a {size}x{size} code")
    except Exception as exc:
        print(f"qr:        FAILED ({exc})")
        failures.append('qr')

    from .desktop import Desktop
    d = Desktop()
    print(f"d-bus:     {'session bus through Gio' if d.bus else 'no Gio session bus; gdbus command: ' + ('yes' if shutil.which('gdbus') else 'no')}")
    print(f"links:     {'soot' if shutil.which('soot') else 'xdg-open' if shutil.which('xdg-open') else 'NOTHING to open links with'}")
    print(f"clipboard: {d.clipboard_backend() or 'not reachable here (needs Plasma: Klipper, or wl-clipboard)'}")
    try:
        from .desktop import Bus
        Bus(system=True).call('org.freedesktop.Avahi', '/', 'org.freedesktop.Avahi.Server',
                              'GetVersionString', reply='(s)')
        print("mdns:      Avahi reachable over D-Bus")
    except Exception as exc:
        alt = 'avahi-publish command' if shutil.which('avahi-publish') else 'none'
        print(f"mdns:      Avahi not reachable over D-Bus here ({exc.__class__.__name__}); "
              f"fallback: {alt}")
    from .control import Control
    print(f"service:   {'running' if Control().running() else 'not running'}")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def _client_cmd(req: dict) -> int:
    from .control import Control, NotRunning
    try:
        reply = Control().request(req)
    except NotRunning as exc:
        print(f"{APP_NAME}: {exc}", file=sys.stderr)
        return 1
    if not reply.get('ok'):
        print(f"{APP_NAME}: {reply.get('error') or '; '.join(reply.get('errors', []))}",
              file=sys.stderr)
        return 1
    for err in reply.get('errors', []):
        print(f"{APP_NAME}: {err}", file=sys.stderr)
    return 0


def print_status() -> int:
    from .control import Control, NotRunning
    try:
        st = Control().request({'cmd': 'status', 'peek': True})
    except NotRunning as exc:
        print(exc)
        return 1
    pc = st['pc']
    print(f"{pc['name']} ({pc['id']}), key {pc['key']}")
    print(f"listening: {'port ' + str(st['port']) if st['listening'] else 'no'}"
          f"{', mDNS ' + st['mdns'] if st['mdns'] else ''}{' - ' + st['error'] if st['error'] else ''}")
    print("features:  " + ', '.join(k for k, on in st['features'].items() if on))
    for dev in st['devices']:
        bat = f", battery {dev['battery']} %" if dev['battery'] is not None else ''
        print(f"phone:     {dev['name']}: {'connected' if dev['connected'] else 'not connected'}"
              f"{bat}")
    if st['pairing']['active']:
        print(f"pairing:   code {st['pairing']['code']}, {st['pairing']['left']} s left")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: your phone and "
                                     "this PC, linked over the local network.")
    parser.add_argument('--service', action='store_true', help="run the background service")
    parser.add_argument('--no-mdns', action='store_true', help="with --service: don't announce "
                        "over mDNS")
    parser.add_argument('--send', nargs='+', metavar='FILE', help="send files to the phone")
    parser.add_argument('--send-url', metavar='URL', help="send a link to the phone")
    parser.add_argument('--ring', action='store_true', help="make the phone ring")
    parser.add_argument('--device', metavar='ID', help="which phone (default: the one connected "
                        "last)")
    parser.add_argument('--status', action='store_true', help="what the service is doing")
    parser.add_argument('--show', action='store_true', help="open the window (used by the "
                        "service when it needs an answer)")
    parser.add_argument('--tab', choices=('devices', 'pair', 'features'), help="open the window "
                        "on this tab")
    parser.add_argument('--self-test', action='store_true', help="check what Spark Link needs")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.service:
        from .service import run_service
        return run_service(announce=not args.no_mdns)
    if args.send:
        return _client_cmd({'cmd': 'send.files', 'device': args.device,
                            'paths': [os.path.abspath(p) for p in args.send]})
    if args.send_url:
        return _client_cmd({'cmd': 'send.url', 'device': args.device, 'url': args.send_url})
    if args.ring:
        return _client_cmd({'cmd': 'ring', 'device': args.device})
    if args.status:
        return print_status()
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter for its window: {exc}", file=sys.stderr)
        return 1
    from .app import App
    from .config import setup_logging
    setup_logging()
    try:
        app = App(tab=args.tab)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
