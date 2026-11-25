"""Spark Boxes without a window: the machine XML, ISO labels, the USB filter, the driver download
(with a fake server) and the manager on libvirt's own test driver (a fake hypervisor, not QEMU).
Nothing here touches a real machine, a real disk or the network. Run: python3 -m unittest
tests.test_core -v"""

import hashlib
import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

os.environ['SPARK_BOXES_URI'] = 'test:///default'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sparkboxes import core, isoinfo, usbdev, virtio, xmlgen  # noqa: E402
from sparkboxes.text import EN, FR, t  # noqa: E402

try:
    import libvirt  # noqa: F401
    HAVE_LIBVIRT = True
except ImportError:
    HAVE_LIBVIRT = False


def spec(preset='linux', **kw):
    base = dict(name='box', preset=preset, cpus=2, memory_mb=2048, kvm=False,
                disk_path='/var/lib/libvirt/images/box.qcow2')
    base.update(kw)
    return xmlgen.VmSpec(**base)


def root_of(s):
    return ET.fromstring(xmlgen.build_xml(s))


class XmlTests(unittest.TestCase):

    def test_windows_11_has_secure_boot_and_a_tpm(self):
        x = xmlgen.build_xml(spec('win11'))
        self.assertIn("name='secure-boot'", x)
        self.assertIn("name='enrolled-keys'", x)
        self.assertIn("<tpm model='tpm-crb'>", x)
        self.assertIn("version='2.0'", x)
        self.assertIn("<smm state='on'/>", x)
        self.assertIn("firmware='efi'", x)
        self.assertNotIn('.fd', x, "no firmware file paths: libvirt picks the firmware")

    def test_windows_gets_plain_devices_until_drivers_exist(self):
        r = root_of(spec('win10'))
        self.assertEqual(r.find("devices/disk[@device='disk']/target").get('bus'), 'sata')
        self.assertEqual(r.find('devices/interface/model').get('type'), 'e1000e')
        self.assertEqual(r.find('devices/video/model').get('type'), 'vga')
        self.assertIsNone(r.find('devices/tpm'))
        self.assertIsNone(r.find("os/firmware"))

    def test_windows_with_drivers_and_linux_use_virtio(self):
        for s in (spec('win11', drivers=True), spec('linux')):
            r = root_of(s)
            self.assertEqual(r.find("devices/disk[@device='disk']/target").get('bus'), 'virtio')
            self.assertEqual(r.find('devices/interface/model').get('type'), 'virtio')

    def test_spice_has_no_network_listener(self):
        r = root_of(spec())
        self.assertEqual(r.find('devices/graphics').get('type'), 'spice')
        self.assertEqual(r.find('devices/graphics/listen').get('type'), 'none')

    def test_boot_order_and_cdrom(self):
        r = root_of(spec(iso_path='/tmp/a.iso'))
        orders = {d.get('device'): d.find('boot').get('order') for d in r.findall('devices/disk')}
        self.assertEqual(orders, {'disk': '2', 'cdrom': '1'})
        self.assertEqual(r.find("devices/disk[@device='cdrom']/source").get('file'), '/tmp/a.iso')

    def test_kvm_and_tcg(self):
        self.assertEqual(root_of(spec(kvm=True)).get('type'), 'kvm')
        self.assertEqual(root_of(spec(kvm=True)).find('cpu').get('mode'), 'host-passthrough')
        self.assertEqual(root_of(spec(kvm=False)).get('type'), 'qemu')

    def test_network_choices(self):
        self.assertEqual(root_of(spec()).find('devices/interface/source').get('network'), 'default')
        self.assertEqual(root_of(spec(network_source='')).find('devices/interface').get('type'), 'user')
        self.assertEqual(root_of(spec(network=False)).find('devices/interface/link').get('state'), 'down')

    def test_names_that_break_things_are_refused(self):
        for bad in ('', ' a', 'a/b'):
            with self.assertRaises(ValueError):
                xmlgen.build_xml(spec(name=bad))
        with self.assertRaises(ValueError):
            xmlgen.build_xml(spec(preset='amiga'))

    def test_xml_special_characters_stay_inside(self):
        r = root_of(spec(name='a<b>&"c', iso_path='/tmp/x"y.iso'))
        self.assertEqual(r.find('name').text, 'a<b>&"c')

    def test_defaults(self):
        self.assertEqual(xmlgen.default_cpus(16), 8)
        self.assertEqual(xmlgen.default_cpus(1), 1)
        self.assertEqual(xmlgen.default_memory_mb('win11', 32768), 8192)
        self.assertEqual(xmlgen.default_memory_mb('win11', 8192), 4096)
        self.assertEqual(xmlgen.default_memory_mb('linux', 2048), 1024)
        self.assertEqual(xmlgen.default_disk_gb('win11'), 80)


