"""spark-secrets: the Secret Service of the Spark session (org.freedesktop.secrets).

Apps ask for saved passwords here (libsecret, Chromium and Electron apps, python-keyring,
secretstorage). It replaces GNOME Keyring: the same bus name and object paths, the same
`login` collection with the alias `default`, plus the Secret portal backend
(org.freedesktop.impl.portal.desktop.sparksecrets) in the same process.

The store is secrets_store.py. It is unlocked at sign-in by the key spark-secrets-pam leaves in
/run/spark-secrets/UID. If that key is missing or does not fit (the password was changed with
passwd, or the sign-in used no password), the first request that needs the store asks for the
password in a spark-ask window and, when the sign-in key exists, re-wraps the master key with it.

The code is split so it runs without a screen:
  Daemon       the state: vault, sessions, the unlock flow
  *Obj         one D-Bus object each (service, collection, item, session, prompt, portal)
  main()       --self-test, --import-gnome-keyring, or the daemon
"""

import fcntl
import logging
import os
import pwd
import secrets as _random
import sys

from . import secrets_store as store

log = logging.getLogger('spark-secrets')

BASE = '/org/freedesktop/secrets'
NAME = 'org.freedesktop.secrets'
PORTAL_NAME = 'org.freedesktop.impl.portal.desktop.sparksecrets'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
ERR = 'org.freedesktop.Secret.Error.'
DH_ALGO = 'dh-ietf1024-sha256-aes128-cbc-pkcs7'
PORTAL_SCHEMA = 'org.freedesktop.portal.Secret'
LABEL = 'org.freedesktop.Secret.Item.Label'
ATTRS = 'org.freedesktop.Secret.Item.Attributes'
TYPE = 'org.freedesktop.Secret.Item.Type'
COL_LABEL = 'org.freedesktop.Secret.Collection.Label'

SERVICE_XML = '''<node><interface name="org.freedesktop.Secret.Service">
<method name="OpenSession"><arg type="s" direction="in"/><arg type="v" direction="in"/>
  <arg type="v" direction="out"/><arg type="o" direction="out"/></method>
<method name="CreateCollection"><arg type="a{sv}" direction="in"/><arg type="s" direction="in"/>
  <arg type="o" direction="out"/><arg type="o" direction="out"/></method>
<method name="SearchItems"><arg type="a{ss}" direction="in"/>
  <arg type="ao" direction="out"/><arg type="ao" direction="out"/></method>
<method name="Unlock"><arg type="ao" direction="in"/><arg type="ao" direction="out"/><arg type="o" direction="out"/></method>
<method name="Lock"><arg type="ao" direction="in"/><arg type="ao" direction="out"/><arg type="o" direction="out"/></method>
<method name="GetSecrets"><arg type="ao" direction="in"/><arg type="o" direction="in"/>
  <arg type="a{o(oayays)}" direction="out"/></method>
<method name="ReadAlias"><arg type="s" direction="in"/><arg type="o" direction="out"/></method>
<method name="SetAlias"><arg type="s" direction="in"/><arg type="o" direction="in"/></method>
<property name="Collections" type="ao" access="read"/>
<signal name="CollectionCreated"><arg type="o"/></signal>
<signal name="CollectionDeleted"><arg type="o"/></signal>
<signal name="CollectionChanged"><arg type="o"/></signal>
</interface></node>'''

COLLECTION_XML = '''<node><interface name="org.freedesktop.Secret.Collection">
<method name="Delete"><arg type="o" direction="out"/></method>
<method name="SearchItems"><arg type="a{ss}" direction="in"/><arg type="ao" direction="out"/></method>
<method name="CreateItem"><arg type="a{sv}" direction="in"/><arg type="(oayays)" direction="in"/>
  <arg type="b" direction="in"/><arg type="o" direction="out"/><arg type="o" direction="out"/></method>
<property name="Items" type="ao" access="read"/>
<property name="Label" type="s" access="readwrite"/>
<property name="Locked" type="b" access="read"/>
<property name="Created" type="t" access="read"/>
<property name="Modified" type="t" access="read"/>
<signal name="ItemCreated"><arg type="o"/></signal>
<signal name="ItemDeleted"><arg type="o"/></signal>
<signal name="ItemChanged"><arg type="o"/></signal>
</interface></node>'''

