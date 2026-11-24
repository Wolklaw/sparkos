"""Reading firewalld: the parsers on the PC's real output, and the snapshot through a fake runner.
Also: reading never runs anything that changes the firewall."""

import unittest

import support
from sparkfirewall import catalog, fw


class Parsers(unittest.TestCase):
    def test_zone(self):
        zone = fw.parse_zone(support.WORKSTATION)
        self.assertEqual(zone.name, "FedoraWorkstation")
        self.assertTrue(zone.default and zone.active)
        self.assertEqual(zone.services, ["dhcpv6-client", "samba-client", "ssh"])
        self.assertEqual(zone.ports, ["1025-65535/udp", "1025-65535/tcp"])
        self.assertEqual(zone.interfaces, ["eno1"])

    def test_zone_without_flags_or_ports(self):
        zone = fw.parse_zone(support.PUBLIC)
        self.assertEqual((zone.name, zone.default, zone.active), ("public", False, False))
        self.assertEqual(zone.ports, [])
        self.assertEqual(zone.services, ["dhcpv6-client", "mdns", "ssh"])

    def test_empty(self):
        self.assertEqual(fw.parse_zone("").name, "")

    def test_service_ports(self):
        self.assertEqual(fw.parse_service(support.SERVICE_INFO["steam-streaming"]),
                         ["27036/tcp", "27037/tcp", "27031-27036/udp", "10400/udp", "10401/udp"])
        self.assertEqual(fw.parse_service("x\n  ports: \n"), [])

    def test_active_zones(self):
        text = "FedoraWorkstation (default)\n  interfaces: eno1 wlan0\nhome\n  sources: 10.0.0.0/8\n"
        self.assertEqual(fw.parse_active_zones(text),
                         {"FedoraWorkstation": ["eno1", "wlan0"], "home": []})

    def test_connections(self):
        rows = fw.parse_connections(support.NMCLI + "Cafe\\: Wi-Fi:abc:802-11-wireless:wlan0\n")
        self.assertEqual([r[3] for r in rows], ["eno1", "tailscale0", "wlan0"])
        self.assertEqual(rows[2][0], "Cafe: Wi-Fi")

    def test_ports(self):
        self.assertEqual(fw.parse_port("5000-5010/udp"), (5000, 5010, "udp"))
        for bad in ("0/tcp", "70000/udp", "x", "10-5/tcp", "80/foo"):
            self.assertIsNone(fw.parse_port(bad))

    def test_covered(self):
        wide = ["1025-65535/udp", "1025-65535/tcp"]
        self.assertTrue(fw.covered(["27036/tcp", "27031-27036/udp"], wide))
        self.assertFalse(fw.covered(["22/tcp"], wide))                 # below 1025
        self.assertFalse(fw.covered(["27036/tcp"], ["1025-65535/udp"]))  # wrong protocol
        self.assertFalse(fw.covered(["27036/tcp", "80/tcp"], wide))
        self.assertFalse(fw.covered([], wide))


class Snapshot(unittest.TestCase):
    def test_running(self):
        runner = support.FakeRun()
        snap = fw.Firewall(runner).snapshot(has_cmd=True)
        self.assertTrue(snap.running)
        self.assertTrue(snap.at_boot)
        self.assertEqual(snap.default_zone, "FedoraWorkstation")
        self.assertIn("FedoraWorkstation", snap.zone)
        self.assertEqual(snap.zone["FedoraWorkstation"].ports[0], "1025-65535/udp")
        self.assertEqual([(n.device, n.zone) for n in snap.networks],
                         [("eno1", "FedoraWorkstation"), ("tailscale0", "")])
        self.assertEqual(snap.service_ports["spark-link"], ["47100/tcp"])
        self.assertEqual(snap.service_ports["nova"], ["8765/tcp", "8766/udp", "8780/tcp"])
        self.assertEqual([r.id for r in catalog.available(snap.services)][:4],
                         ["steam_remote_play", "steam_transfer", "spark_link", "nova"])

    def test_stopped(self):
        snap = fw.Firewall(support.FakeRun(running=False)).snapshot(has_cmd=True)
        self.assertFalse(snap.running)
        self.assertEqual(snap.zone, {})
        self.assertEqual(snap.zones, [])

    def test_not_installed(self):
        runner = support.FakeRun()
        snap = fw.Firewall(runner).snapshot(has_cmd=False)
        self.assertFalse(snap.available)
        self.assertEqual(runner.calls, [])

    def test_a_disabled_service_still_reports(self):
        class Disabled(support.FakeRun):
            def __call__(self, argv):
                if argv[:2] == ["systemctl", "is-enabled"]:
                    self.calls.append(argv)
                    return 1, "disabled\n", ""
                return super().__call__(argv)
        self.assertFalse(fw.Firewall(Disabled()).snapshot(has_cmd=True).at_boot)

    def test_reading_never_changes_anything(self):
        runner = support.FakeRun()
        fw.Firewall(runner).snapshot(want="public", has_cmd=True)
        for argv in runner.calls:
            line = " ".join(argv).replace("is-enabled", "is-read")
            for word in ("--add", "--remove", "--set", "--change", "--reload", "--permanent",
                         "--panic", "modify", "enable", "disable", "start", "stop"):
                self.assertNotIn(word, line)
            self.assertIn(argv[0], ("firewall-cmd", "nmcli", "systemctl"))
            if argv[0] == "systemctl":
                self.assertEqual(argv[1], "is-enabled")
            if argv[0] == "nmcli":
                self.assertIn("show", argv)


if __name__ == '__main__':
    unittest.main()
