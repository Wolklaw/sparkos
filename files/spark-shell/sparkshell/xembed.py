"""Old X11 tray icons (XEmbed: Wine and Proton games, Battle.net, older apps) in the Spark tray.

Only in the Spark compositor session: Plasma has its own bridge. Without one, Wine opens a small
window of its own to hold the icon. This owns the X11 system tray (_NET_SYSTEM_TRAY_S0), docks
every icon in a container window placed off every screen, and publishes each one as a
StatusNotifierItem, which the Spark tray shows like any other. Clicks on that item are sent back
to the icon window.

Run as `spark-shell --xembed` (its own process: it lives on the X11 connection)."""

import logging
import os
import sys

from gi.repository import Gio, GLib

log = logging.getLogger('spark-xembed')

SIZE = 24                   # the icon window's size; the tray scales it
OFFSCREEN = -10000          # the containers sit here: no output there, so nothing is drawn
ITEM_PATH = '/StatusNotifierItem'
WATCHER = ('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher', 'org.kde.StatusNotifierWatcher')
REQUEST_DOCK = 0
XEMBED_EMBEDDED_NOTIFY = 0

ITEM_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
    <signal name="NewIcon"/>
    <signal name="NewTitle"/>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
</node>
"""


def to_argb_be(data: bytes, depth: int) -> bytes:
    """ZPixmap BGRA (little endian) -> the ARGB32 big-endian rows IconPixmap wants. 24-bit
    windows carry no alpha: opaque."""
    out = bytearray(len(data))
    out[1::4] = data[2::4]       # R
    out[2::4] = data[1::4]       # G
    out[3::4] = data[0::4]       # B
    if depth == 32:
        out[0::4] = data[3::4]
    else:
        out[0::4] = b'\xff' * (len(data) // 4)
    return bytes(out)


class Icon:
    """One docked icon and the StatusNotifierItem that stands for it."""

    def __init__(self, tray, wid):
        from Xlib import X
        self.tray, self.wid = tray, wid
        d = tray.d
        self.win = d.create_resource_object('window', wid)
        attrs = self.win.get_attributes()
        geo = self.win.get_geometry()
        self.depth = geo.depth
        root = tray.root
        kw = dict(border_pixel=0, background_pixel=0, override_redirect=1,
                  event_mask=X.SubstructureNotifyMask)
        if self.depth == 32 and tray.argb:
            kw['colormap'] = tray.argb_cmap
            visual = tray.argb
        else:
            visual = attrs.visual
            if visual != tray.screen.root_visual:
                kw['colormap'] = root.create_colormap(visual, X.AllocNone)
        self.box = root.create_window(OFFSCREEN, OFFSCREEN, SIZE, SIZE, 0, self.depth,
                                      X.InputOutput, visual, **kw)
        self.box.set_wm_name('spark-xembed')
        self.box.set_wm_class('spark-xembed', 'spark-xembed')
        self.win.change_attributes(event_mask=X.StructureNotifyMask | X.PropertyChangeMask)
        # save-set: if this process ends, X puts the icon back on the root instead of destroying
        # it with the container, so the app can dock it again (or fall back) when a tray returns
        self.win.change_save_set(X.SetModeInsert)
        self.win.reparent(self.box, 0, 0)
        self.win.configure(width=SIZE, height=SIZE)
        self._xembed_notify()
        self.box.map()
        self.win.map()
        try:
            self.box.composite_redirect_window(0)        # automatic: keeps a pixmap to read
        except Exception:                                # noqa: BLE001 - already redirected
            pass
        d.flush()
        self.title = self._title()
        self.pixels = b''
        self.n = tray.next_n()
        self.bus_name = f'org.kde.StatusNotifierItem-{os.getpid()}-{self.n}'
        self.reg_id = 0
        self.own_id = 0
        self._back = 0
        self._export()

    # X side
    def _xembed_notify(self):
        from Xlib import X
        from Xlib.protocol import event
        t = self.tray
        ev = event.ClientMessage(window=self.win, client_type=t.atom('_XEMBED'),
                                 data=(32, [X.CurrentTime, XEMBED_EMBEDDED_NOTIFY, 0, self.box.id, 0]))
        self.win.send_event(ev, event_mask=X.NoEventMask)

    def _title(self) -> str:
        try:
            name = self.win.get_full_text_property(self.tray.atom('_NET_WM_NAME'))
        except Exception:                                # noqa: BLE001
            name = None
        if not name:
            try:
                name = self.win.get_wm_name()
            except Exception:                            # noqa: BLE001
                name = None
        if not name:
            try:
                cls = self.win.get_wm_class()
                name = cls[1] if cls else None
            except Exception:                            # noqa: BLE001
                name = None
        return str(name or 'Tray icon')

    def snapshot(self) -> bool:
        """Read the icon's pixels; True when they changed."""
        from Xlib import X
        try:
            pix = self.box.composite_name_window_pixmap()
            img = pix.get_image(0, 0, SIZE, SIZE, X.ZPixmap, 0xffffffff)
            pix.free()
        except Exception as exc:                         # noqa: BLE001 - BadMatch while it resizes
            log.debug('snapshot of %#x failed: %s', self.wid, exc)
            return False
        data = img.data if isinstance(img.data, bytes) else bytes(img.data)
        if len(data) != SIZE * SIZE * 4:
            return False
        argb = to_argb_be(data, self.depth)
        if argb == self.pixels:
            return False
        self.pixels = argb
        return True

    def _place(self, bx: int, by: int):
        from Xlib import X
        from Xlib.protocol import event
        self.box.configure(x=bx, y=by, stack_mode=X.Above)
        # what a window manager sends after moving a frame: the window's place on the root
        ev = event.ConfigureNotify(event=self.win, window=self.win, above_sibling=X.NONE, x=bx, y=by,
                                   width=SIZE, height=SIZE, border_width=0, override=0)
        self.win.send_event(ev, event_mask=X.StructureNotifyMask)
        self.tray.d.flush()

    def _hide(self):
        self._back = 0
        try:
            self._place(OFFSCREEN, OFFSCREEN)
        except Exception:                                # noqa: BLE001 - it went away
            pass
        return False

    def click(self, button: int, x: int = 0, y: int = 0, times: int = 1):
        """A press and release (times=2: a double-click) in the middle of the icon window, sent
        to it directly. x, y: where the tray was clicked (0, 0 when unknown). Over the panel, a
        Wayland surface, XWayland doesn't know where the pointer is, so X11's pointer goes there
        first (the real cursor doesn't move)."""
        t = self.tray
        if x or y:
            try:
                t.root.warp_pointer(x, y)
            except Exception:                            # noqa: BLE001
                pass
        try:
            ptr = t.root.query_pointer()
            rx, ry = ptr.root_x, ptr.root_y
        except Exception:                                # noqa: BLE001
            rx, ry = x, y
        # Wine places its menu from where it thinks the icon window is; off every screen, it
        # clamps that to a corner. Bring the icon under the click for a moment (it's the same
        # picture as the tray's, at the same spot) and tell Wine, then put it back.
        if x or y:
            self._place(x - SIZE // 2, y - SIZE // 2)
            if self._back:
                GLib.source_remove(self._back)
            self._back = GLib.timeout_add(1500, self._hide)
        self._press(button, rx, ry)
        if times > 1:
            # Wine needs the second click as a separate one, a moment later; sent back to
            # back, the pair reads as one click
            GLib.timeout_add(80, lambda: self._press(button, rx, ry) and False)

    def _press(self, button: int, rx: int, ry: int) -> bool:
        from Xlib import X
        from Xlib.protocol import event
        t = self.tray
        ex = ey = SIZE // 2
        mask = {1: X.Button1Mask, 2: X.Button2Mask, 3: X.Button3Mask}.get(button, 0)
        try:
            for cls, state in ((event.ButtonPress, 0), (event.ButtonRelease, mask)):
                ev = cls(time=X.CurrentTime, root=t.root, window=self.win, same_screen=1,
                         child=X.NONE, root_x=rx, root_y=ry, event_x=ex, event_y=ey, state=state,
                         detail=button)
                self.win.send_event(ev, event_mask=X.ButtonPressMask if cls is event.ButtonPress
                                    else X.ButtonReleaseMask)
            t.d.flush()
        except Exception:                                # noqa: BLE001 - it went away
            pass
        return False

    # D-Bus side
    def _export(self):
        bus = self.tray.bus
        node = Gio.DBusNodeInfo.new_for_xml(ITEM_XML)
        self.reg_id = bus.register_object(ITEM_PATH if self.n == 0 else f'{ITEM_PATH}{self.n}',
                                          node.interfaces[0], self._call, self._get, None)
        self.path = ITEM_PATH if self.n == 0 else f'{ITEM_PATH}{self.n}'
        self.own_id = Gio.bus_own_name_on_connection(bus, self.bus_name, Gio.BusNameOwnerFlags.NONE,
                                                     self._owned, None)

    def _owned(self, conn, name):
        self.snapshot()
        conn.call(WATCHER[0], WATCHER[1], WATCHER[2], 'RegisterStatusNotifierItem',
                  GLib.Variant('(s)', (f'{name}{self.path}',)), None, Gio.DBusCallFlags.NONE, 3000,
                  None, None)

    def _get(self, conn, sender, path, iface, prop):
        if prop == 'IconPixmap':
            if not self.pixels:
                return GLib.Variant('a(iiay)', [])
            return GLib.Variant('a(iiay)', [(SIZE, SIZE, self.pixels)])
        return {
            'Category': GLib.Variant('s', 'ApplicationStatus'),
            'Id': GLib.Variant('s', f'xembed-{self.title}'),
            'Title': GLib.Variant('s', self.title),
            'Status': GLib.Variant('s', 'Active'),
            'WindowId': GLib.Variant('i', 0),
            'IconName': GLib.Variant('s', ''),
            'ItemIsMenu': GLib.Variant('b', False),
        }.get(prop)

    def _call(self, conn, sender, path, iface, method, params, inv):
        button = {'Activate': 1, 'SecondaryActivate': 2, 'ContextMenu': 3}.get(method)
        if button:
            x, y = params.unpack()
            # Windows tray icons open their app on a double-click (one click does nothing or
            # shows a tooltip); the Spark tray opens apps on one.
            self.click(button, x, y, times=2 if button == 1 else 1)
        inv.return_value(None)

    def changed(self):
        self.tray.bus.emit_signal(None, self.path, 'org.kde.StatusNotifierItem', 'NewIcon', None)

    def close(self):
        if self.reg_id:
            self.tray.bus.unregister_object(self.reg_id)
            self.reg_id = 0
        if self.own_id:
            Gio.bus_unown_name(self.own_id)
            self.own_id = 0
        try:
            self.box.destroy()
            self.tray.d.flush()
        except Exception:                                # noqa: BLE001
            pass


class Tray:
    def __init__(self):
        from Xlib import X, Xatom, display
        from Xlib.protocol import event
        self.d = display.Display()
        if not self.d.has_extension('Composite'):
            raise RuntimeError('the X server has no Composite extension')
        self.screen = self.d.screen()
        self.root = self.screen.root
        self.icons = {}
        self._n = 0
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.argb, self.argb_cmap = self._argb_visual()
        sel = self.atom(f'_NET_SYSTEM_TRAY_S{self.d.get_default_screen()}')
        self.owner = self.root.create_window(OFFSCREEN, OFFSCREEN, 1, 1, 0, X.CopyFromParent,
                                             override_redirect=1, event_mask=X.StructureNotifyMask)
        self.owner.set_wm_name('spark-xembed')
        self.owner.change_property(self.atom('_NET_SYSTEM_TRAY_ORIENTATION'), Xatom.CARDINAL, 32, [0])
        if self.argb:
            self.owner.change_property(self.atom('_NET_SYSTEM_TRAY_VISUAL'), Xatom.VISUALID, 32, [self.argb])
        self.owner.set_selection_owner(sel, X.CurrentTime)
        if self.d.get_selection_owner(sel) != self.owner:
            raise RuntimeError('another program owns the X11 system tray')
        ev = event.ClientMessage(window=self.root, client_type=self.atom('MANAGER'),
                                 data=(32, [X.CurrentTime, sel, self.owner.id, 0, 0]))
        self.root.send_event(ev, event_mask=X.StructureNotifyMask)
        self.d.flush()
        log.info('X11 system tray owned (%s)', 'ARGB icons' if self.argb else 'opaque icons')

    def atom(self, name):
        return self.d.intern_atom(name)

    def next_n(self):
        n = self._n
        self._n += 1
        return n

    def _argb_visual(self):
        from Xlib import X
        for depth in self.screen.allowed_depths:
            if depth.depth != 32:
                continue
            for v in depth.visuals:
                if v.visual_class == X.TrueColor:
                    return v.visual_id, self.root.create_colormap(v.visual_id, X.AllocNone)
        return None, None

    def on_x(self, *_):
        from Xlib import X
        while self.d.pending_events():
            ev = self.d.next_event()
            try:
                if ev.type == X.ClientMessage and ev.client_type == self.atom('_NET_SYSTEM_TRAY_OPCODE'):
                    data = ev.data[1]
                    if data[1] == REQUEST_DOCK and data[2] and data[2] not in self.icons:
                        try:
                            self.icons[data[2]] = Icon(self, data[2])
                            log.info('docked %#x (%s)', data[2], self.icons[data[2]].title)
                        except Exception as exc:          # noqa: BLE001 - it went away already
                            log.warning("couldn't dock %#x: %s", data[2], exc)
                elif ev.type == X.DestroyNotify and ev.window.id in self.icons:
                    self.icons.pop(ev.window.id).close()
                elif ev.type == X.ReparentNotify and ev.window.id in self.icons:
                    icon = self.icons[ev.window.id]
                    if ev.parent.id != icon.box.id:
                        self.icons.pop(ev.window.id).close()
                elif ev.type == X.UnmapNotify and ev.window.id in self.icons:
                    pass        # Wine unmaps while it redraws; the icon goes on DestroyNotify
                elif ev.type == X.PropertyNotify and ev.window.id in self.icons:
                    icon = self.icons[ev.window.id]
                    title = icon._title()
                    if title != icon.title:
                        icon.title = title
                        self.bus.emit_signal(None, icon.path, 'org.kde.StatusNotifierItem', 'NewTitle', None)
                elif ev.type == X.SelectionClear:
                    log.warning('another program took the X11 system tray')
                    GLib.idle_add(lambda: sys.exit(0))
            except Exception as exc:                      # noqa: BLE001 - one bad event
                log.warning('X event %s: %s', ev.type, exc)
        return True

    def poll(self):
        """Icons redraw (animated, status changes): look again every second."""
        for icon in list(self.icons.values()):
            if icon.snapshot():
                icon.changed()
        return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s spark-xembed %(message)s')
    if not os.environ.get('DISPLAY'):
        log.error('no DISPLAY (XWayland is not running)')
        return 1
    try:
        tray = Tray()
    except Exception as exc:                              # noqa: BLE001
        log.error('%s', exc)
        return 1
    GLib.io_add_watch(tray.d.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, tray.on_x)
    GLib.timeout_add(1000, tray.poll)
    tray.on_x()
    GLib.MainLoop().run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