ITEM_XML = '''<node><interface name="org.freedesktop.Secret.Item">
<method name="Delete"><arg type="o" direction="out"/></method>
<method name="GetSecret"><arg type="o" direction="in"/><arg type="(oayays)" direction="out"/></method>
<method name="SetSecret"><arg type="(oayays)" direction="in"/></method>
<property name="Locked" type="b" access="read"/>
<property name="Attributes" type="a{ss}" access="readwrite"/>
<property name="Label" type="s" access="readwrite"/>
<property name="Type" type="s" access="readwrite"/>
<property name="Created" type="t" access="read"/>
<property name="Modified" type="t" access="read"/>
</interface></node>'''

SESSION_XML = '''<node><interface name="org.freedesktop.Secret.Session">
<method name="Close"/></interface></node>'''

PROMPT_XML = '''<node><interface name="org.freedesktop.Secret.Prompt">
<method name="Prompt"><arg type="s" direction="in"/></method>
<method name="Dismiss"/>
<signal name="Completed"><arg type="b"/><arg type="v"/></signal>
</interface></node>'''

PORTAL_XML = '''<node><interface name="org.freedesktop.impl.portal.Secret">
<method name="RetrieveSecret"><arg type="o" direction="in"/><arg type="s" direction="in"/>
  <arg type="h" direction="in"/><arg type="a{sv}" direction="in"/>
  <arg type="u" direction="out"/><arg type="a{sv}" direction="out"/></method>
<property name="version" type="u" access="read"/>
</interface></node>'''


class DBusError(Exception):
    def __init__(self, name, message):
        super().__init__(message)
        self.name, self.message = name, message


def is_locked_error():
    return DBusError(ERR + 'IsLocked', 'The object is locked')


def no_such(path):
    return DBusError(ERR + 'NoSuchObject', f'No such object: {path}')


class Obj:
    """One D-Bus interface exported at one or more paths. Methods are m_Name(inv, sender, path, *args)."""
    xml = ''

    def __init__(self, daemon):
        self.d = daemon
        self.regs = {}

    def export(self, path):
        from gi.repository import Gio
        info = Gio.DBusNodeInfo.new_for_xml(self.xml).interfaces[0]
        self.iface = info.name
        self.regs[path] = self.d.conn.register_object(path, info, self._call, self._get, self._set)

    def unexport(self, path=None):
        for p in [path] if path else list(self.regs):
            rid = self.regs.pop(p, None)
            if rid is not None:
                self.d.conn.unregister_object(rid)

    def _call(self, conn, sender, path, iface, method, params, inv):
        try:
            getattr(self, 'm_' + method)(inv, sender, path, *params.unpack())
        except DBusError as exc:
            inv.return_dbus_error(exc.name, exc.message)
        except store.Locked:
            inv.return_dbus_error(ERR + 'IsLocked', 'The object is locked')
        except store.NoSuchObject as exc:
            inv.return_dbus_error(ERR + 'NoSuchObject', f'No such object: {exc}')
        except Exception:
            log.exception('%s failed', method)      # the traceback never holds a secret
            inv.return_dbus_error('org.freedesktop.DBus.Error.Failed', 'Spark Secrets failed')

    def _get(self, conn, sender, path, iface, prop):
        return self.get(path, prop)

    def _set(self, conn, sender, path, iface, prop, value):
        try:
            self.set(path, prop, value.unpack())
            return True
        except store.StoreError:
            return False

    def reply(self, inv, sig, *values):
        from gi.repository import GLib
        inv.return_value(GLib.Variant(sig, values) if sig else None)

    def changed(self, path, props):
        from gi.repository import GLib
        self.d.conn.emit_signal(None, path, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                                GLib.Variant('(sa{sv}as)', (self.iface, props, [])))


