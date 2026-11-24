"""Unit tests for files/system/usr/libexec/sparkos-windows-drives: partitions from lsblk, the conf, naming, the owner, and drive
letters read from a real registry file layout. No root or disks needed (check_mounts.sh does the real mounting test).

    python3 -m unittest discover -s .github/scripts/windows-drives -v
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "..", "..", "files", "system", "usr", "libexec", "sparkos-windows-drives")
loader = importlib.machinery.SourceFileLoader("windows_drives", SCRIPT)
spec = importlib.util.spec_from_loader("windows_drives", loader)
wd = importlib.util.module_from_spec(spec)
loader.exec_module(wd)
sys.path.insert(0, HERE)
import make_hive  # noqa: E402

C = "0b8f4c55-6a4f-4f0e-9a43-8a3c1f1d2e01"
E = "7c1e2d3f-1111-4a4a-b5b5-c6c6d7d7e8e8"

LSBLK = json.dumps({"blockdevices": [
    {"name": "nvme0n1", "path": "/dev/nvme0n1", "fstype": None, "children": [
        {"name": "nvme0n1p1", "path": "/dev/nvme0n1p1", "fstype": "vfat", "label": "SYSTEM", "partuuid": "aa"},
        {"name": "nvme0n1p3", "path": "/dev/nvme0n1p3", "fstype": "ntfs", "label": None, "mountpoint": None, "partuuid": C.upper(),
         "parttype": "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"},
        {"name": "nvme0n1p4", "path": "/dev/nvme0n1p4", "fstype": "ntfs", "label": "Recovery",
         "partuuid": "bb", "parttype": "de94bba4-06d1-4d40-a16a-bfd50179d6ac"}]},
    {"name": "nvme1n1", "path": "/dev/nvme1n1", "children": [
        {"name": "nvme1n1p1", "path": "/dev/nvme1n1p1", "fstype": "ntfs", "label": "Games", "partuuid": E},
        {"name": "nvme1n1p4", "path": "/dev/nvme1n1p4", "fstype": "btrfs", "label": "sparkos"}]},
    {"name": "sda", "path": "/dev/sda", "children": [
        {"name": "sda2", "path": "/dev/sda2", "fstype": "BitLocker", "label": "", "partuuid": "cc"}]}]})


class WindowsDrivesTests(unittest.TestCase):
    def test_partitions_skip_recovery_and_other_filesystems(self):
        parts = wd.partitions(LSBLK)
        self.assertEqual([p["device"] for p in parts], ["/dev/nvme0n1p3", "/dev/nvme1n1p1", "/dev/sda2"])
        self.assertEqual(parts[0]["partuuid"], C)
        self.assertEqual(parts[2]["fstype"], "bitlocker")

    def test_a_label_can_not_climb_out_of_the_mount_folder(self):
        for label in ("..", ".", "...", "../etc", "/", "-", " . ", ".hidden"):
            taken = set()
            _letter, name = wd.name_for({"partuuid": "12345678-aaaa", "label": label, "name": "x"}, {}, taken)
            self.assertRegex(name, r"^[a-z0-9][a-z0-9._-]*$", label)
            self.assertNotIn(name, (".", ".."))
            self.assertEqual(os.path.dirname(os.path.join("/var/mnt", name)), "/var/mnt", label)
        self.assertEqual(wd.name_for({"partuuid": "12345678-aaaa", "label": "..", "name": "x"}, {}, set()), ("", "12345678"))

    def test_every_mount_is_nosuid_nodev(self):
        calls = []
        self.addCleanup(setattr, wd, "run", wd.run)
        wd.run = lambda cmd: (calls.append(cmd), (1, "no"))[1]
        with tempfile.TemporaryDirectory() as base:
            wd.mount("/dev/x", os.path.join(base, "x"), "rw", 1000, 1000)
        self.assertEqual(len(calls), 3)
        for cmd in calls:
            opts = cmd[cmd.index("-o") + 1].split(",")
            self.assertIn("nosuid", opts)
            self.assertIn("nodev", opts)

    def test_conf(self):
        modes, user = wd.read_conf("# comment\nD ro\ne: RW   # trailing\nX bogus\n* off\nuser=ann\n")
        self.assertEqual(modes, {"D": "ro", "E": "rw", "*": "off"})
        self.assertEqual(user, "ann")

    def test_names_are_letters_then_labels_then_ids(self):
        taken = set()
        parts = wd.partitions(LSBLK)
        self.assertEqual(wd.name_for(parts[0], {C: "C"}, taken), ("C", "c"))
        self.assertEqual(wd.name_for(parts[1], {}, taken), ("", "games"))
        self.assertEqual(wd.name_for({"partuuid": "12345678-aaaa", "label": "", "name": "x"}, {}, taken), ("", "12345678"))
        self.assertEqual(wd.name_for({"partuuid": "", "label": "Games", "name": "y"}, {}, taken), ("", "games-2"))

    def test_owner_is_the_first_regular_account(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("root:x:0:0::/root:/bin/bash\nnobody:x:65534:65534::/:/sbin/nologin\nbob:x:1001:1001::/home/bob:/bin/bash\n"
                    "ann:x:1000:1000::/home/ann:/bin/bash\n")
        try:
            self.assertEqual(wd.owner(None, f.name), (1000, 1000))
        finally:
            os.unlink(f.name)

    def test_drive_letters_from_the_system_registry_file(self):
        with tempfile.TemporaryDirectory() as root:
            hive = os.path.join(root, "WINDOWS", "system32", "Config", "SYSTEM")   # NTFS keeps Windows' own case
            make_hive.make_hive(hive, "MountedDevices", {
                **make_hive.mounted_devices({"C": C, "E": E}),
                "\\DosDevices\\F:": (3, b"\x12\x34\x56\x78" + b"\0" * 8),           # an MBR disk: no GUID, left out
                "\\??\\Volume{1234}": (3, b"DMIO:ID:" + b"\1" * 16)})
            self.assertEqual(wd.system_hive(root), hive)
            self.assertEqual(wd.drive_letters(hive), {"C": C, "E": E})

    def test_damaged_registry_file_gives_no_letters(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"regf" + b"\xff" * 5000)
        try:
            self.assertEqual(wd.drive_letters(f.name), {})
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