class IsoTests(unittest.TestCase):

    def make(self, label: bytes):
        f = tempfile.NamedTemporaryFile(suffix='.iso', delete=False)
        f.write(b'\0' * isoinfo.PVD_OFFSET + b'\x01CD001\x01\0' + b' ' * 32)
        f.seek(isoinfo.LABEL_AT)
        f.write(label.ljust(32))
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_label_is_read(self):
        self.assertEqual(isoinfo.volume_label(self.make(b'Fedora-KDE-Live')), 'Fedora-KDE-Live')

    def test_not_an_iso(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b'x' * 40000)
            f.flush()
            self.assertIsNone(isoinfo.volume_label(f.name))
        self.assertIsNone(isoinfo.volume_label('/nonexistent.iso'))

    def test_guesses(self):
        g = isoinfo.guess_preset
        self.assertEqual(g('CCCOMA_X64FRE_EN-US_DV9'), 'win11')
        self.assertEqual(g('Win10_22H2_English_x64'), 'win10')
        self.assertEqual(g('Fedora-KDE-Live-45'), 'linux')
        self.assertEqual(g('', 'ubuntu-24.04.iso'), 'linux')
        self.assertEqual(g('MYDISC', 'thing.iso'), 'other')
        self.assertEqual(g(None), 'other')

    @unittest.skipUnless(os.path.exists('/tmp/vw/virtio-win-0.1.302.iso'), 'no real driver ISO here')
    def test_a_real_iso(self):
        self.assertTrue(isoinfo.volume_label('/tmp/vw/virtio-win-0.1.302.iso'))