class SessionObj(Obj):
    xml = SESSION_XML

    def __init__(self, daemon, ident, key, sender):
        super().__init__(daemon)
        self.path = f'{BASE}/session/s{ident}'
        self.key, self.sender, self.watch = key, sender, None

    def start(self):
        from gi.repository import Gio
        self.export(self.path)
        self.watch = Gio.bus_watch_name_on_connection(
            self.d.conn, self.sender, Gio.BusNameWatcherFlags.NONE, None,
            lambda conn, name: self.close())

    def close(self):
        from gi.repository import Gio
        if self.watch is not None:
            Gio.bus_unwatch_name(self.watch)
            self.watch = None
        self.unexport()
        self.d.sessions.pop(self.path, None)

    def m_Close(self, inv, sender, path):
        self.close()
        self.reply(inv, None)

    def encode(self, item):
        """The (oayays) a client gets for an item."""
        if self.key is None:
            return (self.path, b'', item.secret, item.content_type)
        iv, blob = store.aes_cbc_encrypt(self.key, item.secret)
        return (self.path, iv, blob, item.content_type)

    def decode(self, secret):
        _, params, value, content_type = secret
        if self.key is None:
            return bytes(value), content_type or store.DEFAULT_TYPE
        try:
            return store.aes_cbc_decrypt(self.key, bytes(params), bytes(value)), \
                content_type or store.DEFAULT_TYPE
        except ValueError:
            raise DBusError('org.freedesktop.DBus.Error.InvalidArgs', 'The secret does not decrypt')


class PromptObj(Obj):
    xml = PROMPT_XML

    def __init__(self, daemon, ident, action):
        super().__init__(daemon)
        self.path = f'{BASE}/prompt/p{ident}'
        self.action = action        # action(done): done(dismissed, GLib.Variant result)
        self.started = self.finished = False

    def start(self):
        self.export(self.path)

    def m_Prompt(self, inv, sender, path, window_id):
        if self.started:
            raise DBusError(ERR + 'NoSuchObject', 'The prompt was already shown')
        self.started = True
        self.reply(inv, None)
        self.action(self._done)

    def _done(self, dismissed, result):
        from gi.repository import GLib
        if self.finished:
            return
        self.finished = True
        self.d.conn.emit_signal(None, self.path, 'org.freedesktop.Secret.Prompt', 'Completed',
                                GLib.Variant('(bv)', (dismissed, result)))
        GLib.idle_add(self._remove)

    def _remove(self):
        self.unexport()
        self.d.prompts.pop(self.path, None)
        return False

    def m_Dismiss(self, inv, sender, path):
        if self.started:
            self.d.cancel_ask()
        self._done(True, self.d.variant_path('/'))
        self.reply(inv, None)


class ItemObj(Obj):
    xml = ITEM_XML

    def __init__(self, daemon, col, ident):
        super().__init__(daemon)
        self.col, self.id = col, ident
        self.path = f'{BASE}/collection/{col.name}/{ident}'

    def item(self):
        return self.d.vault.item(self.col, self.id)

    def get(self, path, prop):
        from gi.repository import GLib
        v = self.d.vault
        if prop == 'Locked':
            return GLib.Variant('b', v.is_locked(self.col))
        it = self.item()
        return {'Attributes': lambda: GLib.Variant('a{ss}', it.attrs),
                'Label': lambda: GLib.Variant('s', it.label),
                'Type': lambda: GLib.Variant('s', it.type),
                'Created': lambda: GLib.Variant('t', it.created),
                'Modified': lambda: GLib.Variant('t', it.modified)}[prop]()

    def set(self, path, prop, value):
        from gi.repository import GLib
        it = self.item()
        if prop == 'Label':
            self.d.vault.update_item(self.col, it, label=value)
        elif prop == 'Attributes':
            self.d.vault.update_item(self.col, it, attrs=value)
        elif prop == 'Type':
            it.type = value
            self.d.vault.update_item(self.col, it)
        else:
            raise store.StoreError('read-only')
        self.changed(self.path, {prop: self.get(path, prop), 'Modified': GLib.Variant('t', it.modified)})
        self.d.col_obj(self.col).signal('ItemChanged', self.path)

    def _session(self, path):
        return self.d.session(path)

    def m_Delete(self, inv, sender, path):
        self.d.vault.delete_item(self.col, self.id)
        self.d.col_obj(self.col).item_removed(self)
        self.reply(inv, '(o)', '/')

    def m_GetSecret(self, inv, sender, path, session):
        it = self.item()
        self.reply(inv, '((oayays))', self._session(session).encode(it))

    def m_SetSecret(self, inv, sender, path, secret):
        it = self.item()
        value, content_type = self._session(secret[0]).decode(secret)
        self.d.vault.update_item(self.col, it, secret=value, content_type=content_type)
        self.d.col_obj(self.col).signal('ItemChanged', self.path)
        self.reply(inv, None)


