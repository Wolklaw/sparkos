"""The background service: `spark-clock --daemon`, run by the systemd user unit
spark-clock.service. One per user (a lock file keeps a second one out). It ticks once a second,
which also catches up after the PC sleeps; the Engine decides what rings."""

import fcntl
import os
import signal
import sys
import time

from . import APP_NAME, VERSION, core, store
from .core import log


def single_instance():
    """Take the service lock; None if another service already has it."""
    fd = os.open(os.path.join(core.state_dir(), 'service.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def run() -> int:
    core.setup_logging()
    lock = single_instance()
    if lock is None:
        print(f"{APP_NAME}: the service is already running.", file=sys.stderr)
        return 0
    try:
        from gi.repository import GLib
        from .engine import Engine
        from .notify import Notifier
        from .sound import Loop
    except (ImportError, ValueError) as exc:
        print(f"{APP_NAME} service needs python3-gobject: {exc}", file=sys.stderr)
        return 1
    try:
        notifier = Notifier()
    except GLib.Error as exc:
        print(f"{APP_NAME} service can't reach the session bus: {exc.message}", file=sys.stderr)
        return 1
    from .wake import WakeScheduler
    engine = Engine(notifier, Loop(), wake=WakeScheduler())
    notifier.on_action = lambda n, action: _answer(engine, n, action)
    notifier.on_closed = engine.notification_closed
    loop = GLib.MainLoop()

    def tick():
        try:
            engine.tick()
        except Exception:                              # one bad tick must not end the service
            log.exception("tick failed")
        return True

    def stop(*_args):
        loop.quit()
        return False

    GLib.timeout_add(1000, tick)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stop)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, stop)
    log.info("service %s running, pid %d, last tick %s", VERSION, os.getpid(),
             time.strftime('%H:%M:%S', time.localtime(engine.last_tick)))
    tick()
    try:
        loop.run()
    finally:
        engine.shutdown()
        log.info("service stopped")
    return 0


def _answer(engine, notification: int, action: str) -> None:
    for ring in list(engine.rings.values()):
        if ring.notification == notification:
            engine.action(ring.key, action)
            return
