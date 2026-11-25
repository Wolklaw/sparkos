"""libvirt's event loop, run by the GLib main loop.

libvirt's own Python loop runs on a second thread and calls back into Python while GTK
is drawing; with PyGObject that corrupts memory. Here libvirt hands us its file handles
and timers, and GLib runs them on the main thread, so there is only one thread of
callbacks. Register before any connection is opened, once per process."""

import itertools
import threading

try:
    import libvirt
except ImportError:                                  # pragma: no cover
    libvirt = None

_IN, _OUT, _ERR, _HUP = 1, 2, 4, 8                   # VIR_EVENT_HANDLE_*

_lock = threading.Lock()
_ids = itertools.count(1)
_handles = {}                                        # id -> dict
_timers = {}                                         # id -> dict
_active = False


def active() -> bool:
    return _active


def _to_glib(events, GLib):
    cond = GLib.IOCondition(0)
    if events & _IN:
        cond |= GLib.IOCondition.IN
    if events & _OUT:
        cond |= GLib.IOCondition.OUT
    if events & _ERR:
        cond |= GLib.IOCondition.ERR
    if events & _HUP:
        cond |= GLib.IOCondition.HUP
    return cond


def _from_glib(cond, GLib):
    ev = 0
    if cond & GLib.IOCondition.IN:
        ev |= _IN
    if cond & GLib.IOCondition.OUT:
        ev |= _OUT
    if cond & GLib.IOCondition.ERR:
        ev |= _ERR
    if cond & GLib.IOCondition.HUP:
        ev |= _HUP
    return ev


def install() -> bool:
    """Register the GLib implementation. False when it can't be (no GLib, or too late)."""
    global _active
    if _active:
        return True
    if libvirt is None:
        return False
    try:
        import gi
        from gi.repository import GLib
    except (ImportError, ValueError):
        return False

    def arm_handle(h):
        if h['source']:
            _kill(GLib, h['source'])
            h['source'] = 0
        if not h['events']:
            return
        h['source'] = GLib.io_add_watch(h['fd'], GLib.PRIORITY_DEFAULT,
                                        _to_glib(h['events'], GLib), h_fire, h['id'])

    def h_fire(_fd, cond, hid):
        h = _handles.get(hid)
        if h is None:
            return False
        old = h['source']
        libvirt.virEventInvokeHandleCallback(hid, h['fd'], _from_glib(cond, GLib),
                                             h['cb'], h['opaque'])
        keep = hid in _handles and h['source'] == old and bool(h['events'])
        if not keep and h['source'] == old:
            h['source'] = 0                      # GLib drops it when we return False
        return keep

    def add_handle(fd, events, cb, opaque):
        with _lock:
            hid = next(_ids)
            h = {'id': hid, 'fd': fd, 'events': events, 'cb': cb, 'opaque': opaque, 'source': 0}
            _handles[hid] = h
        GLib.idle_add(lambda: (arm_handle(h), False)[1]) if not _on_main(GLib) else arm_handle(h)
        return hid

    def update_handle(hid, events):
        h = _handles.get(hid)
        if h is None:
            return
        h['events'] = events
        if _on_main(GLib):
            arm_handle(h)
        else:
            GLib.idle_add(lambda: (arm_handle(h), False)[1])

    def remove_handle(hid):
        h = _handles.pop(hid, None)
        if h is None:
            return None

        def drop():
            if h['source']:
                _kill(GLib, h['source'])
                h['source'] = 0
            return False
        if _on_main(GLib):
            drop()
        else:
            GLib.idle_add(drop)
        return None

    def arm_timer(t):
        if t['source']:
            _kill(GLib, t['source'])
            t['source'] = 0
        if t['ms'] < 0:
            return
        t['source'] = GLib.timeout_add(max(1, t['ms']), t_fire, t['id'])

    def t_fire(tid):
        t = _timers.get(tid)
        if t is None:
            return False
        old = t['source']
        libvirt.virEventInvokeTimeoutCallback(tid, t['cb'], t['opaque'])
        # the callback may have updated or removed the timer; update re-arms a new source
        keep = tid in _timers and t['source'] == old and t['ms'] >= 0
        if not keep and t['source'] == old:
            t['source'] = 0
        return keep

    def add_timeout(ms, cb, opaque):
        with _lock:
            tid = next(_ids)
            t = {'id': tid, 'ms': ms, 'cb': cb, 'opaque': opaque, 'source': 0}
            _timers[tid] = t
        if _on_main(GLib):
            arm_timer(t)
        else:
            GLib.idle_add(lambda: (arm_timer(t), False)[1])
        return tid

    def update_timeout(tid, ms):
        t = _timers.get(tid)
        if t is None:
            return
        t['ms'] = ms
        if _on_main(GLib):
            # from inside its own callback: a new source replaces this one
            arm_timer(t)
        else:
            GLib.idle_add(lambda: (arm_timer(t), False)[1])

    def remove_timeout(tid):
        t = _timers.pop(tid, None)
        if t is None:
            return None

        def drop():
            if t['source']:
                _kill(GLib, t['source'])
                t['source'] = 0
            return False
        if _on_main(GLib):
            drop()
        else:
            GLib.idle_add(drop)
        return None

    try:
        libvirt.virEventRegisterImpl(add_handle, update_handle, remove_handle,
                                     add_timeout, update_timeout, remove_timeout)
    except libvirt.libvirtError:
        return False
    _active = True
    return True


def _on_main(GLib) -> bool:
    return GLib.MainContext.default().is_owner() or \
        threading.current_thread() is threading.main_thread()


def _kill(GLib, source):
    if GLib.MainContext.default().find_source_by_id(source) is not None:
        GLib.source_remove(source)