class CollectionObj(Obj):
    xml = COLLECTION_XML

    def __init__(self, daemon, col):
        super().__init__(daemon)
        self.col = col
        self.path = f'{BASE}/collection/{col.name}'
        self.items = {}

    def start(self):
        self.export(self.path)
        for ident in self.d.vault.item_ids(self.col):
            self.add_item(ident)

    def add_item(self, ident):
        obj = ItemObj(self.d, self.col, ident)
        obj.export(obj.path)
        self.items[ident] = obj
        return obj

    def item_removed(self, obj):
        obj.unexport()
        self.items.pop(obj.id, None)
        self.signal('ItemDeleted', obj.path)
        self.items_changed()

    def items_changed(self):
        from gi.repository import GLib
        self.changed(self.path, {'Items': self.get(self.path, 'Items'),
                                 'Modified': GLib.Variant('t', self.col.modified)})

    def signal(self, name, item_path):
        from gi.repository import GLib
        self.d.conn.emit_signal(None, self.path, 'org.freedesktop.Secret.Collection', name,
                                GLib.Variant('(o)', (item_path,)))

    def refresh_locked(self):
        from gi.repository import GLib
        locked = GLib.Variant('b', self.d.vault.is_locked(self.col))
        self.changed(self.path, {'Locked': locked})
        for obj in self.items.values():
            obj.changed(obj.path, {'Locked': locked})

    def get(self, path, prop):
        from gi.repository import GLib
        c = self.col
        return {'Items': lambda: GLib.Variant('ao', [o.path for o in self.items.values()]),
                'Label': lambda: GLib.Variant('s', c.label),
                'Locked': lambda: GLib.Variant('b', self.d.vault.is_locked(c)),
                'Created': lambda: GLib.Variant('t', c.created),
                'Modified': lambda: GLib.Variant('t', c.modified)}[prop]()

    def set(self, path, prop, value):
        if prop != 'Label':
            raise store.StoreError('read-only')
        self.d.vault.set_label(self.col, value)
        self.changed(self.path, {'Label': self.get(path, 'Label')})
        self.d.service.signal('CollectionChanged', self.path)

    def m_Delete(self, inv, sender, path):
        self.d.delete_collection(self.col)
        self.reply(inv, '(o)', '/')

    def m_SearchItems(self, inv, sender, path, attrs):
        ids = self.d.vault.search(self.col, attrs)
        self.reply(inv, '(ao)', [f'{self.path}/{i}' for i in ids])

    def m_CreateItem(self, inv, sender, path, props, secret, replace):
        if self.d.vault.is_locked(self.col):
            raise is_locked_error()
        value, content_type = self.d.session(secret[0]).decode(secret)
        attrs = props.get(ATTRS, {})
        item, replaced = self.d.vault.create_item(
            self.col, props.get(LABEL, ''), attrs, value, content_type,
            props.get(TYPE, ''), replace)
        if replaced:
            self.signal('ItemChanged', f'{self.path}/{item.id}')
        else:
            obj = self.add_item(item.id)
            self.signal('ItemCreated', obj.path)
            self.items_changed()
        self.reply(inv, '(oo)', f'{self.path}/{item.id}', '/')