class UsbTests(unittest.TestCase):

    def tree(self, devices):
        """devices: list of (name, vendor, product, busnum, devnum, cls, [(block, 'maj:min')])."""
        sysfs = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, sysfs)
        bus = os.path.join(sysfs, 'bus', 'usb', 'devices')
        os.makedirs(bus)
        os.makedirs(os.path.join(sysfs, 'class', 'block'))
        for name, vendor, product, busnum, devnum, cls, blocks in devices:
            d = os.path.join(sysfs, 'devices', name)
            os.makedirs(d)
            for fname, value in (('idVendor', vendor), ('idProduct', product), ('busnum', busnum),
                                 ('devnum', devnum), ('bDeviceClass', cls), ('product', name)):
                with open(os.path.join(d, fname), 'w') as f:
                    f.write(str(value))
            os.symlink(d, os.path.join(bus, name))
            for block, numbers in blocks:
                os.makedirs(os.path.join(d, 'host0', 'block', block))
                os.makedirs(os.path.join(sysfs, 'class', 'block', block))
                with open(os.path.join(sysfs, 'class', 'block', block, 'dev'), 'w') as f:
                    f.write(numbers)
        return sysfs

    @staticmethod
    def mountinfo(*pairs):
        return '\n'.join(f"1 2 {n} / {m} rw - ext4 /dev/x rw" for n, m in pairs)

    def test_filter(self):
        sysfs = self.tree([
            ('mouse', '046d', 'c077', 1, 4, '00', []),
            ('hub', '1d6b', '0002', 1, 1, '09', []),
            ('stick', '0781', '5567', 1, 5, '00', [('sdb', '8:16')]),
            ('sysdisk', '0bc2', 'aaaa', 1, 6, '00', [('sdc', '8:32')]),
            ('ddrive', '1058', 'bbbb', 1, 7, '00', [('sdd', '8:48')]),
            ('usbsys', '1111', '2222', 1, 8, '00', [('sde', '8:64')]),
        ])
        info = self.mountinfo(('8:16', '/run/media/me/STICK'), ('8:32', '/var/home'),
                              ('8:48', '/var/mnt/d'), ('8:64', '/sysroot'))
        found = {d.name: d for d in usbdev.list_devices(sysfs, info)}
        self.assertNotIn('hub', found)
        self.assertEqual(found['mouse'].refused, '')
        self.assertEqual(found['stick'].refused, 'mounted')
        self.assertEqual(found['sysdisk'].refused, 'system')
        self.assertEqual(found['ddrive'].refused, 'd')
        self.assertEqual(found['usbsys'].refused, 'system')
        self.assertTrue(found['mouse'].allowed)
        self.assertFalse(found['ddrive'].allowed)

    def test_an_unmounted_stick_is_allowed(self):
        sysfs = self.tree([('stick', '0781', '5567', 1, 5, '00', [('sdb', '8:16')])])
        self.assertTrue(usbdev.list_devices(sysfs, '')[0].allowed)

    def test_d_prefix_does_not_overmatch(self):
        self.assertEqual(usbdev.refusal(['/var/mnt/data']), 'mounted')
        self.assertEqual(usbdev.refusal(['/var/mnt/d/sub']), 'd')

    def test_no_sysfs(self):
        self.assertEqual(usbdev.list_devices('/nonexistent', ''), [])

    def test_hostdev_xml(self):
        x = usbdev.hostdev_xml(usbdev.UsbDevice(1, 4, '046d', 'c077', 'm'))
        r = ET.fromstring(x)
        self.assertEqual(r.find('source/vendor').get('id'), '0x046d')
        self.assertEqual(r.find('source/address').get('device'), '4')

    @unittest.skipUnless(HAVE_LIBVIRT, 'python3-libvirt missing')
    def test_manager_refuses_a_refused_device(self):
        m = core.Manager()
        m.connect()
        self.addCleanup(m.close)
        bad = usbdev.UsbDevice(1, 2, 'aaaa', 'bbbb', 'Disk D', refused='d')
        with self.assertRaises(core.BoxesError):
            m.usb_give('anything', bad)


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class VirtioTests(unittest.TestCase):
    DATA = b'driver-disc' * 1000

    def opener(self, data=DATA, size=None, listing=b'virtio-win-0.1.302-1.noarch.rpm 123'):
        def open_(url):
            if url == virtio.LISTING:
                return FakeResponse(listing)
            self.assertTrue(url.startswith('https://'))
            return FakeResponse(data, {'Content-Length': str(len(data) if size is None else size)})
        return open_

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, self.dir)
        self.saved = dict(virtio.PINNED)
        self.addCleanup(lambda: (virtio.PINNED.clear(), virtio.PINNED.update(self.saved)))

    def test_version_parse(self):
        self.assertEqual(virtio.parse_version("x virtio-win-0.1.285-1.noarch.rpm y"), '0.1.285')
        self.assertIsNone(virtio.parse_version("nothing"))

    def test_pinned_download_ok(self):
        virtio.PINNED['0.1.302'] = hashlib.sha256(self.DATA).hexdigest()
        path, digest, pinned = virtio.download(self.dir, opener=self.opener())
        self.assertTrue(pinned)
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), self.DATA)
        self.assertEqual(os.listdir(self.dir), ['virtio-win-0.1.302.iso'])

    def test_wrong_checksum_is_deleted(self):
        virtio.PINNED['0.1.302'] = '0' * 64
        with self.assertRaises(virtio.VirtioError):
            virtio.download(self.dir, opener=self.opener())
        self.assertEqual(os.listdir(self.dir), [])

    def test_short_download_is_deleted(self):
        virtio.PINNED.clear()
        with self.assertRaises(virtio.VirtioError):
            virtio.download(self.dir, opener=self.opener(size=len(self.DATA) + 5))
        self.assertEqual(os.listdir(self.dir), [])

    def test_unpinned_version_is_reported_as_such(self):
        virtio.PINNED.clear()
        path, digest, pinned = virtio.download(self.dir, opener=self.opener())
        self.assertFalse(pinned)
        self.assertEqual(digest, hashlib.sha256(self.DATA).hexdigest())

    def test_http_is_refused(self):
        with self.assertRaises(virtio.VirtioError):
            virtio.default_opener('http://fedorapeople.org/x.iso')

    def test_redirect_to_http_is_refused(self):
        handler = virtio._HttpsOnly()
        with self.assertRaises(virtio.VirtioError):
            handler.redirect_request(None, None, 302, 'Found', {}, 'http://evil/x')

    def test_the_pin_matches_the_real_iso_when_present(self):
        real = '/tmp/vw/virtio-win-0.1.302.iso'
        if not os.path.exists(real):
            self.skipTest('no real driver ISO here')
        self.assertEqual(virtio.sha256_file(real), virtio.PINNED['0.1.302'])


