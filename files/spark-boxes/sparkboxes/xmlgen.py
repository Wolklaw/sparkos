"""The libvirt domain XML for a new machine, built from a preset. This is the part most likely to
be wrong, so it lives alone, has no libvirt import, and has golden tests.

q35 machine, host-passthrough CPU, UEFI picked by libvirt's own firmware descriptors (so no OVMF
path is written here), Secure Boot with Microsoft's keys enrolled and a TPM 2.0 for Windows 11,
SATA disk and e1000e network for Windows (they need no driver) or virtio for the rest, SPICE
with no network port (the app opens it through libvirt), a USB tablet, the qemu guest agent
and SPICE agent channels."""

import uuid as uuidlib
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape, quoteattr

PRESETS = ('win11', 'win10', 'linux', 'other')
WINDOWS = ('win11', 'win10')
NS = 'https://wolklaw.dev/sparkos/boxes'

GIB = 1024 ** 3
MEMORY_MB = {'win11': 8192, 'win10': 8192, 'linux': 4096, 'other': 4096}
DISK_GB = {'win11': 80, 'win10': 80, 'linux': 40, 'other': 40}
MIN_MEMORY_MB = 1024


def is_windows(preset: str) -> bool:
    return preset in WINDOWS


def default_cpus(host_threads: int) -> int:
    """Half the host's threads, at least 1 and at most 8."""
    return max(1, min(8, host_threads // 2))


def default_memory_mb(preset: str, host_memory_mb: int) -> int:
    """8 GB for Windows and 4 GB for the rest, never more than half of the host's memory."""
    wanted = MEMORY_MB.get(preset, 4096)
    cap = max(MIN_MEMORY_MB, (host_memory_mb // 2) // 256 * 256)
    return min(wanted, cap)


def default_disk_gb(preset: str) -> int:
    return DISK_GB.get(preset, 40)


@dataclass
class VmSpec:
    name: str
    preset: str = 'linux'
    cpus: int = 2
    memory_mb: int = 4096
    disk_path: str = ''
    iso_path: str = ''
    drivers: bool = False            # virtio disk, network and video (Windows needs the drivers)
    network: bool = True
    uuid: str = ''
    kvm: bool = True                 # False: plain QEMU emulation (tests, a PC without KVM)
    network_source: str = 'default'  # libvirt network; '' gives user-mode networking (qemu:///session)

    @property
    def virtio(self) -> bool:
        return self.drivers or not is_windows(self.preset)


def _attr(value) -> str:
    return quoteattr(str(value))


def build_xml(spec: VmSpec) -> str:
    """The <domain> document for `spec`."""
    if spec.preset not in PRESETS:
        raise ValueError(f"unknown preset {spec.preset!r}")
    if not spec.name or '/' in spec.name or spec.name.strip() != spec.name:
        raise ValueError("the name is empty, has a slash or has spaces at its ends")
    windows = is_windows(spec.preset)
    virtio = spec.virtio
    vm_uuid = spec.uuid or str(uuidlib.uuid4())
    disk_bus, disk_dev = ('virtio', 'vda') if virtio else ('sata', 'sda')
    nic = 'virtio' if virtio else 'e1000e'
    video = 'virtio' if virtio else 'vga'
    secure = spec.preset == 'win11'

    firmware = ''
    if secure:
        firmware = ("    <firmware>\n"
                    "      <feature enabled='yes' name='enrolled-keys'/>\n"
                    "      <feature enabled='yes' name='secure-boot'/>\n"
                    "    </firmware>\n")
    features = "    <acpi/>\n    <apic/>\n"
    if windows:
        features += ("    <hyperv mode='custom'>\n      <relaxed state='on'/>\n"
                     "      <vapic state='on'/>\n      <spinlocks state='on' retries='8191'/>\n"
                     "    </hyperv>\n")
    if secure:
        features += "    <smm state='on'/>\n"
    clock = "  <clock offset='localtime'/>\n" if windows else "  <clock offset='utc'/>\n"

    disk = (f"    <disk type='file' device='disk'>\n"
            f"      <driver name='qemu' type='qcow2' discard='unmap'/>\n"
            f"      <source file={_attr(spec.disk_path)}/>\n"
            f"      <target dev='{disk_dev}' bus='{disk_bus}'/>\n"
            f"      <boot order='2'/>\n"
            f"    </disk>\n") if spec.disk_path else ''
    cdrom_source = f"      <source file={_attr(spec.iso_path)}/>\n" if spec.iso_path else ''
    cdrom = ("    <disk type='file' device='cdrom'>\n"
             "      <driver name='qemu' type='raw'/>\n" + cdrom_source +
             "      <target dev='sdb' bus='sata'/>\n"
             "      <readonly/>\n"
             "      <boot order='1'/>\n"
             "    </disk>\n")
    link = '' if spec.network else "      <link state='down'/>\n"
    if spec.network_source:
        nic_head = f"    <interface type='network'>\n      <source network={_attr(spec.network_source)}/>\n"
    else:
        nic_head = "    <interface type='user'>\n"
    cpu = ("  <cpu mode='host-passthrough' check='none'/>\n" if spec.kvm else
           "  <cpu mode='custom' match='exact'>\n    <model fallback='allow'>qemu64</model>\n  </cpu>\n")
    tpm = ("    <tpm model='tpm-crb'>\n      <backend type='emulator' version='2.0'/>\n"
           "    </tpm>\n") if secure else ''

    return (
        f"<domain type={_attr('kvm' if spec.kvm else 'qemu')}>\n"
        f"  <name>{escape(spec.name)}</name>\n"
        f"  <uuid>{vm_uuid}</uuid>\n"
        f"  <metadata>\n"
        f"    <sparkboxes:vm xmlns:sparkboxes={_attr(NS)} preset={_attr(spec.preset)} "
        f"drivers={_attr('yes' if virtio and windows else 'no')}/>\n"
        f"  </metadata>\n"
        f"  <memory unit='MiB'>{int(spec.memory_mb)}</memory>\n"
        f"  <currentMemory unit='MiB'>{int(spec.memory_mb)}</currentMemory>\n"
        f"  <vcpu placement='static'>{int(spec.cpus)}</vcpu>\n"
        f"  <os firmware='efi'>\n"
        f"    <type arch='x86_64' machine='q35'>hvm</type>\n"
        f"{firmware}"
        f"  </os>\n"
        f"  <features>\n{features}  </features>\n"
        f"{cpu}"
        f"{clock}"
        f"  <on_poweroff>destroy</on_poweroff>\n"
        f"  <on_reboot>restart</on_reboot>\n"
        f"  <on_crash>destroy</on_crash>\n"
        f"  <devices>\n"
        f"{disk}{cdrom}"
        f"    <controller type='usb' model='qemu-xhci'/>\n"
        f"{nic_head}"
        f"      <model type='{nic}'/>\n{link}"
        f"    </interface>\n"
        f"    <graphics type='spice'>\n"
        f"      <listen type='none'/>\n"
        f"      <image compression='off'/>\n"
        f"      <gl enable='no'/>\n"
        f"    </graphics>\n"
        f"    <video>\n"
        f"      <model type='{video}'/>\n"
        f"    </video>\n"
        f"    <sound model='ich9'>\n      <audio id='1'/>\n    </sound>\n"
        f"    <audio id='1' type='spice'/>\n"
        f"    <input type='tablet' bus='usb'/>\n"
        f"    <channel type='unix'>\n"
        f"      <target type='virtio' name='org.qemu.guest_agent.0'/>\n"
        f"    </channel>\n"
        f"    <channel type='spicevmc'>\n"
        f"      <target type='virtio' name='com.redhat.spice.0'/>\n"
        f"    </channel>\n"
        f"{tpm}"
        f"    <memballoon model='virtio'/>\n"
        f"    <rng model='virtio'>\n      <backend model='random'>/dev/urandom</backend>\n    </rng>\n"
        f"  </devices>\n"
        f"</domain>\n")


def cdrom_xml(target: str, iso_path: Optional[str]) -> str:
    """A CD drive's XML for updateDeviceFlags: with a disc, or empty when iso_path is falsy."""
    source = f"<source file={_attr(iso_path)}/>" if iso_path else ''
    return (f"<disk type='file' device='cdrom'><driver name='qemu' type='raw'/>{source}"
            f"<target dev={_attr(target)} bus='sata'/><readonly/></disk>")


def disk_xml(path: str, target: str, bus: str) -> str:
    return (f"<disk type='file' device='disk'><driver name='qemu' type='qcow2' discard='unmap'/>"
            f"<source file={_attr(path)}/><target dev={_attr(target)} bus={_attr(bus)}/></disk>")


def volume_xml(name: str, gigabytes: int) -> str:
    """A thin qcow2 volume for libvirt's storage pool: no space is taken until it is used."""
    return (f"<volume type='file'><name>{escape(name)}</name>"
            f"<capacity unit='bytes'>{int(gigabytes) * GIB}</capacity><allocation>0</allocation>"
            f"<target><format type='qcow2'/></target></volume>")