class ServiceObj(Obj):
    xml = SERVICE_XML

    def __init__(self, daemon):
        super().__init__(daemon)
        self.path = BASE

    def get(self, path, prop):
        from gi.repository import GLib
        return GLib.Variant('ao', [c.path for c in self.d.col_objs.values()])

    def signal(self, name, col_path):
        from gi.repository import GLib
        self.d.conn.emit_signal(None, BASE, 'org.freedesktop.Secret.Service', name,
                                GLib.Variant('(o)', (col_path,)))

    def m_OpenSession(self, inv, sender, path, algorithm, data):
        from gi.repository import GLib
        d = self.d
        if algorithm == 'plain':
            key, out = None, GLib.Variant('s', '')
        elif algorithm == DH_ALGO:
            try:
                private, public = store.dh_server_keys()
                key = store.dh_session_key(private, bytes(data))
            except (ValueError, TypeError):
                raise DBusError('org.freedesktop.DBus.Error.InvalidArgs', 'Bad DH public key')
            out = GLib.Variant('ay', public)
        else:
            raise DBusError('org.freedesktop.DBus.Error.NotSupported', f'No such algorithm: {algorithm}')
        d.session_count += 1
        session = SessionObj(d, d.session_count, key, sender)
        d.sessions[session.path] = session
        session.start()
        self.reply(inv, '(vo)', out, session.path)

    def m_CreateCollection(self, inv, sender, path, props, alias):
        d = self.d
        label = props.get(COL_LABEL, '') or 'Collection'
        if alias:
            known = d.vault.resolve_alias(alias)
            if known:
                return self.reply(inv, '(oo)', f'{BASE}/collection/{known}', '/')

        def create():
            col = d.vault.create_collection(label)
            obj = d.add_collection(col)
            if alias:
                d.set_alias(alias, col.name)
            self.signal('CollectionCreated', obj.path)
            self.changed(BASE, {'Collections': self.get(BASE, 'Collections')})
            return obj.path

        if d.vault.unlocked:
            return self.reply(inv, '(oo)', create(), '/')

        def action(done):
            def after(ok):
                done(not ok, d.variant_path(create() if ok else '/'))
            d.ensure_unlocked(after)
        self.reply(inv, '(oo)', '/', d.new_prompt(action).path)

    def m_SearchItems(self, inv, sender, path, attrs):
        d = self.d
        unlocked, locked = [], []
        for name, cobj in d.col_objs.items():
            col = cobj.col
            hits = [f'{cobj.path}/{i}' for i in d.vault.search(col, attrs)]
            (locked if d.vault.is_locked(col) else unlocked).extend(hits)
        self.reply(inv, '(aoao)', unlocked, locked)

    def _paths(self, paths):
        out = []
        for p in paths:
            if self.d.lookup(p) is None:
                raise no_such(p)
            out.append(p)
        return out

    def m_Unlock(self, inv, sender, path, paths):
        d = self.d
        paths = self._paths(paths)
        if d.vault.unlocked or d.try_keyfile():
            return self.reply(inv, '(aoo)', paths, '/')
        if not any(d.vault.is_locked(d.lookup(p)[0]) for p in paths):
            return self.reply(inv, '(aoo)', paths, '/')

        def action(done):
            d.ensure_unlocked(lambda ok: done(not ok, d.variant_paths(paths if ok else [])))
        self.reply(inv, '(aoo)', [], d.new_prompt(action).path)

    def m_Lock(self, inv, sender, path, paths):
        d = self.d
        paths = self._paths(paths)
        d.vault.lock()
        d.after_lock_change()
        self.reply(inv, '(aoo)', paths, '/')

    def m_GetSecrets(self, inv, sender, path, items, session):
        from gi.repository import GLib
        s = self.d.session(session)
        out = {}
        for p in items:
            found = self.d.lookup(p)
            if found is None or found[1] is None:
                continue
            col, ident = found
            if self.d.vault.is_locked(col):
                continue
            out[p] = s.encode(self.d.vault.item(col, ident))
        inv.return_value(GLib.Variant('(a{o(oayays)})', (out,)))

    def m_ReadAlias(self, inv, sender, path, alias):
        name = self.d.vault.resolve_alias(alias) if alias != 'session' else 'session'
        self.reply(inv, '(o)', f'{BASE}/collection/{name}' if name else '/')

    def m_SetAlias(self, inv, sender, path, alias, target):
        d = self.d
        if target == '/':
            d.set_alias(alias, None)
        else:
            found = d.lookup(target)
            if found is None or found[1] is not None:
                raise no_such(target)
            d.set_alias(alias, found[0].name)
        self.reply(inv, None)


class PortalObj(Obj):
    xml = PORTAL_XML

    def get(self, path, prop):
        from gi.repository import GLib
        return GLib.Variant('u', 1)

    def m_RetrieveSecret(self, inv, sender, path, handle, app_id, fd_index, options):
        from gi.repository import GLib
        d = self.d
        fds = inv.get_message().get_unix_fd_list()
        if fds is None:
            raise DBusError('org.freedesktop.DBus.Error.InvalidArgs', 'No file descriptor')
        fd = fds.get(fd_index)

        def answer(code):
            inv.return_value(GLib.Variant('(ua{sv})', (code, {})))

        def go(ok):
            try:
                if not ok:
                    return answer(1)
                os.write(fd, d.app_secret(app_id))
                answer(0)
            except Exception:
                log.exception('portal secret failed')
                answer(2)
            finally:
                os.close(fd)
        d.ensure_unlocked(go)