@unittest.skipUnless(HAVE_LIBVIRT, 'python3-libvirt missing')
class ManagerTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, self.tmp)
        os.environ['XDG_STATE_HOME'] = self.tmp
        os.environ['XDG_CACHE_HOME'] = self.tmp
        self.m = core.Manager('test:///default')
        self.m.connect()
        self.addCleanup(self.m.close)
        self.names = []

    def tearDown(self):
        for name in self.names:
            try:
                dom = self.m.conn.lookupByName(name)
                if dom.isActive():
                    dom.destroy()
                dom.undefine()
            except Exception:
                pass

    def make(self, name='vm1', preset='linux', **kw):
        s = xmlgen.VmSpec(name=name, preset=preset, cpus=2, memory_mb=2048, kvm=False, **kw)
        self.names.append(name)
        return self.m.create_vm(s, 10)

    def test_create_start_pause_resume_stop_delete(self):
        self.make('cycle')
        self.assertEqual(self.state('cycle'), 'off')
        self.m.start('cycle')
        self.assertEqual(self.state('cycle'), 'running')
        self.m.pause('cycle')
        self.assertEqual(self.state('cycle'), 'paused')
        self.m.resume('cycle')
        self.m.force_off('cycle')
        self.assertEqual(self.state('cycle'), 'off')
        self.m.delete_vm('cycle', True)
        self.assertFalse(self.m.vm_exists('cycle'))

    def state(self, name):
        return next(v.state for v in self.m.list_vms() if v.name == name)

    def test_info_reads_back_what_was_made(self):
        info = self.make('info1', 'win11')
        self.assertEqual((info.name, info.cpus, info.memory_mb, info.preset), ('info1', 2, 2048, 'win11'))
        self.assertFalse(info.drivers)

    def test_a_second_machine_with_the_same_name_is_refused(self):
        self.make('dup')
        with self.assertRaises(core.BoxesError):
            self.make('dup')

    def test_settings_need_the_machine_off(self):
        self.make('set1')
        self.m.set_cpus('set1', 3)
        self.m.set_memory('set1', 1536)
        self.m.set_boot_first('set1', 'cdrom')
        self.assertEqual(self.m.boot_first('set1'), 'cdrom')
        self.m.set_network('set1', False)
        self.assertFalse(self.m.network_on('set1'))
        info = next(v for v in self.m.list_vms() if v.name == 'set1')
        self.assertEqual((info.cpus, info.memory_mb), (3, 1536))
        self.m.start('set1')
        with self.assertRaises(core.BoxesError):
            self.m.set_cpus('set1', 1)

    def test_memory_above_half_the_host_is_refused(self):
        self.make('mem1')
        with self.assertRaises(core.BoxesError):
            self.m.set_memory('mem1', 10 ** 9)

    def test_cdrom_and_driver_disc(self):
        self.make('cd1')
        self.m.import_iso = lambda p, progress=None: p     # the import has its own tests
        self.m.set_cdrom('cd1', '/tmp/x.iso')
        self.assertEqual(self.m.cdrom('cd1'), '/tmp/x.iso')
        self.m.set_cdrom('cd1', None)
        self.assertEqual(self.m.cdrom('cd1'), '')

    def test_snapshots(self):
        self.make('snap1')
        name = self.m.take_snapshot('snap1', 'before')
        self.assertTrue(name.startswith('before ('))
        self.assertEqual([s.name for s in self.m.snapshots('snap1')], [name])
        self.m.revert_snapshot('snap1', name)
        self.m.delete_snapshot('snap1', name)
        self.assertEqual(self.m.snapshots('snap1'), [])

    def test_usb_needs_a_running_machine(self):
        self.make('usb1')
        good = usbdev.UsbDevice(1, 4, '046d', 'c077', 'Mouse')
        with self.assertRaises(core.BoxesError):
            self.m.usb_give('usb1', good)

    def test_unknown_machine(self):
        with self.assertRaises(core.BoxesError):
            self.m.start('nothing-here')

    def test_event_callback_fires(self):
        seen = []
        self.m.watch(lambda name, what: seen.append(name))
        self.make('ev1')
        self.m.start('ev1')
        import time
        for _ in range(50):
            if 'ev1' in seen:
                break
            time.sleep(0.1)
        self.assertIn('ev1', seen)

    def test_import_iso_keeps_a_readable_file_where_it_is(self):
        iso = os.path.join(self.tmp, 'a.iso')
        with open(iso, 'wb') as f:
            f.write(b'x')
        os.chmod(self.tmp, 0o755)
        os.chmod(iso, 0o644)
        if core._can_traverse(iso):
            self.assertEqual(self.m.import_iso(iso), iso)

    def test_import_iso_uploads_a_private_file_into_the_pool(self):
        iso = os.path.join(self.tmp, 'private.iso')
        data = os.urandom(200000)
        with open(iso, 'wb') as f:
            f.write(data)
        os.chmod(iso, 0o600)
        pool_dir = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, pool_dir)
        calls = []
        self.m.ensure_pool = lambda: FakePool(pool_dir)
        self.m.conn = FakeConn(self.m.conn)
        got = self.m.import_iso(iso, lambda d, total: calls.append((d, total)))
        with open(got, 'rb') as f:
            self.assertEqual(f.read(), data)
        self.assertEqual(calls[-1], (len(data), len(data)))

    def test_import_iso_missing_file(self):
        with self.assertRaises(core.BoxesError):
            self.m.import_iso('/nonexistent.iso')