class Daemon:
    def __init__(self, vault, user, ask=None, keyfile=None):
        self.vault = vault
        self.user = user
        self.ask_cmd = ask or os.environ.get('SPARK_SECRETS_ASK', '/usr/bin/spark-ask')
        self.keyfile = keyfile
        self.conn = None
        self.sessions, self.prompts, self.col_objs = {}, {}, {}
        self.session_count = self.prompt_count = 0
        self.waiters = []
        self.proc = None
        self.service = ServiceObj(self)
        self.portal = PortalObj(self)

    # -- exporting --
    def export_all(self, conn):
        self.conn = conn
        self.service.export(BASE)
        for col in self.vault.collections.values():
            self.add_collection(col)
        self.set_alias('session', 'session', save=False)
        for alias, name in self.vault.aliases.items():
            if name in self.vault.collections:
                self.col_objs[name].export(f'{BASE}/aliases/{alias}')
        self.portal.export(PORTAL_PATH)

    def add_collection(self, col):
        obj = CollectionObj(self, col)
        obj.start()
        self.col_objs[col.name] = obj
        return obj

    def col_obj(self, col):
        return self.col_objs[col.name]

    def delete_collection(self, col):
        obj = self.col_objs[col.name]
        self.vault.delete_collection(col.name)
        for item in list(obj.items.values()):
            item.unexport()
        obj.unexport()
        del self.col_objs[col.name]
        self.service.signal('CollectionDeleted', obj.path)
        self.service.changed(BASE, {'Collections': self.service.get(BASE, 'Collections')})

    def set_alias(self, alias, name, save=True):
        old = self.vault.aliases.get(alias) if alias != 'session' else 'session'
        if old in self.col_objs:
            self.col_objs[old].unexport(f'{BASE}/aliases/{alias}')
        if name is None:
            self.vault.aliases.pop(alias, None)
        else:
            if alias != 'session':
                self.vault.aliases[alias] = name
            self.col_objs[name].export(f'{BASE}/aliases/{alias}')
        if save and alias != 'session':
            self.vault.save_aliases()

    # -- lookups --
    def lookup(self, path):
        """(collection, item id or None) for a collection or item path, else None."""
        for prefix in (f'{BASE}/collection/', f'{BASE}/aliases/'):
            if path.startswith(prefix):
                parts = path[len(prefix):].split('/')
                name = parts[0]
                if prefix.endswith('aliases/'):
                    name = 'session' if name == 'session' else self.vault.aliases.get(name)
                col = self.vault.collections.get(name)
                if col is None or len(parts) > 2:
                    return None
                if len(parts) == 2:
                    ident = parts[1]
                    if prefix.endswith('aliases/') or ident not in self.col_objs[name].items:
                        return None
                    return col, ident
                return col, None
        return None

    def session(self, path):
        try:
            return self.sessions[path]
        except KeyError:
            raise DBusError(ERR + 'NoSession', 'The session does not exist')

    def new_prompt(self, action):
        self.prompt_count += 1
        prompt = PromptObj(self, self.prompt_count, action)
        self.prompts[prompt.path] = prompt
        prompt.start()
        return prompt

    @staticmethod
    def variant_path(path):
        from gi.repository import GLib
        return GLib.Variant('o', path)

    @staticmethod
    def variant_paths(paths):
        from gi.repository import GLib
        return GLib.Variant('ao', paths)

    # -- unlocking --
    def keyfile_key(self):
        return store.read_keyfile(self.keyfile)

    def try_keyfile(self):
        """Unlock with the key from sign-in. False if there is none or it does not fit."""
        if self.vault.unlocked:
            return True
        key = self.keyfile_key()
        if key is None:
            return False
        try:
            if not self.vault.has_master():
                self.vault.init_master(key)
            elif not self.vault.unlock(key):
                log.info('the sign-in key does not open the store')
                return False
        except store.StoreError as exc:
            log.error('%s', exc)
            return False
        self.after_lock_change()
        return True

    def after_lock_change(self):
        if self.conn is None:
            return
        for obj in self.col_objs.values():
            obj.refresh_locked()

    def ensure_unlocked(self, done):
        """done(True) once the store is unlocked, done(False) if the person cancelled."""
        if self.vault.unlocked or self.try_keyfile():
            return done(True)
        self.waiters.append(done)
        if len(self.waiters) == 1:
            self._ask(0)

    def cancel_ask(self):
        if self.proc is not None:
            self.proc.force_exit()

    def _finish(self, ok):
        waiters, self.waiters, self.proc = self.waiters, [], None
        for done in waiters:
            done(ok)

    def _ask(self, attempt):
        from gi.repository import Gio, GLib
        if not self.vault.has_master():
            text = 'Choose a password to protect your saved passwords (your sign-in password works best).'
        elif self.keyfile_key() is not None:
            text = 'Your sign-in password changed. Enter the old one to unlock your saved passwords.'
        else:
            text = 'Enter your password to unlock your saved passwords.'
        if attempt:
            text = 'That password did not unlock them. ' + text
        try:
            self.proc = Gio.Subprocess.new(
                [self.ask_cmd, '--title', 'Spark Secrets', '--password', text],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
            self.proc.communicate_utf8_async(None, None, self._asked, attempt)
        except GLib.Error as exc:
            log.error('the password window did not start: %s', exc.message)
            self._finish(False)

    def _asked(self, proc, result, attempt):
        from gi.repository import GLib
        try:
            _, out, _ = proc.communicate_utf8_finish(result)
        except GLib.Error:
            return self._finish(False)
        if not proc.get_successful() or not out:
            return self._finish(False)
        password = out.rstrip('\n').encode()
        try:
            key = store.wrapping_key(password, self.user, self.vault.params)
            if not self.vault.has_master():
                self.vault.init_master(key)
            elif not self.vault.unlock(key):
                if attempt >= 2:
                    return self._finish(False)
                return self._ask(attempt + 1)
            current = self.keyfile_key()
            if current is not None and current != key:
                self.vault.rewrap(current)
                log.info('the master key is wrapped by the new sign-in key')
        except store.StoreError as exc:
            log.error('%s', exc)
            return self._finish(False)
        self.after_lock_change()
        self._finish(True)

    # -- the portal --
    def app_secret(self, app_id) -> bytes:
        col = self.vault.collection('login')
        attrs = {'app_id': app_id, 'xdg:schema': PORTAL_SCHEMA}
        item = self.vault.find_exact(col, attrs)
        if item is None:
            item, _ = self.vault.create_item(
                col, f'Secret of {app_id or "the host"}', attrs, _random.token_bytes(64),
                'application/octet-stream')
            obj = self.col_objs['login'].add_item(item.id)
            self.col_objs['login'].signal('ItemCreated', obj.path)
        return item.secret


# --- the program ------------------------------------------------------------------------------

def current_user() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def take_lock(directory):
    """One process works on a store at a time (the daemon, or the import)."""
    path = os.path.join(directory, '.lock')
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def run_daemon() -> int:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
    directory = store.default_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    lock = take_lock(directory)
    if lock is None:
        print('spark-secrets: another spark-secrets (or an import) is working on this store', file=sys.stderr)
        return 1
    vault = store.Vault(directory)
    for name, why in vault.broken.items():
        log.error('collection %s is damaged and is left alone: %s', name, why)
    daemon = Daemon(vault, current_user())
    loop = GLib.MainLoop()
    status = [0]

    def acquired(conn, name):
        daemon.export_all(conn)
        daemon.try_keyfile()
        Gio.bus_own_name_on_connection(conn, PORTAL_NAME, Gio.BusNameOwnerFlags.NONE, None,
                                       lambda c, n: log.warning('the portal name %s is taken', n))

    def lost(conn, name):
        log.error('%s is owned by another program (is GNOME Keyring still running?)', NAME)
        status[0] = 1
        loop.quit()

    Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.NONE, acquired, None, lost)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, loop.quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 2, loop.quit)
    log.info('running')
    loop.run()
    return status[0]


def _ask_password(text, ask_cmd):
    """The password for the import: stdin if it is piped, else a spark-ask window, else a prompt."""
    import getpass
    import subprocess
    if os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY'):
        try:
            out = subprocess.run([ask_cmd, '--title', 'Spark Secrets', '--password', text],
                                 capture_output=True, text=True, check=True).stdout
            return out.rstrip('\n').encode()
        except (OSError, subprocess.CalledProcessError):
            pass
    return getpass.getpass(text + ' ').encode()


def import_gnome_keyring(argv) -> int:
    """spark-secrets --import-gnome-keyring [FILE] [--password-stdin] [--into COLLECTION]
    Run it while the daemon is not running. Prints how many items were added and skipped."""
    from . import secrets_import as imp
    args = [a for a in argv if a != '--import-gnome-keyring']
    from_stdin = '--password-stdin' in args
    into = None
    if '--into' in args:
        i = args.index('--into')
        into = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    files = [a for a in args if not a.startswith('--')]
    path = files[0] if files else os.path.expanduser('~/.local/share/keyrings/login.keyring')
    try:
        with open(path, 'rb') as handle:
            data = handle.read()
    except OSError as exc:
        print(f'spark-secrets: cannot read {path}: {exc.strerror}', file=sys.stderr)
        return 1
    ask_cmd = os.environ.get('SPARK_SECRETS_ASK', '/usr/bin/spark-ask')
    if from_stdin:
        password = store.password_from_stdin(sys.stdin.buffer.read()).rstrip(b'\n')
    else:
        password = _ask_password('Enter the password of this GNOME Keyring file.', ask_cmd)
    try:
        name, _, _, items = imp.parse_keyring(data, password)
    except imp.ImportError_ as exc:
        print(f'spark-secrets: {exc}', file=sys.stderr)
        return 1

    directory = store.default_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    lock = take_lock(directory)
    if lock is None:
        print('spark-secrets: stop spark-secrets first (systemctl --user stop spark-secrets), '
              'then run the import again', file=sys.stderr)
        return 1
    vault = store.Vault(directory)
    key = store.wrapping_key(password, current_user(), vault.params)
    if vault.has_master():
        try:
            opened = vault.unlock(key)
        except store.StoreError as exc:
            print(f'spark-secrets: {exc}', file=sys.stderr)
            return 1
        if not opened:
            keyfile = store.read_keyfile()
            if keyfile is None or not vault.unlock(keyfile):
                print('spark-secrets: the store is not opened by this password; sign in again '
                      'or unlock it once first', file=sys.stderr)
                return 1
    else:
        vault.init_master(key)
    if into is None and name and store.safe_name(name) != 'login':
        into = name
    if into and store.safe_name(into) != 'login':
        col = vault.collections.get(store.safe_name(into)) or vault.create_collection(into)
    else:
        col = vault.collection('login')
    added, skipped = imp.import_items(vault, col, items)
    print(f'spark-secrets: {added} added, {skipped} already there (collection {col.name})')
    return 0