class FakeVolume:
    def __init__(self, path):
        self._path = path

    def path(self):
        return self._path

    def upload(self, stream, offset, length, flags):
        stream.target = self._path

    def delete(self, flags):
        os.unlink(self._path)


class FakePool:
    def __init__(self, folder):
        self.folder = folder

    def listVolumes(self):
        return os.listdir(self.folder)

    def createXML(self, xml, flags):
        name = ET.fromstring(xml).find('name').text
        path = os.path.join(self.folder, name)
        open(path, 'wb').close()
        return FakeVolume(path)


class FakeStream:
    target = ''

    def sendAll(self, handler, opaque):
        with open(self.target, 'wb') as out:
            while True:
                block = handler(self, 65536, opaque)
                if not block:
                    break
                out.write(block)

    def finish(self):
        pass

    def abort(self):
        pass


class FakeConn:
    def __init__(self, real):
        self.real = real

    def newStream(self, flags):
        return FakeStream()

    def __getattr__(self, name):
        return getattr(self.real, name)


class TextTests(unittest.TestCase):

    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(sorted(EN), sorted(FR))

    def test_french_placeholders_match(self):
        import string
        fields = lambda s: sorted(f for _, f, _, _ in string.Formatter().parse(s) if f)  # noqa: E731
        for key in EN:
            self.assertEqual(fields(EN[key]), fields(FR[key]), key)

    def test_t_fills_in(self):
        os.environ['SPARK_LANG'] = 'fr'
        self.addCleanup(os.environ.pop, 'SPARK_LANG', None)
        self.assertIn('machine', t('new.name_taken', name='x'))


if __name__ == '__main__':
    unittest.main()