def self_test() -> int:
    """No bus, no display: the crypto and the store."""
    import tempfile
    private, public = store.dh_server_keys()
    c_private = int.from_bytes(os.urandom(64), 'big') | 2
    c_public = store.int_to_bytes(pow(store.DH_GENERATOR, c_private, store.DH_PRIME))
    k1 = store.dh_session_key(private, c_public)
    k2 = store.dh_session_key(c_private, public)
    assert k1 == k2 and len(k1) == 16
    iv, blob = store.aes_cbc_encrypt(k1, b'secret')
    assert store.aes_cbc_decrypt(k2, iv, blob) == b'secret'
    with tempfile.TemporaryDirectory() as tmp:
        fast = {'n': 2 ** 10}
        vault = store.Vault(os.path.join(tmp, 's'), fast)
        key = store.wrapping_key(b'pw', 'user', fast)
        vault.init_master(key)
        col = vault.collection('login')
        vault.create_item(col, 'l', {'a': 'b'}, b'hunter2')
        vault.lock()
        assert vault.search(col, {'a': 'b'}) == ['1']
        again = store.Vault(os.path.join(tmp, 's'), fast)
        assert not again.unlock(store.wrapping_key(b'other', 'user', fast))
        assert again.unlock(key)
        assert again.item(again.collection('login'), '1').secret == b'hunter2'
    print('self-test passed')
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format='spark-secrets: %(message)s', stream=sys.stderr)
    if '--version' in argv:
        from . import VERSION
        print(f'spark-secrets {VERSION}')
        return 0
    if '--self-test' in argv:
        return self_test()
    if '--import-gnome-keyring' in argv:
        return import_gnome_keyring(argv)
    return run_daemon()


if __name__ == '__main__':
    sys.exit(main())
